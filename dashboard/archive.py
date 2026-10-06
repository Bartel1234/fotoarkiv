"""Read-only browser for downloaded Google Photos media."""
import asyncio
import os
import re
import json
import hashlib
import sqlite3
from pathlib import Path
from urllib.parse import quote

from aiohttp import web
from PIL import Image, ImageOps, UnidentifiedImageError
from zipstream import ZipStream, ZIP_STORED
from archive_index import ArchiveIndex, query as query_index, album_members, range_members


def date_filters(data):
    from datetime import date
    try:
        year = int(data.get('year','0')); month = int(data.get('month','0'))
        start, end = data.get('from',''), data.get('to','')
        for value in (start, end):
            if value and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) or not date.fromisoformat(value)): raise ValueError()
        if not 0 <= year <= 9999 or not 0 <= month <= 12 or (start and end and start > end): raise ValueError()
    except (ValueError, TypeError): raise web.HTTPBadRequest(text='Invalid date range')
    kind = data.get('kind','')
    if kind not in ('','image','video'): raise web.HTTPBadRequest(text='Invalid media filter')
    return year, month, start, end, kind

ITEM = re.compile(r'^[A-Za-z0-9_-]{20,120}$')
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif', '.bmp', '.tif', '.tiff'}
VIDEOS = {'.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv', '.3gp'}
PAGE_SIZE = 48
MAX_ZIP_FILES = 500
MAX_ZIP_BYTES = 10 * 1024**3


def account_root(request, account):
    if account != 'legacy' and account not in request.app['account_names']():
        raise web.HTTPNotFound(text='Ukendt konto')
    if account!='legacy' and (request.app['thumb_root'].parent/'accounts'/account/'removal-pending').exists():
        raise web.HTTPConflict(text='Account removal is in progress')
    root = request.app['photos_root'] / ('' if account == 'legacy' else account)
    if root.is_symlink() or not root.is_dir():
        raise web.HTTPNotFound(text='Kontoens mappe findes ikke')
    return root


def catalog_file(root, item, name):
    database=root / '.fotoarkiv' / 'catalog.sqlite'
    if database.is_symlink() or database.parent.is_symlink():
        raise web.HTTPForbidden(text='Ugyldigt katalog')
    if not database.is_file(): return None
    with sqlite3.connect(database.as_uri() + '?mode=ro',uri=True) as db:
        row=db.execute('SELECT path FROM files WHERE id=? AND name=?',(item,name)).fetchone()
    return row[0] if row else None

def checked_path(root, relative):
    path=root / relative
    if not path.is_relative_to(root): raise web.HTTPForbidden()
    parent=path
    while parent != root:
        if parent.is_symlink(): raise web.HTTPForbidden()
        parent=parent.parent
    if not path.resolve().is_relative_to(root.resolve()): raise web.HTTPForbidden()
    return path


def media_path(request, account, item, name):
    root = account_root(request, account)
    if not isinstance(item, str) or not isinstance(name, str) or not ITEM.fullmatch(item) or not name or name.startswith('.') or name != Path(name).name or '/' in name or '\\' in name:
        raise web.HTTPBadRequest(text='Ugyldig fil')
    mapped=catalog_file(root,item,name)
    path=checked_path(root,mapped) if mapped else root / item / name
    folder=path.parent
    if folder.is_symlink() or path.is_symlink() or not path.is_file():
        raise web.HTTPNotFound(text='Filen findes ikke')
    if path.suffix.lower() not in IMAGES | VIDEOS or not path.resolve().is_relative_to(root.resolve()):
        raise web.HTTPNotFound(text='Filen er ikke et billede eller en video')
    return path


def favorite_database(root,create=True):
    target=checked_path(root,'.fotoarkiv/favorites.sqlite')
    if not create: return target if target.is_file() else None
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(target) as db:
        db.execute('CREATE TABLE IF NOT EXISTS favorites(id TEXT,name TEXT,PRIMARY KEY(id,name))')
    return target

async def favorite_action(request):
    if request.content_type!='application/json' or (request.content_length or 0)>4096: raise web.HTTPBadRequest()
    try: data=await request.json()
    except ValueError: raise web.HTTPBadRequest()
    if not isinstance(data,dict) or not request.app['valid_token'](data.get('token','')): raise web.HTTPForbidden()
    if type(data.get('favorite')) is not bool: raise web.HTTPBadRequest()
    def save(root):
        target=favorite_database(root)
        with sqlite3.connect(target) as db:
            if data['favorite']: db.execute('INSERT OR IGNORE INTO favorites VALUES(?,?)',(data['id'],data['name']))
            else: db.execute('DELETE FROM favorites WHERE id=? AND name=?',(data['id'],data['name']))
    async with request.app.get('account_lock',request.app['favorite_lock']):
        root=account_root(request,data.get('account',''))
        await asyncio.to_thread(media_path,request,data.get('account',''),data.get('id',''),data.get('name',''))
        await asyncio.to_thread(save,root)
    return web.json_response({'ok':True,'favorite':data['favorite']})


