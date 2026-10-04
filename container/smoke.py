"""Run inside the built image: real display, direct Chrome login, auth and account startup."""
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
    for path in ('/login/', '/login/login.js', '/login/login.css', '/login/stream'):
        try:
            request(path, False)
            raise AssertionError('Login must require portal authentication')
        except urllib.error.HTTPError as error:
            assert error.code == 401
    with request('/login/') as response:
        assert b'<canvas' in response.read()
    for path in ('/login/login.js', '/login/login.css'):
        with request(path) as response:
            assert response.status == 200
    try:
        request('/login/vnc.html')
        raise AssertionError('Obsolete VNC page must not be available')
    except urllib.error.HTTPError as error:
        assert error.code == 404
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
    print('Single-container portal, authentication, login assets, direct Chrome login assets, legacy profile and additional account passed')

asyncio.run(main())
