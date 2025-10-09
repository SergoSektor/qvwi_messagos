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

    # Карта последних сообщений (prev: текст превью, time: время)
    last_map = {}
    try:
        # Вытащим все сообщения текущего пользователя и возьмём по одному последнему на собеседника
        c.execute('''SELECT sender_id, receiver_id, content, file_path, timestamp
                     FROM messages
                     WHERE sender_id = ? OR receiver_id = ?
                     ORDER BY timestamp DESC''', (user_id, user_id))
        rows = c.fetchall()
        def make_preview(content, file_path):
            if file_path:
                import os as _os
                name = _os.path.basename(file_path)
                ext = (name.rsplit('.', 1)[-1] or '').lower()
                if ext in ('jpg','jpeg','png','gif','webp','bmp'):
                    return 'Фото'
                if ext in ('mp3','wav','ogg','flac'):
                    return 'Аудио'
                if ext in ('mp4','webm','mov','mkv'):
                    return 'Видео'
                if ext in ('zip','rar','7z','gz','bz2'):
                    return 'Архив'
                return 'Файл'
            if not content:
                return 'Сообщение'
            if isinstance(content, bytes):
                content = content.decode('utf-8', 'ignore')
            text = str(content)
            if text.startswith('[call]'):
                return 'Звонок'
            if text.startswith('enc:'):
                return 'Сообщение'
            # Обрезаем длинные
            if len(text) > 42:
                text = text[:39] + '…'
            return text
        for r in rows:
            sid, rid, cont, fpath, ts = r
            fid = rid if sid == user_id else sid
            if fid in last_map:
                continue
            # epoch
            epoch = None
            try:
                from datetime import datetime as _dt
                try:
                    epoch = int(_dt.strptime(ts.split('.')[0], '%Y-%m-%d %H:%M:%S').timestamp())
                except Exception:
                    epoch = int(_dt.fromisoformat(ts).timestamp())
            except Exception:
                epoch = 0
            last_map[fid] = {'preview': make_preview(cont, fpath), 'time': ts, 'epoch': epoch}
    except Exception:
        last_map = {}
    
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
                         last_map=last_map,
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
        
    # CSRF для AJAX: берём из заголовка/поля формы (прошёл общий before_request)
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    receiver_id = request.form.get('receiver_id')
    if not receiver_id:
        return jsonify({'error': 'No receiver specified'}), 400
    # Текст к файлу (если отправлен)
    content_text = request.form.get('content', '')
        
    # Разрешаем любые типы файлов (ограничение только по размеру через MAX_CONTENT_LENGTH)
        
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
            (session['user_id'], receiver_id, content_text or '', unique_filename)
        )
        conn.commit()
        message_id = c.lastrowid
        # Получим данные отправителя (для клиента может пригодиться)
        c.execute("SELECT username, avatar FROM users WHERE id = ?", (session['user_id'],))
        sender = c.fetchone()
        conn.close()

        # Отправляем событие через сокеты обоим участникам чата
        try:
            from app import socketio
            sender_id = session['user_id']
            room_id = f"{min(int(sender_id), int(receiver_id))}_{max(int(sender_id), int(receiver_id))}"
            socketio.emit('receive_message', {
                'id': message_id,
                'sender_id': sender_id,
                'receiver_id': int(receiver_id),
                'content': '',
                'file_path': unique_filename,
                'file_name': filename,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'username': sender['username'] if sender else '',
                'avatar': sender['avatar'] if sender else ''
            }, room=room_id)
        except Exception:
            # Если сокеты недоступны, просто продолжим — клиент подтянет по API
            pass
        
        return jsonify({
            'success': True,
            'file_path': unique_filename,
            'original_name': filename,
            'message_id': message_id
        })
    except Exception as e:
        current_app.logger.error(f"File upload error: {str(e)}")
        return jsonify({'error': 'File upload failed'}), 500


@bp.route('/api/messages/delete', methods=['POST'])
def delete_message():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    msg_id = request.form.get('message_id') or request.json.get('message_id') if request.is_json else None
    if not msg_id:
        return jsonify({'success': False, 'error': 'message_id required'}), 400
    try:
        msg_id = int(msg_id)
    except Exception:
        return jsonify({'success': False, 'error': 'bad id'}), 400
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT sender_id, receiver_id FROM messages WHERE id=?', (msg_id,))
    row = c.fetchone()
    if not row:
        conn.close(); return jsonify({'success': False, 'error': 'not found'}), 404
    if row['sender_id'] != session['user_id']:
        conn.close(); return jsonify({'success': False, 'error': 'forbidden'}), 403
    # Мягкое удаление: очищаем файл и ставим специальный контент
    c.execute('UPDATE messages SET content=?, file_path=NULL WHERE id=?', ('[deleted]', msg_id))
    conn.commit()
    sender_id = row['sender_id']; receiver_id = row['receiver_id']
    conn.close()
    # Оповестим собеседников через сокет
    try:
        from app import socketio
        room_id = f"{min(int(sender_id), int(receiver_id))}_{max(int(sender_id), int(receiver_id))}"
        socketio.emit('message_deleted', { 'id': msg_id }, room=room_id)
    except Exception:
        pass
    return jsonify({'success': True})