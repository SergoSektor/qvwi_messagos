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
    c.execute('''SELECT posts.*, users.username, users.avatar 
               FROM posts 
               JOIN users ON posts.user_id = users.id 
               ORDER BY timestamp DESC''')
    posts = c.fetchall()
    conn.close()
    
    return render_template('feed.html', user=user, posts=posts)

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