import asyncio
import os
import sys
import tempfile
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
os.environ['APP_PASSWORD']='local-test-password'
sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
import app as dashboard

async def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);dashboard.CONTROL=root;dashboard.ACCOUNT_LIST=root/'accounts.txt'
        dashboard.ACCOUNT_LIST.write_text('first@example.com\nsecond@example.com\n')
        first=root/'accounts/first@example.com';first.mkdir(parents=True)
        second=root/'accounts/second@example.com';second.mkdir(parents=True)
        for name in ('start-request','rescan-request','organize-request'): (first/name).write_text('1')
        app=web.Application();app['account_lock']=asyncio.Lock();app.router.add_post('/api/accounts/{email}/{action}',dashboard.account_action)
        async with TestClient(TestServer(app)) as client:
            response=await client.post('/api/accounts/first@example.com/stop',json={'token':'bad'});assert response.status==403
            assert not (first/'stop-request').exists()
            response=await client.post('/api/accounts/first@example.com/stop',json={'token':dashboard.TOKEN});assert response.status==200
            assert (first/'stop-request').exists()
            assert all(not (first/name).exists() for name in ('start-request','rescan-request','organize-request'))
            assert not (second/'stop-request').exists()
            response=await client.post('/api/accounts/other@example.com/stop',json={'token':dashboard.TOKEN});assert response.status==404
        print('Stop API rejects invalid tokens/unknown accounts and cancels only the selected account')
asyncio.run(main())

