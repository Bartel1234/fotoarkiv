import asyncio, os, sys, tempfile
from unittest.mock import patch
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
os.environ['APP_PASSWORD']='test-account-tools-password'
sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
import app as dashboard

async def main():
    with tempfile.TemporaryDirectory()as temp:
        root=Path(temp);dashboard.CONTROL=root;dashboard.ACCOUNT_LIST=root/'accounts.txt'
        dashboard.PHOTOS=root/'photos';dashboard.PHOTOS.mkdir()
        dashboard.ACCOUNT_LIST.write_text('first@example.com\nsecond@example.com\n')
        app=web.Application();app['account_lock']=asyncio.Lock();app.router.add_post('/api/accounts/{email}/{action}',dashboard.account_action)
        config={'enabled':False,'hour':4,'days':[1,3],'notify_url':'','notify_success':False,'min_free_gb':2,'min_free_percent':2}
        async with TestClient(TestServer(app))as client:
            base='/api/accounts/first@example.com/'
            response=await client.post(base+'settings',json={'token':'bad','settings':config});assert response.status==403
            response=await client.post(base+'settings',json={'token':dashboard.TOKEN,'settings':config});assert response.status==200
            first=root/'accounts/first@example.com'
            assert dashboard.settings(first)==config
            assert not (root/'accounts/second@example.com/settings.json').exists()
            response=await client.post(base+'settings',json={'token':dashboard.TOKEN,'settings':{**config,'hour':25}});assert response.status==400
            assert dashboard.settings(first)==config
            (first/'running').write_text('busy')
            for action in ['verify','repair']:
                response=await client.post(base+action,json={'token':dashboard.TOKEN});assert response.status==409
            (first/'running').unlink()
            response=await client.post(base+'verify',json={'token':dashboard.TOKEN});assert response.status==200
            assert (first/'verify-request').exists() and (first/'start-request').exists()
            assert not (root/'login-close-request').exists(),'Local verification must not close Google login'
            for name in ['verify-request','start-request']:(first/name).unlink()
            response=await client.post(base+'repair',json={'token':dashboard.TOKEN});assert response.status==200
            assert (first/'rescan-request').exists() and (first/'repair-request').exists()
            assert (root/'login-close-request').read_text()=='first@example.com'
            for name in ['rescan-request','repair-request','start-request']:(first/name).unlink()
            (first/'running').write_text('1');(first/'run-mode').write_text('backup')
            response=await client.post(base+'pause',json={'token':'bad'});assert response.status==403
            response=await client.post(base+'pause',json={'token':dashboard.TOKEN});assert response.status==200
            assert (first/'paused').read_text()=='user' and (first/'stop-request').exists()
            response=await client.post(base+'resume',json={'token':dashboard.TOKEN});assert response.status==409
            (first/'running').unlink();(first/'stop-request').unlink()
            with patch.object(dashboard,'storage',return_value={'low':True}):
                response=await client.post(base+'resume',json={'token':dashboard.TOKEN});assert response.status==409
            assert (first/'paused').exists() and not (first/'start-request').exists()
            with patch.object(dashboard,'storage',return_value={'low':False}):
                response=await client.post(base+'resume',json={'token':dashboard.TOKEN});assert response.status==200
            assert not (first/'paused').exists() and (first/'start-request').exists()
            (first/'start-request').unlink();(root/'login-close-request').unlink()
            response=await client.post(base+'content',json={'token':dashboard.TOKEN});assert response.status==200
            assert (first/'content-request').exists() and not (root/'login-close-request').exists()
            assert not (root/'accounts/second@example.com/paused').exists()
        assert dashboard.version_key('v0.2.0-beta.6')>dashboard.version_key('v0.2.0-beta.5')
        assert dashboard.version_key('v0.2.0')>dashboard.version_key('v0.2.0-beta.6')
        assert dashboard.version_key('bad')is None
    print('Settings validation, CSRF, account isolation and safe queued check/repair passed')
asyncio.run(main())
