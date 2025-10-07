from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from werkzeug.utils import secure_filename
from models import get_db, allowed_file
from config import Config
import os

bp = Blueprint('profile', __name__)

@bp.route('/profile', methods=['GET', 'POST'], defaults={'user_id': None})
@bp.route('/profile/<int:user_id>', methods=['GET'])
def profile(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    # Определяем чей профиль показывать
    if user_id is None:
        user_id = session['user_id']
        is_own_profile = True
    else:
        is_own_profile = (user_id == session['user_id'])

    conn = get_db()
    c = conn.cursor()

    # Обработка POST-запроса
    if request.method == 'POST' and is_own_profile:
        bio = request.form.get('bio', '')
        avatar = request.files.get('avatar')
        banner = request.files.get('banner')

        update_fields = []
        update_values = []

        if bio != '':
            update_fields.append("bio = ?")
            update_values.append(bio)
        
        if avatar and allowed_file(avatar.filename, Config.ALLOWED_EXTENSIONS):
            filename = secure_filename(f"{user_id}_{avatar.filename}")
            avatar_path = os.path.join(Config.UPLOAD_FOLDER, filename)
            avatar.save(avatar_path)
            update_fields.append("avatar = ?")
            update_values.append(filename)

        if banner and allowed_file(banner.filename, Config.ALLOWED_EXTENSIONS):
            banner_name = secure_filename(f"{user_id}_banner_{banner.filename}")
            banner_path = os.path.join(Config.UPLOAD_FOLDER, banner_name)
            banner.save(banner_path)
            update_fields.append("banner = ?")
            update_values.append(banner_name)

        if update_fields:
            update_query = ", ".join(update_fields)
            update_values.append(user_id)
            c.execute(f"UPDATE users SET {update_query} WHERE id = ?", update_values)
            conn.commit()
            flash('Профиль успешно обновлен!', 'success')

    # Получаем данные пользователя
    c.execute("SELECT id, username, email, bio, avatar, banner, is_online, last_seen, is_blocked, block_reason FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Если пользователь не найден
    if not user:
        flash('Пользователь не найден', 'error')
        conn.close()
        return redirect(url_for('feed.feed'))
    
    # Преобразуем в словарь с понятными ключами
    user_data = {
        'id': user[0],
        'username': user[1],
        'email': user[2],
        'bio': user[3],
        'avatar': user[4],
        'banner': user[5],
        'is_online': bool(user[6]),
        'last_seen': user[7],
        'is_blocked': bool(user[8]),
        'block_reason': user[9]
    }

    # Получаем посты пользователя
    c.execute("SELECT id, content, timestamp FROM posts WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    posts = c.fetchall()
    
    conn.close()

    return render_template('profile.html',
                         user=user_data,
                         posts=posts,
                         is_own_profile=is_own_profile)

@bp.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем принадлежность поста пользователю
    c.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,))
    post = c.fetchone()
    
    if post and post[0] == session['user_id']:
        c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
        flash('Пост успешно удален')
    else:
        flash('Ошибка удаления поста')
    
    conn.close()
    return redirect(url_for('profile.profile'))
    