"""Authenticated, account-bound Chrome tab streaming. Never expose raw CDP to clients."""
import asyncio
import contextlib
import html
import json
import math
from pathlib import Path
from urllib.parse import urlsplit
from aiohttp import ClientError, ClientTimeout, WSMsgType, web


def input_command(data):
    """Accept only user input; navigation, script evaluation and cookie APIs are private."""
    kind = data.get('type')
    if kind == 'text':
        text = data.get('text')
        if not isinstance(text, str) or len(text) > 8192:
            raise ValueError('Invalid text')
        return 'Input.insertText', {'text': text}
    if kind == 'mouse':
        event = data.get('event')
        if event not in ('mousePressed', 'mouseReleased', 'mouseMoved', 'mouseWheel'):
            raise ValueError('Invalid mouse event')
        params = {'type': event}
        for key in ('x', 'y'):
            value = data.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 8192:
                raise ValueError('Invalid coordinates')
            params[key] = value
        params['button'] = data.get('button', 'none')
        if params['button'] not in ('none', 'left', 'middle', 'right'):
            raise ValueError('Invalid button')
        params['clickCount'] = 1
        if event == 'mouseWheel':
            for key in ('deltaX', 'deltaY'):
                value = data.get(key, 0)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 10000:
                    raise ValueError('Invalid scroll')
                params[key] = value
        return 'Input.dispatchMouseEvent', params
    if kind == 'key':
        if data.get('event') not in ('keyDown', 'keyUp'):
            raise ValueError('Invalid key event')
        params = {'type': data['event']}
        for key in ('key', 'code'):
            value = data.get(key, '')
            if not isinstance(value, str) or len(value) > 64:
                raise ValueError('Invalid key')
            params[key] = value
        modifiers = data.get('modifiers', 0)
        if not isinstance(modifiers, int) or not 0 <= modifiers <= 15:
            raise ValueError('Invalid modifiers')
        params['modifiers'] = modifiers
        text = data.get('text', '')
        virtual = data.get('virtualKey', 0)
        if not isinstance(text, str) or len(text) > 8 or not isinstance(virtual, int) or not 0 <= virtual <= 255:
            raise ValueError('Invalid key text')
        params['text'] = text
        params['windowsVirtualKeyCode'] = virtual
        return 'Input.dispatchKeyEvent', params
    raise ValueError('Unsupported input')


class ChromeTab:
    def __init__(self, remote, viewer, owned=lambda: True):
        self.remote, self.viewer, self.owned = remote, viewer, owned
        self.serial, self.pending = 0, {}
        self.reader = asyncio.create_task(self.receive())

    async def command(self, method, params=None):
        self.serial += 1
        number = self.serial
        future = asyncio.get_running_loop().create_future()
        self.pending[number] = future
        try:
            await self.remote.send_json({'id': number, 'method': method, 'params': params or {}})
            return await asyncio.wait_for(future, 8)
        finally:
            self.pending.pop(number, None)

    async def receive(self):
        try:
            async for message in self.remote:
                if message.type != WSMsgType.TEXT:
                    break
                data = json.loads(message.data)
                if 'id' in data:
                    future = self.pending.get(data['id'])
                    if future is not None and not future.done():
                        if 'error' in data:
                            future.set_exception(RuntimeError('Chrome rejected the request'))
                        else:
                            future.set_result(data.get('result', {}))
                elif data.get('method') == 'Page.screencastFrame':
                    if not self.owned():
                        await self.viewer.close()
                        break
                    frame = data['params']
                    # Browser consumes one frame before the next is acknowledged.
                    await self.viewer.send_json({'type': 'frame', 'image': frame['data'],
                                                 'session': frame['sessionId'],
                                                 'width': frame['metadata']['deviceWidth'],
                                                 'height': frame['metadata']['deviceHeight']})
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError('Chrome closed'))

    async def close(self):
        self.reader.cancel()
        await asyncio.gather(self.reader, return_exceptions=True)
        await self.remote.close()


