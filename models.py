import sqlite3
from werkzeug.security import generate_password_hash

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
            avatar = user[4] if len(user) > 4 and user[4] else 'default_avatar.png'
            c.execute("INSERT INTO users (username, password, email, bio, avatar) VALUES (?, ?, ?, ?, ?)", 
                     (user[0], user[1], user[2], user[3] if len(user) > 3 else 'none', avatar))
        except:
            pass
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect('social_network.db')
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions