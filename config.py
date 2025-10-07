import os

class Config:
    SECRET_KEY = 'super_secret_key_123!'
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB
    MESSAGE_FILES_FOLDER = 'static/message_files'
    MUSIC_FOLDER = 'static/music'
    ALLOWED_AUDIO = {'mp3', 'wav', 'ogg', 'm4a'}
    DATABASE = 'social_network.db'
    # Настройки TURN из переменных окружения (необязательно)
    TURN_URL = os.getenv('TURN_URL', '')
    TURN_USERNAME = os.getenv('TURN_USERNAME', '')
    TURN_PASSWORD = os.getenv('TURN_PASSWORD', '')