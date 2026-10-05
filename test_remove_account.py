import asyncio
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer

ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'dashboard'));os.environ['APP_PASSWORD']='test-password-only'
import app as portal

async def wait_for(predicate,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return
        await asyncio.sleep(.1)
    raise AssertionError('Timed out')

async def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);control=root/'control';photos=root/'photos';accounts=root/'accounts';scripts=root/'controller';fake=root/'bin';profile=root/'profile'
        for path in [control,photos,accounts,scripts,fake,profile]:path.mkdir()
        for path in [control/'accounts',control/'workers']:path.mkdir()
        emails=['keep@example.com','delete@example.com','other@example.com']
        (control/'accounts.txt').write_text('\n'.join(emails)+'\n')
        for email in emails:
            (photos/email).mkdir();(photos/email/'photo.jpg').write_bytes(b'precious-original')
            (accounts/email/'gphotos-cdp').mkdir(parents=True);(accounts/email/'gphotos-cdp/session').write_text('saved login')
            state=control/'accounts'/email;state.mkdir();(state/'next-run').write_text(str(int(time.time())+86400))
        mapping={'control':control,'download':photos,'accounts':accounts,'controller':scripts,'tmp':profile,'config':profile/'gphotos-cdp'}
        for name in ['worker.sh','account-worker.sh','login/login-loop.sh']:
            s=(ROOT/name).read_text()
            s=re.sub(r'(?<![A-Za-z0-9/])/(control|download|accounts|controller|tmp|config)',lambda m:str(mapping[m[1]]),s)
            (scripts/Path(name).name).write_text(s)
        for name in ['gphotos-cdp','google-chrome']:
            p=fake/name;p.write_text('#!/bin/sh\nexec sleep 1000\n');p.chmod(0o755)
        env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'],BACKUP_STATE=str(ROOT/'dashboard/backup_state.py'))
        processes=[subprocess.Popen(['/bin/sh',str(scripts/name)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) for name in ['worker.sh','login-loop.sh']]
        portal.CONTROL=control;portal.PHOTOS=photos;portal.ACCOUNTS=accounts;portal.ACCOUNT_LIST=control/'accounts.txt'
        app=web.Application(middlewares=[portal.language]);app['account_lock']=asyncio.Lock()
        portal.setup_archive(app,photos,control/'thumbnails',portal.account_names,lambda t:t==portal.TOKEN)
        app.router.add_post('/api/accounts/{email}/{action:remove|start|login}',portal.account_action)
        try:
            async with TestClient(TestServer(app)) as client:
                fields={'token':portal.TOKEN,'mode':'keep','confirmation':emails[0]}
                route='/api/accounts/'+emails[0]+'/remove'
                for bad in [{**fields,'token':'wrong'},{**fields,'confirmation':'wrong'},{**fields,'mode':'wrong'}]:
                    response=await client.post(route,json=bad);assert response.status in [400,403]
                assert not (control/'accounts'/emails[0]/'removal-pending').exists()
                assert (photos/emails[0]/'photo.jpg').read_bytes()==b'precious-original'
                # Two active backups; the second account owns the interactive browser.
                for email in [emails[0],emails[2]]:(control/'accounts'/email/'start-request').write_text('1')
                (control/'login-request').write_text(emails[1]+' 1')
                await wait_for(lambda:all((control/'accounts'/e/'running').exists() for e in [emails[0],emails[2]]) and portal.read('login-active')==emails[1])
                response=await client.post(route,json=fields);assert response.status==200,await response.text();assert (await response.json())['kept_data']
                assert emails[0] not in portal.account_names();assert (photos/emails[0]/'photo.jpg').read_bytes()==b'precious-original'
                assert not (accounts/emails[0]).exists();assert not (control/'accounts'/emails[0]).exists()
                assert (control/'accounts'/emails[2]/'running').exists();assert portal.read('login-active')==emails[1]
                response=await client.post('/api/accounts/'+emails[1]+'/remove',json={'token':portal.TOKEN,'mode':'delete','confirmation':emails[1]});assert response.status==200,await response.text()
                assert not (photos/emails[1]).exists() and not (accounts/emails[1]).exists()
                assert emails[1] not in portal.account_names();assert (photos/emails[2]/'photo.jpg').exists()
                assert (control/'accounts'/emails[2]/'running').exists()
                # Failed worker acknowledgement must preserve membership and media.
                with patch.object(portal,'REMOVAL_TIMEOUT',0):
                    response=await client.post('/api/accounts/'+emails[2]+'/remove',json={'token':portal.TOKEN,'mode':'delete','confirmation':emails[2]})
                assert response.status==409;assert emails[2] in portal.account_names();assert (photos/emails[2]/'photo.jpg').exists()
                response=await client.post('/api/accounts/legacy/remove',json={'token':portal.TOKEN,'mode':'delete','confirmation':'legacy'});assert response.status==400
            print('Removal: typed confirmation, token, keep/delete files, active worker shutdown, browser shutdown, isolation and timeout safety passed')
        finally:
            for process in processes:process.terminate()
            for process in processes:process.wait(timeout=35)

asyncio.run(main())

