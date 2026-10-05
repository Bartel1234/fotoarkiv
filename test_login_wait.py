"""A busy profile explains the wait and resumes after a backup is stopped."""
import asyncio
import sys
import tempfile
from pathlib import Path
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer
sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
from login_view import setup

async def main():
    with tempfile.TemporaryDirectory() as temp:
        control=Path(temp);(control/'running').write_text('busy')
        app=web.Application()
        async def session(app):
            app['session']=ClientSession();yield;await app['session'].close()
        app.cleanup_ctx.append(session)
        setup(app,control,lambda:[],'token',lambda value:value=='token')
        async with TestClient(TestServer(app)) as client:
            origin=str(client.make_url('/')).rstrip('/')
            async with client.ws_connect('/login/stream?account=legacy',headers={'Origin':origin})as ws:
                await ws.send_json({'token':'token'})
                assert (await ws.receive_json(timeout=2))['type']=='waiting'
                assert (await ws.receive_json(timeout=2))['type']=='waiting_backup'
                # The same stream should resume starting, without another sign-in request.
                (control/'running').unlink()
                assert (await ws.receive_json(timeout=2))['type']=='waiting'
    print('Login explains the active backup and resumes when its profile is released')
asyncio.run(main())
