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
from aiohttp import ClientSession, ClientTimeout, ClientError, WSMsgType, web
from archive import setup as setup_archive
from progress import progress
from login_view import setup as setup_login
from backup_state import settings, validate, atomic, load, next_run
from library_tools import storage, album_review
from operations import live, smtp_validate, smtp_public, smtp_save, send_mail, diagnostics

CONTROL = Path('/control')
PHOTOS = Path(os.environ.get('PHOTOS_DIR', '/photos'))
ACCOUNTS = Path('/accounts')
ACCOUNT_LIST = CONTROL / 'accounts.txt'
PASSWORD = os.environ['APP_PASSWORD']
TOKEN = secrets.token_urlsafe(24)
REMOVAL_TIMEOUT = 45
ASSETS = Path(__file__).parent
try:
    APP_VERSION = (ASSETS / 'VERSION').read_text(encoding='utf-8').strip()
except OSError:
    APP_VERSION = 'development'
DISPLAY_VERSION = 'v' + APP_VERSION if APP_VERSION != 'development' else APP_VERSION
TRANSLATIONS = json.loads((ASSETS / 'translations.json').read_text(encoding='utf-8'))

def translated(request, text):
    return text if request.cookies.get('fotoarkiv_language') == 'da' else TRANSLATIONS.get(text, text)

def page_template(name):
    catalog = json.dumps(TRANSLATIONS, ensure_ascii=False).replace('<', '\u003c')
    return (ASSETS / name).read_text(encoding='utf-8').replace('%%APP_VERSION%%', html.escape(DISPLAY_VERSION)).replace('</head>', '<script id="translation-catalog" type="application/json">' + catalog + '</script></head>')

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
            due=int(value('next-run'))
            account_next_run = datetime.fromtimestamp(due).strftime('%d/%m/%Y kl. %H:%M') if due else 'Automatisk backup slået fra'
        except (ValueError, OverflowError, OSError):
            account_next_run = 'Ikke planlagt'
        running = online and (state / 'running').exists()
        pending = (state / 'start-request').exists()
        stopping = (state / 'stop-request').exists()
        login_active = read('login-active') == email
        phase = progress(state, raw_account_log, online=online, running=running, pending=pending, stopping=stopping, login_active=login_active)
        removing = (state / 'removal-pending').exists()
        if removing: phase['phase'] = 'removing'
        result.append({**account_details(state), **phase, 'removing': removing, 'email': email, 'folder': email, 'count': count, 'bytes': size,
                       'online': online, 'running': online and (state / 'running').exists(),
                       'pending': (state / 'start-request').exists(),
                       'stopping': (state / 'stop-request').exists(),
                       'login_active': read('login-active') == email,
                       'last_run': value('last-run') or 'Ingen endnu', 'last_exit': value('last-exit'),
                       'next_run': account_next_run, 'log': account_log or 'Der er endnu ingen aktivitet for denne konto.'})
    return result


def load_text(path):
    try: return path.read_text().strip()
    except OSError: return ""


def account_details(state):
    return {'live':live(state), 'failure':load(state/'download-failure.json',None),'email_notification':load(state/'email-status.json',None),'settings': settings(state), 'history': load(state/'history.json', []),
            'paused': (state/'paused').exists(), 'pause_reason': load_text(state/'paused'),
            'run_mode': load_text(state/'run-mode') or 'backup',
            'storage': load(state/'storage.json', None), 'coverage': load(state/'coverage.json', None),
            'content': load(state/'content.json', None), 'duplicates': load(state/'duplicates.json', None),
            'album_review': load(state/'album-review.json', None),
            'verification': load(state/'verification.json', None),
            'last_success': load(state/'last-success.json', None),
            'notification': load(state/'notification-status.json', None)}


