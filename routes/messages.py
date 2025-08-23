from flask import Blueprint, render_template, session, jsonify, redirect, url_for, request, current_app
from models import get_db, allowed_file
from datetime import datetime
import os
from werkzeug.utils import secure_filename

bp = Blueprint('messages', __name__)

@bp.route('/messages')
@bp.route('/messages/<int:friend_id>')
def messages(friend_id=None):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Получаем текущего пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Получаем список друзей с информацией об онлайн-статусе
    c.execute('''SELECT users.id, users.username, users.avatar, users.is_online, users.last_seen 
                FROM friends 
                JOIN users ON friends.friend_id = users.id 
                WHERE friends.user_id = ? AND friends.status = 'accepted'
                UNION
                SELECT users.id, users.username, users.avatar, users.is_online, users.last_seen 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'accepted' 
                ORDER BY username''', (user_id, user_id))
    friends = c.fetchall()
    
    # Получаем историю сообщений если выбран друг
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
    return render_template('messages.html', 
                         user=user, 
                         friends=friends, 
                         messages=messages, 
                         friend_id=friend_id, 
                         active_friend=active_friend,
                         active_page='messages')

@bp.route('/api/messages/<int:friend_id>')
def get_messages(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    conn = get_db()
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
            'id': msg['id'],
            'sender_id': msg['sender_id'],
            'receiver_id': msg['receiver_id'],
            'content': msg['content'],
            'file_path': msg['file_path'],
            'timestamp': msg['timestamp'],
            'username': msg['username'],
            'avatar': msg['avatar']
        }
        
        # Добавляем имя файла, если есть путь к файлу
        if msg['file_path']:
            message_data['file_name'] = os.path.basename(msg['file_path'])
        
        formatted_messages.append(message_data)
    
    return jsonify(messages=formatted_messages)

@bp.route('/upload_message_file', methods=['POST'])
def upload_message_file():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    receiver_id = request.form.get('receiver_id')
    if not receiver_id:
        return jsonify({'error': 'No receiver specified'}), 400
        
    if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
        return jsonify({'error': 'File type not allowed'}), 400
        
    # Генерация уникального имени файла
    filename = secure_filename(file.filename)
    unique_filename = f"{session['user_id']}_{receiver_id}_{int(datetime.now().timestamp())}_{filename}"
    
    try:
        upload_folder = current_app.config['MESSAGE_FILES_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        # Сохраняем сообщение в БД
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO messages (sender_id, receiver_id, content, file_path) VALUES (?, ?, ?, ?)",
            (session['user_id'], receiver_id, '', unique_filename)
        )
        conn.commit()
        message_id = c.lastrowid
        conn.close()
        
        return jsonify({
            'success': True,
            'file_path': unique_filename,
            'original_name': filename,
            'message_id': message_id
        })
    except Exception as e:
        current_app.logger.error(f"File upload error: {str(e)}")
        return jsonify({'error': 'File upload failed'}), 500