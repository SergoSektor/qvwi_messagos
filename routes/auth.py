from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import get_db, allowed_file
from config import Config
import os

bp = Blueprint('auth', __name__)

@bp.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' in session:
        return redirect(url_for('feed.feed'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'login':
            username = request.form['username']
            password = request.form['password']
            
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            conn.close()
            
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                return redirect(url_for('feed.feed'))
            else:
                flash('Неверное имя пользователя или пароль')
        
        elif action == 'register':
            username = request.form['username']
            password = generate_password_hash(request.form['password'])
            email = request.form.get('email', '')
            
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", 
                         (username, password, email))
                conn.commit()
                flash('Регистрация успешна! Теперь войдите.')
            except sqlite3.IntegrityError:
                flash('Имя пользователя уже занято')
            finally:
                conn.close()
    
    return render_template('index.html')

@bp.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('auth.index'))