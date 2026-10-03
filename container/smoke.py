"""Run inside the built image: real display, VNC WebSocket, auth and account startup."""
import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
import aiohttp

def request(path, authenticated=True):
    headers = {}
    if authenticated:
        token = base64.b64encode(('smoke:' + os.environ['APP_PASSWORD']).encode()).decode()
        headers['Authorization'] = 'Basic ' + token
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8787' + path, headers=headers), timeout=10)

async def main():
    assert Path('/tmp/gphotos-cdp').resolve() == Path('/config').resolve()
    assert os.environ['PHOTOS_DIR'] == '/download'
    with request('/') as response:
        assert b'PhotoHarbor' in response.read()
    for path, kind in [('/photoharbor.svg', 'image/svg+xml'), ('/photoharbor-512.png', 'image/png'), ('/favicon.ico', 'image/')]:
        with request(path) as response:
            assert response.status == 200 and kind in response.headers['Content-Type']
            assert len(response.read()) > 100
    with request('/archive/legacy') as response:
        assert b'PhotoHarbor' in response.read()
    with request('/api/status') as response:
        assert json.load(response)['online']
    try:
        request('/login/vnc.html', False)
        raise AssertionError('Login service must require portal authentication')
    except urllib.error.HTTPError as error:
        assert error.code == 401
    with request('/login/') as response:
        assert '/login/vnc.html' in response.url
        assert b'noVNC' in response.read()
    # noVNC imports relative assets under the /login/ proxy prefix.
    with request('/login/app/ui.js') as response:
        assert response.status == 200
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth('smoke', os.environ['APP_PASSWORD'])) as client:
        async with client.ws_connect('http://127.0.0.1:8787/login/websockify', timeout=10) as socket:
            message = await socket.receive(timeout=10)
            assert message.type == aiohttp.WSMsgType.BINARY, message
            assert message.data.startswith(b'RFB '), message
    account = 'smoke@example.com'
    Path('/control/accounts.txt').write_text(account + '\n')
    deadline = time.monotonic() + 25
    heartbeat = Path('/control/accounts') / account / 'heartbeat'
    while not heartbeat.exists():
        if time.monotonic() > deadline:
            raise AssertionError('Additional account worker did not start')
        await asyncio.sleep(.2)
    with request('/api/status') as response:
        data = json.load(response)
        assert any(a['email'] == account and a['online'] for a in data['accounts'])
    assert Path('/download', account).is_dir()
    assert Path('/accounts', account, 'gphotos-cdp').is_dir()
    print('Single-container portal, authentication, login assets, real VNC handshake, legacy profile and additional account passed')

asyncio.run(main())
