"""Disposable, persistent read index. Media and the backup catalog remain authoritative."""
import asyncio
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

ITEM=re.compile(r'^[A-Za-z0-9_-]{20,120}$')
VIDEOS={'.mp4','.mov','.m4v','.webm','.avi','.mkv','.3gp'}
MEDIA=VIDEOS|{'.jpg','.jpeg','.png','.webp','.gif','.heic','.heif','.bmp','.tif','.tiff'}
SCHEMA=3

def source_signature(root):
    def stamp(path):
        try:
            st=path.stat();return (st.st_mtime_ns,st.st_size)
        except FileNotFoundError:return None
    return (stamp(root),stamp(root/'.fotoarkiv/catalog.sqlite'))

def regular_media(root,relative):
    path=root/relative
    if path.suffix.lower() not in MEDIA or not path.resolve().is_relative_to(root.resolve()):return None
    if not path.is_relative_to(root):return None
    parent=path
    while parent!=root:
        if parent.is_symlink():return None
        parent=parent.parent
    try:
        return path.stat() if path.is_file() else None
    except OSError:return None

def records(root):
    known=set()
    database=root/'.fotoarkiv/catalog.sqlite'
    if database.is_symlink() or database.parent.is_symlink():raise ValueError('Ugyldigt katalog')
    if database.is_file():
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
            rows=db.execute('SELECT id,name,path,timestamp,albums,date_label FROM files').fetchall()
        for item,name,relative,stamp,albums,label in rows:
            if not ITEM.fullmatch(item):continue
            stat=regular_media(root,relative)
            if stat is None:continue
            known.add((item,name))
            yield (item,name,relative,stamp,stat.st_size,'video' if Path(relative).suffix.lower() in VIDEOS else 'image',label,'google',name.casefold()),json.loads(albums)
    with os.scandir(root) as folders:
        for folder in folders:
            if not ITEM.fullmatch(folder.name) or not folder.is_dir(follow_symlinks=False):continue
            try:
                with os.scandir(folder.path) as files:
                    for file in files:
                        if (folder.name,file.name) in known or file.name.startswith('.') or Path(file.name).suffix.lower() not in MEDIA or not file.is_file(follow_symlinks=False):continue
                        try:stat=file.stat(follow_symlinks=False)
                        except OSError:continue
                        yield (folder.name,file.name,folder.name+'/'+file.name,stat.st_mtime,stat.st_size,'video' if Path(file.name).suffix.lower() in VIDEOS else 'image',datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M'),'download',file.name.casefold()),[]
            except FileNotFoundError:continue

def rebuild(root,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(target) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS files (id TEXT,name TEXT,path TEXT,stamp REAL,size INTEGER,kind TEXT,label TEXT,source TEXT,search_name TEXT,PRIMARY KEY(id,name));
        CREATE INDEX IF NOT EXISTS files_date ON files(stamp DESC,id DESC,name DESC);
        CREATE TABLE IF NOT EXISTS members (album TEXT,id TEXT,name TEXT,stamp REAL,PRIMARY KEY(album,id,name));
        CREATE INDEX IF NOT EXISTS members_page ON members(album,stamp DESC,id DESC,name DESC);
        CREATE INDEX IF NOT EXISTS members_file ON members(id,name);
        CREATE TABLE IF NOT EXISTS albums (id TEXT PRIMARY KEY,title TEXT,count INTEGER);
        ''')
        columns = {row[1] for row in db.execute('PRAGMA table_info(files)')}
        for column in ('year','month'):
            if column not in columns: db.execute('ALTER TABLE files ADD COLUMN '+column+' INTEGER')
        if 'day' not in columns: db.execute('ALTER TABLE files ADD COLUMN day TEXT')
        db.execute('CREATE INDEX IF NOT EXISTS files_calendar ON files(year,month,kind)')
        db.execute('BEGIN')
        db.execute('DELETE FROM files');db.execute('DELETE FROM members');db.execute('DELETE FROM albums')
        counts={}
        for row,albums in records(root):
            try: calendar = datetime.strptime(row[6], '%d/%m/%Y %H:%M')
            except ValueError: calendar = datetime.fromtimestamp(row[3])
            db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (*row, calendar.year, calendar.month, calendar.date().isoformat()))
            for album in albums:
                key=album['id'];title=album['title']
                inserted=db.execute('INSERT OR IGNORE INTO members VALUES(?,?,?,?)',(key,row[0],row[1],row[3])).rowcount
                counts.setdefault(key,[title,0])[1]+=inserted
        db.executemany('INSERT INTO albums VALUES(?,?,?)',[(key,title,n) for key,(title,n) in counts.items()])
        db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('schema',str(SCHEMA)))
        db.commit()

def ready(target):
    if not target.is_file():return False
    try:
        with sqlite3.connect(target.as_uri()+'?mode=ro',uri=True) as db:
            return db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()==(str(SCHEMA),)
    except sqlite3.DatabaseError:return False

def query(target,album,search,page,year=0,month=0,kind="",sort="newest",start='',end=''):
    with sqlite3.connect(target.as_uri()+'?mode=ro',uri=True) as db:
        db.create_function('casefold',1,lambda value:value.casefold(),deterministic=True)
        params=[]
        if album and album!='__none__':
            source='members AS m JOIN files AS f ON f.id=m.id AND f.name=m.name'
            where='m.album=?';params.append(album)
            order='m.stamp DESC,m.id DESC,m.name DESC'
        else:
            source='files AS f';where='1';order='f.stamp DESC,f.id DESC,f.name DESC'
            if album=='__none__':where+=' AND NOT EXISTS (SELECT 1 FROM members AS m WHERE m.id=f.id AND m.name=f.name)'
        if search:
            where += ' AND (instr(f.search_name,?)>0 OR EXISTS (SELECT 1 FROM members sm JOIN albums sa ON sa.id=sm.album WHERE sm.id=f.id AND sm.name=f.name AND instr(casefold(sa.title),?)>0))'
            params.extend([search.casefold(), search.casefold()])
        if year: where+=' AND f.year=?';params.append(year)
        if month: where+=' AND f.month=?';params.append(month)
        if kind: where+=' AND f.kind=?';params.append(kind)
        if start: where+=' AND f.day>=?';params.append(start)
        if end: where+=' AND f.day<=?';params.append(end)
        if sort=='oldest': order=order.replace('DESC','ASC')
        total=db.execute('SELECT COUNT(*) FROM '+source+' WHERE '+where,params).fetchone()[0]
        rows=db.execute('SELECT f.id,f.name,f.size,f.kind,f.label,f.source FROM '+source+' WHERE '+where+' ORDER BY '+order+' LIMIT 48 OFFSET ?',params+[(page-1)*48]).fetchall()
        albums=[{'id':id,'title':title,'count':n} for id,title,n in db.execute('SELECT id,title,count FROM albums')]
        albums.sort(key=lambda a:a['title'].casefold())
        return rows,total,albums


def range_members(target, year=0, month=0, start='', end='', kind=''):
    with sqlite3.connect(target.as_uri()+'?mode=ro', uri=True) as db:
        where, params = ['1'], []
        for column, value, operator in [('year',year,'='),('month',month,'='),('day',start,'>='),('day',end,'<='),('kind',kind,'=')]:
            if value: where.append(column+operator+'?'); params.append(value)
        return db.execute('SELECT path FROM files WHERE '+' AND '.join(where)+' ORDER BY day,id,name',params).fetchall()

class ArchiveIndex:
    def __init__(self,directory):
        self.directory=directory;self.states={};self.tasks={}
    def target(self,account):return self.directory/(account+'.sqlite')
    async def build(self,account,root):
        state=self.states.setdefault(account,{'at':0,'signature':None})
        signature=await asyncio.to_thread(source_signature,root)
        try:
            await asyncio.to_thread(rebuild,root,self.target(account))
            state.update(at=time.monotonic(),signature=signature)
        except Exception:
            state['at']=time.monotonic()  # Retry later while serving the last good snapshot.
            raise
        finally:self.tasks.pop(account,None)
    async def ensure(self,account,root):
        target=self.target(account)
        state=self.states.setdefault(account,{'at':0,'signature':None})
        exists=await asyncio.to_thread(ready,target)
        if not exists:
            task=self.tasks.get(account)
            if task is None:
                task=asyncio.create_task(self.build(account,root));self.tasks[account]=task
            await asyncio.shield(task)
            return target
        now=time.monotonic()
        if now-state['at']>=30 and account not in self.tasks:
            signature=await asyncio.to_thread(source_signature,root)
            if signature!=state['signature'] or now-state['at']>=300:
                task=asyncio.create_task(self.build(account,root));self.tasks[account]=task
                def done(task):
                    if not task.cancelled():
                        error=task.exception()
                        if error:
                            import logging
                            logging.exception('Archive index refresh failed',exc_info=(type(error),error,error.__traceback__))
                task.add_done_callback(done)
        return target
    async def close(self):
        # Finish worker-thread writes before releasing the application's filesystem.
        if self.tasks:await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)

def album_members(target, album):
    with sqlite3.connect(target.as_uri()+'?mode=ro',uri=True) as db:
        title=db.execute('SELECT title FROM albums WHERE id=?',(album,)).fetchone()
        if title is None:return None,[]
        rows=db.execute('SELECT f.path FROM members m JOIN files f ON f.id=m.id AND f.name=m.name WHERE m.album=? ORDER BY m.stamp,m.id,m.name',(album,)).fetchall()
        return title[0],[row[0] for row in rows]