def status():
    try:
        with (CONTROL / 'activity.log').open(encoding='utf-8', errors='replace') as f:
            raw_log = ''.join(deque(f, maxlen=180))
            log = readable_log(raw_log)[-14000:]
    except OSError:
        log = raw_log = ''
    try:
        due=int(read('next-run'))
        next_run = datetime.fromtimestamp(due).strftime('%d/%m/%Y kl. %H:%M') if due else 'Automatisk backup slået fra'
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
    return {**account_details(CONTROL), **inventory(), **phase, 'accounts': account_summaries(), 'label': label, 'tone': tone, 'online': online,
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
        return web.Response(status=401, text=translated(request, 'Login kræves'), headers={'WWW-Authenticate': 'Basic realm="PhotoHarbor"'})
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
    data['update'] = request.app.get('release_status', {'state':'checking', 'installed':APP_VERSION})
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
    if (CONTROL/'paused').exists(): raise web.HTTPConflict(text='Resume the paused backup from the account card')
    if not (CONTROL / 'running').exists():
        request_login_close('legacy')
        (CONTROL / 'start-request').write_text(str(int(time.time())), encoding='utf-8')
    raise web.HTTPSeeOther('/')


def removal_paths(email):
    paths = (ACCOUNTS / email, PHOTOS / email, CONTROL / 'accounts' / email)
    for path in paths:
        if path.is_symlink() or path.parent.is_symlink() or path.resolve().parent != path.parent.resolve():
            raise web.HTTPConflict(text='Mappen kan ikke bruges')
    return paths

async def remove_account(request, email, data):
    if email == 'legacy' or not EMAIL.fullmatch(email):
        raise web.HTTPBadRequest(text='Kun konti med egen mailmappe kan fjernes')
    if data.get('confirmation') != email or data.get('mode') not in ('keep', 'delete'):
        raise web.HTTPBadRequest(text='Vælg hvad der skal ske med filerne, og bekræft mailadressen')
    async with request.app['account_lock']:
        if email not in account_names(): raise web.HTTPNotFound(text='Ukendt konto')
        profile, photos, state = removal_paths(email)
        state.mkdir(parents=True, exist_ok=True)
        for name in ('worker-stopped', 'login-stopped'):
            (state / name).unlink(missing_ok=True)
        (state / 'removal-pending').write_text('1')
        request_login_close(email)
        for name in ('start-request', 'rescan-request', 'organize-request', 'verify-request', 'repair-request', 'content-request', 'duplicates-request', 'album-approve-request'):
            (state / name).unlink(missing_ok=True)
        try:
            deadline = time.monotonic() + REMOVAL_TIMEOUT
            while not ((state / 'worker-stopped').is_file() and (state / 'login-stopped').is_file() and read('login-active') != email):
                if time.monotonic() >= deadline:
                    raise web.HTTPConflict(text='Kontoen kunne ikke stoppes sikkert. Ingen filer er slettet. Prøv igen efter genstart af sync og login.')
                await asyncio.sleep(.5)
            # No new account operations can start while removal is pending.
            names = [name for name in account_names() if name != email]
            tmp = ACCOUNT_LIST.with_suffix('.tmp')
            tmp.write_text(''.join(name + '\n' for name in names), encoding='utf-8')
            tmp.replace(ACCOUNT_LIST)
            index = request.app['archive_index']
            task = index.tasks.get(email)
            if task: await asyncio.gather(asyncio.shield(task), return_exceptions=True)
            def clean():
                removal_paths(email)
                if data['mode'] == 'delete' and photos.exists(): shutil.rmtree(photos)
                if profile.exists(): shutil.rmtree(profile)
                for path in (CONTROL / 'thumbnails').glob(email + '-*'):
                    if not re.fullmatch(r'[A-Za-z0-9_-]{20,120}', path.name[len(email)+1:]): continue
                    if path.is_symlink(): path.unlink()
                    elif path.is_dir(): shutil.rmtree(path)
                index.target(email).unlink(missing_ok=True)
                if state.exists(): shutil.rmtree(state)
            await asyncio.to_thread(clean)
            index.states.pop(email, None)
            _account_cache['at'] = 0; _cache['at'] = 0
            return web.json_response({'ok': True, 'kept_data': data['mode'] == 'keep', 'folder': str(photos)})
        finally:
            (state / 'removal-pending').unlink(missing_ok=True)

async def account_action(request):
    if request.content_type != 'application/json' or (request.content_length or 0) > 4096:
        raise web.HTTPBadRequest(text='Forkert formular')
    try:
        data = await request.json()
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text='Ugyldig JSON')
    if not isinstance(data, dict):
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
    if action == 'remove':
        return await remove_account(request, email, data)
    if email != 'legacy' and (CONTROL / 'accounts' / email / 'removal-pending').exists():
        raise web.HTTPConflict(text='Kontoen er ved at blive fjernet')
    state = CONTROL if email == 'legacy' else CONTROL / 'accounts' / email
    state.mkdir(parents=True, exist_ok=True)
    async with request.app['account_lock']:
        if email != 'legacy' and (email not in account_names() or (state/'removal-pending').exists()):
            raise web.HTTPConflict(text='Account membership changed; refresh the portal')
        if action == 'settings':
            try: config = validate(data.get('settings', {}))
            except (ValueError, TypeError, AttributeError) as error: raise web.HTTPBadRequest(text=str(error))
            atomic(state/'settings.json', config)
            return web.json_response({'ok':True, 'settings':config})
        if action == 'login':
            if read('login-active') != email:
                (CONTROL / 'login-request').write_text(f'{email} {int(time.time())}\n', encoding='utf-8')
        elif action == 'close-login':
            request_login_close(email)
        elif action == 'pause':
            if not (state/'running').exists() or load_text(state/'run-mode') not in ('backup','repair'):
                raise web.HTTPConflict(text='Only an active backup can be paused')
            (state/'paused').write_text('user')
            (state/'stop-request').write_text('1')
            (state/'start-request').unlink(missing_ok=True)
        elif action == 'resume':
            if not (state/'paused').exists() or (state/'running').exists() or (state/'stop-request').exists():
                raise web.HTTPConflict(text='Wait until the paused backup has stopped')
            root = PHOTOS if email == 'legacy' else PHOTOS/email
            if (await asyncio.to_thread(storage, root, state))['low']:
                raise web.HTTPConflict(text='Free more disk space or adjust the reserve before resuming')
            (state/'paused').unlink()
            request_login_close(email)
            (state/'start-request').write_text('1')
        elif action == 'stop':
            state = CONTROL if email == 'legacy' else CONTROL / 'accounts' / email
            (state / 'stop-request').write_text(str(int(time.time())), encoding='utf-8')
            (state/'paused').unlink(missing_ok=True)
            for name in ('start-request', 'rescan-request', 'organize-request', 'verify-request', 'repair-request', 'content-request', 'duplicates-request', 'album-approve-request'):
                (state / name).unlink(missing_ok=True)
        elif action in ('start', 'rescan', 'organize', 'verify', 'repair', 'content', 'duplicates', 'approve-albums'):
            state = CONTROL if email == 'legacy' else CONTROL / 'accounts' / email
            if action in ('verify', 'repair', 'content', 'duplicates', 'approve-albums'):
                if (state/'running').exists() or (state/'start-request').exists():
                    raise web.HTTPConflict(text='Wait for the current job to finish')
                if action == 'approve-albums':
                    root = PHOTOS if email == 'legacy' else PHOTOS/email
                    review = await asyncio.to_thread(album_review, root, state)
                    if data.get('confirmation') != email or data.get('revision') != review.get('revision'):
                        raise web.HTTPConflict(text='Review album changes and confirm the account before applying')
                    (state/'album-approve-revision').write_text(review['revision'])
                    (state/'album-approve-request').write_text('1')
                elif action in ('verify','content','duplicates'): (state/({'verify':'verify','content':'content','duplicates':'duplicates'}[action]+'-request')).write_text('1')
                else:
                    (state/'repair-request').write_text('1')
                    (state/'rescan-request').write_text('1')
            if action == 'organize':
                if (state / 'running').exists():
                    raise web.HTTPConflict(text='Vent til den aktuelle backup er afsluttet')
                (state / 'organize-request').write_text(str(int(time.time())), encoding='utf-8')
            if action == 'rescan':
                if (state / 'running').exists():
                    raise web.HTTPConflict(text='Vent til den aktuelle synkronisering er afsluttet')
                (state / 'rescan-request').write_text(str(int(time.time())), encoding='utf-8')
            if action in ('start','rescan','repair'): (state/'paused').unlink(missing_ok=True)
            if action not in ('verify','content','duplicates','approve-albums'): request_login_close(email)
            (state / 'start-request').write_text(str(int(time.time())), encoding='utf-8')
        else:
            raise web.HTTPNotFound()
        return web.json_response({'ok': True})


