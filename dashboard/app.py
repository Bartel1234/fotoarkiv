import base64
import hmac
import json
import os
import secrets
import shutil
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

CONTROL = Path('/control')
PHOTOS = Path('/photos')
PASSWORD = os.environ['APP_PASSWORD']
TOKEN = secrets.token_urlsafe(24)
ASSETS = Path(__file__).parent
_cache = {'at': 0, 'data': {}}


def read(name, default=''):
    try:
        return (CONTROL / name).read_text(encoding='utf-8').strip()
    except OSError:
        return default


def inventory():
    now = time.monotonic()
    if now - _cache['at'] < 20:
        return _cache['data']
    count, size, recent = 0, 0, []
    for root, _, files in os.walk(PHOTOS):
        for name in files:
            try:
                st = (Path(root) / name).stat()
                count += 1
                size += st.st_size
                recent.append((st.st_mtime, name, st.st_size))
                if len(recent) > 50:
                    recent.sort(reverse=True)
                    del recent[10:]
            except OSError:
                pass
    recent.sort(reverse=True)
    try:
        disk = shutil.disk_usage(PHOTOS)
        free, total = disk.free, disk.total
    except OSError:
        free, total = 0, 0
    data = {'count': count, 'bytes': size, 'free': free, 'total': total,
            'recent': [{'name': name, 'bytes': nbytes, 'time': datetime.fromtimestamp(ts).strftime('%d/%m %H:%M')}
                       for ts, name, nbytes in recent[:6]]}
    _cache.update(at=now, data=data)
    return data


def status():
    try:
        with (CONTROL / 'activity.log').open(encoding='utf-8', errors='replace') as f:
            log = ''.join(deque(f, maxlen=90))[-14000:]
    except OSError:
        log = ''
    try:
        next_run = datetime.fromtimestamp(int(read('next-run'))).strftime('%d/%m/%Y kl. %H:%M')
    except (ValueError, OverflowError, OSError):
        next_run = 'Ikke planlagt'
    try:
        online = time.time() - int(read('heartbeat')) < 45
    except ValueError:
        online = False
    running = (CONTROL / 'running').exists() and online
    pending = (CONTROL / 'start-request').exists()
    exit_code = read('last-exit')
    if not online:
        label, tone = 'Synkronisering offline', 'error'
    elif running:
        label, tone = 'Synkroniserer nu', 'active'
    elif pending:
        label, tone = 'Starter snart', 'pending'
    elif exit_code and exit_code != '0':
        label, tone = 'Kræver opmærksomhed', 'error'
    elif exit_code == '0':
        label, tone = 'Alt er opdateret', 'good'
    else:
        label, tone = 'Klar til første kørsel', 'pending'
    return {**inventory(), 'label': label, 'tone': tone, 'online': online,
            'running': running, 'pending': pending, 'last_run': read('last-run') or 'Ingen endnu',
            'next_run': next_run, 'last_exit': exit_code, 'started': read('running') if running else '',
            'log': log or 'Der er endnu ingen aktivitet.'}


class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        header = self.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return False
        try:
            raw = base64.b64decode(header[6:], validate=True).decode('utf-8')
            _, supplied = raw.split(':', 1)
        except (ValueError, UnicodeError):
            return False
        return hmac.compare_digest(supplied, PASSWORD)

    def respond(self, body, code=200, mime='text/html; charset=utf-8'):
        data = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'")
        if code == 401:
            self.send_header('WWW-Authenticate', 'Basic realm="Fotoarkiv Backup"')
        self.end_headers()
        self.wfile.write(data)

    def guard(self):
        if self.authorized():
            return True
        self.respond('Login kræves', 401, 'text/plain; charset=utf-8')
        return False

    def do_GET(self):
        if not self.guard():
            return
        if self.path == '/':
            template = (ASSETS / 'index.html').read_text(encoding='utf-8')
            self.respond(template.replace('%%CSRF_TOKEN%%', TOKEN))
        elif self.path == '/api/status':
            self.respond(json.dumps(status(), ensure_ascii=False), mime='application/json; charset=utf-8')
        elif self.path in ('/style.css', '/app.js'):
            name = self.path[1:]
            mime = 'text/css; charset=utf-8' if name.endswith('.css') else 'text/javascript; charset=utf-8'
            self.respond((ASSETS / name).read_text(encoding='utf-8'), mime=mime)
        else:
            self.respond('Ikke fundet', 404)

    def do_POST(self):
        if not self.guard():
            return
        if self.path != '/start' or self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            self.respond('Forkert forespørgsel', 400)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.respond('Forkert længde', 400)
            return
        if not 0 < length <= 4096:
            self.respond('Forkert længde', 400)
            return
        body = parse_qs(self.rfile.read(length).decode('utf-8', 'replace'))
        if not hmac.compare_digest(body.get('token', [''])[0], TOKEN):
            self.respond('Ugyldig formular', 403)
            return
        if not (CONTROL / 'running').exists():
            (CONTROL / 'start-request').write_text(str(int(time.time())), encoding='utf-8')
        self.send_response(303)
        self.send_header('Location', '/')
        self.send_header('Content-Length', '0')
        self.end_headers()


if __name__ == '__main__':
    if PASSWORD == 'SKIFT_TIL_EN_LANG_ADGANGSKODE' or len(PASSWORD) < 12:
        raise SystemExit('Sæt APP_PASSWORD til mindst 12 tegn i .env')
    ThreadingHTTPServer(('0.0.0.0', 8787), Handler).serve_forever()
