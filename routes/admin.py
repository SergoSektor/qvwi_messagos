from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from models import get_db
from config import Config
import os
from datetime import datetime
import sqlite3
from sockets import emit_to_user

bp = Blueprint('admin', __name__)

@bp.route('/admin')
def admin():
    # Проверяем, вошел ли пользователь
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Получаем текущего пользователя
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    # Проверяем, является ли пользователь администратором
    if not user or user['role'] != 'admin':
        return redirect(url_for('feed.feed'))
    
    # Получаем статистику
    c.execute("SELECT COUNT(*) FROM users")
    users_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM posts")
    posts_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages")
    messages_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admins_count = c.fetchone()[0]
    
    # Получаем список всех пользователей
    c.execute("SELECT id, username, email, bio, avatar, role, is_online, last_seen, is_blocked, block_reason FROM users")
    users = c.fetchall()

    # Настройки регистрации
    c.execute("SELECT key, value FROM settings")
    settings = {row['key']: row['value'] for row in c.fetchall()}

    # Открытые жалобы для вкладки "Модерация контента"
    c.execute("SELECT id, target_type, target_id, reason, created_at FROM reports WHERE status='open' ORDER BY created_at DESC")
    reports = c.fetchall()

    # Открытые жалобы на музыку
    c.execute('''SELECT mr.id, mr.track_id, mr.reason, mr.created_at, m.title, m.filename, u.username
                 FROM music_reports mr JOIN music m ON mr.track_id=m.id JOIN users u ON mr.reporter_id=u.id
                 WHERE mr.status='open' ORDER BY mr.created_at DESC''')
    music_reports = c.fetchall()
    
    conn.close()
    
    return render_template('admin.html', 
                           user=user, 
                           users_count=users_count,
                           posts_count=posts_count,
                           messages_count=messages_count,
                           admins_count=admins_count,
                           users=users,
                           settings=settings,
                           reports=reports,
                           music_reports=music_reports)

@bp.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    current_user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем, является ли текущий пользователь администратором
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    current_user_role = c.fetchone()['role']
    if current_user_role != 'admin':
        return redirect(url_for('feed.feed'))
    
    # Удаляем пользователя
    try:
        # Удаляем связанные записи
        c.execute("DELETE FROM friends WHERE user_id = ? OR friend_id = ?", (user_id, user_id))
        c.execute("DELETE FROM messages WHERE sender_id = ? OR receiver_id = ?", (user_id, user_id))
        c.execute("DELETE FROM posts WHERE user_id = ?", (user_id,))
        
        # Удаляем самого пользователя
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin.admin'))

@bp.route('/admin/reports')
def reports_list():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (session['user_id'],))
    if c.fetchone()['role'] not in ('admin','moderator'):
        return redirect(url_for('feed.feed'))
    c.execute("SELECT * FROM reports WHERE status='open' ORDER BY created_at DESC")
    reports = c.fetchall(); conn.close()
    return render_template('admin_reports.html', reports=reports)

@bp.route('/report/create', methods=['POST'])
def create_report():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    target_type = request.form.get('target_type')
    target_id = request.form.get('target_id')
    reason = request.form.get('reason')
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason) VALUES (?,?,?,?)",
              (session['user_id'], target_type, target_id, reason))
    conn.commit(); conn.close()
    return redirect(url_for('feed.feed'))

@bp.route('/admin/report/<int:report_id>', methods=['GET','POST'])
def report_view(report_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (session['user_id'],))
    role = c.fetchone()['role']
    if role not in ('admin','moderator'):
        return redirect(url_for('feed.feed'))
    if request.method == 'POST':
        action = request.form.get('action')
        ban_minutes = int(request.form.get('ban_minutes', 0) or 0)
        target_type = request.form.get('target_type')
        target_id = int(request.form.get('target_id'))
        # Удаление
        if action == 'delete':
            if target_type == 'post':
                c.execute('DELETE FROM posts WHERE id=?', (target_id,))
            elif target_type == 'comment':
                c.execute('DELETE FROM comments WHERE id=?', (target_id,))
        # Временный бан
        if action == 'ban' and ban_minutes > 0:
            from datetime import datetime, timedelta
            until = datetime.now() + timedelta(minutes=ban_minutes)
            # Ставим флаг и запись о бане
            c.execute('UPDATE users SET is_blocked=1, block_reason=? WHERE id=?', (f'Бан на {ban_minutes} мин.', target_id if target_type=='user' else (0)))
            if target_type == 'user':
                c.execute('INSERT INTO bans (user_id, until, reason) VALUES (?,?,?)', (target_id, until, f'Бан на {ban_minutes} мин.'))
        c.execute("UPDATE reports SET status='resolved' WHERE id=?", (report_id,))
        conn.commit(); conn.close()
        return redirect(url_for('admin.reports_list'))
    # GET
    c.execute('SELECT * FROM reports WHERE id=?', (report_id,))
    report = c.fetchone()
    target = None
    if report['target_type'] == 'post':
        c.execute('SELECT * FROM posts WHERE id=?', (report['target_id'],))
        target = c.fetchone()
    elif report['target_type'] == 'comment':
        c.execute('SELECT * FROM comments WHERE id=?', (report['target_id'],))
        target = c.fetchone()
    elif report['target_type'] == 'user':
        c.execute('SELECT id, username, avatar FROM users WHERE id=?', (report['target_id'],))
        target = c.fetchone()
    conn.close()
    return render_template('admin_report_view.html', report=report, target=target)

