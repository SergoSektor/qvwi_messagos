from flask import Blueprint, send_from_directory, session, redirect, url_for
from config import Config
import os

bp = Blueprint('static', __name__)

@bp.route('/static/<path:filename>')
def static_files(filename):
    """Обработка статических файлов (CSS, JS, изображения)"""
    return send_from_directory('static', filename)

@bp.route('/uploads/<filename>')
def uploaded_file(filename):
    """Отдача загруженных файлов из папки uploads"""
    # Проверка аутентификации
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    return send_from_directory(Config.UPLOAD_FOLDER, filename)

@bp.route('/message_files/<filename>')
def message_file(filename):
    """Отдача файлов сообщений с проверкой прав доступа"""
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    # Здесь можно добавить дополнительную проверку прав доступа к файлу
    return send_from_directory(Config.MESSAGE_FILES_FOLDER, filename, as_attachment=True)

@bp.route('/download/<path:filename>')
def download_file(filename):
    """Скачивание файлов с проверкой аутентификации"""
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    return send_from_directory(Config.MESSAGE_FILES_FOLDER, filename, as_attachment=True)

@bp.route('/logout')
def logout():
    """Выход из системы с очисткой сессии"""
    session.clear()
    return redirect(url_for('auth.index'))