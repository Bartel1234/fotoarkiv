"""Real headed Chrome: stream frames, enter text, send keys, close saved-profile login."""
import asyncio, json, os, re, time
from pathlib import Path
from urllib.parse import quote
import aiohttp

async def main():
    marker=Path('/control/login-request')
    marker.write_text('legacy 0\n')
    async with aiohttp.ClientSession() as internal, aiohttp.ClientSession(auth=aiohttp.BasicAuth('smoke',os.environ['APP_PASSWORD'])) as portal:
        try:
            deadline=time.monotonic()+40
            while True:
                try:
                    async with internal.get('http://127.0.0.1:9222/json/list',timeout=aiohttp.ClientTimeout(total=2)) as r:targets=await r.json()
                    pages=[p for p in targets if p.get('type')=='page']
                    if pages:break
                except (aiohttp.ClientError,TimeoutError):pass
                assert time.monotonic()<deadline,'Chrome login did not start'
                await asyncio.sleep(.2)
            async with internal.ws_connect(pages[0]['webSocketDebuggerUrl']) as chrome:
                serial=0
                async def command(method,params):
                    nonlocal serial
                    serial+=1;n=serial
                    await chrome.send_json({'id':n,'method':method,'params':params})
                    while True:
                        data=json.loads((await chrome.receive(timeout=10)).data)
                        if data.get('id')==n:
                            assert 'error' not in data,data
                            return data.get('result',{})
                doc='<html><body><input id="entry" style="position:absolute;left:20px;top:20px;width:250px;height:50px"><script>window.entered=0;document.addEventListener("keydown",e=>{if(e.key==="Enter")window.entered++})</script></body></html>'
                await command('Page.navigate',{'url':'data:text/html,'+quote(doc)})
                await asyncio.sleep(.3)
                async with portal.get('http://127.0.0.1:8787/login/?account=legacy') as r:
                    page=await r.text();token=re.search(r'id="token"[^>]*value="([^"]+)"',page).group(1)
                    assert '<canvas' in page and 'noVNC' not in page
                async with portal.ws_connect('http://127.0.0.1:8787/login/stream?account=legacy',headers={'Origin':'http://127.0.0.1:8787'}) as viewer:
                    await viewer.send_json({'token':token})
                    while True:
                        frame=await viewer.receive_json(timeout=15)
                        if frame['type']=='frame':break
                    import base64
                    assert base64.b64decode(frame['image']).startswith(b'\xff\xd8')
                    assert frame['width']>100 and frame['height']>100
                    await viewer.send_json({'type':'ack','session':frame['session']})
                    for event in ['mousePressed','mouseReleased']:
                        await viewer.send_json({'type':'mouse','event':event,'x':40,'y':40,'button':'left'})
                    await viewer.send_json({'type':'text','text':'PhotoHarbor smoke'})
                    for event in ['keyDown','keyUp']:
                        await viewer.send_json({'type':'key','event':event,'key':'Enter','code':'Enter','virtualKey':13})
                    deadline=time.monotonic()+10
                    while True:
                        result=await command('Runtime.evaluate',{'expression':'JSON.stringify([document.getElementById("entry").value,window.entered])','returnByValue':True})
                        if json.loads(result['result']['value'])==['PhotoHarbor smoke',1]:break
                        assert time.monotonic()<deadline,'Input did not reach Chrome'
                        await asyncio.sleep(.1)
                    async with portal.post('http://127.0.0.1:8787/api/accounts/legacy/close-login',json={'token':token}) as r:assert r.status==200
                    deadline=time.monotonic()+15
                    while Path('/control/login-active').exists():
                        assert time.monotonic()<deadline,'Login browser did not close'
                        await asyncio.sleep(.2)
                    assert Path('/config/Default').is_dir(),'Profile was not preserved'
        finally:
            Path('/control/login-close-request').write_text('legacy')
    print('Real Chrome frames, mouse, text, keyboard and saved-profile closure passed without VNC')
asyncio.run(main())
