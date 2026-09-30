import html
import base64
import asyncio
import hmac
import json
import os
import re
import secrets
import shutil
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs
from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from archive import setup as setup_archive
from progress import progress

CONTROL = Path('/control')
PHOTOS = Path('/photos')
ACCOUNTS = Path('/accounts')
ACCOUNT_LIST = CONTROL / 'accounts.txt'
PASSWORD = os.environ['APP_PASSWORD']
TOKEN = secrets.token_urlsafe(24)
LOGIN_URL = os.environ.get('LOGIN_URL', 'http://login:80').rstrip('/')
ASSETS = Path(__file__).parent
TRANSLATIONS = json.loads((ASSETS / 'translations.json').read_text(encoding='utf-8'))

def translated(request, text):
    return text if request.cookies.get('fotoarkiv_language') == 'da' else TRANSLATIONS.get(text, text)

def page_template(name):
    catalog = json.dumps(TRANSLATIONS, ensure_ascii=False).replace('<', '\u003c')
    return (ASSETS / name).read_text(encoding='utf-8').replace('</head>', '<script id="translation-catalog" type="application/json">' + catalog + '</script></head>')

@web.middleware
async def language(request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as error:
        if error.text in TRANSLATIONS:
            error.text = translated(request, error.text)
        raise
    return response

_cache = {'at': 0, 'data': {}}
_account_cache = {'at': 0, 'counts': {}}
EMAIL = re.compile(r'^[a-z0-9][a-z0-9._+-]{0,63}@[a-z0-9][a-z0-9.-]{0,62}\.[a-z]{2,24}$')



def readable_log(raw):
    kept, browser_messages = [], 0
    for line in raw.splitlines():
        if 'Event: {Type:keyDown' in line or 'Event: {Type:keyUp' in line:
            continue
        if ('ERROR: unhandled page event *page.EventDownloadWillBegin' in line
                or 'ERROR: could not unmarshal event: unknown ClientNavigationReason value' in line):
            browser_messages += 1
            continue
        kept.append(line)
    if browser_messages:
        kept.insert(0, f'{browser_messages} gentagne browsermeddelelser samlet (DownloadWillBegin/ClientNavigationReason). Den fulde rå log bevares i activity.log.')
    return '\n'.join(kept)

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
    for root, dirs, files in os.walk(PHOTOS):
        dirs[:] = [d for d in dirs if d not in ("Albums", ".fotoarkiv") and not (Path(root) / d).is_symlink()]
        for name in files:
            if name.startswith('.') or name.endswith(('.crdownload', '.part', '.tmp')):
                continue
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


def account_names():
    try:
        return [name for name in ACCOUNT_LIST.read_text(encoding='utf-8').splitlines() if EMAIL.fullmatch(name)]
    except OSError:
        return []


def account_summaries():
    result = []
    now = time.monotonic()
    if now - _account_cache['at'] > 30:
        counts = {}
        for email in account_names():
            count = size = 0
            for root, dirs, files in os.walk(PHOTOS / email):
                dirs[:] = [d for d in dirs if d not in ("Albums", ".fotoarkiv") and not (Path(root) / d).is_symlink()]
                for file in files:
                    if file.startswith('.') or file.endswith(('.crdownload', '.part', '.tmp')):
                        continue
                    try:
                        count += 1
                        size += (Path(root) / file).stat().st_size
                    except OSError:
                        pass
            counts[email] = (count, size)
        _account_cache.update(at=now, counts=counts)
    for email in account_names():
        state = CONTROL / 'accounts' / email
        count, size = _account_cache['counts'].get(email, (0, 0))
        def value(name):
            try:
                return (state / name).read_text(encoding='utf-8').strip()
            except OSError:
                return ''
        try:
            online = time.time() - int(value('heartbeat')) < 45
        except ValueError:
            online = False
        try:
            with (state / 'activity.log').open(encoding='utf-8', errors='replace') as f:
                raw_account_log = ''.join(deque(f, maxlen=180))
                account_log = readable_log(raw_account_log)[-14000:]
        except OSError:
            account_log = raw_account_log = ''
        try:
            account_next_run = datetime.fromtimestamp(int(value('next-run'))).strftime('%d/%m/%Y kl. %H:%M')
        except (ValueError, OverflowError, OSError):
            account_next_run = 'Ikke planlagt'
        running = online and (state / 'running').exists()
        pending = (state / 'start-request').exists()
        stopping = (state / 'stop-request').exists()
        login_active = read('login-active') == email
        phase = progress(state, raw_account_log, online=online, running=running, pending=pending, stopping=stopping, login_active=login_active)
        result.append({**phase, 'email': email, 'folder': email, 'count': count, 'bytes': size,
                       'online': online, 'running': online and (state / 'running').exists(),
                       'pending': (state / 'start-request').exists(),
                       'stopping': (state / 'stop-request').exists(),
                       'login_active': read('login-active') == email,
                       'last_run': value('last-run') or 'Ingen endnu', 'last_exit': value('last-exit'),
                       'next_run': account_next_run, 'log': account_log or 'Der er endnu ingen aktivitet for denne konto.'})
    return result


def status():
    try:
        with (CONTROL / 'activity.log').open(encoding='utf-8', errors='replace') as f:
            raw_log = ''.join(deque(f, maxlen=180))
            log = readable_log(raw_log)[-14000:]
    except OSError:
        log = raw_log = ''
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
    elif exit_code == '130':
        label, tone = 'Backup afbrudt af brugeren', 'pending'
    elif exit_code and exit_code != '0':
        label, tone = 'Kræver opmærksomhed', 'error'
    elif exit_code == '0':
        label, tone = 'Seneste kørsel afsluttet', 'good'
    else:
        label, tone = 'Klar til første kørsel', 'pending'
    phase = progress(CONTROL, raw_log, online=online, running=running, pending=pending, stopping=(CONTROL / 'stop-request').exists(), login_active=read('login-active') == 'legacy')
    return {**inventory(), **phase, 'accounts': account_summaries(), 'label': label, 'tone': tone, 'online': online,
            'running': running, 'pending': pending, 'stopping': (CONTROL / 'stop-request').exists(), 'login_active': read('login-active') == 'legacy', 'last_run': read('last-run') or 'Ingen endnu',
            'next_run': next_run, 'last_exit': exit_code, 'started': read('running') if running else '',
            'log': log or 'Der er endnu ingen aktivitet.'}


@web.middleware
async def auth(request, handler):
    header = request.headers.get('Authorization', '')
    try:
        raw = base64.b64decode(header.removeprefix('Basic '), validate=True).decode('utf-8')
        _, supplied = raw.split(':', 1)
        valid = header.startswith('Basic ') and hmac.compare_digest(supplied, PASSWORD)
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        return web.Response(status=401, text=translated(request, 'Login kræves'), headers={'WWW-Authenticate': 'Basic realm="Fotoarkiv Backup"'})
    response = await handler(request)
    response.headers.setdefault('Cache-Control', 'no-store')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    return response


async def home(request):
    template = page_template('index.html')
    return web.Response(text=template.replace('%%CSRF_TOKEN%%', TOKEN), content_type='text/html',
                        headers={'Content-Security-Policy': "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; media-src 'self'; frame-src 'self'; form-action 'self'; base-uri 'none'"})


async def archive_page(request):
    account = request.match_info['email']
    if account != 'legacy' and account not in account_names():
        raise web.HTTPNotFound(text='Ukendt konto')
    template = page_template('archive.html')
    return web.Response(text=template.replace('%%ACCOUNT%%', html.escape(account, quote=True)).replace('%%CSRF_TOKEN%%', TOKEN),
                        content_type='text/html',
                        headers={'Content-Security-Policy': "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; media-src 'self'; frame-src 'self'; form-action 'self'; base-uri 'none'"})


async def api_status(request):
    data = await asyncio.to_thread(status)
    for record in [data, *data.get('accounts', [])]:
        for key in ('label', 'last_run', 'next_run', 'log'):
            if key in record:
                record[key] = translated(request, record[key])
                if key == 'next_run' and request.cookies.get('fotoarkiv_language') != 'da':
                    record[key] = record[key].replace(' kl. ', ' at ')
                if key == 'next_run' and request.cookies.get('fotoarkiv_language') != 'da':
                    record[key] = record[key].replace(' kl. ', ' at ')
    return web.json_response(data)


async def asset(request):
    return web.FileResponse(ASSETS / request.match_info['name'])



def request_login_close(email):
    queued = read('login-request').split(' ', 1)[0]
    if queued == email:
        (CONTROL / 'login-request').unlink(missing_ok=True)
    (CONTROL / 'login-close-request').write_text(email, encoding='utf-8')

async def start(request):
    if request.content_type != 'application/x-www-form-urlencoded' or request.content_length is None or not 0 < request.content_length <= 4096:
        raise web.HTTPBadRequest(text='Forkert formular')
    body = parse_qs(await request.text())
    if not hmac.compare_digest(body.get('token', [''])[0], TOKEN):
        raise web.HTTPForbidden(text='Ugyldig formular')
    if not (CONTROL / 'running').exists():
        request_login_close('legacy')
        (CONTROL / 'start-request').write_text(str(int(time.time())), encoding='utf-8')
    raise web.HTTPSeeOther('/')


async def account_action(request):
    if request.content_type != 'application/json' or (request.content_length or 0) > 4096:
        raise web.HTTPBadRequest(text='Forkert formular')
    try:
        data = await request.json()
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text='Ugyldig JSON')
    if not hmac.compare_digest(str(data.get('token', '')), TOKEN):
        raise web.HTTPForbidden(text='Ugyldig formular')
    action = request.match_info.get('action', 'add')
    if action == 'add':
        email = str(data.get('email', '')).strip().lower()
        if len(email) > 128 or not EMAIL.fullmatch(email):
            raise web.HTTPBadRequest(text='Angiv en gyldig mailadresse')
        async with request.app['account_lock']:
            names = account_names()
            if email in names:
                raise web.HTTPConflict(text='Kontoen findes allerede')
            for folder in (ACCOUNTS / email, PHOTOS / email, CONTROL / 'accounts' / email):
                if folder.is_symlink():
                    raise web.HTTPConflict(text='Mappen kan ikke bruges')
                folder.mkdir(parents=True, exist_ok=True)
            (ACCOUNTS / email / 'gphotos-cdp').mkdir(exist_ok=True)
            tmp = ACCOUNT_LIST.with_suffix('.tmp')
            tmp.write_text(''.join(name + '\n' for name in [*names, email]), encoding='utf-8')
            tmp.replace(ACCOUNT_LIST)
            _account_cache['at'] = 0
        return web.json_response({'email': email, 'folder': email}, status=201)
    email = request.match_info['email']
    if email != 'legacy' and email not in account_names():
        raise web.HTTPNotFound(text='Ukendt konto')
    if action == 'login':
        if read('login-active') != email:
            (CONTROL / 'login-request').write_text(f'{email} {int(time.time())}\n', encoding='utf-8')
    elif action == 'close-login':
        request_login_close(email)
    elif action == 'stop':
        state = CONTROL if email == 'legacy' else CONTROL / 'accounts' / email
        (state / 'stop-request').write_text(str(int(time.time())), encoding='utf-8')
        for name in ('start-request', 'rescan-request', 'organize-request'):
            (state / name).unlink(missing_ok=True)
    elif action in ('start', 'rescan', 'organize'):
        state = CONTROL if email == 'legacy' else CONTROL / 'accounts' / email
        if action == 'organize':
            if (state / 'running').exists():
                raise web.HTTPConflict(text='Vent til den aktuelle backup er afsluttet')
            (state / 'organize-request').write_text(str(int(time.time())), encoding='utf-8')
        if action == 'rescan':
            if (state / 'running').exists():
                raise web.HTTPConflict(text='Vent til den aktuelle synkronisering er afsluttet')
            (state / 'rescan-request').write_text(str(int(time.time())), encoding='utf-8')
        request_login_close(email)
        (state / 'start-request').write_text(str(int(time.time())), encoding='utf-8')
    else:
        raise web.HTTPNotFound()
    return web.json_response({'ok': True})