def version_key(version):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?', version)
    if not match: return None
    return tuple(map(int, match.groups()[:3])) + (int(match[4]) if match[4] else 10**9,)


def configuration_export():
    accounts = []
    for email in ['legacy', *account_names()]:
        state = CONTROL if email == 'legacy' else CONTROL/'accounts'/email
        config = settings(state)
        config['notify_url'] = ''  # Topic URLs can contain secrets; re-enter them after restoring.
        accounts.append({'email': email, 'settings': config})
    return {'format': 'photoharbor-settings', 'schema': 1, 'version': APP_VERSION, 'accounts': accounts}


def configuration_validate(document):
    if not isinstance(document, dict) or document.get('format') != 'photoharbor-settings' or document.get('schema') != 1:
        raise ValueError('Invalid PhotoHarbor settings backup')
    entries = document.get('accounts')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 128: raise ValueError('Invalid account list')
    seen, result = set(), []
    for entry in entries:
        if not isinstance(entry, dict): raise ValueError('Invalid account')
        email = entry.get('email', '')
        if not isinstance(email, str) or len(email) > 128 or (email != 'legacy' and not EMAIL.fullmatch(email)) or email != email.lower() or email in seen:
            raise ValueError('Invalid or duplicate account')
        seen.add(email)
        config = validate(entry.get('settings', {}))
        config['notify_url'] = ''
        result.append({'email': email, 'settings': config})
    return result


