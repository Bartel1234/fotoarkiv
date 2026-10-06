"""Local library reports. Long operations run in the account worker, never the HTTP loop."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from backup_state import atomic, load, settings
from archive_index import records, regular_media, VIDEOS


def now(): return datetime.now().isoformat(timespec='seconds')


def storage(root, state):
    usage = shutil.disk_usage(root)
    config = settings(state)
    reserve = max(int(config['min_free_gb'] * 1024**3), int(usage.total * config['min_free_percent'] / 100))
    report = {'at': now(), 'free': usage.free, 'total': usage.total, 'reserve': reserve,
              'low': usage.free < reserve, 'warning': usage.free < max(reserve * 2, 1024**3)}
    atomic(state / 'storage.json', report)
    return report


def coverage(root, state):
    metadata = load(root / '.fotoarkiv/metadata.json', {})
    if metadata.get('complete') is not True:
        report = {'available': False, 'at': now(), 'years': [], 'albums': []}
    else:
        local = {row[0] for row, _ in records(root) if row[4] > 0}
        years, albums, samples = {}, {}, []
        for item, info in metadata.get('items', {}).items():
            stamp = float(info.get('timestamp', 0)) / 1000
            date = datetime.fromtimestamp(stamp, timezone.utc) + timedelta(seconds=float(info.get('offset', 0)))
            year = str(date.year)
            missing = item not in local
            for key, table in [(year, years), *[(a, albums) for a in info.get('albums', [])]]:
                counts = table.setdefault(key, {'indexed': 0, 'local': 0, 'missing': 0})
                counts['indexed'] += 1; counts['local'] += not missing; counts['missing'] += missing
            if missing and len(samples) < 20: samples.append({'id': item, 'year': date.year})
        report = {'available': True, 'at': now(), 'indexed_at': metadata.get('updated'),
                  'indexed': len(metadata.get('items', {})), 'local': len(set(metadata.get('items', {})) & local),
                  'years': [{'year': k, **v} for k, v in sorted(years.items())],
                  'albums': [{'id': k, 'title': metadata.get('albums', {}).get(k, {}).get('title', k), **v} for k, v in albums.items()],
                  'samples': samples}
        report['missing'] = report['indexed'] - report['local']
        report['albums'].sort(key=lambda a: a['title'].casefold())
    atomic(state / 'coverage.json', report)
    return report


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''): digest.update(block)
    return digest.hexdigest()


def decode(path):
    """A timeout/unsupported codec is unverified, never proof of corruption."""
    if path.suffix.lower() in VIDEOS:
        try:
            result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '2',
                '-protocol_whitelist', 'file,pipe', '-i', str(path), '-map', '0:v?', '-map', '0:a?',
                '-f', 'null', '-'], capture_output=True, timeout=300)
            if result.returncode == 0: return 'decoded'
            text = result.stderr.decode(errors='replace').lower()
            return 'unsupported' if any(s in text for s in ('decoder not found', 'unknown decoder', 'not implemented')) else 'decode-error'
        except (FileNotFoundError, subprocess.TimeoutExpired): return 'unverified'
    try:
        from PIL import Image
        with Image.open(path) as image: image.verify()
        with Image.open(path) as image: image.load()
        return 'decoded'
    except Exception:
        return 'unsupported' if path.suffix.lower() in ('.heic', '.heif') else 'decode-error'


def content_check(root, state, deep=False):
    files = list(records(root))
    report = {'at': now(), 'running': True, 'total': len(files), 'checked': 0, 'changed': 0,
              'decode_errors': 0, 'unverified': 0, 'issues': [], 'deep': deep}
    atomic(state / 'content.json', report)
    database = state / 'checksums.sqlite'
    if database.is_symlink(): raise ValueError('Invalid checksum database')
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS hashes(path TEXT PRIMARY KEY,digest TEXT,size INTEGER,dev INTEGER,inode INTEGER,seen TEXT)')
        stamp = str(time.time_ns())
        current = []
        for row, _ in files:
            relative = row[2]; path = root / relative
            before = regular_media(root, relative)
            if before is None: continue
            digest = sha256(path)
            decoded = decode(path) if deep else 'not-requested'
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('A file changed during checking; rerun when backup is idle')
            previous = db.execute('SELECT digest FROM hashes WHERE path=?', (relative,)).fetchone()
            changed = bool(previous and previous[0] != digest)
            current.append((relative, digest, after.st_size, after.st_dev, after.st_ino))
            report['checked'] += 1; report['changed'] += changed
            report['decode_errors'] += decoded == 'decode-error'
            report['unverified'] += decoded in ('unsupported', 'unverified')
            if changed or decoded in ('decode-error', 'unsupported', 'unverified'):
                if len(report['issues']) < 200: report['issues'].append({'name': row[1], 'path': relative, 'checksum_changed': changed, 'decode': decoded})
            # Preserve the first checksum as a baseline; do not silently accept changed bytes.
            db.execute('INSERT INTO hashes VALUES(?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET size=excluded.size,dev=excluded.dev,inode=excluded.inode,seen=excluded.seen',
                       (relative, digest, after.st_size, after.st_dev, after.st_ino, stamp))
            db.commit()
            if report['checked'] % 25 == 0:
                atomic(state / 'content.json', report)
                print(f"Content check: {report['checked']}/{report['total']}", flush=True)
        # Group current hashes (not the original baseline) so changed content cannot cause false duplicates.
        groups = {}
        for relative, digest, size, dev, inode in current:
            if size: groups.setdefault((digest, size), {})[(dev, inode)] = relative
        duplicates = [{'sha256': digest, 'size': size, 'files': list(paths.values())} for (digest, size), paths in groups.items() if len(paths) > 1]
        duplicate_report = {'at': now(), 'groups': [{**g, 'files': g['files'][:20], 'count': len(g['files'])} for g in duplicates[:200]], 'group_count': len(duplicates),
                            'extra_files': sum(len(g['files']) - 1 for g in duplicates),
                            'extra_bytes': sum((len(g['files']) - 1) * g['size'] for g in duplicates)}
        atomic(state / 'duplicates.json', duplicate_report)
    report['running'] = False; report['finished'] = now()
    atomic(state / 'content.json', report)
    return report


def album_snapshot(root, state):
    metadata = load(root / '.fotoarkiv/metadata.json', {})
    if metadata.get('complete') is True and not (state / 'album-baseline.json').exists():
        atomic(state / 'album-baseline.json', metadata)
    refs = load(state / 'album-references.json', {})
    for row, albums in records(root):
        for album in albums: refs[album['path']] = row[2]
    atomic(state / 'album-references.json', refs)


def album_review(root, state):
    metadata = load(root / '.fotoarkiv/metadata.json', {})
    baseline = load(state / 'album-baseline.json', {})
    if metadata.get('complete') is not True: return {'available': False}
    changes = []
    old, new = baseline.get('albums', {}), metadata.get('albums', {})
    def members(data):
        result = {}
        for item, info in data.get('items', {}).items():
            for album in info.get('albums', []): result.setdefault(album, set()).add(item)
        return result
    old_members, new_members = members(baseline), members(metadata)
    for album in sorted(set(old) | set(new)):
        before, after = old.get(album, {}).get('title'), new.get(album, {}).get('title')
        added = len(new_members.get(album, set()) - old_members.get(album, set()))
        removed = len(old_members.get(album, set()) - new_members.get(album, set()))
        if before != after or added or removed:
            changes.append({'id': album, 'before': before, 'after': after, 'added': added, 'removed': removed})
    current = {a['path'] for _, albums in records(root) for a in albums}
    obsolete = {p: primary for p, primary in load(state / 'album-references.json', {}).items() if p not in current}
    revision = hashlib.sha256(json.dumps([metadata, obsolete], sort_keys=True).encode()).hexdigest()
    report = {'available': True, 'at': now(), 'revision': revision, 'changes': changes, 'obsolete': len(obsolete)}
    atomic(state / 'album-review.json', report)
    return report


def approve_albums(root, state, revision):
    report = album_review(root, state)
    if revision != report.get('revision'): raise ValueError('Album review changed; review again')
    current = {a['path'] for _, albums in records(root) for a in albums}
    refs = load(state / 'album-references.json', {})
    work = []
    for relative, primary in refs.items():
        if relative in current: continue
        # Only old registered album references; primary media is never moved.
        if not relative.startswith('Albums/') or regular_media(root, relative) is None: continue
        if regular_media(root, primary) is None: raise ValueError('Primary file missing; album reference retained')
        source, canonical = root / relative, root / primary
        if not os.path.samefile(source, canonical) and sha256(source) != sha256(canonical):
            raise ValueError('Album reference differs; retained for review')
        target = root / '.fotoarkiv/album-history' / report['revision'][:16] / relative
        # Validate destination before moving anything.
        if '..' in target.parts or not target.resolve().is_relative_to(root.resolve()): raise ValueError('Invalid album history path')
        parent = target
        while parent != root:
            if parent.is_symlink(): raise ValueError('Invalid album history path')
            parent = parent.parent
        if target.exists(): raise ValueError('Album history conflict; originals retained')
        work.append((source, target))
    for source, target in work:
        target.parent.mkdir(parents=True, exist_ok=True); source.rename(target)
        try: source.parent.rmdir()
        except OSError: pass
    atomic(state / 'album-baseline.json', load(root / '.fotoarkiv/metadata.json', {}))
    atomic(state / 'album-references.json', {})
    album_snapshot(root, state); album_review(root, state)
    return len(work)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['storage', 'coverage', 'content', 'duplicates', 'snapshot', 'albums', 'approve-albums', 'interrupted'])
    parser.add_argument('state', type=Path); parser.add_argument('root', type=Path)
    parser.add_argument('--revision', default='')
    args = parser.parse_args()
    if args.action == 'storage': raise SystemExit(3 if storage(args.root, args.state)['low'] else 0)
    elif args.action == 'coverage': coverage(args.root, args.state)
    elif args.action in ('content', 'duplicates'):
        report = content_check(args.root, args.state, args.action == 'content')
        if args.action == 'content' and (report['changed'] or report['decode_errors']): raise SystemExit(1)
    elif args.action == 'interrupted':
        report = load(args.state/'content.json', {})
        if report.get('running'):
            report.update(running=False, interrupted=True, finished=now()); atomic(args.state/'content.json',report)
    elif args.action == 'snapshot': album_snapshot(args.root, args.state)
    elif args.action == 'albums': album_review(args.root, args.state)
    else: approve_albums(args.root, args.state, args.revision)
