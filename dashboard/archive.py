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
from archive_index import ArchiveIndex, query as query_index

ITEM = re.compile(r'^[A-Za-z0-9_-]{20,120}$')
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif', '.bmp', '.tif', '.tiff'}
VIDEOS = {'.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv', '.3gp'}
PAGE_SIZE = 48
MAX_ZIP_FILES = 500
MAX_ZIP_BYTES = 10 * 1024**3


def account_root(request, account):
    if account != 'legacy' and account not in request.app['account_names']():
        raise web.HTTPNotFound(text='Ukendt konto')
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


async def listing(request):
    account=request.query.get('account','')
    root=account_root(request,account)
    try: page=int(request.query.get('page','1'))
    except ValueError:raise web.HTTPBadRequest(text='Ugyldigt sidetal')
    if page<1 or page>100000:raise web.HTTPBadRequest(text='Ugyldigt sidetal')
    album=request.query.get('album','')[:200]
    search=request.query.get('q','').strip()[:100]
    target=await request.app['archive_index'].ensure(account,root)
    rows,total,albums=await asyncio.to_thread(query_index,target,album,search,page)
    items=[]
    for item,name,size,kind,label,source in rows:
        suffix='/'.join(quote(part,safe='') for part in (account,item,name))
        items.append({'id':item,'name':name,'size':size,'kind':kind,'modified':label,
                      'date_source':source,'url':'/api/archive/file/'+suffix,
                      'thumb':'/api/archive/thumb/'+suffix if kind=='image' else None})
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
    if path.suffix.lower() not in IMAGES:
        raise web.HTTPNotFound()
    stat = path.stat()
    key = request.match_info['account'] + '-' + request.match_info['item']
    target = request.app['thumb_root'] / key / (str(stat.st_mtime_ns) + '-' + hashlib.sha256(path.name.encode('utf-8')).hexdigest()[:16] + '.jpg')
    if not target.is_file():
        try:
            async with request.app['thumb_slots']:
                if not target.is_file():
                    await asyncio.to_thread(create_thumb, path, target)
        except (OSError, UnidentifiedImageError, ValueError):
            raise web.HTTPNotFound(text='Kan ikke lave miniature')
    return web.FileResponse(target, headers={'Cache-Control': 'private, max-age=86400'})


def next_chunk(iterator):
    return next(iterator, None)


async def download_zip(request):
    if request.content_type != 'application/x-www-form-urlencoded' or (request.content_length or 0) > 100000:
        raise web.HTTPBadRequest(text='Ugyldig anmodning')
    data = await request.post()
    if not request.app['valid_token'](data.get('token', '')):
        raise web.HTTPForbidden(text='Ugyldig formular')
    account = data.get('account', '')
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
        path = media_path(request, account, entry.get('id', ''), entry.get('name', ''))
        total += path.stat().st_size
        if total > MAX_ZIP_BYTES:
            raise web.HTTPBadRequest(text='Vælg højst 10 GB ad gangen')
        selected.append((path, str(path.relative_to(account_root(request,account)))))
    zip_file = ZipStream(compress_type=ZIP_STORED)
    for path, item in selected:
        zip_file.add_path(path, item)
    response = web.StreamResponse(headers={
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename="fotoarkiv-udvalg.zip"',
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