async def configuration_action(request):
    if request.content_type != 'application/json' or (request.content_length or 0) > 262144: raise web.HTTPBadRequest()
    try: data = await request.json()
    except ValueError: raise web.HTTPBadRequest()
    if not isinstance(data, dict) or not hmac.compare_digest(str(data.get('token','')), TOKEN): raise web.HTTPForbidden()
    action = request.match_info['action']
    if action == 'export':
        return web.json_response(configuration_export(), headers={'Content-Disposition':'attachment; filename="photoharbor-settings.json"','Cache-Control':'no-store'})
    try: entries = configuration_validate(data.get('document'))
    except (ValueError, TypeError, AttributeError) as error: raise web.HTTPBadRequest(text=str(error))
    if action == 'preview':
        return web.json_response({'accounts':[{'email': e['email'], 'new': e['email'] != 'legacy' and e['email'] not in account_names()} for e in entries]})
    if data.get('confirmation') != 'IMPORT': raise web.HTTPBadRequest(text='Confirm the settings restore')
    async with request.app['account_lock']:
        for entry in entries:
            email = entry['email']; state = CONTROL if email == 'legacy' else CONTROL/'accounts'/email
            if any((state/name).exists() for name in ('running','start-request','removal-pending')):
                raise web.HTTPConflict(text='Stop account jobs before restoring settings')
            if email != 'legacy': removal_paths(email)
        names = account_names(); previous = []
        try:
            for entry in entries:
                email = entry['email']; state = CONTROL if email == 'legacy' else CONTROL/'accounts'/email
                if email != 'legacy':
                    for folder in (state, ACCOUNTS/email/'gphotos-cdp', PHOTOS/email):
                        if folder.is_symlink(): raise web.HTTPConflict(text='Invalid account folder')
                        folder.mkdir(parents=True, exist_ok=True)
                    if email not in names: names.append(email)
                path = state/'settings.json'
                previous.append((path, path.read_bytes() if path.exists() else None))
                config = entry['settings']
                # Existing notification destinations are preserved, never imported from a file.
                config['notify_url'] = settings(state)['notify_url']
                atomic(path, config)
            tmp = ACCOUNT_LIST.with_suffix('.tmp'); tmp.write_text(''.join(e+'\n' for e in names)); tmp.replace(ACCOUNT_LIST)
        except Exception:
            for path, original in previous:
                if original is None: path.unlink(missing_ok=True)
                else: path.write_bytes(original)
            raise
        _account_cache['at'] = 0
    return web.json_response({'ok': True, 'accounts': len(entries)})

async def email_settings(request):
    path=CONTROL/'smtp.json'
    if request.method=='GET': return web.json_response(smtp_public(load(path,{})),headers={'Cache-Control':'no-store'})
    if request.content_type!='application/json' or (request.content_length or 0)>10000: raise web.HTTPBadRequest()
    try: data=await request.json()
    except ValueError: raise web.HTTPBadRequest()
    if not isinstance(data,dict) or not hmac.compare_digest(str(data.get('token','')),TOKEN): raise web.HTTPForbidden()
    async with request.app['account_lock']:
        if request.match_info['action']=='save':
            try: config=smtp_validate(data.get('settings'),load(path,{}))
            except (ValueError,TypeError): raise web.HTTPBadRequest(text='Invalid email settings; use encrypted SMTP and complete addresses')
            await asyncio.to_thread(smtp_save,path,config)
            return web.json_response(smtp_public(config),headers={'Cache-Control':'no-store'})
        config=load(path,{})
        try: await asyncio.to_thread(send_mail,config,'PhotoHarbor test email','PhotoHarbor email delivery is working. This message contains no media or Google sign-in information.')
        except Exception: raise web.HTTPBadGateway(text='Test email failed. Check SMTP host, encryption, sender and credentials.')
    return web.json_response({'ok':True})

