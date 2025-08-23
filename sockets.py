from flask import session
from flask_socketio import emit, join_room, leave_room
from models import get_db
import time
import os
from config import Config
from werkzeug.utils import secure_filename
from flask_socketio import emit, join_room, leave_room


# Глобальный словарь для отслеживания набора текста
typing_status = {}

def register_socket_handlers(socketio):
    @socketio.on('connect')
    def handle_connect():
        """Обработчик подключения клиента"""
        if 'user_id' in session:
            join_room(str(session['user_id']))
            emit('connection_response', {'status': 'connected'})

    @socketio.on('disconnect')
    def handle_disconnect():
        """Обработчик отключения клиента"""
        if 'user_id' in session:
            leave_room(str(session['user_id']))

    @socketio.on('join_chat')
    def handle_join_chat(data):
        """Присоединение к чату с конкретным пользователем"""
        if 'user_id' not in session:
            return
        
        user_id = session['user_id']
        friend_id = data.get('friend_id')
        
        if not friend_id:
            return

        # Создаем уникальный ID комнаты (упорядоченный)
        room_id = f"{min(user_id, friend_id)}_{max(user_id, friend_id)}"
        join_room(room_id)
        emit('join_response', {'room': room_id, 'status': 'success'})

    @socketio.on('send_message')
    def handle_send_message(data):
        """Обработчик отправки сообщения"""
        if 'user_id' not in session:
            return

        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        content = data.get('content')
        file_data = data.get('file')

        if not all([sender_id, receiver_id, content]):
            return

        # Обработка прикрепленного файла
        file_path = None
        file_name = None
        if file_data:
            try:
                # Проверка размера файла
                if len(file_data['data']) > Config.MAX_CONTENT_LENGTH:
                    emit('file_error', {'error': 'File size exceeds limit'})
                    return

                # Сохранение файла
                filename = secure_filename(f"{int(time.time())}_{file_data['filename']}")
                file_path = os.path.join(Config.MESSAGE_FILES_FOLDER, filename)
                file_name = file_data['filename']
                
                os.makedirs(Config.MESSAGE_FILES_FOLDER, exist_ok=True)
                with open(file_path, 'wb') as f:
                    f.write(file_data['data'])
            except Exception as e:
                emit('file_error', {'error': str(e)})
                return

        # Сохранение сообщения в БД
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO messages (sender_id, receiver_id, content, file_path) VALUES (?, ?, ?, ?)",
                (sender_id, receiver_id, content, file_path)
            )
            conn.commit()

            # Получаем данные отправителя
            c.execute("SELECT username, avatar FROM users WHERE id = ?", (sender_id,))
            sender_data = c.fetchone()
        finally:
            conn.close()

        # Формируем данные сообщения
        message_data = {
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'content': content,
            'file_path': file_path,
            'file_name': file_name,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'username': sender_data['username'],
            'avatar': sender_data['avatar']
        }

        # Отправка сообщения в комнату чата
        room_id = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
        emit('receive_message', message_data, room=room_id)

    @socketio.on('typing')
    def handle_typing(data):
        """Обработчик индикатора набора текста"""
        if 'user_id' not in session:
            return

        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')

        if not receiver_id:
            return

        # Устанавливаем статус набора текста
        key = f"{sender_id}_{receiver_id}"
        typing_status[key] = True

        # Отправляем уведомление
        room_id = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
        emit('user_typing', {'sender_id': sender_id}, room=room_id)
    
    # WebRTC обработчики для звонков
    @socketio.on('webrtc_offer')
    def handle_webrtc_offer(data):
        """Обработчик предложения WebRTC"""
        if 'user_id' not in session:
            return
        
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        offer = data.get('offer')
        
        if not all([sender_id, receiver_id, offer]):
            return
        
        # Пересылаем предложение получателю
        emit('webrtc_offer', {
            'offer': offer,
            'sender_id': sender_id
        }, room=str(receiver_id))
    
    @socketio.on('webrtc_answer')
    def handle_webrtc_answer(data):
        """Обработчик ответа WebRTC"""
        if 'user_id' not in session:
            return
        
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        answer = data.get('answer')
        
        if not all([sender_id, receiver_id, answer]):
            return
        
        # Пересылаем ответ инициатору звонка
        emit('webrtc_answer', {
            'answer': answer,
            'sender_id': sender_id
        }, room=str(receiver_id))
    
    @socketio.on('webrtc_ice_candidate')
    def handle_webrtc_ice_candidate(data):
        """Обработчик ICE кандидата WebRTC"""
        if 'user_id' not in session:
            return
        
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        candidate = data.get('candidate')
        
        if not all([sender_id, receiver_id, candidate]):
            return
        
        # Пересылаем ICE кандидат
        emit('webrtc_ice_candidate', {
            'candidate': candidate,
            'sender_id': sender_id
        }, room=str(receiver_id))
    
    @socketio.on('webrtc_end_call')
    def handle_webrtc_end_call(data):
        """Обработчик завершения звонка"""
        if 'user_id' not in session:
            return
        
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        
        if not all([sender_id, receiver_id]):
            return
        
        # Уведомляем получателя о завершении звонка
        emit('webrtc_end_call', {
            'sender_id': sender_id
        }, room=str(receiver_id))
    