"""Persistent account policy, run history and non-destructive local backup checks."""
import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def load(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return default


def settings(state):
    default = {'enabled': True, 'hour': int(os.environ.get('SYNC_HOUR', '3')), 'days': list(range(7)),
               'notify_url': '', 'notify_success': False, 'min_free_gb': 2, 'min_free_percent': 2}
    default.update(load(state / 'settings.json', {}))
    return default


def validate(data):
    enabled, hour, days = data.get('enabled'), data.get('hour'), data.get('days')
    if not isinstance(enabled, bool) or type(hour) is not int or not 0 <= hour <= 23:
        raise ValueError('Invalid schedule')
    if not isinstance(days, list) or not days or any(type(d) is not int or d not in range(7) for d in days):
        raise ValueError('Choose at least one weekday')
    from urllib.parse import urlsplit
    url = data.get('notify_url', '').strip()
    parsed = urlsplit(url)
    if len(url) > 1000 or (url and (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment)):
        raise ValueError('Use an HTTP(S) ntfy topic URL without credentials')
    if not isinstance(data.get('notify_success', False), bool): raise ValueError('Invalid notification setting')
    limits = {}
    for key, default, maximum in [('min_free_gb', 2, 100000), ('min_free_percent', 2, 50)]:
        value = data.get(key, default)
        if type(value) not in (int, float) or not __import__('math').isfinite(value) or not 0 <= value <= maximum:
            raise ValueError('Invalid free-space reserve')
        limits[key] = value
    return {'enabled': enabled, 'hour': hour, 'days': sorted(set(days)), 'notify_url': url,
            'notify_success': data.get('notify_success', False), **limits}


def next_run(config, now=None):
    if not config['enabled']: return 0
    now = datetime.now() if now is None else now
    for offset in range(8):
        candidate = (now + timedelta(days=offset)).replace(hour=config['hour'], minute=0, second=0, microsecond=0)
        if candidate > now and candidate.weekday() in config['days']: return int(candidate.timestamp())
    raise ValueError('Invalid schedule')


def inventory(root):
    count = size = 0
    for directory, folders, files in os.walk(root):
        folders[:] = [f for f in folders if f not in ('Albums', '.fotoarkiv') and not (Path(directory) / f).is_symlink()]
        for name in files:
            path = Path(directory) / name
            if name.startswith('.') or path.suffix.lower() not in MEDIA or path.is_symlink(): continue
            try: stat = path.stat()
            except OSError: continue
            count += 1; size += stat.st_size
    return {'files': count, 'bytes': size}

MEDIA = {'.jpg','.jpeg','.png','.webp','.gif','.heic','.heif','.bmp','.tif','.tiff','.mp4','.mov','.m4v','.webm','.avi','.mkv','.3gp'}


def check(root, state):
    database = root / '.fotoarkiv/catalog.sqlite'
    report = {'at': datetime.now().isoformat(timespec='seconds'), 'checked': 0, 'missing': 0, 'empty': 0,
              'unbacked_items': None, 'samples': [], 'scope': 'catalog-existence-and-size'}
    downloaded = {}
    if database.is_file() and not database.is_symlink() and not database.parent.is_symlink():
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            rows = db.execute('SELECT id,name,path FROM files').fetchall()
        for item, name, relative in rows:
            path = root / relative
            report['checked'] += 1
            valid = '..' not in path.parts and path.is_relative_to(root) and path.resolve().is_relative_to(root.resolve())
            parent = path
            while valid and parent != root:
                if parent.is_symlink(): valid = False; break
                parent = parent.parent
            try: present = valid and path.is_file(); size = path.stat().st_size if present else 0
            except OSError: present, size = False, 0
            reason = 'missing' if not present else 'empty' if not size else ''
            if reason:
                report[reason] += 1
                if len(report['samples']) < 20: report['samples'].append({'name': name, 'reason': reason})
            else: downloaded.setdefault(item, []).append(relative)
        # Include unorganized files in coverage, but never invent catalog mappings.
        present_items = set(downloaded)
        import re
        for folder in root.iterdir():
            if folder.is_dir() and not folder.is_symlink() and re.fullmatch(r'[A-Za-z0-9_-]{20,120}', folder.name):
                if any(p.is_file() and not p.is_symlink() and p.suffix.lower() in MEDIA and p.stat().st_size > 0 for p in folder.iterdir()): present_items.add(folder.name)
        metadata = load(root / '.fotoarkiv/metadata.json', {})
        if metadata.get('complete') is True:
            report['unbacked_items'] = len(set(metadata.get('items', {})) - present_items)
        # Invalidate the downloader's disposable skip manifest only for missing/empty items.
        if report['missing'] or report['empty']:
            invalid = {item for item, name, relative in rows if item not in downloaded}
            # An item with several files must be retried if ANY of its files failed the check.
            for item, name, relative in rows:
                if relative not in downloaded.get(item, []): invalid.add(item)
            for item in invalid: downloaded.pop(item, None)
            atomic(root / '.fotoarkiv/downloaded.json', downloaded)
    report['available'] = database.is_file()
    atomic(state / 'verification.json', report)
    print('Backup check: ' + json.dumps(report), flush=True)
    return report


def prepare_repair(root):
    # Empty files are preserved in a quarantine directory before redownload.
    database = root/'.fotoarkiv/catalog.sqlite'
    if root.is_symlink() or not database.is_file() or database.is_symlink() or database.parent.is_symlink(): return
    import hashlib
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
        rows = db.execute('SELECT path,albums FROM files').fetchall()
    for relative, albums in rows:
        for value in [relative, *[a['path'] for a in json.loads(albums)]]:
            path = root/value
            if path == root or not path.is_relative_to(root) or '..' in path.parts or not path.resolve().is_relative_to(root.resolve()) or path.is_symlink(): raise ValueError('Invalid repair path')
            parent = path.parent
            while parent != root:
                if parent.is_symlink(): raise ValueError('Invalid repair path')
                parent = parent.parent
            if path.is_file() and path.stat().st_size == 0:
                target = root/'.fotoarkiv/quarantine'/str(time.time_ns())/hashlib.sha256(value.encode()).hexdigest()
                target.parent.mkdir(parents=True, exist_ok=True)
                path.rename(target)


def begin(root, state, mode):
    atomic(state / 'current-run.json', {'started': time.time(), 'before': inventory(root), 'mode': mode})


def finish(root, state, result):
    current = load(state / 'current-run.json', {'started': time.time(), 'before': {'files': 0, 'bytes': 0}, 'mode': 'backup'})
    after = inventory(root)
    entry = {'started': datetime.fromtimestamp(current['started']).isoformat(timespec='seconds'),
             'finished': datetime.now().isoformat(timespec='seconds'), 'duration': int(time.time()-current['started']),
             'result': result, 'mode': current['mode'], 'files': after['files'], 'bytes': after['bytes'],
             'new_files': max(0, after['files']-current['before']['files']),
             'new_bytes': max(0, after['bytes']-current['before']['bytes']),
             'verification': load(state / 'verification.json', None)}
    history = load(state / 'history.json', [])
    atomic(state / 'history.json', [entry, *history][:50])
    if result == 0 and current['mode'] in ('backup','repair'): atomic(state / 'last-success.json', entry)
    state.joinpath('current-run.json').unlink(missing_ok=True)
    config = settings(state)
    if current['mode'] in ('backup','repair') and config['notify_url'] and (result not in (0, 130, 131) or (result == 0 and config['notify_success'])):
        import urllib.request
        summary = ('Backup completed' if result == 0 else 'Backup failed; check PhotoHarbor and Google sign-in')
        # Account addresses, file names, media and login secrets are never sent.
        message = f'{summary}. New files: {entry["new_files"]}. Exit code: {result}.'
        req = urllib.request.Request(config['notify_url'], data=message.encode(), method='POST',
                                     headers={'Title': 'PhotoHarbor backup', 'Content-Type': 'text/plain'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status >= 300: raise OSError('Notification rejected')
            atomic(state / 'notification-status.json', {'ok': True, 'at': entry['finished']})
        except Exception:
            atomic(state / 'notification-status.json', {'ok': False, 'at': entry['finished']})
            print('Notification failed; backup result is unchanged', flush=True)
    return entry


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['next', 'begin', 'finish', 'check', 'repair'])
    parser.add_argument('state', type=Path); parser.add_argument('root', type=Path, nargs='?')
    parser.add_argument('--result', type=int, default=0); parser.add_argument('--mode', default='backup')
    args = parser.parse_args()
    if args.action == 'next': print(next_run(settings(args.state)))
    elif args.action == 'begin': begin(args.root, args.state, args.mode)
    elif args.action == 'repair': prepare_repair(args.root)
    elif args.action == 'check': check(args.root, args.state)
    else: finish(args.root, args.state, args.result)