@bp.route('/admin/report/resolve', methods=['POST'])
def resolve_report():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (session['user_id'],))
    role = c.fetchone()['role']
    if role not in ('admin','moderator'):
        return redirect(url_for('feed.feed'))

    report_id = int(request.form.get('report_id'))
    target_type = request.form.get('target_type')
    target_id = int(request.form.get('target_id'))
    action = request.form.get('action')
    ban_minutes = int(request.form.get('ban_minutes', 0) or 0)
    ban_reason = request.form.get('ban_reason', 'Нарушение правил').strip()
    forever = request.form.get('forever') == '1'
    moderator_id = session['user_id']

    target_user_id = None
    if target_type == 'user':
        target_user_id = target_id
    elif target_type == 'post':
        c.execute('SELECT user_id FROM posts WHERE id=?', (target_id,))
        row = c.fetchone(); target_user_id = row['user_id'] if row else None
    elif target_type == 'comment':
        c.execute('SELECT user_id FROM comments WHERE id=?', (target_id,))
        row = c.fetchone(); target_user_id = row['user_id'] if row else None
    elif target_type == 'music':
        c.execute('SELECT user_id FROM music WHERE id=?', (target_id,))
        row = c.fetchone(); target_user_id = row['user_id'] if row else None

    # Для логов: если музыка, не связываем с основной таблицей reports
    rep_for_log = report_id if target_type != 'music' else None

    # Удаление контента
    if action == 'delete':
        if target_type == 'post':
            c.execute('DELETE FROM posts WHERE id=?', (target_id,))
        elif target_type == 'comment':
            c.execute('DELETE FROM comments WHERE id=?', (target_id,))
        elif target_type == 'music':
            c.execute('SELECT filename FROM music WHERE id=?', (target_id,))
            rowf = c.fetchone()
            if rowf and rowf['filename']:
                try:
                    os.remove(os.path.join(Config.MUSIC_FOLDER, rowf['filename']))
                except Exception:
                    pass
            c.execute('DELETE FROM music WHERE id=?', (target_id,))
        c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                  (rep_for_log, moderator_id, 'delete', target_type, target_id, None))

    # Временный бан
    if action == 'ban' and target_user_id and ban_minutes > 0:
        from datetime import datetime, timedelta
        until = datetime.now() + timedelta(minutes=ban_minutes)
        reason_text = f'Бан на {ban_minutes} минут: {ban_reason}'
        c.execute('UPDATE users SET is_blocked=1, block_reason=? WHERE id=?', (reason_text, target_user_id))
        c.execute('INSERT INTO bans (user_id, until, reason, moderator_id) VALUES (?,?,?,?)', (target_user_id, until, ban_reason, moderator_id))
        c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                  (rep_for_log, moderator_id, 'ban', target_type, target_id, reason_text))
        try:
            emit_to_user('account_blocked', {'reason': reason_text}, target_user_id)
        except Exception:
            pass
    
    # Постоянная блокировка
    if action == 'block' and target_user_id:
        reason_text = f'Блокировка: {ban_reason}'
        c.execute('UPDATE users SET is_blocked=1, block_reason=? WHERE id=?', (reason_text, target_user_id))
        c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                  (rep_for_log, moderator_id, 'block', target_type, target_id, reason_text))
        try:
            emit_to_user('account_blocked', {'reason': reason_text}, target_user_id)
        except Exception:
            pass

    # Комбинированное действие: заблокировать и удалить
    if action in ('ban_delete', 'block_delete'):
        # удалить контент
        if target_type == 'post':
            c.execute('DELETE FROM posts WHERE id=?', (target_id,))
        elif target_type == 'comment':
            c.execute('DELETE FROM comments WHERE id=?', (target_id,))
        elif target_type == 'music':
            c.execute('SELECT filename FROM music WHERE id=?', (target_id,))
            rowf = c.fetchone()
            if rowf and rowf['filename']:
                try:
                    os.remove(os.path.join(Config.MUSIC_FOLDER, rowf['filename']))
                except Exception:
                    pass
            c.execute('DELETE FROM music WHERE id=?', (target_id,))

        if target_user_id:
            if forever or action == 'block_delete':
                reason_text = f'Блокировка: {ban_reason}'
                c.execute('UPDATE users SET is_blocked=1, block_reason=? WHERE id=?', (reason_text, target_user_id))
                c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                          (report_id, moderator_id, 'block_delete', target_type, target_id, reason_text))
                try:
                    emit_to_user('account_blocked', {'reason': reason_text}, target_user_id)
                except Exception:
                    pass
            else:
                if ban_minutes > 0:
                    from datetime import datetime, timedelta
                    until = datetime.now() + timedelta(minutes=ban_minutes)
                    reason_text = f'Бан на {ban_minutes} минут: {ban_reason}'
                    c.execute('UPDATE users SET is_blocked=1, block_reason=? WHERE id=?', (reason_text, target_user_id))
                    c.execute('INSERT INTO bans (user_id, until, reason, moderator_id) VALUES (?,?,?,?)', (target_user_id, until, ban_reason, moderator_id))
                    c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                              (rep_for_log, moderator_id, 'ban_delete', target_type, target_id, reason_text))
                    try:
                        emit_to_user('account_blocked', {'reason': reason_text}, target_user_id)
                    except Exception:
                        pass

    if target_type == 'music':
        c.execute("UPDATE music_reports SET status='resolved' WHERE id=?", (report_id,))
    else:
        c.execute("UPDATE reports SET status='resolved' WHERE id=?", (report_id,))
    conn.commit(); conn.close()
    # AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=True, report_id=report_id)
    return redirect(url_for('admin.admin'))

