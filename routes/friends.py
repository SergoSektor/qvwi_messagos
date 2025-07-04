from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from models import get_db

bp = Blueprint('friends', __name__)

@bp.route('/friends', methods=['GET'])
def friends():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Получаем текущего пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Запросы в друзья (входящие)
    c.execute('''SELECT users.id, users.username, users.avatar 
                FROM friends 
                JOIN users ON friends.user_id = users.id 
                WHERE friends.friend_id = ? AND friends.status = 'pending' ''', (user_id,))
    requests = c.fetchall()
    
    # Список друзей (взаимные)
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
    friends_list = c.fetchall()
    
    # Поиск пользователей
    search_query = request.args.get('search', '')
    search_results = []
    if search_query:
        c.execute("SELECT id, username, avatar FROM users WHERE username LIKE ? AND id != ?", 
                 (f'%{search_query}%', user_id))
        search_results = c.fetchall()
    
    conn.close()
    
    return render_template('friends.html', 
                         user=user, 
                         requests=requests, 
                         friends=friends_list, 
                         search_results=search_results,
                         search_query=search_query)

@bp.route('/add_friend/<int:friend_id>')
def add_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Проверяем, не существует ли уже запроса
        c.execute("SELECT * FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)", 
                 (user_id, friend_id, friend_id, user_id))
        existing = c.fetchone()
        
        if not existing:
            c.execute("INSERT INTO friends (user_id, friend_id, status) VALUES (?, ?, 'pending')", 
                     (user_id, friend_id))
            conn.commit()
            flash('Запрос в друзья отправлен!')
        else:
            status = existing['status'] if existing else None
            if status == 'pending':
                flash('Запрос уже отправлен и ожидает подтверждения')
            elif status == 'accepted':
                flash('Вы уже друзья с этим пользователем')
    except Exception as e:
        flash(f'Ошибка при отправке запроса: {str(e)}')
    finally:
        conn.close()
    
    return redirect(url_for('friends.friends'))

@bp.route('/accept_friend/<int:friend_id>')
def accept_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Проверяем существование запроса
        c.execute("SELECT * FROM friends WHERE user_id = ? AND friend_id = ? AND status = 'pending'", 
                 (friend_id, user_id))
        request_exists = c.fetchone()
        
        if request_exists:
            # Принимаем запрос в друзья
            c.execute("UPDATE friends SET status = 'accepted' WHERE user_id = ? AND friend_id = ?", 
                     (friend_id, user_id))
            conn.commit()
            flash('Запрос в друзья принят!')
        else:
            flash('Запрос в друзья не найден или уже был обработан')
    except Exception as e:
        flash(f'Ошибка при принятии запроса: {str(e)}')
    finally:
        conn.close()
    
    return redirect(url_for('friends.friends'))

@bp.route('/remove_friend/<int:friend_id>')
def remove_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Удаляем из друзей (вне зависимости от статуса)
        c.execute("DELETE FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)", 
                 (user_id, friend_id, friend_id, user_id))
        conn.commit()
        flash('Пользователь удален из друзей')
    except Exception as e:
        flash(f'Ошибка при удалении из друзей: {str(e)}')
    finally:
        conn.close()
    
    return redirect(url_for('friends.friends'))