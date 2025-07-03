# social_network.py
import os
import sqlite3
import time
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room, leave_room
from gevent import monkey
monkey.patch_all()

app = Flask(__name__)
app.secret_key = 'super_secret_key_123!'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
socketio = SocketIO(app)
os.environ['GEVENT_SUPPORT'] = 'True'
# Глобальный словарь для отслеживания набора текста
typing_status = {}

# Создаем базу данных и тестовые данные
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
                file_path TEXT,
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
    
    
    
    # Добавляем тестовых пользователей
    users = [
        ('alex', generate_password_hash('pass123'), 'alex@example.com', 'none', 'alex.gif'),
        ('masha', generate_password_hash('pass123'), 'masha@example.com', 'none', 'masha.jpg'),
        ('sasha', generate_password_hash('pass123'), 'sasha@example.com', 'none', 'sasha.png'),
        ('dasha', generate_password_hash('pass123'), 'dasha@example.com', '123', 'dasha.gif'),
    ]
    
    for user in users:
        try:
            c.execute("INSERT INTO users (username, password, email, bio, avatar) VALUES (?, ?, ?, ?, ?)", user)
        except:
            pass
    
    # Добавляем тестовые посты


   


# Создаем папку для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализируем БД
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
        action = request.form.get('action')
        
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
    
    return render_template('index.html')

# Лента новостей
@app.route('/feed')
def feed():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Получаем текущего пользователя
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    
    # Получаем посты
    c.execute('''SELECT posts.*, users.username, users.avatar 
               FROM posts 
               JOIN users ON posts.user_id = users.id 
               ORDER BY timestamp DESC''')
    posts = c.fetchall()
    conn.close()
    
    return render_template('feed.html', user=user, posts=posts)

@app.route('/profile', methods=['GET', 'POST'], defaults={'user_id': None})
@app.route('/profile/<int:user_id>', methods=['GET'])
def profile(user_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Определяем, чей профиль показывать
    if user_id is None:
        user_id = session['user_id']
        is_own_profile = True
    else:
        is_own_profile = (user_id == session['user_id'])
    
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Обработка POST-запроса только для своего профиля
    if request.method == 'POST' and is_own_profile:
        bio = request.form['bio']
        avatar = request.files.get('avatar')
        
        if avatar and allowed_file(avatar.filename):
            filename = secure_filename(f"{user_id}_{avatar.filename}")
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            c.execute("UPDATE users SET avatar = ? WHERE id = ?", (filename, user_id))
        
        c.execute("UPDATE users SET bio = ? WHERE id = ?", (bio, user_id))
        conn.commit()
        flash('Профиль обновлен!')
    
    # Получаем данные пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Получаем посты пользователя
    c.execute("SELECT * FROM posts WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    posts = c.fetchall()
    
    conn.close()
    
    if not user:
        flash('Пользователь не найден')
        return redirect(url_for('feed'))
    
    return render_template(
        'profile.html', 
        user=user, 
        posts=posts,
        is_own_profile=is_own_profile
    )

# Добавить новую конфигурацию для файлов
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8 MB
app.config['MESSAGE_FILES_FOLDER'] = 'static/message_files'
os.makedirs(app.config['MESSAGE_FILES_FOLDER'], exist_ok=True)

# Галерея фотографий
@app.route('/gallery')
def gallery():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Получаем текущего пользователя
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    
    # Получаем аватарки
    c.execute("SELECT avatar FROM users WHERE avatar IS NOT NULL")
    avatars = [row[0] for row in c.fetchall()]
    conn.close()
    
    return render_template('gallery.html', user=user, avatars=avatars)

# Система сообщений
@app.route('/messages')
@app.route('/messages/<int:friend_id>')
def messages(friend_id=None):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Получаем текущего пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Получаем список друзей
    c.execute('''SELECT users.id, users.username, users.avatar 
                FROM friends 
                JOIN users ON friends.friend_id = users.id 
                WHERE friends.user_id = ? AND friends.status = 'accepted'
                UNION
                SELECT users.id, users.username, users.avatar 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'accepted' 
                ORDER BY username''', (user_id, user_id))
    friends = c.fetchall()
    
    # Получаем историю сообщений
    messages = []
    active_friend = None
    if friend_id:
        # Получаем информацию о друге
        c.execute("SELECT * FROM users WHERE id = ?", (friend_id,))
        active_friend = c.fetchone()
        
        # Получаем сообщения
        c.execute('''SELECT messages.*, users.username, users.avatar 
                    FROM messages 
                    JOIN users ON messages.sender_id = users.id 
                    WHERE (sender_id = ? AND receiver_id = ?) 
                    OR (sender_id = ? AND receiver_id = ?)
                    ORDER BY timestamp''', 
                 (user_id, friend_id, friend_id, user_id))
        messages = c.fetchall()
    
    conn.close()
    return render_template('messages.html', user=user, friends=friends, 
                          messages=messages, friend_id=friend_id, active_friend=active_friend)

# Система друзей
@app.route('/friends', methods=['GET'])
def friends():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Получаем текущего пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Запросы в друзья
    c.execute('''SELECT users.id, users.username, users.avatar 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'pending' ''', (user_id,))
    requests = c.fetchall()
    
    # Список друзей
    c.execute('''SELECT users.id, users.username, users.avatar 
                FROM friends 
                JOIN users ON friends.friend_id = users.id 
                WHERE friends.user_id = ? AND friends.status = 'accepted'
                UNION
                SELECT users.id, users.username, users.avatar 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'accepted' 
                ORDER BY username''', (user_id, user_id))
    friends_list = c.fetchall()
    
    # Поиск пользователей
    search_query = request.args.get('search', '')
    search_results = []
    if search_query:
        c.execute("SELECT id, username, avatar FROM users WHERE username LIKE ? AND id != ?", 
                 (f'%{search_query}%', user_id))
        search_results = c.fetchall()
    
    conn.close()
    return render_template('friends.html', user=user, requests=requests, 
                          friends=friends_list, search_results=search_results, 
                          search_query=search_query)

@app.route('/add_friend/<int:friend_id>')
def add_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    try:
        # Проверяем, не существует ли уже запроса
        c.execute("SELECT * FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)", 
                 (user_id, friend_id, friend_id, user_id))
        existing = c.fetchone()
        
        if not existing:
            c.execute("INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, 'pending')", 
                     (user_id, friend_id))
            conn.commit()
            flash('Запрос отправлен!')
        else:
            flash('Запрос уже отправлен или вы уже друзья')
    except sqlite3.IntegrityError:
        flash('Ошибка при отправке запроса')
    
    conn.close()
    return redirect(url_for('friends'))

@app.route('/accept_friend/<int:friend_id>')
def accept_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Принимаем запрос в друзья
    c.execute("UPDATE friends SET status = 'accepted' WHERE user_id = ? AND friend_id = ?", 
             (friend_id, user_id))
    conn.commit()
    conn.close()
    
    flash('Запрос в друзья принят!')
    return redirect(url_for('friends'))

@app.route('/remove_friend/<int:friend_id>')
def remove_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Удаляем из друзей
    c.execute("DELETE FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)", 
             (user_id, friend_id, friend_id, user_id))
    conn.commit()
    conn.close()
    
    flash('Пользователь удален из друзей')
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

@app.route('/delete_post/<int:post_id>')
def delete_post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Проверяем, принадлежит ли пост текущему пользователю
    c.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,))
    post = c.fetchone()
    
    if post and post[0] == session['user_id']:
        c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
        flash('Пост удалён!')
    else:
        flash('Ошибка удаления')
    
    conn.close()
    return redirect(url_for('feed'))


