#!/usr/bin/env python3
"""Resumable local organization. Never change media bytes or overwrite a conflict."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

ID = re.compile(r'^[A-Za-z0-9_-]{20,120}$')
MEDIA = {'.jpg','.jpeg','.png','.webp','.gif','.heic','.heif','.bmp','.tif','.tiff','.mp4','.mov','.m4v','.webm','.avi','.mkv','.3gp'}

def safe(text):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip(' .')[:100] or 'Uden navn'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.digest()

def is_within(path,root):
    # Path.is_relative_to requires Python 3.9; the desktop base uses Python 3.8.
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

def inside(root,path):
    if not is_within(path,root) or not is_within(path.resolve(),root.resolve()): raise ValueError('Ugyldig sti')
    current=path
    while current != root:
        if current.is_symlink(): raise ValueError('Symlink afvist: '+str(current))
        current=current.parent
    if root.is_symlink(): raise ValueError('Symlink rod afvist')

def materialize(root,source,target):
    inside(root,source); inside(root,target)
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if target.is_file() and os.path.samefile(source,target): return 'existing'
        if not target.is_file() or source.stat().st_size!=target.stat().st_size or digest(source)!=digest(target):
            raise ValueError('Filkonflikt; original bevaret: '+str(target))
        return 'existing'
    try:
        os.link(source,target)
        return 'link'
    except OSError:
        temporary=target.with_name('.'+target.name+'.tmp')
        inside(root,temporary)
        if temporary.exists():
            if not temporary.is_file(): raise ValueError('Ugyldig midlertidig fil')
            temporary.unlink()  # Only our own staging file; source is still intact.
        with source.open('rb') as src, temporary.open('xb') as dst:
            shutil.copyfileobj(src,dst,1024*1024); dst.flush(); os.fsync(dst.fileno())
        if digest(source)!=digest(temporary): raise ValueError('Kopiverifikation fejlede')
        shutil.copystat(source,temporary)
        # Exclusive hardlink promotion prevents overwriting an existing target.
        os.link(temporary,target); temporary.unlink()
        return 'copy'

def organize(root,only=None):
    root=root.absolute(); inside(root,root)
    state=root/'.fotoarkiv'; inside(root,state)
    metadata=json.loads((state/'metadata.json').read_text())
    if metadata.get('version')!=1 or metadata.get('complete') is not True: raise ValueError('Albumindeks er ufuldstændigt')
    inside(root,state/'catalog.sqlite')
    db=sqlite3.connect(state/'catalog.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS files (id TEXT, name TEXT, path TEXT, timestamp REAL, albums TEXT, date_label TEXT, PRIMARY KEY(id,name))')
    moved=copies=unknown=0
    try:
        # Existing catalog rows are included so new/renamed albums are added on later runs.
        work={}
        rows=db.execute('SELECT id,name,path FROM files WHERE id=?',(only,)) if only else db.execute('SELECT id,name,path FROM files')
        for item,name,relative in rows:
            source=root/relative; inside(root,source)
            if source.is_file(): work[(item,name)]=source
        for folder in ([root/only] if only else root.iterdir()):
            if folder.is_symlink() or not folder.is_dir() or not ID.fullmatch(folder.name): continue
            for source in folder.iterdir():
                if source.is_file() and not source.is_symlink() and source.suffix.lower() in MEDIA:
                    work[(folder.name,source.name)]=source
        for (item,name),source in work.items():
            info=metadata['items'].get(item)
            if not info: unknown+=1; continue
            stamp=float(info['timestamp'])/1000
            offset=float(info.get('offset',0))
            date=datetime.fromtimestamp(stamp,timezone.utc)+timedelta(seconds=offset)
            leaf=safe(Path(name).stem)+'--'+item+Path(name).suffix.lower()
            target=root/'Bibliotek'/str(date.year)/f'{date.month:02d}'/leaf
            method=materialize(root,source,target) if source!=target else 'existing'
            if method=='copy': copies+=1
            os.utime(target,(target.stat().st_atime,stamp))
            albums=[]
            for album in info.get('albums',[]):
                title=metadata['albums'][album]['title']
                folder=safe(title)+'--'+hashlib.sha256(album.encode()).hexdigest()[:12]
                album_path=root/'Albums'/folder/leaf
                if materialize(root,target,album_path)=='copy': copies+=1
                os.utime(album_path,(album_path.stat().st_atime,stamp))
                albums.append({'id':album,'title':title,'path':str(album_path.relative_to(root))})
            db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)',(item,name,str(target.relative_to(root)),stamp,json.dumps(albums,ensure_ascii=False),date.strftime('%d/%m/%Y %H:%M')))
            db.commit()  # Persist mapping BEFORE removing old source: safe after interruption.
            if source!=target:
                source.unlink(); moved+=1
                try: source.parent.rmdir()
                except OSError: pass
            if not only and moved and moved%100==0: print(f'Organiseret {moved} filer',flush=True)
        if only: return
        downloaded={}
        for item,path in db.execute('SELECT id,path FROM files'):
            downloaded.setdefault(item,[]).append(path)
        tmp=state/'downloaded.json.tmp'; tmp.write_text(json.dumps(downloaded)); tmp.replace(state/'downloaded.json')
        copies=0
        for relative,albums in db.execute('SELECT path,albums FROM files'):
            canonical=root/relative
            for album in json.loads(albums):
                album_path=root/album['path']; inside(root,album_path)
                if canonical.is_file() and album_path.is_file() and not os.path.samefile(canonical,album_path): copies+=1
        report={'moved':moved,'copies':copies,'missing_metadata':unknown,'updated':datetime.now(timezone.utc).isoformat()}
        tmp=state/'organization.json.tmp'; tmp.write_text(json.dumps(report)); tmp.replace(state/'organization.json')
        print(f'Organisering færdig: {moved} flyttet, {copies} albumkopier, {unknown} uden metadata',flush=True)
    finally: db.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path,nargs='?');parser.add_argument('--download',type=Path)
    args=parser.parse_args()
    if args.download:
        item=args.download.parent.name
        if ID.fullmatch(item):
            root=args.download.parent.parent
            if (root/'.fotoarkiv/metadata.json').is_file(): organize(root,item)
    elif args.root: organize(args.root)
    else: parser.error('Angiv mappe eller downloadfil')
