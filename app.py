import signal
import sys
from flask import Flask, session, request, redirect, url_for, render_template
from flask_socketio import SocketIO
from config import Config
from models import init_db
from datetime import datetime 
import os
import socket
import ssl
from routes.auth import bp as auth_bp
from routes.feed import bp as feed_bp
from routes.profile import bp as profile_bp
from routes.gallery import bp as gallery_bp
from routes.messages import bp as messages_bp
from routes.friends import bp as friends_bp
from routes.static import bp as static_bp
from gevent import monkey
from routes.admin import bp as admin_bp

# Монки-патчинг должен быть самым первым!
monkey.patch_all()

os.environ['GEVENT_SUPPORT'] = 'True'

# Обработчик сигнала для корректного завершения
def handle_sigint(signal, frame):
    print("\nПолучен сигнал SIGINT (Ctrl+C). Завершение работы...")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

app = Flask(__name__)
app.config.from_object(Config)
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15 MB limit

# Инициализация базы данных
init_db()

# Создание папок для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MESSAGE_FILES_FOLDER'], exist_ok=True)

# Создание папки для SSL сертификатов
os.makedirs('ssl', exist_ok=True)

# Инициализация SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Регистрация blueprint'ов
from routes import auth, feed, profile, gallery, messages, friends, static

app.register_blueprint(auth.bp)
app.register_blueprint(feed.bp)
app.register_blueprint(profile.bp)
app.register_blueprint(gallery.bp)
app.register_blueprint(messages.bp)
app.register_blueprint(friends.bp)
app.register_blueprint(static.bp)
app.register_blueprint(admin_bp)

# Импорт сокетов
from sockets import register_socket_handlers
register_socket_handlers(socketio)

def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    if not value:
        return ''
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value)
        dt = None
        # Попытки распарсить разные форматы (с/без микросекунд, ISO с 'T')
        for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                pass
        if dt is None:
            try:
                dt = datetime.fromisoformat(s)
            except Exception:
                return s
    return dt.strftime(format)

app.jinja_env.filters['datetimeformat'] = datetimeformat  # Регистрируем фильтр

# Фильтр для отображения только сути причины бана, без префиксов
def banreason(value):
    if not value:
        return ''
    try:
        s = str(value)
        parts = s.split(':', 1)
        return parts[1].strip() if len(parts) == 2 else s
    except Exception:
        return value

app.jinja_env.filters['banreason'] = banreason

# Пробрасываем TURN-конфиг в шаблоны
app.jinja_env.globals.update(
    TURN_URL=Config.TURN_URL,
    TURN_USERNAME=Config.TURN_USERNAME,
    TURN_PASSWORD=Config.TURN_PASSWORD
)

# Глобальная защита: заблокированный пользователь всегда видит страницу блокировки
@app.before_request
def enforce_account_block():
    try:
        # Исключения: статика, сокеты, страница блокировки и корневой индекс
        if request.path.startswith('/static') or request.path.startswith('/socket.io'):
            return None
        if request.endpoint in {'auth.blocked', 'auth.index', 'static.static_files'}:
            return None
        if 'user_id' not in session:
            return None
        from models import get_db
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT is_blocked, block_reason FROM users WHERE id = ?', (session['user_id'],))
        row = c.fetchone()
        conn.close()
        if row and row['is_blocked']:
            reason = row['block_reason'] or 'Профиль заблокирован администратором'
            return render_template('blocked.html', reason=reason)
    except Exception:
        # Не препятствуем работе при ошибках проверки
        return None

def generate_self_signed_cert():
    """Генерация самоподписанного SSL сертификата"""
    try:
        from OpenSSL import crypto
        from socket import gethostname
        
        # При установке переменной окружения SSL_REGEN=1 принудительно пересоздаем сертификаты
        force_regen = os.getenv("SSL_REGEN", "0") == "1"
        # Проверяем, существуют ли уже сертификаты
        if (os.path.exists("ssl/cert.pem") and os.path.exists("ssl/key.pem")) and not force_regen:
            print("SSL сертификаты уже существуют")
            return True
            
        # Создаем ключ
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 2048)
        
        # Создаем самоподписанный сертификат
        cert = crypto.X509()
        cert.get_subject().C = "RU"
        cert.get_subject().ST = "Moscow"
        cert.get_subject().L = "Moscow"
        cert.get_subject().O = "Localhost"
        cert.get_subject().OU = "Development"
        cert.get_subject().CN = gethostname()
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365*24*60*60)  # 1 год
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)

        # Добавляем расширения и SubjectAltName (SAN), иначе Chrome может не доверять
        local_ip = None
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = None

        extra_san = os.getenv("EXTRA_SAN", "")  # через запятую: dns1,dns2,ip1,ip2
        san_entries = [
            "DNS:localhost",
            "IP:127.0.0.1",
        ]
        if local_ip and local_ip != "127.0.0.1":
            san_entries.append(f"IP:{local_ip}")
        if extra_san:
            for item in [s.strip() for s in extra_san.split(',') if s.strip()]:
                # Простая эвристика: если похоже на IP, добавим как IP, иначе как DNS
                parts = item.split('.')
                if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                    san_entries.append(f"IP:{item}")
                else:
                    san_entries.append(f"DNS:{item}")

        extensions = [
            crypto.X509Extension(b"basicConstraints", True, b"CA:FALSE"),
            crypto.X509Extension(b"keyUsage", True, b"digitalSignature, keyEncipherment"),
            crypto.X509Extension(b"extendedKeyUsage", False, b"serverAuth"),
            crypto.X509Extension(b"subjectAltName", False, ", ".join(san_entries).encode("utf-8")),
        ]
        cert.add_extensions(extensions)

        cert.sign(key, 'sha256')
        
        # Сохраняем сертификат и ключ
        with open("ssl/cert.pem", "wt") as f:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("utf-8"))
        with open("ssl/key.pem", "wt") as f:
            f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key).decode("utf-8"))
            
        print("Самоподписанные SSL сертификаты сгенерированы (с SAN):", ", ".join(san_entries))
        return True
        
    except ImportError:
        print("Для генерации SSL сертификатов установите pyOpenSSL: pip install pyOpenSSL")
        return False
    except Exception as e:
        print(f"Ошибка при генерации SSL сертификатов: {e}")
        return False

def create_ssl_context():
    """Создание SSL контекста для Flask-SocketIO"""
    if not (os.path.exists("ssl/cert.pem") and os.path.exists("ssl/key.pem")):
        return None
        
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain("ssl/cert.pem", "ssl/key.pem")
        return context
    except Exception as e:
        print(f"Ошибка создания SSL контекста: {e}")
        return None

if __name__ == '__main__':
    # Генерируем самоподписанные сертификаты
    ssl_context = None
    if generate_self_signed_cert():
        ssl_context = create_ssl_context()
        if ssl_context:
            print("Запуск с HTTPS")
        else:
            print("Не удалось создать SSL контекст, запуск с HTTP")
    else:
        print("Запуск с HTTP (без SSL)")
    
    try:
        # Запуск на всех сетевых интерфейсах (0.0.0.0) и порту 5000
        socketio.run(
            app, 
            host='0.0.0.0',  # Доступ с любого IP-адреса
            port=5000,       # Порт (можно изменить при необходимости)
            debug=True,
            allow_unsafe_werkzeug=True,  # Для работы в локальной сети
            ssl_context=ssl_context,     # SSL контекст
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\nПриложение завершено по запросу пользователя")
        sys.exit(0)