@bp.route('/admin/report/<int:report_id>/json')
def report_json(report_id):
    if 'user_id' not in session:
        return jsonify({'error': 'unauth'}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (session['user_id'],))
    role = c.fetchone()['role']
    if role not in ('admin','moderator'):
        conn.close(); return jsonify({'error': 'forbidden'}), 403
    c.execute('SELECT id, reporter_id, target_type, target_id, reason, status, created_at FROM reports WHERE id=?', (report_id,))
    r = c.fetchone()
    if not r:
        conn.close(); return jsonify({'error': 'not_found'}), 404
    data = {
        'id': r['id'], 'reporter_id': r['reporter_id'], 'target_type': r['target_type'],
        'target_id': r['target_id'], 'reason': r['reason'], 'status': r['status'], 'created_at': r['created_at']
    }
    target = None
    # История логов по тикету
    c.execute('''SELECT ml.id, ml.action, ml.details, ml.created_at, u.username as moderator
                 FROM moderation_logs ml JOIN users u ON ml.moderator_id=u.id
                 WHERE ml.report_id=? ORDER BY ml.created_at DESC''', (report_id,))
    logs = [dict(id=row['id'], action=row['action'], details=row['details'], created_at=row['created_at'], moderator=row['moderator']) for row in c.fetchall()]
    if r['target_type'] == 'post':
        c.execute('SELECT p.id, p.user_id, p.content, p.timestamp, u.username, u.avatar FROM posts p JOIN users u ON p.user_id=u.id WHERE p.id=?', (r['target_id'],))
        t = c.fetchone();
        if t: target = {'id': t['id'], 'user_id': t['user_id'], 'content': t['content'], 'timestamp': t['timestamp'], 'username': t['username'], 'avatar': t['avatar']}
    elif r['target_type'] == 'comment':
        c.execute('SELECT c.id, c.user_id, c.content, c.timestamp, u.username, u.avatar FROM comments c JOIN users u ON c.user_id=u.id WHERE c.id=?', (r['target_id'],))
        t = c.fetchone();
        if t: target = {'id': t['id'], 'user_id': t['user_id'], 'content': t['content'], 'timestamp': t['timestamp'], 'username': t['username'], 'avatar': t['avatar']}
    elif r['target_type'] == 'user':
        c.execute('SELECT id, username, avatar, email FROM users WHERE id=?', (r['target_id'],))
        t = c.fetchone();
        if t: target = {'id': t['id'], 'username': t['username'], 'avatar': t['avatar'], 'email': t['email']}
    conn.close()
    return jsonify({'report': data, 'target': target, 'logs': logs})

