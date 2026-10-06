import os,re,subprocess,tempfile,time,json
from pathlib import Path

ROOT=Path(__file__).parent
def wait_for(predicate,seconds=40):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.1)
    raise AssertionError('Timed out')

with tempfile.TemporaryDirectory()as temp:
    root=Path(temp);control=root/'control';media=root/'media';profiles=root/'profiles';fake=root/'bin'
    for folder in [control,media,profiles,fake]:folder.mkdir()
    script=root/'worker.sh'
    mapping={'control':control,'download':media,'accounts':profiles}
    script.write_text(re.sub(r'(?<![A-Za-z0-9/])/(control|download|accounts)',lambda m:str(mapping[m[1]]),(ROOT/'account-worker.sh').read_text()))
    command=fake/'gphotos-cdp';command.write_text('#!/bin/sh\necho x >> "$TMPDIR/started"\nexec sleep 1000\n');command.chmod(0o755)
    state=control/'accounts/test@example.com';state.mkdir(parents=True)
    state.joinpath('settings.json').write_text(json.dumps({'enabled':True,'hour':3,'days':[0],'min_free_gb':0,'min_free_percent':0}))
    state.joinpath('start-request').write_text('1')
    env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'],BACKUP_STATE=str(ROOT/'dashboard/backup_state.py'))
    process=subprocess.Popen(['/bin/sh',str(script),'test@example.com'],env=env)
    profile=profiles/'test@example.com'
    try:
        wait_for(lambda:(profile/'started').exists())
        state.joinpath('paused').write_text('user');state.joinpath('stop-request').write_text('1')
        wait_for(lambda:state.joinpath('last-exit').exists() and state.joinpath('last-exit').read_text().strip()=='131')
        assert not state.joinpath('running').exists() and process.poll()is None
        # An overdue schedule must not restart a paused account.
        state.joinpath('next-run').write_text('1');time.sleep(11)
        assert len(profile.joinpath('started').read_text().splitlines())==1
        state.joinpath('paused').unlink();state.joinpath('start-request').write_text('1')
        wait_for(lambda:len(profile.joinpath('started').read_text().splitlines())==2)
        # Change the reserve during a live download: worker pauses this account.
        config=json.loads(state.joinpath('settings.json').read_text());config['min_free_gb']=100000
        state.joinpath('settings.json').write_text(json.dumps(config))
        wait_for(lambda:state.joinpath('last-exit').read_text().strip()=='132',50)
        assert state.joinpath('paused').read_text().strip()=='storage'
        assert not state.joinpath('running').exists()
        assert json.loads(state.joinpath('storage.json').read_text())['low']
        # Restarting the worker preserves pause and never starts Chrome on low space.
        process.terminate();process.wait(timeout=10)
        process=subprocess.Popen(['/bin/sh',str(script),'test@example.com'],env=env)
        time.sleep(11)
        assert len(profile.joinpath('started').read_text().splitlines())==2
        print('Pause preserves worker, blocks overdue schedules, resumes on request and persists low-space pause across restart')
    finally:
        process.terminate();process.wait(timeout=10)
