import os
import subprocess
import tempfile
import time
from pathlib import Path

def wait_for(predicate,seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.1)
    raise AssertionError('Timed out')

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);control=root/'control'; control.mkdir(); fake=root/'bin';fake.mkdir()
    command=fake/'gphotos-cdp'
    command.write_text('#!/bin/sh\necho $$ > "$TMPDIR/test-pid"\nsleep 1000 &\necho $! > "$TMPDIR/child-pid"\nwait\n');command.chmod(0o755)
    script=root/'worker.sh'
    source=(Path(__file__).parent/'account-worker.sh').read_text().replace('/control',str(control)).replace('/download',str(root/'download')).replace('/accounts',str(root/'accounts'))
    # Only literal runtime roots are replaced; both parent/child execute the same script.
    script.write_text(source)
    env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'])
    workers=[]
    try:
        for account in ['first@example.com','second@example.com']:
            state=Path(str(control)+'/accounts/'+account)
            # Account-root substitution also changes this subpath in this test only.
            state=Path(str(control)+str(root/'accounts')+'/'+account)
            state.mkdir(parents=True);(state/'start-request').write_text('1')
            workers.append((account,state,subprocess.Popen(['/bin/sh',str(script),account],env=env)))
        first,second=workers
        profile=root/'accounts'/first[0]
        wait_for(lambda:(profile/'child-pid').exists())
        other=root/'accounts'/second[0]
        wait_for(lambda:(other/'child-pid').exists())
        (first[1]/'stop-request').write_text('1')
        wait_for(lambda:(first[1]/'last-exit').exists())
        assert (first[1]/'last-exit').read_text().strip()=='130'
        assert not (first[1]/'running').exists()
        otherpid=int((other/'test-pid').read_text());os.kill(otherpid,0)
        assert second[1].joinpath('running').exists()
        assert first[2].poll() is None
        print('Stop terminates the account job, keeps its worker alive and leaves another account running')
    finally:
        for _,_,process in workers:
            process.terminate()
        for _,_,process in workers:process.wait(timeout=10)
