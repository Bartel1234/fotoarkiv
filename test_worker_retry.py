"""Exercise actual shell orchestration without Google or outbound mail."""
import json,os,re,subprocess,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).parent
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);state=root/'control/accounts/test@example.com';media=root/'download/test@example.com';profiles=root/'accounts/test@example.com';fake=root/'bin'
 for folder in (state,media,profiles,fake):folder.mkdir(parents=True)
 (media/'.fotoarkiv').mkdir();(media/'.fotoarkiv/metadata.json').write_text(json.dumps({'version':1,'complete':True,'updated':datetime.now(timezone.utc).isoformat(),'items':{},'albums':{}}))
 (state/'settings.json').write_text(json.dumps({'min_free_gb':0,'min_free_percent':0,'retry_count':2,'index_hours':24}))
 script=root/'worker.sh';mapping={key:root/key for key in ['control','download','accounts']}
 text=re.sub(r'(?<![A-Za-z0-9/])/(control|download|accounts)',lambda m:str(mapping[m[1]]),(ROOT/'account-worker.sh').read_text())
 organizer=root/'organize.py';organizer.write_text('print("fake organizer passed")\n')
 text=text.replace('/usr/local/bin/fotoarkiv-organize.py',str(organizer)).replace('sleep $((30*retries))','sleep 0.05');script.write_text(text)
 command=fake/'gphotos-cdp';command.write_text('''#!/usr/bin/env python3
import json,os,time
from pathlib import Path
state=Path(os.environ['PHOTOHARBOR_RUN_STATE']);attempt=int(os.environ['PHOTOHARBOR_ATTEMPT']);(state/'calls').open('a').write(str(attempt)+'\\n')
if attempt<1:
 (state/'download-failure.json').write_text(json.dumps({'at':time.time(),'retryable':True,'category':'download','id':'test'}));raise SystemExit(1)
(state/'downloads.jsonl').open('a').write(json.dumps({'id':'test','name':'a.jpg','kind':'image','bytes':123})+'\\n')
''');command.chmod(0o755)
 env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'],BACKUP_STATE=str(ROOT/'dashboard/backup_state.py'))
 result=subprocess.run(['/bin/sh',str(script),'test@example.com','--run','0','backup'],env=env,capture_output=True,text=True,timeout=20)
 assert result.returncode==0,result.stdout+result.stderr
 assert (state/'calls').read_text().splitlines()==['0','1']
 assert (state/'retry-count').read_text().strip()=='1'
 assert 'Using cached' in result.stdout and 'retry 1/2' in result.stdout
 # Permanent failures must stop without retry or advancing the downloader cursor.
 command.write_text(command.read_text().replace("'retryable':True","'retryable':False").replace('if attempt<1:','if True:'))
 (state/'calls').unlink()
 result=subprocess.run(['/bin/sh',str(script),'test@example.com','--run','0','backup'],env=env,capture_output=True,text=True,timeout=20)
 assert result.returncode==1 and (state/'calls').read_text().splitlines()==['0']
 print('Worker reuses complete fresh metadata, retries transient errors, records retry count, and stops on permanent failures')