@bp.route('/admin/modlog.json')
def modlog_json():
    if 'user_id' not in session:
        return jsonify({'error':'unauth'}), 401
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (session['user_id'],))
    role = c.fetchone()['role']
    if role not in ('admin','moderator'):
        conn.close(); return jsonify({'error':'forbidden'}), 403
    # Фильтры
    q = (request.args.get('q') or '').strip()
    action = (request.args.get('action') or '').strip()
    moderator = (request.args.get('moderator') or '').strip()
    date_from = (request.args.get('from') or '').strip()
    date_to = (request.args.get('to') or '').strip()

    base_sql = '''SELECT ml.created_at, u.username AS moderator, ml.action, ml.target_type, ml.target_id, ml.details, ml.report_id
                  FROM moderation_logs ml JOIN users u ON ml.moderator_id=u.id'''
    where = []
    params = []
    if q:
        where.append('(ml.details LIKE ? OR ml.action LIKE ? OR u.username LIKE ? OR CAST(ml.target_id AS TEXT) LIKE ? OR ml.target_type LIKE ?)')
        like = f'%{q}%'
        params += [like, like, like, like, like]
    if action:
        where.append('ml.action = ?'); params.append(action)
    if moderator:
        where.append('u.username LIKE ?'); params.append(f'%{moderator}%')
    if date_from:
        where.append('ml.created_at >= ?'); params.append(date_from)
    if date_to:
        where.append('ml.created_at <= ?'); params.append(date_to)
    if where:
        base_sql += ' WHERE ' + ' AND '.join(where)
    base_sql += ' ORDER BY ml.created_at DESC LIMIT 500'
    c.execute(base_sql, tuple(params))
    rows = [dict(created_at=r['created_at'], moderator=r['moderator'], action=r['action'], target_type=r['target_type'], target_id=r['target_id'], details=r['details'], report_id=r['report_id']) for r in c.fetchall()]
    conn.close()
    return jsonify({'logs': rows})

@bp.route('/admin/modlog.csv')
def modlog_csv():
    if 'user_id' not in session:
        return 'unauth', 401
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (session['user_id'],))
    role = c.fetchone()['role']
    if role not in ('admin','moderator'):
        conn.close(); return 'forbidden', 403
    # такие же фильтры
    q = (request.args.get('q') or '').strip()
    action = (request.args.get('action') or '').strip()
    moderator = (request.args.get('moderator') or '').strip()
    date_from = (request.args.get('from') or '').strip()
    date_to = (request.args.get('to') or '').strip()
    base_sql = '''SELECT ml.created_at, u.username AS moderator, ml.action, ml.target_type, ml.target_id, ml.details, ml.report_id
                  FROM moderation_logs ml JOIN users u ON ml.moderator_id=u.id'''
    where = []
    params = []
    if q:
        like = f'%{q}%'
        where.append('(ml.details LIKE ? OR ml.action LIKE ? OR u.username LIKE ? OR CAST(ml.target_id AS TEXT) LIKE ? OR ml.target_type LIKE ?)')
        params += [like, like, like, like, like]
    if action:
        where.append('ml.action = ?'); params.append(action)
    if moderator:
        where.append('u.username LIKE ?'); params.append(f'%{moderator}%')
    if date_from:
        where.append('ml.created_at >= ?'); params.append(date_from)
    if date_to:
        where.append('ml.created_at <= ?'); params.append(date_to)
    if where:
        base_sql += ' WHERE ' + ' AND '.join(where)
    base_sql += ' ORDER BY ml.created_at DESC'
    c.execute(base_sql, tuple(params))
    rows = c.fetchall(); conn.close()
    # CSV
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['created_at','moderator','action','target_type','target_id','details','report_id'])
    for r in rows:
        writer.writerow([r['created_at'], r['moderator'], r['action'], r['target_type'], r['target_id'], r['details'], r['report_id']])
    from flask import Response
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=modlog.csv'})