def setup(app, control, account_names, token, valid_token, cdp_url='http://127.0.0.1:9222', version='development'):
    assets = Path(__file__).parent
    connections = set()

    def active():
        try:
            return (control / 'login-active').read_text().strip()
        except OSError:
            return ''

    def account(request):
        value = request.query.get('account', 'legacy')
        if value != 'legacy' and value not in account_names():
            raise web.HTTPNotFound(text='Unknown account')
        return value

    async def page(request):
        name = account(request)
        template = (assets / 'login.html').read_text()
        text = template.replace('%%ACCOUNT%%', html.escape(name, quote=True)).replace('%%CSRF_TOKEN%%', token).replace('%%APP_VERSION%%', html.escape(version))
        return web.Response(text=text, content_type='text/html', headers={
            'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"})

    async def asset(request):
        return web.FileResponse(assets / request.match_info['asset'])

    async def stream(request):
        name = account(request)
        origin = urlsplit(request.headers.get('Origin', ''))
        # Basic credentials alone are insufficient: require same-origin and the page token.
        if origin.netloc != request.host or origin.scheme not in ('http', 'https'):
            raise web.HTTPForbidden(text='Invalid origin')
        viewer = web.WebSocketResponse(heartbeat=20, max_msg_size=16384)
        await viewer.prepare(request)
        tab = None
        monitor = None
        attached = False
        try:
            first = await viewer.receive(timeout=10)
            if first.type != WSMsgType.TEXT:
                return viewer
            hello = json.loads(first.data)
            if not isinstance(hello, dict) or not valid_token(hello.get('token')):
                await viewer.close(code=1008, message=b'Invalid token')
                return viewer
            for previous in list(connections):
                await previous.close(code=1001, message=b'New sign-in viewer opened')
            connections.add(viewer)
            await viewer.send_json({'type': 'waiting'})

            async def watch():
                nonlocal tab, attached
                target_id = None
                last_wait = None
                deadline = asyncio.get_running_loop().time() + 90
                while not viewer.closed:
                    state = control if name == 'legacy' else control/'accounts'/name
                    backup_busy = (state/'running').exists()
                    if not attached and backup_busy:
                        deadline = asyncio.get_running_loop().time() + 90
                        if last_wait != 'backup':
                            await viewer.send_json({'type':'waiting_backup'})
                            last_wait = 'backup'
                    elif not attached and last_wait == 'backup':
                        await viewer.send_json({'type':'waiting'})
                        last_wait = 'browser'
                    if not attached and asyncio.get_running_loop().time() > deadline:
                        await viewer.send_json({'type': 'error', 'message': 'Login did not start. Close this window and try Google sign-in again.'})
                        await viewer.close()
                        return
                    if active() != name:
                        if attached:
                            await viewer.send_json({'type': 'closed'})
                            await viewer.close()
                            return
                        if asyncio.get_running_loop().time() > deadline:
                            await viewer.send_json({'type': 'error', 'message': 'Login did not start. Close this window and try Google sign-in again.'})
                            await viewer.close()
                            return
                    else:
                        try:
                            async with app['session'].get(cdp_url + '/json/list', timeout=ClientTimeout(total=3)) as response:
                                targets = await response.json()
                            pages = [p for p in targets if p.get('type') == 'page' and p.get('webSocketDebuggerUrl')]
                            if pages and (pages[0]['id'] != target_id or tab is None or tab.remote.closed):
                                if tab:
                                    await tab.close()
                                    tab = None
                                target = pages[0]
                                # Replace the advertised host; never use a target-provided network destination.
                                path = urlsplit(target['webSocketDebuggerUrl']).path
                                if not path.startswith('/devtools/page/'):
                                    raise ValueError('Invalid Chrome target')
                                remote = await app['session'].ws_connect(cdp_url + path, max_msg_size=8 * 1024 * 1024)
                                tab = ChromeTab(remote, viewer, lambda: active() == name)
                                await tab.command('Page.enable')
                                await tab.command('Page.startScreencast', {'format': 'jpeg', 'quality': 80, 'maxWidth': 1600, 'maxHeight': 1200, 'everyNthFrame': 1})
                                target_id = target['id']
                                attached = True
                                await viewer.send_json({'type': 'ready'})
                        except (ClientError, ConnectionError, OSError, ValueError, RuntimeError, asyncio.TimeoutError):
                            if tab:
                                await tab.close()
                                tab = None
                            target_id = None
                    await asyncio.sleep(.5)

            monitor = asyncio.create_task(watch())
            async for message in viewer:
                if message.type != WSMsgType.TEXT:
                    break
                # Recheck ownership for every input, including while changing accounts.
                if active() != name:
                    if attached:
                        await viewer.close(code=1008, message=b'Login account changed')
                        break
                    continue
                data = json.loads(message.data)
                if not isinstance(data, dict):
                    raise ValueError('Invalid input')
                current = tab
                if current is None:
                    continue
                if data.get('type') == 'ack':
                    if not isinstance(data.get('session'), int):
                        raise ValueError('Invalid frame acknowledgement')
                    await current.command('Page.screencastFrameAck', {'sessionId': data['session']})
                else:
                    method, params = input_command(data)
                    await current.command(method, params)
        except (ValueError, OSError, RuntimeError, asyncio.TimeoutError):
            if not viewer.closed:
                await viewer.close(code=1008, message=b'Login connection ended')
        finally:
            if monitor:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            if tab:
                await tab.close()
            connections.discard(viewer)
            await viewer.close()
        return viewer

    async def shutdown(app):
        await asyncio.gather(*(ws.close(code=1001) for ws in list(connections)))

    app.on_shutdown.append(shutdown)
    app.router.add_get('/login', page)
    app.router.add_get('/login/', page)
    app.router.add_get('/login/{asset:login.js|login.css}', asset)
    app.router.add_get('/login/stream', stream)

