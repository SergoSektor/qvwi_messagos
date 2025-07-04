import os

class Config:
    SECRET_KEY = 'super_secret_key_123!'
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB
    MESSAGE_FILES_FOLDER = 'static/message_files'
    DATABASE = 'social_network.db'