@bp.route('/make_admin/<int:user_id>', methods=['POST'])
def make_admin(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    
    current_user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем, является ли текущий пользователь администратором
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    current_user_role = c.fetchone()['role']
    if current_user_role != 'admin':
        return redirect(url_for('feed.feed'))
    
    # Назначаем пользователя администратором
    try:
        c.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin.admin'))

@bp.route('/toggle_block/<int:user_id>', methods=['POST'])
def toggle_block(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))

    current_user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    # Проверяем, является ли текущий пользователь администратором
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    current_user_role = c.fetchone()['role']
    if current_user_role != 'admin':
        return redirect(url_for('feed.feed'))

    # Переключаем статус блокировки
    try:
        reason = request.form.get('reason', '')
        # Узнаем текущий статус
        c.execute("SELECT is_blocked FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        was_blocked = bool(row['is_blocked']) if row else False
        # Переключаем
        c.execute("UPDATE users SET is_blocked = CASE WHEN is_blocked=1 THEN 0 ELSE 1 END, block_reason = CASE WHEN is_blocked=1 THEN NULL ELSE ? END WHERE id = ?", (reason, user_id))
        conn.commit()
        # Уведомляем пользователя в реальном времени
        if not was_blocked:
            emit_to_user('account_blocked', {'reason': reason or 'Профиль заблокирован администратором'}, user_id)
            # Логируем блокировку, если вдруг использовали toggle как блокировку
            try:
                c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                          (None, current_user_id, 'block', 'user', user_id, reason))
                conn.commit()
            except Exception:
                pass
        else:
            emit_to_user('account_unblocked', {}, user_id)
            # Логируем разблокировку
            try:
                c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                          (None, current_user_id, 'unblock', 'user', user_id, None))
                conn.commit()
            except Exception:
                pass
    except sqlite3.Error:
        conn.rollback()
    finally:
        conn.close()

    return redirect(url_for('admin.admin'))

@bp.route('/admin/ban_user/<int:user_id>', methods=['POST'])
def ban_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    current_user_id = session['user_id']
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    current_user_role = c.fetchone()['role']
    if current_user_role not in ('admin','moderator'):
        return redirect(url_for('feed.feed'))

    reason = request.form.get('reason', 'Нарушение правил сообщества').strip()
    forever = request.form.get('forever') == '1'
    minutes = int(request.form.get('minutes', '60') or 60)
    try:
        if forever:
            c.execute("UPDATE users SET is_blocked=1, block_reason=? WHERE id=?", (reason or 'Блокировка', user_id))
            conn.commit()
            emit_to_user('account_blocked', {'reason': reason}, user_id)
            # Лог
            try:
                c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                          (None, current_user_id, 'block', 'user', user_id, reason))
                conn.commit()
            except Exception:
                pass
        else:
            from datetime import datetime, timedelta
            until = datetime.now() + timedelta(minutes=max(1, minutes))
            c.execute("UPDATE users SET is_blocked=1, block_reason=? WHERE id=?", (f'Бан на {minutes} минут: {reason}', user_id))
            c.execute("INSERT INTO bans (user_id, until, reason) VALUES (?,?,?)", (user_id, until, reason))
            conn.commit()
            emit_to_user('account_blocked', {'reason': f'Бан на {minutes} минут: {reason}'}, user_id)
            # Лог
            try:
                c.execute("INSERT INTO moderation_logs (report_id, moderator_id, action, target_type, target_id, details) VALUES (?,?,?,?,?,?)",
                          (None, current_user_id, 'ban', 'user', user_id, f'Бан на {minutes} минут: {reason}'))
                conn.commit()
            except Exception:
                pass
    finally:
        conn.close()
    # AJAX поддержка
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=True)
    return redirect(url_for('admin.admin'))

@bp.route('/admin/settings', methods=['POST'])
def admin_settings():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    current_user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    if c.fetchone()['role'] != 'admin':
        return redirect(url_for('feed.feed'))

    reg_mode = request.form.get('registration_mode', 'open')  # open | invite | closed
    moderation = request.form.get('content_moderation', 'auto')
    c.execute("REPLACE INTO settings (key, value) VALUES ('registration_mode', ?)", (reg_mode,))
    c.execute("REPLACE INTO settings (key, value) VALUES ('content_moderation', ?)", (moderation,))
    conn.commit(); conn.close()
    return redirect(url_for('admin.admin'))

@bp.route('/admin/invites', methods=['POST'])
def admin_invites():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    current_user_id = session['user_id']
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    if c.fetchone()['role'] != 'admin':
        return redirect(url_for('feed.feed'))
    import secrets
    code = secrets.token_urlsafe(8)
    uses = int(request.form.get('uses', 1))
    c.execute("INSERT INTO invites (code, uses_left) VALUES (?, ?)", (code, uses))
    conn.commit(); conn.close()
    return redirect(url_for('admin.admin'))

@bp.route('/admin/update_user/<int:user_id>', methods=['POST'])
def admin_update_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    current_user_id = session['user_id']
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    if c.fetchone()['role'] not in ('admin', 'moderator'):
        return redirect(url_for('feed.feed'))
    new_username = request.form.get('username', '').strip()
    new_email = request.form.get('email', '').strip()
    if new_username:
        c.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))
    if new_email is not None:
        c.execute("UPDATE users SET email=? WHERE id=?", (new_email, user_id))
    conn.commit(); conn.close()
    return redirect(url_for('admin.admin'))