import os

class Config:
    # Секретный ключ: берем из переменных окружения, чтобы не хранить в коде
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-in-env')
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB
    MESSAGE_FILES_FOLDER = 'static/message_files'
    MUSIC_FOLDER = 'static/music'
    ALLOWED_AUDIO = {'mp3', 'wav', 'ogg', 'm4a'}
    DATABASE = 'social_network.db'

    # Безопасность cookie сессии
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = True

    # CORS для Socket.IO: по умолчанию только same-origin (None)
    CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS')  # например: "https://example.com,https://admin.example.com"
    # Настройки TURN из переменных окружения (необязательно)
    TURN_URL = os.getenv('TURN_URL', '')
    TURN_USERNAME = os.getenv('TURN_USERNAME', '')
    TURN_PASSWORD = os.getenv('TURN_PASSWORD', '')