async def listing(request):
    account=request.query.get('account','')
    root=account_root(request,account)
    try: page=int(request.query.get('page','1'))
    except ValueError:raise web.HTTPBadRequest(text='Ugyldigt sidetal')
    if page<1 or page>100000:raise web.HTTPBadRequest(text='Ugyldigt sidetal')
    album=request.query.get('album','')[:200]
    search=request.query.get('q','').strip()[:100]
    year,month,start,end,kind = date_filters(request.query)
    sort=request.query.get('sort','newest')
    if not 0<=year<=9999 or not 0<=month<=12 or kind not in ('','image','video') or sort not in ('newest','oldest'): raise web.HTTPBadRequest(text='Invalid filter')
    target=await request.app['archive_index'].ensure(account,root)
    favorite_db=await asyncio.to_thread(favorite_database,root,False)
    favorites=request.query.get('favorites','0')=='1'
    anniversary=request.query.get('anniversary','')
    if anniversary:
        from datetime import datetime
        try:
            if not re.fullmatch(r'\d{2}-\d{2}',anniversary): raise ValueError()
            datetime.strptime('2000-'+anniversary,'%Y-%m-%d')
        except ValueError: raise web.HTTPBadRequest(text='Invalid anniversary date')
    rows,total,albums=await asyncio.to_thread(query_index,target,album,search,page,year,month,kind,sort,start,end,favorite_db,favorites,anniversary)
    def saved():
        if not favorite_db: return set()
        with sqlite3.connect(favorite_db) as db: return {(item,name) for item,name in db.execute('SELECT id,name FROM favorites')}
    favorite_set=await asyncio.to_thread(saved)
    items=[]
    for item,name,size,kind,label,source in rows:
        suffix='/'.join(quote(part,safe='') for part in (account,item,name))
        items.append({'favorite':(item,name) in favorite_set,'id':item,'name':name,'size':size,'kind':kind,'modified':label,
                      'date_source':source,'url':'/api/archive/file/'+suffix,
                      'thumb':'/api/archive/thumb/'+suffix})
    def report():
        try:return json.loads((root/'.fotoarkiv/organization.json').read_text())
        except (OSError,ValueError):return None
    organization=await asyncio.to_thread(report)
    return web.json_response({'items':items,'total':total,'page':page,'page_size':PAGE_SIZE,
                              'albums':albums,'organization':organization})


