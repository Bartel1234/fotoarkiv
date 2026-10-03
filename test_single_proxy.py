"""Verify the single-container sign-in redirect, authenticated assets and WebSocket proxy."""
import asyncio
import base64
import os
import runpy
import tempfile
from pathlib import Path
from unittest.mock import patch
from aiohttp import web, WSMsgType
from aiohttp.test_utils import TestClient, TestServer

async def main():
    with tempfile.TemporaryDirectory() as temp:
        async def upstream(request):
            assert 'Authorization' not in request.headers
            if request.path == '/websockify':
                socket = web.WebSocketResponse()
                await socket.prepare(request)
                await socket.send_bytes(b'RFB 003.008\n')
                async for message in socket:
                    if message.type == WSMsgType.BINARY:
                        await socket.send_bytes(message.data)
                    else:
                        break
                return socket
            return web.Response(text='noVNC asset: ' + request.path)
        remote = web.Application()
        remote.router.add_route('*', '/{tail:.*}', upstream)
        async with TestServer(remote) as server:
            environment = {'APP_PASSWORD': 'test-password-1234', 'PHOTOS_DIR': temp,
                           'LOGIN_URL': str(server.make_url('/')).rstrip('/'),
                           'LOGIN_PAGE': '/login/vnc.html?autoconnect=1&resize=remote&path=login/websockify'}
            import sys
            sys.path.insert(0, str(Path(__file__).parent / 'dashboard'))
            captured = []
            with patch.dict(os.environ, environment), patch.object(web, 'run_app', side_effect=lambda app, **kw: captured.append(app)):
                runpy.run_path(str(Path(__file__).parent / 'dashboard/app.py'), run_name='__main__')
            async with TestClient(TestServer(captured[0])) as client:
                for path in ('/login/', '/login/vnc.html', '/login/websockify'):
                    response = await client.get(path, allow_redirects=False)
                    assert response.status == 401
                token = base64.b64encode(b'test:test-password-1234').decode()
                headers = {'Authorization': 'Basic ' + token}
                response = await client.get('/login/', headers=headers, allow_redirects=False)
                assert response.status == 302
                assert response.headers['Location'] == environment['LOGIN_PAGE']
                response = await client.get('/login/app/ui.js', headers=headers)
                assert await response.text() == 'noVNC asset: /app/ui.js'
                async with client.ws_connect('/login/websockify', headers=headers) as socket:
                    message = await socket.receive(timeout=5)
                    assert message.data == b'RFB 003.008\n'
                    await socket.send_bytes(b'RFB 003.008\n')
                    assert (await socket.receive(timeout=5)).data == b'RFB 003.008\n'
    print('Single-container sign-in redirect, authenticated assets, credential stripping and bidirectional VNC proxy passed')

asyncio.run(main())