async def diagnostic_download(request):
    try: data=await request.json()
    except ValueError: raise web.HTTPBadRequest()
    if not isinstance(data,dict) or not hmac.compare_digest(str(data.get('token','')),TOKEN): raise web.HTTPForbidden()
    email=request.match_info['email']
    if email!='legacy' and email not in account_names(): raise web.HTTPNotFound()
    state=CONTROL if email=='legacy' else CONTROL/'accounts'/email
    report=await asyncio.to_thread(diagnostics,state,APP_VERSION)
    return web.json_response(report,headers={'Content-Disposition':'attachment; filename="photoharbor-diagnostics.json"','Cache-Control':'no-store'})


async def release_watch(app):
    # Public release metadata only. No user/account data is sent to GitHub.
    while True:
        try:
            async with app['session'].get('https://api.github.com/repos/Bartel1234/fotoarkiv/releases?per_page=100',
                    headers={'Accept':'application/vnd.github+json'}, timeout=ClientTimeout(total=15)) as response:
                response.raise_for_status(); releases = await response.json()
            candidates = [r for r in releases if not r.get('draft') and version_key(r.get('tag_name',''))]
            if not candidates: raise ValueError('No published releases')
            latest = max(candidates, key=lambda r: version_key(r['tag_name']))
            url = latest.get('html_url','')
            if not url.startswith('https://github.com/Bartel1234/fotoarkiv/releases/tag/'): raise ValueError('Invalid release URL')
            channels={}
            for channel,prerelease in [('stable',False),('beta',True)]:
                choices=[r for r in candidates if bool(r.get('prerelease'))==prerelease]
                if choices:
                    candidate=max(choices,key=lambda r:version_key(r['tag_name']))
                    link=candidate.get('html_url','')
                    if link.startswith('https://github.com/Bartel1234/fotoarkiv/releases/tag/'):
                        channels[channel]={'version':candidate['tag_name'],'url':link,'notes':str(candidate.get('body') or '')[:12000]}
            installed = version_key(APP_VERSION)
            app['release_status'] = {'state':'available' if installed and version_key(latest['tag_name']) > installed else 'current',
                'installed':APP_VERSION, 'latest':latest['tag_name'], 'url':url,'channels':channels}
        except (ClientError, ValueError, TypeError, asyncio.TimeoutError):
            app['release_status'] = {**app.get('release_status', {}), 'state':'unavailable', 'installed':APP_VERSION}
        await asyncio.sleep(21600)


async def client_session(app):
    app['session'] = ClientSession(timeout=ClientTimeout(total=None, sock_connect=15))
    task = asyncio.create_task(release_watch(app))
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
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
    app.router.add_get('/{name:style.css|app.js|enhancements.js|upgrades.js|archive.js|i18n.js|flag-en.svg|flag-da.svg|photoharbor.svg|photoharbor-wordmark.svg|photoharbor-192.png|photoharbor-512.png|favicon.ico}', asset)
    app.router.add_post('/start', start)
    app.router.add_post('/api/accounts', account_action)
    app.router.add_post('/api/config/{action:export|preview|restore}', configuration_action)
    app.router.add_get('/api/email', email_settings)
    app.router.add_post('/api/email/{action:save|test}', email_settings)
    app.router.add_post('/api/diagnostics/{email}', diagnostic_download)
    app.router.add_post('/api/accounts/{email}/{action:login|close-login|start|rescan|organize|stop|remove|settings|verify|repair|pause|resume|content|duplicates|approve-albums}', account_action)
    setup_archive(app, PHOTOS, CONTROL / 'thumbnails', account_names,
                  lambda supplied: isinstance(supplied, str) and hmac.compare_digest(supplied, TOKEN))
    setup_login(app, CONTROL, account_names, TOKEN,
                lambda supplied: isinstance(supplied, str) and hmac.compare_digest(supplied, TOKEN), version=DISPLAY_VERSION)
    async def missing(request):
        raise web.HTTPNotFound()
    app.router.add_route('*', '/{tail:.*}', missing)
    web.run_app(app, host='0.0.0.0', port=8787)
