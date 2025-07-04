from flask import Flask
from flask_socketio import SocketIO
from config import Config
from models import init_db
from datetime import datetime 
import os
from routes.auth import bp as auth_bp
from routes.feed import bp as feed_bp
from routes.profile import bp as profile_bp
from routes.gallery import bp as gallery_bp
from routes.messages import bp as messages_bp
from routes.friends import bp as friends_bp
from routes.static import bp as static_bp
from gevent import monkey
monkey.patch_all()

os.environ['GEVENT_SUPPORT'] = 'True'


app = Flask(__name__)
app.config.from_object(Config)

# Инициализация базы данных
init_db()

# Создание папок для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MESSAGE_FILES_FOLDER'], exist_ok=True)

# Инициализация SocketIO
socketio = SocketIO(app)

# Регистрация blueprint'ов
from routes import auth, feed, profile, gallery, messages, friends, static

app.register_blueprint(auth.bp)
app.register_blueprint(feed.bp)
app.register_blueprint(profile.bp)
app.register_blueprint(gallery.bp)
app.register_blueprint(messages.bp)
app.register_blueprint(friends.bp)
app.register_blueprint(static.bp)

# Импорт сокетов
from sockets import register_socket_handlers
register_socket_handlers(socketio)

def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    if isinstance(value, str):
        # Преобразуем строку из БД в объект datetime
        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return value.strftime(format)

app.jinja_env.filters['datetimeformat'] = datetimeformat  # Регистрируем фильтр

if __name__ == '__main__':
    socketio.run(app, debug=True)