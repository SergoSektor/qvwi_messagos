from flask import Blueprint, render_template, session, redirect, url_for
from models import get_db

bp = Blueprint('gallery', __name__)

@bp.route('/gallery')
def gallery():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    # Получаем текущего пользователя
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    
    # Получаем все аватарки пользователей
    c.execute("SELECT avatar FROM users WHERE avatar IS NOT NULL AND avatar != 'default_avatar.png'")
    avatars = [row['avatar'] for row in c.fetchall()]
    
    conn.close()
    
    return render_template('gallery.html', user=user, avatars=avatars)