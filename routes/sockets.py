from flask import session
from flask_socketio import emit, join_room, leave_room
from datetime import datetime
from models import get_db
from config import Config
import os
from werkzeug.utils import secure_filename

# Глобальный словарь для хранения статусов набора текста
typing_status = {}

def get_user_room(user_id):
    """Генерирует уникальное имя комнаты для пользователя"""
    return f"user_{user_id}"

def register_socket_handlers(socketio):
    """Регистрирует все обработчики событий Socket.IO"""
    
    @socketio.on('connect')
    def handle_connect():
        """Обработчик подключения пользователя"""
        if 'user_id' in session:
            user_id = session['user_id']
            join_room(get_user_room(user_id))
            print(f"Пользователь {user_id} подключился")
            
            # Обновляем статус онлайн в базе данных
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE users SET is_online = 1, last_seen = ? WHERE id = ?", 
                     (datetime.now(), user_id))
            conn.commit()
            conn.close()

    @socketio.on('disconnect')
    def handle_disconnect():
        """Обработчик отключения пользователя"""
        if 'user_id' in session:
            user_id = session['user_id']
            print(f"Пользователь {user_id} отключился")
            
            # Обновляем статус оффлайн в базе данных
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE users SET is_online = 0, last_seen = ? WHERE id = ?", 
                     (datetime.now(), user_id))
            conn.commit()
            conn.close()

    @socketio.on('join_chat')
    def handle_join_chat(data):
        """Обработчик присоединения к чату с конкретным пользователем"""
        if 'user_id' not in session:
            return
        
        friend_id = data.get('friend_id')
        if not friend_id:
            return
            
        user_id = session['user_id']
        
        # Создаем общую комнату для двух пользователей
        room_id = f"chat_{min(user_id, friend_id)}_{max(user_id, friend_id)}"
        join_room(room_id)
        print(f"Пользователь {user_id} присоединился к чату с {friend_id}")

    @socketio.on('send_message')
    def handle_send_message(data):
        """Обработчик отправки сообщения"""
        try:
            sender_id = session.get('user_id')
            if not sender_id:
                return
            
            receiver_id = data.get('receiver_id')
            content = data.get('content', '').strip()
            file_path = data.get('file_path')
            
            if not receiver_id or (not content and not file_path):
                return
            
            conn = get_db()
            c = conn.cursor()
            
            # Сохраняем сообщение в БД
            c.execute('''INSERT INTO messages (sender_id, receiver_id, content, file_path, timestamp)
                         VALUES (?, ?, ?, ?, ?)''',
                     (sender_id, receiver_id, content, file_path, datetime.now()))
            
            conn.commit()
            
            # Получаем информацию об отправителе
            c.execute("SELECT username, avatar FROM users WHERE id = ?", (sender_id,))
            sender_info = c.fetchone()
            
            # Отправляем сообщение получателю
            emit('receive_message', {
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'content': content,
                'file_path': file_path,
                'file_name': data.get('file_name'),
                'sender_name': sender_info['username'],
                'sender_avatar': sender_info['avatar'],
                'timestamp': datetime.now().strftime('%H:%M')
            }, room=get_user_room(receiver_id))
            
            # Также отправляем себе для синхронизации
            emit('receive_message', {
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'content': content,
                'file_path': file_path,
                'file_name': data.get('file_name'),
                'sender_name': sender_info['username'],
                'sender_avatar': sender_info['avatar'],
                'timestamp': datetime.now().strftime('%H:%M')
            }, room=get_user_room(sender_id))
            
        except Exception as e:
            print(f"Ошибка при отправке сообщения: {str(e)}")
        finally:
            conn.close()

    @socketio.on('typing')
    def handle_typing(data):
        """Обработчик статуса набора текста"""
        sender_id = session.get('user_id')
        receiver_id = data.get('receiver_id')
        
        if not sender_id or not receiver_id:
            return
        
        # Устанавливаем статус набора текста
        key = f"{sender_id}_{receiver_id}"
        typing_status[key] = True
        
        # Отправляем уведомление получателю
        emit('user_typing', {
            'sender_id': sender_id,
            'receiver_id': receiver_id
        }, room=get_user_room(receiver_id))
        
        # Сбрасываем статус через 3 секунды
        socketio.sleep(3)
        typing_status[key] = False

    @socketio.on('upload_file')
    def handle_upload_file(data):
        """Обработчик загрузки файла (альтернативный вариант)"""
        try:
            if 'user_id' not in session:
                return {'error': 'Unauthorized'}
                
            file_data = data.get('file_data')
            file_name = data.get('file_name')
            receiver_id = data.get('receiver_id')
            
            if not all([file_data, file_name, receiver_id]):
                return {'error': 'Invalid data'}
                
            # Проверка размера файла (15 МБ)
            if len(file_data) > 15 * 1024 * 1024:
                return {'error': 'File too large. Max 15MB'}
                
            # Генерация уникального имени файла
            safe_name = secure_filename(file_name)
            unique_name = f"{session['user_id']}_{receiver_id}_{int(datetime.now().timestamp())}_{safe_name}"
            file_path = os.path.join(Config.MESSAGE_FILES_FOLDER, unique_name)
            
            # Сохранение файла
            with open(file_path, 'wb') as f:
                f.write(file_data)
                
            return {
                'success': True,
                'file_path': unique_name,
                'original_name': file_name
            }
            
        except Exception as e:
            print(f"Ошибка при загрузке файла: {str(e)}")
            return {'error': 'File upload failed'}