async def file_response(request):
    path = await asyncio.to_thread(media_path, request, request.match_info['account'], request.match_info['item'], request.match_info['name'])
    disposition = 'attachment' if request.query.get('download') == '1' else 'inline'
    response = web.FileResponse(path)
    response.headers['Content-Disposition'] = disposition + "; filename*=UTF-8''" + quote(path.name, safe='')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def create_thumb(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in VIDEOS:
        import subprocess
        temporary=target.with_suffix('.tmp')
        try:
            subprocess.run(['ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-frames:v','1','-vf','scale=320:320:force_original_aspect_ratio=decrease','-f','image2','-vcodec','mjpeg',str(temporary)], check=True, timeout=15, capture_output=True)
            os.replace(temporary,target)
        finally: temporary.unlink(missing_ok=True)
        return
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((320, 320))
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        temporary = target.with_suffix('.tmp')
        image.save(temporary, format='JPEG', quality=78)
        os.replace(temporary, target)


async def thumbnail(request):
    path = await asyncio.to_thread(media_path, request, request.match_info['account'], request.match_info['item'], request.match_info['name'])
    if path.suffix.lower() not in IMAGES | VIDEOS:
        raise web.HTTPNotFound()
    stat = path.stat()
    key = request.match_info['account'] + '-' + request.match_info['item']
    target = request.app['thumb_root'] / key / (str(stat.st_mtime_ns) + '-' + hashlib.sha256(path.name.encode('utf-8')).hexdigest()[:16] + '.jpg')
    if not target.is_file():
        try:
            async with request.app['thumb_slots']:
                if not target.is_file():
                    await asyncio.to_thread(create_thumb, path, target)
        except (OSError, UnidentifiedImageError, ValueError, __import__("subprocess").SubprocessError):
            raise web.HTTPNotFound(text='Kan ikke lave miniature')
    return web.FileResponse(target, headers={'Cache-Control': 'private, max-age=86400'})


def next_chunk(iterator):
    return next(iterator, None)


def prepare_album(root, target, album):
    title, members = album_members(target, album)
    if title is None or not members:
        raise web.HTTPNotFound(text='Albummet har ingen lokale filer')
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', title).strip(' .')[:100] or 'album'
    selected, total = [], 0
    for relative in members:
        path = checked_path(root, relative)
        if not path.is_file() or path.suffix.lower() not in IMAGES | VIDEOS:
            raise web.HTTPConflict(text='Albumindekset skal opdateres. Genindlæs galleriet og prøv igen.')
        total += path.stat().st_size
        selected.append((path, name + '/' + path.name))
    return selected, total, name + '.zip'

async def album_selection(request, data):
    account = data.get('account', '')
    root = account_root(request, account)
    album = data.get('album', '')
    if not isinstance(album, str) or not album or album == '__none__' or len(album) > 200:
        raise web.HTTPBadRequest(text='Vælg et album først')
    target = await request.app['archive_index'].ensure(account, root)
    return await asyncio.to_thread(prepare_album, root, target, album)

async def album_info(request):
    if request.content_type != 'application/x-www-form-urlencoded' or (request.content_length or 0) > 4096:
        raise web.HTTPBadRequest(text='Ugyldig anmodning')
    data = await request.post()
    if not request.app['valid_token'](data.get('token', '')):
        raise web.HTTPForbidden(text='Ugyldig formular')
    selected, total, filename = await album_selection(request, data)
    return web.json_response({'count':len(selected), 'bytes':total, 'filename':filename})


async def range_selection(request, data):
    root = account_root(request, data.get('account',''))
    year, month, start, end, kind = date_filters(data)
    if not year and not (start and end): raise web.HTTPBadRequest(text='Choose a year or both interval dates')
    target = await request.app['archive_index'].ensure(data['account'], root)
    rows = await asyncio.to_thread(range_members, target, year, month, start, end, kind)
    def prepare():
        selected, size = [], 0
        for (relative,) in rows:
            path = checked_path(root,relative)
            if not path.is_file() or path.suffix.lower() not in IMAGES|VIDEOS: raise web.HTTPConflict(text='Files changed; refresh the gallery')
            selected.append((path,str(path.relative_to(root))));size += path.stat().st_size
        if not selected: raise web.HTTPNotFound(text='No local files in the selected date range')
        return selected,size,'photoharbor-'+(str(year)+(f'-{month:02d}' if month else '') if year else start+'_'+end)+'.zip'
    return await asyncio.to_thread(prepare)


async def range_info(request):
    if request.content_type != 'application/x-www-form-urlencoded' or (request.content_length or 0)>4096: raise web.HTTPBadRequest()
    data = await request.post()
    if not request.app['valid_token'](data.get('token','')): raise web.HTTPForbidden()
    selected,size,filename = await range_selection(request,data)
    return web.json_response({'count':len(selected),'bytes':size,'filename':filename})

async def download_zip(request):
    if request.content_type != 'application/x-www-form-urlencoded' or (request.content_length or 0) > 100000:
        raise web.HTTPBadRequest(text='Ugyldig anmodning')
    data = await request.post()
    if not request.app['valid_token'](data.get('token', '')):
        raise web.HTTPForbidden(text='Ugyldig formular')
    account = data.get('account', '')
    filename = 'fotoarkiv-selection.zip'
    if data.get('export') == 'dates':
        selected, total, filename = await range_selection(request, data)
    elif 'album' in data:
        selected, total, filename = await album_selection(request, data)
    else:
        try:
            files = json.loads(data.get('files', '[]'))
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text='Ugyldigt filvalg')
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_ZIP_FILES:
            raise web.HTTPBadRequest(text='Vælg mellem 1 og 500 filer')
        selected, total = [], 0
        for entry in files:
            if not isinstance(entry, dict):
                raise web.HTTPBadRequest(text='Ugyldigt filvalg')
            path = await asyncio.to_thread(media_path, request, account, entry.get('id', ''), entry.get('name', ''))
            total += path.stat().st_size
            if total > MAX_ZIP_BYTES:
                raise web.HTTPBadRequest(text='Vælg højst 10 GB ad gangen')
            selected.append((path, str(path.relative_to(account_root(request,account)))))
    zip_file = ZipStream(compress_type=ZIP_STORED)
    for path, item in selected:
        zip_file.add_path(path, item)
    response = web.StreamResponse(headers={
        'Content-Type': 'application/zip',
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename, safe=''),
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store'})
    await response.prepare(request)
    iterator = iter(zip_file)
    try:
        while (chunk := await asyncio.to_thread(next_chunk, iterator)) is not None:
            await response.write(chunk)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return response


def setup(app, photos_root, thumb_root, account_names, valid_token):
    app['archive_index'] = ArchiveIndex(thumb_root.parent / 'archive-index')
    app['thumb_slots'] = asyncio.Semaphore(3)
    app['favorite_lock'] = asyncio.Lock()
    async def cleanup(app):
        await app['archive_index'].close()
    app.on_cleanup.append(cleanup)
    app['photos_root'] = photos_root
    app['thumb_root'] = thumb_root
    app['account_names'] = account_names
    app['valid_token'] = valid_token
    app.router.add_get('/api/archive', listing)
    app.router.add_get('/api/archive/file/{account}/{item}/{name}', file_response)
    app.router.add_get('/api/archive/thumb/{account}/{item}/{name}', thumbnail)
    app.router.add_post('/api/archive/zip', download_zip)
    app.router.add_post('/api/archive/album', album_info)
    app.router.add_post('/api/archive/range', range_info)
    app.router.add_post('/api/archive/favorite', favorite_action)
