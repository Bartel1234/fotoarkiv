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
                        async with internal.get('http://127.0.0.1:9223/json/list')as response:targets=await response.json()
                        pages=[p for p in targets if p.get('type')=='page' and p.get('url')=='about:blank']
                        if pages:break
                    except aiohttp.ClientError:pass
                    assert time.monotonic()<deadline,'Frontend Chrome did not start';await asyncio.sleep(.2)
                async with internal.ws_connect(pages[0]['webSocketDebuggerUrl'])as chrome:
                    serial=0;events=[]
                    async def command(method,params=None):
                        nonlocal serial
                        serial+=1;number=serial
                        await chrome.send_json({'id':number,'method':method,'params':params or {}})
                        while True:
                            data=json.loads((await chrome.receive(timeout=15)).data)
                            if data.get('method') in ('Runtime.exceptionThrown','Log.entryAdded','Page.javascriptDialogOpening'): events.append(data)
                            if data.get('id')==number:
                                assert 'error' not in data,data
                                return data.get('result',{})
                    async def evaluate(expression):
                        result=await command('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
                        assert 'exceptionDetails' not in result,result
                        return result.get('result',{}).get('value')
                    async def until(expression):
                        deadline=time.monotonic()+45
                        while not await evaluate(expression):
                            if time.monotonic()>=deadline:
                                print('UI diagnostics:',await evaluate("JSON.stringify({url:location.href,title:document.title,body:document.body.innerText.slice(0,3000),scripts:[...document.scripts].map(s=>s.src)})"),events[-10:])
                                raise AssertionError(expression)
                            await asyncio.sleep(.1)
                    await command('Runtime.enable');await command('Log.enable')
                    await command('Network.enable')
                    auth=base64.b64encode(('smoke:'+os.environ['APP_PASSWORD']).encode()).decode()
                    await command('Network.setExtraHTTPHeaders',{'headers':{'Authorization':'Basic '+auth}})
                    await command('Page.navigate',{'url':'http://127.0.0.1:8787/'})
                    await until("document.getElementById('account-list')?.children.length>0")
                    await evaluate("document.querySelector('.account-card .account-actions button:nth-child(5)').click()")
                    await until("document.getElementById('account-tools')?.open")
                    await evaluate("document.getElementById('schedule-enabled').checked=false;document.getElementById('schedule-hour').value=7;document.getElementById('reserve-gb').value=3;document.getElementById('reserve-percent').value=1;document.getElementById('tools-settings-form').requestSubmit()")
                    await until("document.getElementById('tools-message').textContent.includes('Settings saved')")
                    assert json.loads(Path('/control/settings.json').read_text())['hour']==7
                    assert json.loads(Path('/control/settings.json').read_text())['min_free_gb']==3
                    await evaluate("document.getElementById('tools-close').click();document.getElementById('email-open').click()")
                    await until("document.getElementById('email-dialog').open")
                    await evaluate("document.getElementById('smtp-enabled').checked=false;document.getElementById('smtp-host').value='smtp.example.com';document.getElementById('smtp-sender').value='backup@example.com';document.getElementById('smtp-recipient').value='recipient@example.com';document.getElementById('smtp-password').value='frontend-fixture-secret';document.getElementById('smtp-form').requestSubmit()")
                    await until("document.getElementById('smtp-message').textContent.includes('Email settings saved')")
                    assert json.loads(Path('/control/smtp.json').read_text())['password']=='frontend-fixture-secret'
                    assert not await evaluate("fetch('/api/email').then(r=>r.text()).then(t=>t.includes('frontend-fixture-secret'))")
                    await evaluate("document.getElementById('smtp-close').click();document.getElementById('versions-open').click()")
                    await until("document.getElementById('versions-dialog').open")
                    assert await evaluate("document.getElementById('installed-version').textContent") == Path('/app/VERSION').read_text().strip()
                    await evaluate("document.getElementById('versions-close').click()")
                    # Real account actions render pause/resume at the account being operated on.
                    Path('/control/running').write_text('frontend pause fixture');Path('/control/run-mode').write_text('backup')
                    await evaluate('refresh()')
                    await until("[...document.querySelectorAll('.account-card button')].some(b=>b.textContent==='Pause backup')")
                    await evaluate("[...document.querySelectorAll('.account-card button')].find(b=>b.textContent==='Pause backup').click()")
                    await until("[...document.querySelectorAll('.account-card button')].some(b=>b.textContent==='Resume backup')")
                    assert Path('/control/paused').read_text()=='user'
                    for marker in ('running','paused','stop-request'):Path('/control',marker).unlink(missing_ok=True)
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
                    await command('Page.navigate',{'url':'http://127.0.0.1:8787/'})
                    await until("[...document.querySelectorAll('.account-card strong')].some(n=>n.textContent==='frontend@example.com')")
                    await evaluate("[...document.querySelectorAll('.account-card')].find(c=>c.querySelector('strong').textContent==='frontend@example.com').querySelector('.account-actions button:nth-child(5)').click()")
                    await until("document.getElementById('account-tools').open&&document.getElementById('tools-content').disabled===false")
                    await evaluate("document.getElementById('tools-content').click()")
                    await until("document.getElementById('content-summary').textContent.includes('2 / 2')")
                    report=json.loads((state/'content.json').read_text());assert report['deep'] and not report['running'] and report['decode_errors']==0
                    await command('Page.navigate',{'url':'http://127.0.0.1:8787/archive/'+account})
                    await until("document.querySelectorAll('.archive-card').length===2")
                    await evaluate("document.querySelector('.favorite-toggle').click()")
                    await until("document.querySelector('.favorite-toggle').getAttribute('aria-pressed')==='true'")
                    await evaluate("document.getElementById('archive-favorites').checked=true;document.getElementById('archive-favorites').dispatchEvent(new Event('change'))")
                    await until("document.querySelectorAll('.archive-card').length===1")
                    await evaluate("document.getElementById('archive-reset').click()")
                    await until("document.querySelectorAll('.archive-card').length===2")
                    await evaluate("document.getElementById('archive-kind').value='video' ;document.getElementById('archive-kind').dispatchEvent(new Event('change'))")
                    await until("document.querySelectorAll('.archive-card').length===1&&document.querySelector('.archive-card strong').textContent==='sample.mp4'")
                    async with portal.get('http://127.0.0.1:8787/api/archive/thumb/'+account+'/'+item+'/sample.mp4')as response:
                        assert response.status==200 and (await response.read()).startswith(b'\xff\xd8')
                    await evaluate("document.querySelector('.archive-tile').click()")
                    await until("document.querySelector('#archive-preview video')?.readyState>=1")
                    assert await evaluate("document.getElementById('archive-preview').open")
                    await evaluate("document.getElementById('archive-close').click()")
                    await command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
                    assert await evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),'Mobile gallery overflows horizontally'
                    await command('Page.enable')
                    await evaluate("document.getElementById('archive-year').value=String(new Date().getFullYear());document.getElementById('archive-range-download').click()")
                    if not any(e.get('method')=='Page.javascriptDialogOpening' for e in events):
                        while True:
                            event=json.loads((await chrome.receive(timeout=20)).data)
                            if event.get('method')=='Page.javascriptDialogOpening':break
                    # Dismiss the native confirmation; API ZIP contents are verified separately.
                    await command('Page.handleJavaScriptDialog',{'accept':False})
            print('Real browser: reserves saved, pause rendered, local decoding, gallery filters, mobile layout and date-export confirmation passed')
        finally:
            Path('/control/running').unlink(missing_ok=True)
            Path('/control/paused').unlink(missing_ok=True)
            Path('/control/stop-request').unlink(missing_ok=True)
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
asyncio.run(main())