# Статические файлы
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# Загрузка изображений
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# API для получения истории сообщений
@app.route('/api/messages/<int:friend_id>')
def get_messages(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    c.execute('''SELECT messages.*, users.username, users.avatar 
                FROM messages 
                JOIN users ON messages.sender_id = users.id 
                WHERE (sender_id = ? AND receiver_id = ?) 
                OR (sender_id = ? AND receiver_id = ?)
                ORDER BY timestamp''', 
             (user_id, friend_id, friend_id, user_id))
    messages = c.fetchall()
    conn.close()
    
    # Форматируем сообщения для JSON
    formatted_messages = []
    for msg in messages:
        message_data = {
            'id': msg[0],
            'sender_id': msg[1],
            'receiver_id': msg[2],
            'content': msg[3],
            'file_path': msg[5],  # Добавляем путь к файлу
            'timestamp': msg[4],
            'username': msg[6],
            'avatar': msg[7]
        }
        formatted_messages.append(message_data)
    
    return jsonify(messages=formatted_messages)

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(
        app.config['MESSAGE_FILES_FOLDER'], 
        filename, 
        as_attachment=True
    )

# API для получения статуса набора текста
@app.route('/api/typing_status/<int:friend_id>')
def get_typing_status(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    key = f"{friend_id}_{user_id}"
    is_typing = typing_status.get(key, False)
    
    # Сбрасываем статус после проверки
    typing_status[key] = False
    
    return jsonify({'is_typing': is_typing})

# Обработчики WebSocket
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        join_room(str(session['user_id']))

@socketio.on('disconnect')
def handle_disconnect():
    if 'user_id' in session:
        leave_room(str(session['user_id']))

@socketio.on('join_chat')
def handle_join_chat(data):
    friend_id = data['friend_id']
    user_id = session['user_id']
    room_id = f"{min(user_id, friend_id)}_{max(user_id, friend_id)}"
    join_room(room_id)

@socketio.on('send_message')
def handle_send_message(data):
    sender_id = session['user_id']
    receiver_id = data['receiver_id']
    content = data['content']
    file = data.get('file')  # Получаем файл если есть
    
    file_path = None
    if file:
        # Проверяем размер файла
        if len(file['data']) > 8 * 1024 * 1024:
            emit('file_error', {'error': 'File size exceeds 8 MB limit'})
            return
        
        # Сохраняем файл
        filename = secure_filename(f"{int(time.time())}_{file['filename']}")
        file_path = os.path.join(app.config['MESSAGE_FILES_FOLDER'], filename)
        with open(file_path, 'wb') as f:
            f.write(file['data'])
    
    # Сохраняем сообщение в БД
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender_id, receiver_id, content, file_path) VALUES (?, ?, ?, ?)", 
             (sender_id, receiver_id, content, file_path))
    conn.commit()
    
    # Получаем данные отправителя
    c.execute("SELECT username, avatar FROM users WHERE id = ?", (sender_id,))
    sender_data = c.fetchone()
    conn.close()
    
    # Формируем данные сообщения
    message_data = {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'content': content,
        'file_path': file_path,
        'file_name': file['filename'] if file else None,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'username': sender_data[0],
        'avatar': sender_data[1]
    }
    
    # Отправляем сообщение
    room_id = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    emit('receive_message', message_data, room=room_id)

