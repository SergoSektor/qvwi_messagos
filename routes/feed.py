from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from models import get_db
from werkzeug.utils import secure_filename
import os
from config import Config

bp = Blueprint('feed', __name__)

@bp.route('/feed')
def feed():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    # Получаем текущего пользователя
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    
    # Получаем посты всех пользователей
    c.execute('''SELECT p.*, u.username, u.avatar,
                        COALESCE(l.cnt,0) AS likes_count,
                        COALESCE(cm.cnt,0) AS comments_count,
                        EXISTS(SELECT 1 FROM likes WHERE post_id=p.id AND user_id=?) AS liked
                 FROM posts p
                 JOIN users u ON p.user_id = u.id
                 LEFT JOIN (SELECT post_id, COUNT(*) cnt FROM likes GROUP BY post_id) l ON l.post_id = p.id
                 LEFT JOIN (SELECT post_id, COUNT(*) cnt FROM comments GROUP BY post_id) cm ON cm.post_id = p.id
                 ORDER BY p.timestamp DESC''', (session['user_id'],))
    posts = c.fetchall()
    # Загружаем комментарии ко всем постам одним запросом
    comments_by_post = {}
    post_ids = [str(p[0]) for p in posts]
    if post_ids:
        q = f"SELECT c.post_id, c.id, c.user_id, c.content, c.timestamp, u.username, u.avatar FROM comments c JOIN users u ON c.user_id=u.id WHERE c.post_id IN ({','.join(['?']*len(post_ids))}) ORDER BY c.timestamp ASC"
        c.execute(q, tuple(post_ids))
        rows = c.fetchall()
        for r in rows:
            pid = r[0]
            comments_by_post.setdefault(pid, []).append({
                'id': r[1],
                'user_id': r[2],
                'content': r[3],
                'timestamp': r[4],
                'username': r[5],
                'avatar': r[6]
            })
    conn.close()
    
    return render_template('feed.html', user=user, posts=posts, comments_by_post=comments_by_post)

@bp.route('/post/like/<int:post_id>', methods=['POST'])
def like_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO likes (post_id, user_id) VALUES (?, ?)", (post_id, session['user_id']))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('feed.feed'))

@bp.route('/post/unlike/<int:post_id>', methods=['POST'])
def unlike_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("DELETE FROM likes WHERE post_id=? AND user_id=?", (post_id, session['user_id']))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('feed.feed'))

@bp.route('/post/comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    content = request.form.get('comment','').strip()
    if not content:
        return redirect(url_for('feed.feed'))
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)", (post_id, session['user_id'], content))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('feed.feed'))

@bp.route('/comment/delete/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id FROM comments WHERE id=?", (comment_id,))
    row = c.fetchone()
    if row and row['user_id'] == session['user_id']:
        c.execute("DELETE FROM comments WHERE id=?", (comment_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('feed.feed'))

@bp.route('/create_post', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    content = request.form['content']
    user_id = session['user_id']
    
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO posts (user_id, content) VALUES (?, ?)", (user_id, content))
    conn.commit()
    conn.close()
    
    flash('Пост успешно опубликован!')
    return redirect(url_for('feed.feed'))

@bp.route('/delete_post/<int:post_id>')
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем, принадлежит ли пост текущему пользователю
    c.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,))
    post = c.fetchone()
    
    if post and post['user_id'] == session['user_id']:
        c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
        flash('Пост удалён!')
    else:
        flash('Ошибка удаления: вы не можете удалить этот пост')
    
    conn.close()
    return redirect(url_for('feed.feed'))