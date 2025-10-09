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
                avatar TEXT,
                banner TEXT,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'moderator', 'user')),
                is_blocked BOOLEAN DEFAULT 0,
                block_reason TEXT,
                is_online BOOLEAN DEFAULT FALSE,
                last_seen DATETIME)''')
    
    # Проверяем наличие столбцов
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    
    if 'role' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    
    if 'is_online' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN is_online BOOLEAN DEFAULT FALSE")
    
    if 'last_seen' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN last_seen DATETIME")
        c.execute("UPDATE users SET last_seen = datetime('now')")

    # Добавляем баннер при отсутствии
    if 'banner' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN banner TEXT")

    # Флаг блокировки
    if 'is_blocked' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
    if 'block_reason' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN block_reason TEXT")
    
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

    # Ключи шифрования чатов (серверное хранилище): пара пользователей -> общий AES ключ (base64)
    c.execute('''CREATE TABLE IF NOT EXISTS chat_keys (
                 a_user_id INTEGER NOT NULL,
                 b_user_id INTEGER NOT NULL,
                 key_b64 TEXT NOT NULL,
                 PRIMARY KEY (a_user_id, b_user_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Глобальные настройки (key/value)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                 key TEXT PRIMARY KEY,
                 value TEXT)''')
    # Значения по умолчанию
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_mode', 'open')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('content_moderation', 'auto')")

    # Коды приглашений для режима регистрации по приглашениям
    c.execute('''CREATE TABLE IF NOT EXISTS invites (
                 code TEXT PRIMARY KEY,
                 uses_left INTEGER NOT NULL DEFAULT 1,
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                 expires_at DATETIME)''')

    # Миграция: добавляем expires_at, если его нет
    c.execute("PRAGMA table_info(invites)")
    invite_cols = [col[1] for col in c.fetchall()]
    if 'expires_at' not in invite_cols:
        try:
            c.execute("ALTER TABLE invites ADD COLUMN expires_at DATETIME")
        except sqlite3.OperationalError:
            pass

    # Лайки и комментарии к постам
    c.execute('''CREATE TABLE IF NOT EXISTS likes (
                 post_id INTEGER NOT NULL,
                 user_id INTEGER NOT NULL,
                 PRIMARY KEY (post_id, user_id),
                 FOREIGN KEY(post_id) REFERENCES posts(id),
                 FOREIGN KEY(user_id) REFERENCES users(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS comments (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 post_id INTEGER NOT NULL,
                 user_id INTEGER NOT NULL,
                 content TEXT NOT NULL,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(post_id) REFERENCES posts(id),
                 FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Жалобы
    c.execute('''CREATE TABLE IF NOT EXISTS reports (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 reporter_id INTEGER NOT NULL,
                 target_type TEXT NOT NULL CHECK(target_type IN ('post','comment','user')),
                 target_id INTEGER NOT NULL,
                 reason TEXT NOT NULL,
                 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved','rejected')),
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(reporter_id) REFERENCES users(id))''')

    # Музыка
    c.execute('''CREATE TABLE IF NOT EXISTS music (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 filename TEXT NOT NULL,
                 title TEXT,
                 uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS music_reports (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 reporter_id INTEGER NOT NULL,
                 track_id INTEGER NOT NULL,
                 reason TEXT NOT NULL,
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved','rejected')),
                 FOREIGN KEY(reporter_id) REFERENCES users(id),
                 FOREIGN KEY(track_id) REFERENCES music(id))''')

    # Плейлисты
    c.execute('''CREATE TABLE IF NOT EXISTS playlists (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 title TEXT NOT NULL,
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS playlist_tracks (
                 playlist_id INTEGER NOT NULL,
                 track_id INTEGER NOT NULL,
                 position INTEGER DEFAULT 0,
                 PRIMARY KEY (playlist_id, track_id),
                 FOREIGN KEY(playlist_id) REFERENCES playlists(id),
                 FOREIGN KEY(track_id) REFERENCES music(id))''')

    # Временные блокировки
    c.execute('''CREATE TABLE IF NOT EXISTS bans (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 until DATETIME NOT NULL,
                 reason TEXT,
                 moderator_id INTEGER,
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Добавляем недостающие столбцы в bans
    c.execute("PRAGMA table_info(bans)")
    bans_cols = [col[1] for col in c.fetchall()]
    if 'moderator_id' not in bans_cols:
        try:
            c.execute("ALTER TABLE bans ADD COLUMN moderator_id INTEGER")
        except sqlite3.OperationalError:
            pass

    # Логи модерации
    c.execute('''CREATE TABLE IF NOT EXISTS moderation_logs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  report_id INTEGER,
                  moderator_id INTEGER NOT NULL,
                  action TEXT NOT NULL,
                  target_type TEXT,
                  target_id INTEGER,
                  details TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(report_id) REFERENCES reports(id),
                  FOREIGN KEY(moderator_id) REFERENCES users(id))''')

    # Заявки на приглашение (для закрытой регистрации)
    c.execute('''CREATE TABLE IF NOT EXISTS invite_requests (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT,
                  message TEXT,
                  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  processed_at DATETIME
                )''')
    
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