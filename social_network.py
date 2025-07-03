# social_network.py
import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Создаем базу данных и таблицы при первом запуске
def init_db():
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                bio TEXT,
                avatar TEXT)''')
    
    # Таблица друзей
    c.execute('''CREATE TABLE IF NOT EXISTS friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                status TEXT CHECK(status IN ('pending', 'accepted')),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(friend_id) REFERENCES users(id))''')
    
    # Таблица сообщений
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(receiver_id) REFERENCES users(id))''')
    
    # Таблица постов
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Главная страница (вход/регистрация)
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' in session:
        return redirect(url_for('feed'))
    
    if request.method == 'POST':
        action = request.form.get('action'))
        
        if action == 'login':
            username = request.form['username']
            password = request.form['password']
            
            conn = sqlite3.connect('social_network.db')
            c = conn.cursor()
            c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            conn.close()
            
            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]
                return redirect(url_for('feed'))
            else:
                flash('Неверное имя пользователя или пароль')
        
        elif action == 'register':
            username = request.form['username']
            password = generate_password_hash(request.form['password'])
            email = request.form.get('email', '')
            
            try:
                conn = sqlite3.connect('social_network.db')
                c = conn.cursor()
                c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", 
                         (username, password, email))
                conn.commit()
                flash('Регистрация успешна! Теперь войдите.')
            except sqlite3.IntegrityError:
                flash('Имя пользователя уже занято')
            finally:
                conn.close()
    
    return render_template('index.html'))

# Лента новостей
@app.route('/feed')
def feed():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    c.execute("SELECT posts.*, users.username FROM posts JOIN users ON posts.user_id = users.id ORDER BY timestamp DESC")
    posts = c.fetchall()
    conn.close()
    
    return render_template('feed.html', posts=posts))

# Профиль пользователя
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        bio = request.form['bio']
        avatar = request.files.get('avatar'))
        
        conn = sqlite3.connect('social_network.db')
        c = conn.cursor()
        
        if avatar and allowed_file(avatar.filename):
            filename = secure_filename(f"{user_id}_{avatar.filename}")
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            c.execute("UPDATE users SET avatar = ? WHERE id = ?", (filename, user_id))
        
        c.execute("UPDATE users SET bio = ? WHERE id = ?", (bio, user_id))
        conn.commit()
        conn.close()
        flash('Профиль обновлен!')
    
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    return render_template('profile.html', user=user))

# Галерея фотографий
@app.route('/gallery')
def gallery():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    c.execute("SELECT avatar FROM users WHERE avatar IS NOT NULL")
    avatars = [row[0] for row in c.fetchall()]
    conn.close()
    
    return render_template('gallery.html', avatars=avatars))

# Система сообщений
@app.route('/messages')
@app.route('/messages/<int:friend_id>', methods=['GET', 'POST'])
def messages(friend_id=None):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Получаем список друзей для боковой панели
    c.execute('''SELECT users.id, users.username 
                FROM friends 
                JOIN users ON friends.friend_id = users.id 
                WHERE friends.user_id = ? AND friends.status = 'accepted'
                UNION
                SELECT users.id, users.username 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'accepted' 
                ORDER BY username''', (user_id, user_id))
    friends = c.fetchall()
    
    # Обработка отправки сообщения
    if request.method == 'POST' and friend_id:
        content = request.form['content']
        c.execute("INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)", 
                 (user_id, friend_id, content))
        conn.commit()
    
    # Получаем историю сообщений
    messages = []
    if friend_id:
        c.execute('''SELECT * FROM messages 
                    WHERE (sender_id = ? AND receiver_id = ?) 
                    OR (sender_id = ? AND receiver_id = ?)
                    ORDER BY timestamp''', 
                 (user_id, friend_id, friend_id, user_id))
        messages = c.fetchall()
    
    conn.close()
    return render_template('messages.html', friends=friends, messages=messages, friend_id=friend_id))

# Система друзей
@app.route('/friends')
def friends():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Запросы в друзья
    c.execute('''SELECT users.id, users.username 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'pending' ''', (user_id,))
    requests = c.fetchall()
    
    # Список друзей
    c.execute('''SELECT users.id, users.username 
                FROM friends 
                JOIN users ON friends.friend_id = users.id 
                WHERE friends.user_id = ? AND friends.status = 'accepted'
                UNION
                SELECT users.id, users.username 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'accepted' 
                ORDER BY username''', (user_id, user_id))
    friends = c.fetchall()
    
    conn.close()
    return render_template('friends.html', requests=requests, friends=friends))

# Обработка запросов в друзья
@app.route('/add_friend/<int:friend_id>')
def add_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    try:
        c.execute("INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, 'pending')", 
                 (user_id, friend_id))
        conn.commit()
        flash('Запрос отправлен!')
    except sqlite3.IntegrityError:
        flash('Запрос уже отправлен')
    
    conn.close()
    return redirect(url_for('friends'))

@app.route('/accept_friend/<int:friend_id>')
def accept_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    c.execute("UPDATE friends SET status = 'accepted' WHERE user_id = ? AND friend_id = ?", 
             (friend_id, user_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('friends'))

# Создание поста
@app.route('/create_post', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    content = request.form['content']
    user_id = session['user_id']
    
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    c.execute("INSERT INTO posts (user_id, content) VALUES (?, ?)", (user_id, content))
    conn.commit()
    conn.close()
    
    return redirect(url_for('feed'))

# Выход из системы
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)