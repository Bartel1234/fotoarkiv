import asyncio,json,os,sys,tempfile
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
os.environ['APP_PASSWORD']='test-config-only-password'
sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
import app as portal


async def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);portal.CONTROL=root/'control';portal.PHOTOS=root/'media';portal.ACCOUNTS=root/'profiles';portal.ACCOUNT_LIST=portal.CONTROL/'accounts.txt'
        for folder in (portal.CONTROL,portal.PHOTOS,portal.ACCOUNTS,portal.CONTROL/'accounts'):folder.mkdir(parents=True,exist_ok=True)
        portal.ACCOUNT_LIST.write_text('first@example.com\n')
        state=portal.CONTROL/'accounts/first@example.com';state.mkdir()
        portal.atomic(state/'settings.json',{'enabled':True,'hour':3,'days':[0],'notify_url':'https://ntfy.sh/private-secret','notify_success':True})
        app=web.Application();app['account_lock']=asyncio.Lock();app.router.add_post('/api/config/{action}',portal.configuration_action)
        async with TestClient(TestServer(app))as client:
            response=await client.post('/api/config/export',json={'token':'bad'});assert response.status==403
            response=await client.post('/api/config/export',json={'token':portal.TOKEN});document=await response.json()
            assert response.status==200 and 'private-secret' not in json.dumps(document)
            document['accounts'][1]['settings']['hour']=7
            document['accounts'].append({'email':'new@example.com','settings':document['accounts'][1]['settings']})
            data={'token':portal.TOKEN,'document':document}
            response=await client.post('/api/config/preview',json=data);assert response.status==200
            assert not (portal.PHOTOS/'new@example.com').exists()
            response=await client.post('/api/config/restore',json=data);assert response.status==400
            (state/'running').write_text('1')
            response=await client.post('/api/config/restore',json={**data,'confirmation':'IMPORT'});assert response.status==409
            assert portal.settings(state)['hour']==3
            (state/'running').unlink()
            response=await client.post('/api/config/restore',json={**data,'confirmation':'IMPORT'});assert response.status==200,await response.text()
            assert portal.settings(state)['hour']==7 and portal.settings(state)['notify_url'].endswith('private-secret')
            assert (portal.PHOTOS/'new@example.com').is_dir() and 'new@example.com' in portal.account_names()
            assert not list((portal.ACCOUNTS/'new@example.com/gphotos-cdp').iterdir())
            invalid={**document,'accounts':[{'email':'../../outside','settings':document['accounts'][1]['settings']}]}
            response=await client.post('/api/config/restore',json={**data,'document':invalid,'confirmation':'IMPORT'});assert response.status==400
    print('Settings export excludes credentials; preview, confirmation, busy guard, restoration and account validation passed')

asyncio.run(main())
