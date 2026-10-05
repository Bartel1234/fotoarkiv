"""Execute portal JavaScript in a real Chrome browser, not just endpoint mocks."""
import asyncio, base64, json, os, re, subprocess, tempfile, time
from pathlib import Path
import aiohttp

async def main():
    with tempfile.TemporaryDirectory() as profile:
        process=subprocess.Popen(['google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--remote-debugging-port=9223','--user-data-dir='+profile,'--window-size=1440,1000','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            async with aiohttp.ClientSession() as internal,aiohttp.ClientSession(auth=aiohttp.BasicAuth('smoke',os.environ['APP_PASSWORD']))as portal:
                deadline=time.monotonic()+20
                while True:
                    try:
                        async with internal.get('http://127.0.0.1:9223/json/list')as response:pages=await response.json()
                        if pages:break
                    except aiohttp.ClientError:pass
                    assert time.monotonic()<deadline,'Frontend Chrome did not start';await asyncio.sleep(.2)
                async with internal.ws_connect(pages[0]['webSocketDebuggerUrl'])as chrome:
                    serial=0
                    async def command(method,params=None):
                        nonlocal serial
                        serial+=1;number=serial
                        await chrome.send_json({'id':number,'method':method,'params':params or {}})
                        while True:
                            data=json.loads((await chrome.receive(timeout=15)).data)
                            if data.get('id')==number:
                                assert 'error' not in data,data
                                return data.get('result',{})
                    async def evaluate(expression):
                        result=await command('Runtime.evaluate',{'expression':expression,'returnByValue':True})
                        assert 'exceptionDetails' not in result,result
                        return result.get('result',{}).get('value')
                    async def until(expression):
                        deadline=time.monotonic()+20
                        while not await evaluate(expression):
                            assert time.monotonic()<deadline,expression
                            await asyncio.sleep(.1)
                    await command('Network.enable')
                    auth=base64.b64encode(('smoke:'+os.environ['APP_PASSWORD']).encode()).decode()
                    await command('Network.setExtraHTTPHeaders',{'headers':{'Authorization':'Basic '+auth}})
                    await command('Page.navigate',{'url':'http://127.0.0.1:8787/'})
                    await until("document.getElementById('account-list')?.children.length>0")
                    await evaluate("document.querySelector('.account-card .account-actions button:nth-child(5)').click()")
                    await until("document.getElementById('account-tools')?.open")
                    await evaluate("document.getElementById('schedule-enabled').checked=false;document.getElementById('schedule-hour').value=7;document.getElementById('tools-settings-form').requestSubmit()")
                    await until("document.getElementById('tools-message').textContent.includes('Settings saved')")
                    assert json.loads(Path('/control/settings.json').read_text())['hour']==7
                    # Verify the busy-login message is actually rendered by login.js.
                    Path('/control/running').write_text('frontend test')
                    await command('Page.navigate',{'url':'http://127.0.0.1:8787/login/?account=legacy'})
                    await until("document.getElementById('stop-backup')?.hidden===false")
                    assert 'Backup is running' in await evaluate("document.getElementById('status').textContent")
                    assert await evaluate("document.querySelector('.app-version').textContent")=='v'+Path('/app/VERSION').read_text().strip()
                    Path('/control/running').unlink()
                    # Known local media exercise the archive UI and video thumbnail route.
                    account='frontend@example.com';state=Path('/control/accounts')/account
                    state.mkdir(parents=True,exist_ok=True)
                    state.joinpath('settings.json').write_text(json.dumps({'enabled':False,'hour':3,'days':[0],'notify_url':'','notify_success':False}))
                    async with portal.get('http://127.0.0.1:8787/')as response:page=await response.text()
                    token=re.search(r'name="token" value="([^"]+)"',page).group(1)
                    async with portal.post('http://127.0.0.1:8787/api/accounts',json={'email':account,'token':token})as response:assert response.status==201
                    item='AF1Q'+'f'*36;folder=Path('/download')/account/item;folder.mkdir()
                    from PIL import Image
                    Image.new('RGB',(100,80),'blue').save(folder/'sample.jpg')
                    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=red:s=160x120:d=1','-c:v','libx264',str(folder/'sample.mp4')],check=True)
                    await command('Page.navigate',{'url':'http://127.0.0.1:8787/archive/'+account})
                    await until("document.querySelectorAll('.archive-card').length===2")
                    await evaluate("document.getElementById('archive-kind').value='video';document.getElementById('archive-kind').dispatchEvent(new Event('change'))")
                    await until("document.querySelectorAll('.archive-card').length===1&&document.querySelector('.archive-card strong').textContent==='sample.mp4'")
                    async with portal.get('http://127.0.0.1:8787/api/archive/thumb/'+account+'/'+item+'/sample.mp4')as response:
                        assert response.status==200 and (await response.read()).startswith(b'\xff\xd8')
                    await evaluate("document.querySelector('.archive-tile').click()")
                    await until("document.querySelector('#archive-preview video')?.readyState>=1")
                    assert await evaluate("document.getElementById('archive-preview').open")
            print('Real browser: settings saved, busy login explained, gallery filters and video playback/thumbnail passed')
        finally:
            Path('/control/running').unlink(missing_ok=True)
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
asyncio.run(main())
