import sqlite3
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('social_network.db')
    c = conn.cursor()
    
    # Таблица пользователей с новым полем role
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                bio TEXT,
                avatar TEXT,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'moderator', 'user')))''')
    
    # Проверяем наличие столбца role в существующей таблице
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'role' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user' CHECK(role IN ('admin', 'moderator', 'user'))")
    
    # Остальные таблицы без изменений
    c.execute('''CREATE TABLE IF NOT EXISTS friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                status TEXT CHECK(status IN ('pending', 'accepted')),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(friend_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                file_path TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(receiver_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Тестовые пользователи с ролями
    users = [
        ('alex', generate_password_hash('pass123'), 'alex@example.com', 'none', 'alex.gif', 'admin'),
        ('masha', generate_password_hash('pass123'), 'masha@example.com', 'none', 'masha.jpg', 'moderator'),
        ('sasha', generate_password_hash('pass123'), 'sasha@example.com', 'none', 'sasha.png', 'user'),
        ('dasha', generate_password_hash('pass123'), 'dasha@example.com', '123', 'dasha.gif', 'user'),
    ]
    
    for user in users:
        try:
            # Все поля теперь включают роль
            c.execute("""INSERT INTO users 
                      (username, password, email, bio, avatar, role) 
                      VALUES (?, ?, ?, ?, ?, ?)""", 
                      user)
        except sqlite3.IntegrityError:
            # Обновляем роль для существующих пользователей
            c.execute("""UPDATE users SET role = ? 
                      WHERE username = ?""", 
                      (user[5], user[0]))
    
    conn.commit()
    conn.close()

# Остальные функции без изменений
def get_db():
    conn = sqlite3.connect('social_network.db')
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions