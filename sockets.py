from flask import session
from flask_socketio import emit, join_room, leave_room
from models import get_db
import time
import os
import threading
import logging
from config import Config
from werkzeug.utils import secure_filename
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные словари для отслеживания
typing_status = {}
pending_calls = {}  # Для хранения входящих вызовов
active_calls = {}   # Для отслеживания активных звонков
# Дополнительно: быстрый доступ по паре собеседников для вычисления длительности
active_calls_by_pair = {}
socketio_ref = None  # Глобальная ссылка на socketio

def emit_to_user(event: str, data: dict, user_id: int):
    """Эмит события конкретному пользователю из других модулей."""
    try:
        if socketio_ref is not None:
            socketio_ref.emit(event, data, room=str(user_id))
    except Exception:
        logger.exception("emit_to_user failed")
user_pubkeys = {}   # Для хранения публичных ключей E2E по user_id

def register_socket_handlers(socketio):
    @socketio.on('connect')
    def handle_connect():
        """Обработчик подключения клиента"""
        if 'user_id' in session:
            user_id = session['user_id']
            join_room(str(user_id))
            logger.info(f"User {user_id} connected")
            emit('connection_response', {'status': 'connected'})

            # Обновляем онлайн-статус и last_seen
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute("UPDATE users SET is_online = 1, last_seen = ? WHERE id = ?", (datetime.now(), user_id))
                conn.commit()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            # Широковещательный статус
            emit('user_status', {
                'user_id': user_id,
                'is_online': True,
                'last_seen': datetime.now().isoformat()
            }, broadcast=True)

    @socketio.on('disconnect')
    def handle_disconnect():
        """Обработчик отключения клиента"""
        if 'user_id' in session:
            user_id = session['user_id']
            leave_room(str(user_id))
            logger.info(f"User {user_id} disconnected")
            
            # Завершаем активные и ожидающие звонки при отключении (перезагрузке/закрытии)
            for call_id, call_data in list(active_calls.items()):
                if call_data['caller_id'] == user_id or call_data['receiver_id'] == user_id:
                    other_user = call_data['receiver_id'] if call_data['caller_id'] == user_id else call_data['caller_id']
                    emit('webrtc_end_call', {
                        'sender_id': user_id,
                        'reason': 'User disconnected'
                    }, room=str(other_user))
                    del active_calls[call_id]
                    logger.info(f"Call {call_id} ended due to user disconnect")
            for call_id, call_data in list(pending_calls.items()):
                if call_data['caller_id'] == user_id or call_data['receiver_id'] == user_id:
                    other_user = call_data['receiver_id'] if call_data['caller_id'] == user_id else call_data['caller_id']
                    emit('webrtc_end_call', {
                        'sender_id': user_id,
                        'reason': 'User disconnected'
                    }, room=str(other_user))
                    del pending_calls[call_id]
                    logger.info(f"Pending call {call_id} cleared due to user disconnect")
            # Снимаем занятость пары (на случай перезагрузки страницы)
            for key, data in list(active_calls_by_pair.items()):
                if data.get('a') == user_id or data.get('b') == user_id:
                    del active_calls_by_pair[key]
                    logger.info(f"Active pair {key} cleared due to user disconnect")

            # Обновляем оффлайн-статус и last_seen
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute("UPDATE users SET is_online = 0, last_seen = ? WHERE id = ?", (datetime.now(), user_id))
                conn.commit()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            # Широковещательный статус
            emit('user_status', {
                'user_id': user_id,
                'is_online': False,
                'last_seen': datetime.now().isoformat()
            }, broadcast=True)

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
        logger.info(f"User {user_id} joined chat room {room_id}")

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
            message_id = c.lastrowid

            # Получаем данные отправителя
            c.execute("SELECT username, avatar FROM users WHERE id = ?", (sender_id,))
            sender_data = c.fetchone()
        finally:
            conn.close()

        # Формируем данные сообщения
        message_data = {
            'id': message_id,
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
        # Глобальное уведомление о новом сообщении (для всех разделов, подписанных по user room)
        emit('global_notification', {
            'type': 'message',
            'from_user_id': sender_id,
            'to_user_id': receiver_id,
            'preview': content or (file_name or 'Файл')
        }, room=str(receiver_id))
        logger.info(f"Message sent from {sender_id} to {receiver_id}")

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
    
    # Функция для очистки устаревших вызовов
    def cleanup_pending_calls():
        """Очистка устаревших вызовов"""
        current_time = time.time()
        to_remove = []
        for call_id, call_data in pending_calls.items():
            if current_time - call_data['timestamp'] > 30:  # 30 секунд таймаут
                to_remove.append(call_id)
        
        for call_id in to_remove:
            # Уведомляем участников о таймауте
            call_data = pending_calls[call_id]
            emit('call_timeout', {
                'call_id': call_id,
                'caller_id': call_data['caller_id']
            }, room=str(call_data['receiver_id']))
            emit('call_timeout', {
                'call_id': call_id,
                'receiver_id': call_data['receiver_id']
            }, room=str(call_data['caller_id']))
            if call_id in pending_calls:
                del pending_calls[call_id]
                logger.info(f"Call {call_id} timeout and removed")
    
    # Запускаем очистку каждые 30 секунд
    def start_cleanup_thread():
        while True:
            time.sleep(30)
            cleanup_pending_calls()
    
    # Запускаем поток очистки в фоновом режиме
    cleanup_thread = threading.Thread(target=start_cleanup_thread)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    # Авторазбан по истечению срока
    def start_bans_thread():
        while True:
            try:
                conn = get_db(); c = conn.cursor()
                now = datetime.now()
                c.execute("SELECT id, user_id FROM bans WHERE until <= ?", (now,))
                rows = c.fetchall()
                for row in rows:
                    uid = row['user_id']
                    # снимаем блокировку
                    c.execute("UPDATE users SET is_blocked=0, block_reason=NULL WHERE id=?", (uid,))
                    c.execute("DELETE FROM bans WHERE id=?", (row['id'],))
                    conn.commit()
                    # уведомляем пользователя, если онлайн
                    emit_to_user('account_unblocked', {}, uid)
                conn.close()
            except Exception:
                logger.exception('bans cleanup failed')
            finally:
                import time as _t; _t.sleep(60)
    bans_thread = threading.Thread(target=start_bans_thread)
    bans_thread.daemon = True
    bans_thread.start()
    global socketio_ref
    socketio_ref = socketio
    
    # WebRTC обработчики для звонков
    @socketio.on('call_request')
    def handle_call_request(data):
        """Обработчик запроса звонка (запрос разрешения)"""
        if 'user_id' not in session:
            return
        
        caller_id = session['user_id']
        receiver_id = data.get('receiver_id')
        
        if not all([caller_id, receiver_id]):
            return
        
        # Проверяем, есть ли уже активный вызов для этого пользователя
        for call_id, call_data in pending_calls.items():
            if call_data['receiver_id'] == receiver_id:
                emit('call_error', {
                    'error': 'У пользователя уже есть активный вызов',
                    'receiver_id': receiver_id
                }, room=str(caller_id))
                return
        
        # Сохраняем информацию о вызове
        call_id = f"{caller_id}_{receiver_id}_{int(time.time())}"
        pending_calls[call_id] = {
            'caller_id': caller_id,
            'receiver_id': receiver_id,
            'timestamp': time.time()
        }
        
        # Отправляем запрос разрешения получателю
        emit('incoming_call', {
            'call_id': call_id,
            'caller_id': caller_id
        }, room=str(receiver_id))
        
        # Отправляем подтверждение инициатору вызова
        emit('call_initiated', {
            'call_id': call_id,
            'receiver_id': receiver_id
        }, room=str(caller_id))
        logger.info(f"Call request from {caller_id} to {receiver_id}, call_id: {call_id}")

    @socketio.on('call_response')
    def handle_call_response(data):
        """Обработчик ответа на вызов"""
        if 'user_id' not in session:
            return
            
        call_id = data.get('call_id')
        accepted = data.get('accepted')
        error_type = data.get('error_type')  # Новое поле: тип ошибки
        
        if not call_id or call_id not in pending_calls:
            return
            
        call_data = pending_calls[call_id]
        caller_id = call_data['caller_id']
        receiver_id = call_data['receiver_id']
        
        # Проверяем, что ответ отправляет именно получатель вызова
        if session['user_id'] != receiver_id:
            return
        
        if accepted:
            # Добавляем вызов в активные
            active_calls[call_id] = {
                'caller_id': caller_id,
                'receiver_id': receiver_id,
                'start_time': time.time()
            }
            
            # Уведомляем звонящего о принятии вызова
            emit('call_accepted', {
                'call_id': call_id,
                'receiver_id': receiver_id
            }, room=str(caller_id))
            logger.info(f"Call {call_id} accepted by {receiver_id}")
        else:
            # Определяем причину отклонения
            error_message = "Вызов отклонен"
            if error_type == "media_permission":
                error_message = "Не удалось получить доступ к медиаустройствам"
            elif error_type == "user_busy":
                error_message = "Пользователь занят"
            
            # Уведомляем об отклонении вызова
            emit('call_declined', {
                'call_id': call_id,
                'receiver_id': receiver_id,
                'reason': error_message
            }, room=str(caller_id))
            logger.info(f"Call {call_id} declined by {receiver_id}, reason: {error_message}")
            
        # Удаляем вызов из ожидания
        if call_id in pending_calls:
            del pending_calls[call_id]

    @socketio.on('call_error')
    def handle_call_error(data):
        """Обработчик ошибок при звонке"""
        if 'user_id' not in session:
            return
        
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        error_msg = data.get('error')
        error_type = data.get('error_type', 'unknown')
        
        if not all([sender_id, receiver_id, error_msg]):
            return
        
        # Уведомляем получателя об ошибке
        emit('call_error', {
            'error': error_msg,
            'error_type': error_type,
            'sender_id': sender_id
        }, room=str(receiver_id))
        
        # Очищаем pending_calls если есть соответствующий вызов
        for call_id, call_data in list(pending_calls.items()):
            if (call_data['caller_id'] == sender_id and 
                call_data['receiver_id'] == receiver_id):
                if call_id in pending_calls:
                    del pending_calls[call_id]
                    logger.info(f"Call {call_id} removed due to error: {error_msg}")

    @socketio.on('webrtc_offer')
    def handle_webrtc_offer(data):
        """Обработчик предложения WebRTC (после принятия вызова)"""
        if 'user_id' not in session:
            return
        
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        offer = data.get('offer')
        
        if not all([sender_id, receiver_id, offer]):
            return
        
        # Если один из пользователей уже в активном звонке — отклоняем как "занят"
        try:
            def _is_busy(uid:int)->bool:
                for _k,_d in active_calls_by_pair.items():
                    if _d.get('a') == uid or _d.get('b') == uid:
                        return True
                return False
            if _is_busy(receiver_id) or _is_busy(sender_id):
                busy_uid = receiver_id if _is_busy(receiver_id) else sender_id
                emit('call_busy', { 'receiver_id': receiver_id, 'busy_user_id': busy_uid }, room=str(sender_id))
                logger.info(f"Rejecting offer from {sender_id} to {receiver_id}: busy")
                return
        except Exception:
            logger.exception('busy-check failed')
        
        # Пересылаем предложение получателю с именем и аватаром звонящего
        try:
            conn = get_db(); c = conn.cursor()
            c.execute("SELECT username, avatar FROM users WHERE id = ?", (sender_id,))
            row = c.fetchone(); conn.close()
            sender_username = row['username'] if row else ''
            sender_avatar = row['avatar'] if row else None
        except Exception:
            sender_username = ''
            sender_avatar = None

        emit('webrtc_offer', {
            'offer': offer,
            'sender_id': sender_id,
            'sender_username': sender_username,
            'sender_avatar': sender_avatar
        }, room=str(receiver_id))
        logger.info(f"WebRTC offer sent from {sender_id} to {receiver_id}")
    
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
        logger.info(f"WebRTC answer sent from {sender_id} to {receiver_id}")
        # Зафиксируем старт звонка для дальнейшего логирования длительности
        try:
            key = (min(sender_id, receiver_id), max(sender_id, receiver_id))
            active_calls_by_pair[key] = { 'start_time': time.time(), 'a': sender_id, 'b': receiver_id }
            # Системное сообщение о начале звонка
            conn = get_db(); c = conn.cursor()
            content = '[call] started'
            c.execute(
                "INSERT INTO messages (sender_id, receiver_id, content, file_path) VALUES (?, ?, ?, ?)",
                (sender_id, receiver_id, content, None)
            )
            conn.commit()
            msg_id = c.lastrowid
            c.execute("SELECT username, avatar FROM users WHERE id = ?", (sender_id,))
            srow = c.fetchone(); conn.close()
            room_id = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
            emit('receive_message', {
                'id': msg_id,
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'content': content,
                'file_path': None,
                'file_name': None,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'username': srow['username'] if srow else '',
                'avatar': srow['avatar'] if srow else None
            }, room=room_id)
        except Exception:
            logger.exception('failed to log call start')
    
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
        logger.info(f"WebRTC ICE candidate sent from {sender_id} to {receiver_id}")
    
    @socketio.on('webrtc_end_call')
    def handle_webrtc_end_call(data):
        """Обработчик завершения звонка"""
        if 'user_id' not in session:
            return
        
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        reason = data.get('reason', 'Call ended')
        
        if not all([sender_id, receiver_id]):
            return
        
        # Уведомляем получателя о завершении звонка
        emit('webrtc_end_call', {
            'sender_id': sender_id,
            'reason': reason
        }, room=str(receiver_id))
        logger.info(f"WebRTC call ended by {sender_id}, reason: {reason}")

        # Попытка залогировать завершение звонка как системное сообщение с длительностью
        try:
            key = (min(sender_id, receiver_id), max(sender_id, receiver_id))
            started = active_calls_by_pair.get(key, {}).get('start_time')
            duration_sec = int(time.time() - started) if started else None
            if key in active_calls_by_pair:
                del active_calls_by_pair[key]
            conn = get_db(); c = conn.cursor()
            content = '[call] ended' + (f'|duration={duration_sec}' if duration_sec is not None else '')
            c.execute(
                "INSERT INTO messages (sender_id, receiver_id, content, file_path) VALUES (?, ?, ?, ?)",
                (sender_id, receiver_id, content, None)
            )
            conn.commit()
            message_id = c.lastrowid
            c.execute("SELECT username, avatar FROM users WHERE id = ?", (sender_id,))
            sender_data = c.fetchone(); conn.close()
            room_id = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
            emit('receive_message', {
                'id': message_id,
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'content': content,
                'file_path': None,
                'file_name': None,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'username': sender_data['username'] if sender_data else '',
                'avatar': sender_data['avatar'] if sender_data else None
            }, room=room_id)
        except Exception:
            logger.exception('failed to log call end message')
        
        # Очищаем active_calls и pending_calls если есть соответствующий вызов
        for call_id, call_data in list(active_calls.items()):
            if (call_data['caller_id'] == sender_id and 
                call_data['receiver_id'] == receiver_id) or \
               (call_data['caller_id'] == receiver_id and 
                call_data['receiver_id'] == sender_id):
                if call_id in active_calls:
                    del active_calls[call_id]
                    logger.info(f"Active call {call_id} removed")
        
        for call_id, call_data in list(pending_calls.items()):
            if (call_data['caller_id'] == sender_id and 
                call_data['receiver_id'] == receiver_id) or \
               (call_data['caller_id'] == receiver_id and 
                call_data['receiver_id'] == sender_id):
                if call_id in pending_calls:
                    del pending_calls[call_id]
                    logger.info(f"Pending call {call_id} removed")

    # E2E: обмен публичными ключами (ECDH)
    @socketio.on('e2e_pubkey')
    def handle_e2e_pubkey(data):
        """Получаем публичный ключ отправителя и отдаем получателю"""
        if 'user_id' not in session:
            return
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        pubkey = data.get('pubkey')
        if not receiver_id or not pubkey:
            return
        # Сохраняем последний публичный ключ пользователя
        user_pubkeys[sender_id] = pubkey
        # Пересылаем ключ собеседнику
        emit('e2e_peer_pubkey', {
            'sender_id': sender_id,
            'pubkey': pubkey
        }, room=str(receiver_id))

    @socketio.on('e2e_request_pubkey')
    def handle_e2e_request_pubkey(data):
        """По запросу отправляем известный публичный ключ пользователя"""
        if 'user_id' not in session:
            return
        requester_id = session['user_id']
        target_user_id = data.get('user_id')
        if not target_user_id:
            return
        pubkey = user_pubkeys.get(target_user_id)
        if pubkey:
            emit('e2e_peer_pubkey', {
                'sender_id': target_user_id,
                'pubkey': pubkey
            }, room=str(requester_id))

    # Событие mute/unmute микрофона
    @socketio.on('webrtc_toggle_mute')
    def handle_webrtc_toggle_mute(data):
        """Ретрансляция статуса mute/unmute собеседнику"""
        if 'user_id' not in session:
            return
        sender_id = session['user_id']
        receiver_id = data.get('receiver_id')
        muted = data.get('muted', False)
        if not receiver_id:
            return
        emit('webrtc_peer_mute', {
            'sender_id': sender_id,
            'muted': bool(muted)
        }, room=str(receiver_id))

    # Запрос на повторную отправку оффера (когда принимающий только что перешёл в чат)
    @socketio.on('request_resend_offer')
    def handle_request_resend_offer(data):
        if 'user_id' not in session:
            return
        target_sender_id = data.get('sender_id')
        if not target_sender_id:
            return
        # Пересылаем запрос инициатору звонка
        emit('resend_offer', { 'from_user_id': session['user_id'] }, room=str(target_sender_id))

    # Добавляем новый обработчик для диагностики медиаустройств
    @socketio.on('media_devices_status')
    def handle_media_devices_status(data):
        """Обработчик статуса медиаустройств"""
        if 'user_id' not in session:
            return
        
        user_id = session['user_id']
        has_audio = data.get('has_audio', False)
        has_video = data.get('has_video', False)
        devices = data.get('devices', [])
        
        logger.info(f"User {user_id} media devices status - Audio: {has_audio}, Video: {has_video}, Devices: {devices}")
        
        # Отправляем подтверждение клиенту
        emit('media_devices_status_received', {
            'status': 'success',
            'has_audio': has_audio,
            'has_video': has_video
        })