@socketio.on('typing')
def handle_typing(data):
    sender_id = session['user_id']
    receiver_id = data['receiver_id']
    
    # Устанавливаем статус набора текста
    key = f"{sender_id}_{receiver_id}"
    typing_status[key] = True
    
    # Отправляем уведомление о наборе текста
    room_id = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    emit('user_typing', {'sender_id': sender_id}, room=room_id)

# HTML шаблоны в виде строк
app.jinja_env.globals.update(zip=zip)

templates = {
    'index.html': '''<!DOCTYPE html>
<html>
<head>
    <title>Социальная сеть</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f0f2f5; }
        .container { max-width: 400px; margin: 50px auto; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .logo { text-align: center; margin-bottom: 20px; }
        .logo h1 { color: #1877f2; font-size: 3rem; margin: 0; }
        .form-group { margin-bottom: 15px; }
        input[type="text"], input[type="password"], input[type="email"] {
            width: 100%; padding: 12px; font-size: 16px; border: 1px solid #dddfe2; border-radius: 6px;
        }
        button { width: 100%; padding: 12px; background: #1877f2; color: white; border: none; border-radius: 6px; font-size: 18px; font-weight: bold; cursor: pointer; }
        .tabs { display: flex; margin-bottom: 15px; }
        .tab { flex: 1; text-align: center; padding: 12px; background: #f0f2f5; cursor: pointer; border-radius: 6px; margin: 0 5px; }
        .tab.active { background: #1877f2; color: white; }
        .form-container { display: none; }
        .form-container.active { display: block; }
        .divider { height: 1px; background: #dadde1; margin: 20px 0; }
        .footer { text-align: center; margin-top: 20px; font-size: 14px; }
        .flash-messages { margin-bottom: 15px; }
        .flash-message { padding: 10px; background: #ffeeba; border-radius: 4px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>social</h1>
        </div>
        
        <div class="flash-messages">
            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash-message">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('login')">Вход</div>
            <div class="tab" onclick="showTab('register')">Регистрация</div>
        </div>

        <form id="login-form" class="form-container active" method="post">
            <div class="form-group">
                <input type="text" name="username" placeholder="Имя пользователя" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" placeholder="Пароль" required>
            </div>
            <input type="hidden" name="action" value="login">
            <button type="submit">Войти</button>
        </form>

        <form id="register-form" class="form-container" method="post">
            <div class="form-group">
                <input type="text" name="username" placeholder="Имя пользователя" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" placeholder="Пароль" required>
            </div>
            <div class="form-group">
                <input type="email" name="email" placeholder="Email (необязательно)">
            </div>
            <input type="hidden" name="action" value="register">
            <button type="submit">Зарегистрироваться</button>
        </form>
        
        <div class="divider"></div>
        
        <div class="footer">
            <p>Для теста используйте: alex/pass123, masha/pass123, sasha/pass123, dasha/pass123</p>
        </div>
    </div>

    <script>
        function showTab(tabName) {
            document.querySelectorAll('.form-container').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
            
            if(tabName === 'login') {
                document.getElementById('login-form').classList.add('active');
                document.querySelectorAll('.tab')[0].classList.add('active');
            } else {
                document.getElementById('register-form').classList.add('active');
                document.querySelectorAll('.tab')[1].classList.add('active');
            }
        }
    </script>
</body>
</html>''',
    
    'feed.html': '''<!DOCTYPE html>
<html>
<head>
    <title>Лента новостей</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; background: #f0f2f5; }
        
        .sidebar { width: 280px; background: white; height: 100vh; position: fixed; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .profile-card { display: flex; align-items: center; padding-bottom: 20px; border-bottom: 1px solid #eee; margin-bottom: 20px; }
        .profile-card img { width: 60px; height: 60px; border-radius: 50%; object-fit: cover; margin-right: 15px; }
        .nav a { display: flex; align-items: center; padding: 12px 15px; text-decoration: none; color: #333; border-radius: 8px; margin-bottom: 5px; transition: all 0.2s; }
        .nav a:hover { background: #f0f2f5; }
        .nav a.active { background: #1877f2; color: white; }
        .nav a i { margin-right: 10px; }
        
        .content { flex: 1; margin-left: 280px; padding: 20px; }
        .create-post { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .create-post textarea { width: 100%; height: 80px; padding: 12px; border: 1px solid #ddd; border-radius: 8px; resize: none; margin-bottom: 10px; font-family: inherit; }
        .create-post button { background: #1877f2; color: white; border: none; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        
        .post { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .post-header { display: flex; align-items: center; margin-bottom: 12px; }
        .post-header img { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; margin-right: 10px; }
        .post-info h3 { margin: 0; font-size: 16px; }
        .post-info time { color: #65676b; font-size: 12px; }
        .post-content { margin: 15px 0; line-height: 1.5; }
        .post-actions { display: flex; border-top: 1px solid #eee; padding-top: 10px; }
        .post-actions button { flex: 1; background: none; border: none; padding: 8px; border-radius: 4px; cursor: pointer; color: #65676b; }
        .post-actions button:hover { background: #f0f2f5; }
        
        .empty-feed { text-align: center; padding: 40px; color: #65676b; }
        .empty-feed i { font-size: 48px; margin-bottom: 15px; opacity: 0.5; }
    </style>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <div class="sidebar">
        <div class="profile-card">
            <img src="{{ url_for('static', filename='uploads/' + user[5]) if user[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
            <div>
                <h3>{{ user[1] }}</h3>
                <small>{{ user[4] or 'Нет информации' | truncate(20) }}</small>
            </div>
        </div>
        
        <div class="nav">
            <a href="{{ url_for('feed') }}" class="active">
                <i class="fas fa-newspaper"></i> Новости
            </a>
            <a href="{{ url_for('profile') }}">
                <i class="fas fa-user"></i> Профиль
            </a>
            <a href="{{ url_for('gallery') }}">
                <i class="fas fa-images"></i> Фотографии
            </a>
            <a href="{{ url_for('messages') }}">
                <i class="fas fa-comments"></i> Сообщения
            </a>
            <a href="{{ url_for('friends') }}">
                <i class="fas fa-user-friends"></i> Друзья
            </a>
            <a href="{{ url_for('logout') }}">
                <i class="fas fa-sign-out-alt"></i> Выйти
            </a>
        </div>
    </div>

    <div class="content">
        <div class="create-post">
            <form method="POST" action="{{ url_for('create_post') }}">
                <textarea name="content" placeholder="Что у вас нового?" required></textarea>
                <button type="submit">Опубликовать</button>
            </form>
        </div>

        {% if posts %}
            {% for post in posts %}
            <div class="post">
                <div class="post-header">
                    <img src="{{ url_for('static', filename='uploads/' + post[5]) if post[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
                    <div class="post-info">
                        <h3>{{ post[4] }}</h3>
                        <time>{{ post[3] }}</time>
                    </div>
                </div>
                <div class="post-content">
                    {{ post[2] }}
                </div>
                <div class="post-actions">
                    <button><i class="fas fa-thumbs-up"></i> Нравится</button>
                    <button><i class="fas fa-comment"></i> Комментировать</button>
                    <button><i class="fas fa-share"></i> Поделиться</button>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <div class="empty-feed">
                <i class="fas fa-newspaper"></i>
                <h3>Новостей пока нет</h3>
                <p>Будьте первым, кто опубликует что-то интересное!</p>
            </div>
        {% endif %}
    </div>
</body>
</html>''',
    
    'profile.html': '''<!DOCTYPE html>
<html>
<head>
    <title>Профиль</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; background: #f0f2f5; }
        
        .sidebar { width: 280px; background: white; height: 100vh; position: fixed; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .profile-card { display: flex; align-items: center; padding-bottom: 20px; border-bottom: 1px solid #eee; margin-bottom: 20px; }
        .profile-card img { width: 60px; height: 60px; border-radius: 50%; object-fit: cover; margin-right: 15px; }
        .nav a { display: flex; align-items: center; padding: 12px 15px; text-decoration: none; color: #333; border-radius: 8px; margin-bottom: 5px; transition: all 0.2s; }
        .nav a:hover { background: #f0f2f5; }
        .nav a.active { background: #1877f2; color: white; }
        .nav a i { margin-right: 10px; }
        
        .content { flex: 1; margin-left: 280px; padding: 20px; }
        .profile-header { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .profile-info { display: flex; }
        .avatar-section { width: 200px; text-align: center; padding: 20px; }
        .avatar-section img { width: 150px; height: 150px; border-radius: 50%; object-fit: cover; margin-bottom: 15px; }
        .info-section { flex: 1; padding: 20px; }
        .info-section h1 { margin-bottom: 20px; }
        .info-item { margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
        .info-item label { display: block; color: #65676b; font-size: 14px; margin-bottom: 5px; }
        .info-item p { font-size: 16px; }
        
        .edit-form { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group textarea { width: 100%; height: 100px; padding: 12px; border: 1px solid #ddd; border-radius: 8px; resize: none; font-family: inherit; }
        .form-group input[type="file"] { padding: 10px 0; }
        .edit-form button { background: #1877f2; color: white; border: none; padding: 12px 25px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        
        .flash-messages { margin-bottom: 15px; }
        .flash-message { padding: 10px; background: #d4edda; border-radius: 4px; margin-bottom: 10px; color: #155724; }
    </style>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <div class="sidebar">
        <div class="profile-card">
            <img src="{{ url_for('static', filename='uploads/' + user[5]) if user[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
            <div>
                <h3>{{ user[1] }}</h3>
                <small>{{ user[4] or 'Нет информации' | truncate(20) }}</small>
            </div>
        </div>
        
        <div class="nav">
            <a href="{{ url_for('feed') }}">
                <i class="fas fa-newspaper"></i> Новости
            </a>
            <a href="{{ url_for('profile') }}" class="active">
                <i class="fas fa-user"></i> Профиль
            </a>
            <a href="{{ url_for('gallery') }}">
                <i class="fas fa-images"></i> Фотографии
            </a>
            <a href="{{ url_for('messages') }}">
                <i class="fas fa-comments"></i> Сообщения
            </a>
            <a href="{{ url_for('friends') }}">
                <i class="fas fa-user-friends"></i> Друзья
            </a>
            <a href="{{ url_for('logout') }}">
                <i class="fas fa-sign-out-alt"></i> Выйти
            </a>
        </div>
    </div>

    <div class="content">
        <div class="flash-messages">
            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash-message">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
        </div>
        
        <div class="profile-header">
            <div class="profile-info">
                <div class="avatar-section">
                    <img src="{{ url_for('static', filename='uploads/' + user[5]) if user[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
                    <h2>{{ user[1] }}</h2>
                </div>
                <div class="info-section">
                    <h1>Информация о профиле</h1>
                    <div class="info-item">
                        <label>Имя пользователя</label>
                        <p>{{ user[1] }}</p>
                    </div>
                    <div class="info-item">
                        <label>Email</label>
                        <p>{{ user[3] or 'Не указан' }}</p>
                    </div>
                    <div class="info-item">
                        <label>О себе</label>
                        <p>{{ user[4] or 'Не указано' }}</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="edit-form">
            <h2>Редактировать профиль</h2>
            <form method="POST" enctype="multipart/form-data">
                <div class="form-group">
                    <label for="bio">О себе:</label>
                    <textarea id="bio" name="bio" placeholder="Расскажите о себе...">{{ user[4] or '' }}</textarea>
                </div>
                <div class="form-group">
                    <label for="avatar">Аватарка:</label>
                    <input type="file" id="avatar" name="avatar">
                    <small>Поддерживаются JPG, PNG и GIF (анимированные)</small>
                </div>
                <button type="submit">Сохранить изменения</button>
            </form>
        </div>
    </div>
</body>
</html>''',
    
    'gallery.html': '''<!DOCTYPE html>
<html>
<head>
    <title>Галерея</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; background: #f0f2f5; }
        
        .sidebar { width: 280px; background: white; height: 100vh; position: fixed; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .profile-card { display: flex; align-items: center; padding-bottom: 20px; border-bottom: 1px solid #eee; margin-bottom: 20px; }
        .profile-card img { width: 60px; height: 60px; border-radius: 50%; object-fit: cover; margin-right: 15px; }
        .nav a { display: flex; align-items: center; padding: 12px 15px; text-decoration: none; color: #333; border-radius: 8px; margin-bottom: 5px; transition: all 0.2s; }
        .nav a:hover { background: #f0f2f5; }
        .nav a.active { background: #1877f2; color: white; }
        .nav a i { margin-right: 10px; }
        
        .content { flex: 1; margin-left: 280px; padding: 20px; }
        .gallery-title { margin-bottom: 20px; }
        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
        .gallery-item { border-radius: 10px; overflow: hidden; box-shadow: 0 3px 10px rgba(0,0,0,0.1); transition: all 0.3s; }
        .gallery-item:hover { transform: translateY(-5px); box-shadow: 0 8px 20px rgba(0,0,0,0.15); }
        .gallery-item img { width: 100%; height: 200px; object-fit: cover; display: block; }
        .gallery-item p { padding: 10px; text-align: center; background: white; }
        
        .empty-gallery { text-align: center; padding: 40px; color: #65676b; }
        .empty-gallery i { font-size: 48px; margin-bottom: 15px; opacity: 0.5; }
    </style>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <div class="sidebar">
        <div class="profile-card">
            <img src="{{ url_for('static', filename='uploads/' + user[5]) if user[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
            <div>
                <h3>{{ user[1] }}</h3>
                <small>{{ user[4] or 'Нет информации' | truncate(20) }}</small>
            </div>
        </div>
        
        <div class="nav">
            <a href="{{ url_for('feed') }}">
                <i class="fas fa-newspaper"></i> Новости
            </a>
            <a href="{{ url_for('profile') }}">
                <i class="fas fa-user"></i> Профиль
            </a>
            <a href="{{ url_for('gallery') }}" class="active">
                <i class="fas fa-images"></i> Фотографии
            </a>
            <a href="{{ url_for('messages') }}">
                <i class="fas fa-comments"></i> Сообщения
            </a>
            <a href="{{ url_for('friends') }}">
                <i class="fas fa-user-friends"></i> Друзья
            </a>
            <a href="{{ url_for('logout') }}">
                <i class="fas fa-sign-out-alt"></i> Выйти
            </a>
        </div>
    </div>

    <div class="content">
        <div class="gallery-title">
            <h1>Галерея фотографий</h1>
            <p>Все аватарки пользователей сети</p>
        </div>
        
        {% if avatars %}
            <div class="gallery-grid">
                {% for avatar in avatars %}
                <div class="gallery-item">
                    <img src="{{ url_for('static', filename='uploads/' + avatar) }}" alt="Фото">
                    <p>Аватар пользователя</p>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="empty-gallery">
                <i class="fas fa-camera"></i>
                <h3>Пока нет фотографий</h3>
                <p>Будьте первым, кто добавит аватарку!</p>
            </div>
        {% endif %}
    </div>
</body>
</html>''',
    
    'messages.html': '''<!DOCTYPE html>
<html>
<head>
    <title>Сообщения</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; background: #f0f2f5; }
        
        .sidebar { width: 280px; background: white; height: 100vh; position: fixed; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .profile-card { display: flex; align-items: center; padding-bottom: 20px; border-bottom: 1px solid #eee; margin-bottom: 20px; }
        .profile-card img { width: 60px; height: 60px; border-radius: 50%; object-fit: cover; margin-right: 15px; }
        .nav a { display: flex; align-items: center; padding: 12px 15px; text-decoration: none; color: #333; border-radius: 8px; margin-bottom: 5px; transition: all 0.2s; }
        .nav a:hover { background: #f0f2f5; }
        .nav a.active { background: #1877f2; color: white; }
        .nav a i { margin-right: 10px; }
        
        .content { flex: 1; margin-left: 280px; padding: 20px; display: flex; height: calc(100vh - 40px); }
        .friends-list { width: 300px; background: white; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); padding: 15px; margin-right: 20px; overflow-y: auto; }
        .friends-list h2 { margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
        .friend-item { display: flex; align-items: center; padding: 12px; cursor: pointer; border-radius: 8px; margin-bottom: 8px; }
        .friend-item:hover { background: #f0f2f5; }
        .friend-item.active { background: #e7f3ff; }
        .friend-item img { width: 45px; height: 45px; border-radius: 50%; object-fit: cover; margin-right: 12px; }
        .friend-info h3 { margin: 0; font-size: 16px; }
        .friend-info p { color: #65676b; font-size: 13px; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        
        .chat-container { flex: 1; background: white; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); display: flex; flex-direction: column; }
        .chat-header { display: flex; align-items: center; padding: 15px; border-bottom: 1px solid #eee; }
        .chat-header img { width: 45px; height: 45px; border-radius: 50%; object-fit: cover; margin-right: 12px; }
        .chat-messages { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; }
        .message { max-width: 75%; padding: 12px; border-radius: 18px; margin-bottom: 15px; position: relative; }
        .sent { align-self: flex-end; background: #1877f2; color: white; border-bottom-right-radius: 5px; }
        .received { align-self: flex-start; background: #f0f2f5; border-bottom-left-radius: 5px; }
        .message-time { font-size: 12px; margin-top: 5px; opacity: 0.8; }
        .sent .message-time { text-align: right; }
        .chat-input { padding: 15px; border-top: 1px solid #eee; display: flex; }
        .chat-input textarea { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 20px; resize: none; min-height: 50px; font-family: inherit; }
        .chat-input button { background: #1877f2; color: white; border: none; border-radius: 20px; padding: 0 25px; margin-left: 10px; cursor: pointer; font-weight: bold; }
        
        .typing-indicator { padding: 0 20px; font-style: italic; color: #777; min-height: 20px; }
        
        .empty-chat { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #65676b; }
        .empty-chat i { font-size: 60px; margin-bottom: 20px; opacity: 0.3; }
    </style>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.socket.io/4.0.1/socket.io.min.js"></script>
</head>
<body>
    <div class="sidebar">
        <div class="profile-card">
            <img src="{{ url_for('static', filename='uploads/' + user[5]) if user[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
            <div>
                <h3>{{ user[1] }}</h3>
                <small>{{ user[4] or 'Нет информации' | truncate(20) }}</small>
            </div>
        </div>
        
        <div class="nav">
            <a href="{{ url_for('feed') }}">
                <i class="fas fa-newspaper"></i> Новости
            </a>
            <a href="{{ url_for('profile') }}">
                <i class="fas fa-user"></i> Профиль
            </a>
            <a href="{{ url_for('gallery') }}">
                <i class="fas fa-images"></i> Фотографии
            </a>
            <a href="{{ url_for('messages') }}" class="active">
                <i class="fas fa-comments"></i> Сообщения
            </a>
            <a href="{{ url_for('friends') }}">
                <i class="fas fa-user-friends"></i> Друзья
            </a>
            <a href="{{ url_for('logout') }}">
                <i class="fas fa-sign-out-alt"></i> Выйти
            </a>
        </div>
    </div>

    <div class="content">
        <div class="friends-list">
            <h2>Диалоги</h2>
            {% for friend in friends %}
            <div class="friend-item {% if friend_id == friend[0] %}active{% endif %}" onclick="location.href='{{ url_for('messages', friend_id=friend[0]) }}'">
                <img src="{{ url_for('static', filename='uploads/' + friend[2]) if friend[2] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
                <div class="friend-info">
                    <h3>{{ friend[1] }}</h3>
                    <p>Последнее сообщение...</p>
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="chat-container">
            {% if friend_id %}
            <div class="chat-header">
                <img src="{{ url_for('static', filename='uploads/' + active_friend[5]) if active_friend[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
                <div>
                    <h3>{{ active_friend[1] }}</h3>
                    <small>в сети</small>
                </div>
            </div>
            
            <div class="chat-messages" id="chat-messages">
                {% for msg in messages %}
                <div class="message {% if msg[1] == session['user_id'] %}sent{% else %}received{% endif %}">
                    <div class="message-text">{{ msg[3] }}</div>
                    <div class="message-time">{{ msg[4] }}</div>
                </div>
                {% endfor %}
            </div>
            
            <div class="typing-indicator" id="typing-indicator" style="display: none;">
                {{ active_friend[1] }} печатает...
            </div>
            
            <div class="chat-input">
                <textarea id="message-input" placeholder="Напишите сообщение..."></textarea>
                <button id="send-button"><i class="fas fa-paper-plane"></i></button>
            </div>
            {% else %}
            <div class="empty-chat">
                <i class="fas fa-comments"></i>
                <h3>Выберите диалог</h3>
                <p>Начните общение с вашими друзьями</p>
            </div>
            {% endif %}
        </div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const socket = io();
            const userId = {{ session['user_id'] }};
            const friendId = {{ friend_id if friend_id else 0 }};
            const chatMessages = document.getElementById('chat-messages');
            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            const typingIndicator = document.getElementById('typing-indicator');
            
            // Присоединяемся к комнатам
            socket.emit('connect');
            if (friendId) {
                socket.emit('join_chat', { friend_id: friendId });
            }
            
            // Обработчик отправки сообщения
            sendButton.addEventListener('click', sendMessage);
            messageInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // Отслеживание набора текста
            messageInput.addEventListener('input', function() {
                if (messageInput.value.trim() !== '') {
                    socket.emit('typing', { receiver_id: friendId });
                }
            });
            
            // Получение новых сообщений
            socket.on('receive_message', function(data) {
                addMessageToChat(data);
                scrollToBottom();
            });
            
            // Уведомление о наборе текста
            socket.on('user_typing', function(data) {
                if (data.sender_id === friendId) {
                    typingIndicator.style.display = 'block';
                    setTimeout(() => {
                        typingIndicator.style.display = 'none';
                    }, 2000);
                }
            });
            
            function sendMessage() {
                const content = messageInput.value.trim();
                if (content && friendId) {
                    socket.emit('send_message', {
                        receiver_id: friendId,
                        content: content
                    });
                    messageInput.value = '';
                }
            }
            
            function addMessageToChat(msg) {
                const isSent = msg.sender_id == userId;
                const messageElement = document.createElement('div');
                messageElement.className = `message ${isSent ? 'sent' : 'received'}`;
                messageElement.innerHTML = `
                    <div class="message-text">${msg.content}</div>
                    <div class="message-time">${msg.timestamp}</div>
                `;
                chatMessages.appendChild(messageElement);
            }
            
            function scrollToBottom() {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
            
            // Загрузка истории сообщений при открытии чата
            if (friendId) {
                fetch(`/api/messages/${friendId}`)
                    .then(response => response.json())
                    .then(data => {
                        data.messages.forEach(msg => {
                            addMessageToChat(msg);
                        });
                        scrollToBottom();
                    });
            }
        });
    </script>
</body>
</html>''',
    
    'friends.html': '''<!DOCTYPE html>
<html>
<head>
    <title>Друзья</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; background: #f0f2f5; }
        
        .sidebar { width: 280px; background: white; height: 100vh; position: fixed; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .profile-card { display: flex; align-items: center; padding-bottom: 20px; border-bottom: 1px solid #eee; margin-bottom: 20px; }
        .profile-card img { width: 60px; height: 60px; border-radius: 50%; object-fit: cover; margin-right: 15px; }
        .nav a { display: flex; align-items: center; padding: 12px 15px; text-decoration: none; color: #333; border-radius: 8px; margin-bottom: 5px; transition: all 0.2s; }
        .nav a:hover { background: #f0f2f5; }
        .nav a.active { background: #1877f2; color: white; }
        .nav a i { margin-right: 10px; }
        
        .content { flex: 1; margin-left: 280px; padding: 20px; }
        .search-container { margin-bottom: 20px; }
        .search-container form { display: flex; }
        .search-container input { flex: 1; padding: 12px 20px; border: 1px solid #ddd; border-radius: 30px 0 0 30px; font-size: 16px; outline: none; }
        .search-container button { background: #1877f2; color: white; border: none; padding: 0 25px; border-radius: 0 30px 30px 0; cursor: pointer; font-size: 16px; }
        
        .section { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .section-title { display: flex; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
        .section-title h2 { font-size: 1.5rem; color: #2c3e50; margin-right: 15px; }
        .badge { background: #e74c3c; color: white; border-radius: 50%; width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; font-size: 14px; }
        
        .friends-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 20px; }
        .friend-card { background: #f9f9f9; border-radius: 10px; overflow: hidden; transition: all 0.3s; box-shadow: 0 3px 10px rgba(0,0,0,0.05); }
        .friend-card:hover { transform: translateY(-5px); box-shadow: 0 8px 20px rgba(0,0,0,0.08); }
        .friend-header { padding: 20px; text-align: center; background: linear-gradient(to right, #4a76a8, #5c8ac0); color: white; }
        .friend-avatar { width: 80px; height: 80px; border-radius: 50%; border: 3px solid rgba(255,255,255,0.3); object-fit: cover; margin-bottom: 15px; }
        .friend-name { font-size: 1.1rem; font-weight: 600; }
        .friend-actions { padding: 15px; display: flex; justify-content: center; gap: 10px; }
        .friend-actions a { padding: 8px 15px; border: none; border-radius: 5px; cursor: pointer; font-size: 0.9rem; transition: background 0.2s; text-decoration: none; display: inline-block; }
        .friend-actions .btn-accept { background: #2ecc71; color: white; }
        .friend-actions .btn-reject { background: #e74c3c; color: white; }
        .friend-actions .btn-remove { background: #f0f0f0; color: #333; }
        .friend-actions .btn-message { background: #3498db; color: white; }
        .friend-actions a:hover { opacity: 0.9; }
        
        .empty-state { text-align: center; padding: 40px; color: #95a5a6; }
        .empty-state i { font-size: 3rem; margin-bottom: 20px; opacity: 0.5; }
        .empty-state p { font-size: 1.1rem; }
        
        .flash-messages { margin-bottom: 15px; }
        .flash-message { padding: 10px; background: #d4edda; border-radius: 4px; margin-bottom: 10px; color: #155724; }
    </style>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <div class="sidebar">
        <div class="profile-card">
            <img src="{{ url_for('static', filename='uploads/' + user[5]) if user[5] else 'https://via.placeholder.com/150?text=Avatar' }}" alt="Avatar">
            <div>
                <h3>{{ user[1] }}</h3>
                <small>{{ user[4] or 'Нет информации' | truncate(20) }}</small>
            </div>
        </div>
        
        <div class="nav">
            <a href="{{ url_for('feed') }}">
                <i class="fas fa-newspaper"></i> Новости
            </a>
            <a href="{{ url_for('profile') }}">
                <i class="fas fa-user"></i> Профиль
            </a>
            <a href="{{ url_for('gallery') }}">
                <i class="fas fa-images"></i> Фотографии
            </a>
            <a href="{{ url_for('messages') }}">
                <i class="fas fa-comments"></i> Сообщения
            </a>
            <a href="{{ url_for('friends') }}" class="active">
                <i class="fas fa-user-friends"></i> Друзья
                {% if requests %}<span class="badge">{{ requests|length }}</span>{% endif %}
            </a>
            <a href="{{ url_for('logout') }}">
                <i class="fas fa-sign-out-alt"></i> Выйти
            </a>
        </div>
    </div>

    <div class="content">
        <div class="flash-messages">
            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash-message">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
        </div>
        
        <div class="search-container">
            <form method="GET" action="{{ url_for('friends') }}">
                <input type="text" name="search" placeholder="Найти друзей..." value="{{ search_query }}">
                <button type="submit"><i class="fas fa-search"></i> Поиск</button>
            </form>
        </div>

        {% if search_results %}
        <div class="section">
            <div class="section-title">
                <h2>Результаты поиска</h2>
            </div>
            <div class="friends-grid">
                {% for user in search_results %}
                <div class="friend-card">
                    <div class="friend-header">
                        <img src="{{ url_for('static', filename='uploads/' + user[2]) if user[2] else 'https://via.placeholder.com/150?text=Avatar' }}" 
                             class="friend-avatar" alt="{{ user[1] }}">
                        <div class="friend-name">{{ user[1] }}</div>
                    </div>
                    <div class="friend-actions">
                        <a href="{{ url_for('add_friend', friend_id=user[0]) }}" class="btn-message">
                            <i class="fas fa-user-plus"></i> Добавить
                        </a>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        <div class="section">
            <div class="section-title">
                <h2>Запросы в друзья {% if requests %}<span class="badge">{{ requests|length }}</span>{% endif %}</h2>
            </div>
            
            {% if requests %}
            <div class="friends-grid">
                {% for req in requests %}
                <div class="friend-card">
                    <div class="friend-header">
                        <img src="{{ url_for('static', filename='uploads/' + req[2]) if req[2] else 'https://via.placeholder.com/150?text=Avatar' }}" 
                             class="friend-avatar" alt="{{ req[1] }}">
                        <div class="friend-name">{{ req[1] }}</div>
                    </div>
                    <div class="friend-actions">
                        <a href="{{ url_for('accept_friend', friend_id=req[0]) }}" class="btn-accept">
                            <i class="fas fa-check"></i> Принять
                        </a>
                        <a href="{{ url_for('remove_friend', friend_id=req[0]) }}" class="btn-reject">
                            <i class="fas fa-times"></i> Отклонить
                        </a>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <i class="fas fa-user-clock"></i>
                <p>У вас нет новых запросов в друзья</p>
            </div>
            {% endif %}
        </div>

        <div class="section">
            <div class="section-title">
                <h2>Мои друзья {% if friends %}<span class="badge">{{ friends|length }}</span>{% endif %}</h2>
            </div>
            
            {% if friends %}
            <div class="friends-grid">
                {% for friend in friends %}
                <div class="friend-card">
                    <div class="friend-header">
                        <img src="{{ url_for('static', filename='uploads/' + friend[2]) if friend[2] else 'https://via.placeholder.com/150?text=Avatar' }}" 
                             class="friend-avatar" alt="{{ friend[1] }}">
                        <div class="friend-name">{{ friend[1] }}</div>
                    </div>
                    <div class="friend-actions">
                        <a href="{{ url_for('messages', friend_id=friend[0]) }}" class="btn-message">
                            <i class="fas fa-comment"></i> Написать
                        </a>
                        <a href="{{ url_for('remove_friend', friend_id=friend[0]) }}" class="btn-remove">
                            <i class="fas fa-user-minus"></i> Удалить
                        </a>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <i class="fas fa-users"></i>
                <p>У вас пока нет друзей. Найдите новых друзей через поиск!</p>
            </div>
            {% endif %}
        </div>
    </div>

    <script>
        // Анимация карточек
        document.querySelectorAll('.friend-card').forEach(card => {
            card.addEventListener('mouseenter', () => {
                card.style.transform = 'translateY(-5px)';
                card.style.boxShadow = '0 8px 20px rgba(0,0,0,0.08)';
            });
            
            card.addEventListener('mouseleave', () => {
                card.style.transform = '';
                card.style.boxShadow = '';
            });
        });
    </script>
</body>
</html>'''
}

# Регистрируем шаблоны
@app.route('/<path:path>')
def serve_html(path):
    if path in templates:
        return templates[path]
    return "Page not found", 404

if __name__ == '__main__':
    socketio.run(app, debug=True)