async def proxy(request):
    # The desktop app uses absolute asset and WebSocket paths, so route all
    # non-dashboard paths to it. It is reachable only through this auth guard.
    path = request.path.removeprefix('/login') if request.path.startswith('/login/') else request.path
    if not path:
        path = '/'
    upstream = LOGIN_URL + path + ('?' + request.query_string if request.query_string else '')
    headers = {k: v for k, v in request.headers.items() if k.lower() not in
               {'authorization', 'host', 'connection', 'upgrade', 'content-length', 'accept-encoding'}}
    session = request.app['session']
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        browser = web.WebSocketResponse()
        await browser.prepare(request)
        try:
            async with session.ws_connect(upstream, headers=headers) as remote:
                async def forward():
                    async for msg in browser:
                        if msg.type == WSMsgType.TEXT:
                            await remote.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await remote.send_bytes(msg.data)
                        else:
                            break
                task = asyncio.create_task(forward())
                try:
                    async for msg in remote:
                        if msg.type == WSMsgType.TEXT:
                            await browser.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await browser.send_bytes(msg.data)
                        else:
                            break
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        except Exception:
            pass
        return browser
    try:
        async with session.request(request.method, upstream, headers=headers, data=await request.read(), allow_redirects=False) as remote:
            payload = await remote.read()
            response_headers = {k: v for k, v in remote.headers.items() if k.lower() not in
                                {'connection', 'transfer-encoding', 'content-length', 'content-encoding', 'x-frame-options', 'content-security-policy'}}
            return web.Response(body=payload, status=remote.status, headers=response_headers)
    except Exception:
        raise web.HTTPBadGateway(text='Login-skrivebordet starter stadig. Prøv igen om lidt.')


