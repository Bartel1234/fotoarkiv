import asyncio
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
import archive
sys.path.insert(0,str(Path(__file__).parent/'login'))
import organize

async def main():
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp); root=base/'photos'/'test@example.com';root.mkdir(parents=True)
        item='AF1Q'+'b'*36;album='album123456789';(root/item).mkdir();(root/'.fotoarkiv').mkdir()
        Image.new('RGB',(40,40),'red').save(root/item/'photo.jpg')
        (root/item/'video.mp4').write_bytes(b'0123456789')
        metadata={'version':1,'complete':True,'items':{item:{'timestamp':1041379200000,'offset':0,'albums':[album]}},'albums':{album:{'title':'Familie'}}}
        (root/'.fotoarkiv/metadata.json').write_text(json.dumps(metadata));organize.organize(root)
        app=web.Application();archive.setup(app,base/'photos',base/'thumbs',lambda:['test@example.com'],lambda t:t=='test-token')
        async with TestClient(TestServer(app)) as client:
            response=await client.get('/api/archive?account=test@example.com');assert response.status==200
            data=await response.json();assert data['total']==2;assert data['albums'][0]['count']==2
            assert all(i['modified']=='01/01/2003 00:00' and i['date_source']=='google' for i in data['items'])
            response=await client.get('/api/archive?account=test@example.com&album='+album);assert (await response.json())['total']==2
            response=await client.get('/api/archive?account=test@example.com&album=__none__');assert (await response.json())['total']==0
            image=next(i for i in data['items'] if i['kind']=='image');video=next(i for i in data['items'] if i['kind']=='video')
            response=await client.get(image['thumb']);assert response.status==200;assert (await response.read()).startswith(b'\xff\xd8')
            response=await client.get(video['url'],headers={'Range':'bytes=2-5'});assert response.status==206;assert await response.read()==b'2345'
            response=await client.post('/api/archive/zip',data={'token':'bad','account':'test@example.com','files':'[]'});assert response.status==403
            response=await client.post('/api/archive/zip',data={'token':'test-token','account':'test@example.com','files':json.dumps([{'id':i['id'],'name':i['name']} for i in data['items']])})
            assert response.status==200
            with zipfile.ZipFile(io.BytesIO(await response.read())) as z:
                assert len(z.namelist())==2 and all(n.startswith('Bibliotek/2003/01/') for n in z.namelist())
            response=await client.get('/api/archive?account=other@example.com');assert response.status==404
            target=root/item;target.symlink_to(base,target_is_directory=True)
            response=await client.get('/api/archive/file/test@example.com/'+item+'/unknown.jpg');assert response.status==404
        print('Archive API, Google dates, album filters, thumbnails, video ranges and ZIP passed')

asyncio.run(main())
