from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from models import get_db
from config import Config
import os

bp = Blueprint('music', __name__)

def allowed_audio(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_AUDIO

@bp.route('/music')
def music_index():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT id, username, email, bio, avatar, role FROM users WHERE id=?', (session['user_id'],))
    me = c.fetchone()
    current_user = None
    if me:
        current_user = {
            'id': me['id'],
            'username': me['username'],
            'email': me['email'],
            'bio': me['bio'],
            'avatar': me['avatar'],
            'role': me['role'],
        }
    c.execute('''SELECT m.id, m.filename, m.title, m.uploaded_at, u.username
                 FROM music m JOIN users u ON m.user_id=u.id
                 ORDER BY m.uploaded_at DESC''')
    tracks = c.fetchall(); conn.close()
    return render_template('music.html', current_user=current_user, tracks=tracks, active_page='music')

@bp.route('/music/upload', methods=['POST'])
def music_upload():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    file = request.files.get('file'); title = request.form.get('title','').strip()
    if not file or file.filename == '' or not allowed_audio(file.filename):
        return redirect(url_for('music.music_index'))
    os.makedirs(Config.MUSIC_FOLDER, exist_ok=True)
    safe_name = secure_filename(f"{session['user_id']}_{file.filename}")
    path = os.path.join(Config.MUSIC_FOLDER, safe_name)
    file.save(path)
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT INTO music (user_id, filename, title) VALUES (?,?,?)', (session['user_id'], safe_name, title or file.filename))
    conn.commit(); conn.close()
    return redirect(url_for('music.music_index'))

@bp.route('/music/playlist/create', methods=['POST'])
def playlist_create():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    title = request.form.get('title','').strip() or 'Плейлист'
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT INTO playlists (user_id, title) VALUES (?,?)', (session['user_id'], title))
    conn.commit(); conn.close()
    return redirect(url_for('music.music_index'))

@bp.route('/music/playlist/add', methods=['POST'])
def playlist_add():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    playlist_id = int(request.form.get('playlist_id'))
    track_id = int(request.form.get('track_id'))
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position) VALUES (?,?,?)', (playlist_id, track_id, 0))
    conn.commit(); conn.close()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=True)
    return redirect(url_for('music.music_index'))

@bp.route('/music/report', methods=['POST'])
def music_report():
    if 'user_id' not in session:
        return redirect(url_for('auth.index'))
    track_id = request.form.get('track_id'); reason = request.form.get('reason','').strip()
    if not track_id or not reason:
        return redirect(url_for('music.music_index'))
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT INTO music_reports (reporter_id, track_id, reason) VALUES (?,?,?)', (session['user_id'], track_id, reason))
    conn.commit(); conn.close()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=True)
    return redirect(url_for('music.music_index'))


