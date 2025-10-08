from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import get_db, allowed_file
from config import Config
import os
from flask import abort
from datetime import datetime, timedelta

bp = Blueprint('auth', __name__)

@bp.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' in session:
        # Проверим блокировку
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT is_blocked, block_reason FROM users WHERE id = ?", (session['user_id'],))
        row = c.fetchone()
        conn.close()
        if row and row['is_blocked']:
            return render_template('blocked.html', reason=row['block_reason'] or 'Профиль заблокирован администратором')
        return redirect(url_for('feed.feed'))
    # Загружаем системные настройки (для отображения режима регистрации на форме)
    conn_s = get_db(); c_s = conn_s.cursor()
    try:
        c_s.execute("SELECT key, value FROM settings")
        settings = {row['key']: row['value'] for row in c_s.fetchall()}
    finally:
        conn_s.close()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'login':
            username = request.form['username']
            password = request.form['password']
            
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT id, password, is_blocked FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            conn.close()
            
            if user and check_password_hash(user['password'], password):
                if user['is_blocked']:
                    return render_template('blocked.html', reason='Профиль заблокирован администратором')
                session['user_id'] = user['id']
                return redirect(url_for('feed.feed'))
            else:
                flash('Неверное имя пользователя или пароль')
        
        elif action == 'register':
            username = request.form['username']
            password = generate_password_hash(request.form['password'])
            email = request.form.get('email', '')
            # Проверяем режим регистрации
            conn = get_db(); c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='registration_mode'")
            mode_row = c.fetchone(); reg_mode = (mode_row['value'] if mode_row else 'open')
            invite_code = request.form.get('invite_code', '').strip()
            if reg_mode == 'closed':
                flash('Регистрация закрыта администратором')
                conn.close()
                return render_template('index.html', settings=settings)
            if reg_mode == 'invite':
                c.execute("""
                    SELECT uses_left, expires_at FROM invites WHERE code=?
                """, (invite_code,))
                inv = c.fetchone()
                if (not inv) or (inv['uses_left'] <= 0):
                    flash('Неверный или исчерпанный код приглашения')
                    conn.close(); return render_template('index.html', settings=settings)
                # Проверяем срок действия
                if inv['expires_at'] is not None:
                    try:
                        # SQLite хранит как текст; допускаем несколько форматов
                        from datetime import datetime
                        exp = inv['expires_at']
                        # Пытаемся разобрать ISO и стандартный формат
                        try:
                            dt = datetime.fromisoformat(exp)
                        except Exception:
                            try:
                                dt = datetime.strptime(exp, '%Y-%m-%d %H:%M:%S')
                            except Exception:
                                dt = None
                        if dt and dt <= datetime.now():
                            flash('Срок действия кода приглашения истёк')
                            conn.close(); return render_template('index.html', settings=settings)
                    except Exception:
                        pass
            try:
                c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", 
                         (username, password, email))
                conn.commit()
                if reg_mode == 'invite':
                    c.execute("UPDATE invites SET uses_left = uses_left - 1 WHERE code=?", (invite_code,))
                    conn.commit()
                flash('Регистрация успешна! Теперь войдите.')
            except sqlite3.IntegrityError:
                flash('Имя пользователя уже занято')
            finally:
                conn.close()
    
    return render_template('index.html', settings=settings)

@bp.route('/request_invite', methods=['POST'])
def request_invite():
    # При закрытой регистрации пользователь может подать заявку
    email = (request.form.get('email') or '').strip()
    message = (request.form.get('message') or '').strip()
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO invite_requests (email, message) VALUES (?, ?)", (email or None, message or None))
    conn.commit(); conn.close()
    flash('Заявка отправлена. Мы свяжемся с вами, когда будет доступ.','success')
    return redirect(url_for('auth.index'))

@bp.route('/blocked')
def blocked():
    reason = request.args.get('reason', 'Профиль заблокирован администратором')
    return render_template('blocked.html', reason=reason)

@bp.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('auth.index'))