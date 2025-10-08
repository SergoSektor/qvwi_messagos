from flask import Blueprint, send_from_directory, session, redirect, url_for, abort
from config import Config
import os
from models import get_db
from werkzeug.utils import secure_filename

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

@bp.route('/message_files/<path:filename>')
def message_file(filename):
    """Отдача файлов сообщений с проверкой: файл должен принадлежать диалогу пользователя"""
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))

    # Нормализуем имя, чтобы не допустить экзотических путей
    safe_name = secure_filename(filename)
    if not safe_name:
        abort(404)

    # Проверяем, что файл есть в сообщениях текущего пользователя (отправителя или получателя)
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT 1 FROM messages 
        WHERE file_path = ? AND (sender_id = ? OR receiver_id = ?) 
        LIMIT 1
    """, (safe_name, session['user_id'], session['user_id']))
    row = c.fetchone(); conn.close()
    if not row:
        abort(403)

    return send_from_directory(Config.MESSAGE_FILES_FOLDER, safe_name, as_attachment=True)

@bp.route('/download/<path:filename>')
def download_file(filename):
    """Скачивание файлов сообщений с проверкой доступа (тот же механизм, что и выше)"""
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))

    safe_name = secure_filename(filename)
    if not safe_name:
        abort(404)

    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT 1 FROM messages 
        WHERE file_path = ? AND (sender_id = ? OR receiver_id = ?)
        LIMIT 1
    """, (safe_name, session['user_id'], session['user_id']))
    row = c.fetchone(); conn.close()
    if not row:
        abort(403)

    return send_from_directory(Config.MESSAGE_FILES_FOLDER, safe_name, as_attachment=True)

@bp.route('/logout')
def logout():
    """Выход из системы с очисткой сессии"""
    session.clear()
    return redirect(url_for('auth.index'))