async def client_session(app):
    app['session'] = ClientSession(timeout=ClientTimeout(total=None, sock_connect=15))
    yield
    await app['session'].close()


if __name__ == '__main__':
    if PASSWORD == 'SKIFT_TIL_EN_LANG_ADGANGSKODE' or len(PASSWORD) < 12:
        raise SystemExit('Sæt APP_PASSWORD til mindst 12 tegn i .env')
    app = web.Application(middlewares=[language, auth])
    app['account_lock'] = asyncio.Lock()
    app.cleanup_ctx.append(client_session)
    app.router.add_get('/', home)
    app.router.add_get('/archive/{email}', archive_page)
    app.router.add_get('/api/status', api_status)
    app.router.add_get('/{name:style.css|app.js|archive.js|i18n.js|flag-en.svg|flag-da.svg}', asset)
    app.router.add_post('/start', start)
    app.router.add_post('/api/accounts', account_action)
    app.router.add_post('/api/accounts/{email}/{action:login|close-login|start|rescan|organize|stop}', account_action)
    setup_archive(app, PHOTOS, CONTROL / 'thumbnails', account_names,
                  lambda supplied: isinstance(supplied, str) and hmac.compare_digest(supplied, TOKEN))
    app.router.add_route('*', '/{tail:.*}', proxy)
    web.run_app(app, host='0.0.0.0', port=8787)
