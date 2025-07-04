from flask import Blueprint, render_template, session, jsonify
from models import get_db
from datetime import datetime

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
    
    # Получаем список друзей
    c.execute('''SELECT users.id, users.username, users.avatar 
                FROM friends 
                JOIN users ON friends.friend_id = users.id 
                WHERE friends.user_id = ? AND friends.status = 'accepted'
                UNION
                SELECT users.id, users.username, users.avatar 
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
                         active_friend=active_friend)

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
        formatted_messages.append({
            'id': msg['id'],
            'sender_id': msg['sender_id'],
            'receiver_id': msg['receiver_id'],
            'content': msg['content'],
            'file_path': msg['file_path'],
            'timestamp': msg['timestamp'],
            'username': msg['username'],
            'avatar': msg['avatar']
        })
    
    return jsonify(messages=formatted_messages)

@bp.route('/api/typing_status/<int:friend_id>')
def get_typing_status(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    key = f"{friend_id}_{user_id}"
    is_typing = typing_status.get(key, False)
    
    # Сбрасываем статус после проверки
    typing_status[key] = False
    
    return jsonify({'is_typing': is_typing})