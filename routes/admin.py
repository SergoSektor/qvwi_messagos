from flask import Blueprint, render_template, session, redirect, url_for, request
from models import get_db
from datetime import datetime
import sqlite3

bp = Blueprint('admin', __name__)

@bp.route('/admin')
def admin():
    # Проверяем, вошел ли пользователь
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Получаем текущего пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Проверяем, является ли пользователь администратором
    if not user or user['role'] != 'admin':
        return redirect(url_for('feed.feed'))
    
    # Получаем статистику
    c.execute("SELECT COUNT(*) FROM users")
    users_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM posts")
    posts_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages")
    messages_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admins_count = c.fetchone()[0]
    
    # Получаем список всех пользователей
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    
    conn.close()
    
    return render_template('admin.html', 
                           user=user, 
                           users_count=users_count,
                           posts_count=posts_count,
                           messages_count=messages_count,
                           admins_count=admins_count,
                           users=users)

@bp.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    current_user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем, является ли текущий пользователь администратором
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    current_user_role = c.fetchone()['role']
    if current_user_role != 'admin':
        return redirect(url_for('feed.feed'))
    
    # Удаляем пользователя
    try:
        # Удаляем связанные записи
        c.execute("DELETE FROM friends WHERE user_id = ? OR friend_id = ?", (user_id, user_id))
        c.execute("DELETE FROM messages WHERE sender_id = ? OR receiver_id = ?", (user_id, user_id))
        c.execute("DELETE FROM posts WHERE user_id = ?", (user_id,))
        
        # Удаляем самого пользователя
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin.admin'))

@bp.route('/make_admin/<int:user_id>', methods=['POST'])
def make_admin(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    current_user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем, является ли текущий пользователь администратором
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    current_user_role = c.fetchone()['role']
    if current_user_role != 'admin':
        return redirect(url_for('feed.feed'))
    
    # Назначаем пользователя администратором
    try:
        c.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin.admin'))