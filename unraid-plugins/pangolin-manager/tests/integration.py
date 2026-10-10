#!/usr/bin/env python3
"""Real HTTP/PHP integration with a fixture Docker CLI; never touches Unraid paths."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

class Origin(BaseHTTPRequestHandler):
    docker_mode = 'up'
    def do_GET(self):
        if self.path.startswith('/containers/'):
            code = 404 if self.docker_mode == 'missing' else 500 if self.docker_mode == 'error' else 200
            self.send_response(code);self.end_headers()
            if self.docker_mode == 'invalid': self.wfile.write(b'not-json');return
            if self.path.startswith('/containers/json'):
                value = [] if self.docker_mode == 'empty' else [
                    {'Names':['/Other'],'Image':'other:fixture','State':'exited'},
                    {'Names':['/Newt'],'Image':'fosrl/newt:fixture','State':'running'}]
            else: value = {'Id':'socket-fixture','State':{'Running':True},'Config':{'Env':[]}}
            self.wfile.write(json.dumps(value).encode());return
        if self.path.startswith('/slow'): time.sleep(.35)
        code = 503 if self.path == '/bad' else 403 if self.path == '/auth' else 200
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b'fixture')
    def log_message(self, *args): pass

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

origin = ThreadingHTTPServer(('127.0.0.1', 0), Origin)
threading.Thread(target=origin.serve_forever, daemon=True).start()
root = Path(__file__).resolve().parents[1]
php = os.environ.get('PM_TEST_PHP', 'php')
args = [php, '-n']
if os.environ.get('PM_TEST_PHP_CURL'): args += ['-d', 'extension=' + os.environ['PM_TEST_PHP_CURL']]
if os.environ.get('PM_TEST_DISABLE_PROC_OPEN'): args += ['-d', 'disable_functions=proc_open']

with tempfile.TemporaryDirectory(prefix='pm-integration-') as temp:
    tmp = Path(temp)
    src = tmp / 'app'; shutil.copytree(root / 'src', src)
    lib = (src / 'lib.php').read_text().replace('/boot/config/plugins/pangolin-manager/settings.json', str(tmp / 'settings.json')).replace('/var/local/pangolin-manager', str(tmp / 'runtime')).replace('/var/local/emhttp/var.ini', str(tmp / 'var.ini'))
    (src / 'lib.php').write_text(lib)
    (tmp / 'var.ini').write_text('csrf_token="test-csrf"\n')
    (tmp / 'mode').write_text('up')
    # This test-only executable stands in for Docker. The plugin itself is unmodified
    # except for filesystem paths in its isolated test copy.
    docker = tmp / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import json,sys,pathlib
mode=pathlib.Path(__file__).with_name('mode').read_text()
if mode=='failed':
 print('NEWT_SECRET=never-expose-this',file=sys.stderr);sys.exit(2)
if sys.argv[1]=='inspect':
 print(json.dumps([{'Id':'fixture-id','State':{'Running':mode!='stopped','Paused':False,'Restarting':False},'RestartCount':0,'Config':{'Env':['HEALTH_FILE=/tmp/healthy','NEWT_SECRET=private-fixture-secret']}}]))
elif sys.argv[1]=='ps': print(json.dumps({'Names':'Newt','Image':'fosrl/newt:fixture','State':'running'}))
elif sys.argv[1]=='exec': sys.exit(1 if mode=='offline' else 0)
elif sys.argv[1]=='logs': print('NEWT_SECRET=private-fixture-secret token=fixture-token')
elif sys.argv[1]=='restart': print('fixture-id')
else: sys.exit(2)
''')
    docker.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp)+os.pathsep+os.environ['PATH'])
    api_port = port()
    server = subprocess.Popen(args+['-S',f'127.0.0.1:{api_port}','-t',str(src)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{api_port}/api.php'
    def request(action, payload=None, token='test-csrf', **extra):
        data = None if payload is None else urlencode({'action':action,'csrf_token':token,'payload':json.dumps(payload),**extra}).encode()
        target=url+('?action='+action if data is None else '')
        try:
            with urllib.request.urlopen(urllib.request.Request(target,data=data),timeout=20) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    count=0
    def expect(condition, label):
        global count
        assert condition,label
        count+=1
    try:
        for _ in range(100):
            try: request('status');break
            except urllib.error.URLError: time.sleep(.03)
        endpoint=f'http://127.0.0.1:{origin.server_port}'
        expect(request('containers')[1]['containers'][0]['name']=='Newt','Discover containers through CLI fallback')
        (tmp/'mode').write_text('failed');code,body=request('containers')
        expect(code==503 and 'kode 2' in body['error'] and 'never-expose-this' not in json.dumps(body),'Expose controlled Docker errors without raw stderr')
        (tmp/'mode').write_text('up')
        cfg={'container':'Newt','endpoint':endpoint,'health_file':'','api_url':'','api_key':'private-api-key','org_id':'','site_id':'','notifications':False,
             'services':[{'name':'Good','url':endpoint+'/healthy','mode':'http','public_url':''},
                         {'name':'Broken','url':endpoint+'/bad','mode':'http','public_url':''},
                         {'name':'Protected','url':endpoint+'/auth','mode':'http','public_url':''}]}
        expect(request('save',cfg,token='wrong')[0]==403,'Reject wrong CSRF token')
        expect(request('save',dict(cfg,container='--help'))[0]==400,'Reject unsafe container over HTTP')
        expect(request('save',cfg)[0]==200,'Save valid configuration')
        public=request('settings')[1]['settings'];expect(public['has_api_key'] and 'api_key' not in public,'Do not expose API key in settings')
        s=request('test',{})[1]['status'];expect(s['container']['state']=='up','Read container running state')
        expect(s['tunnel']['state']=='up','Read tunnel healthfile')
        expect([x['state'] for x in s['services']]==['up','down','unknown'],'Actual HTTP status classification')
        expect('private-api-key' not in json.dumps(s),'Do not leak key in status')
        expect('private-fixture-secret' not in request('logs',{})[1]['logs'],'Redact actual fixture log')
        (tmp/'mode').write_text('offline');expect(request('test',{})[1]['status']['tunnel']['state']=='down','Missing healthfile is offline')
        (tmp/'mode').write_text('stopped');expect(request('test',{})[1]['status']['container']['state']=='down','Stopped container detected')
        expect(request('restart',{})[0]==400,'Restart requires explicit confirmation')
        expect(request('restart',{},confirm='restart-newt')[0]==200,'Confirmed restart targets configured container')
        (tmp/'mode').write_text('up')
        cfg['api_key']='';cfg['services']=[{'name':f'Slow {i}','url':endpoint+'/slow'+str(i),'mode':'http','public_url':''} for i in range(5)]
        request('save',cfg);started=time.monotonic();s=request('test',{})[1]['status'];duration=time.monotonic()-started
        expect(all(x['state']=='up' for x in s['services']) and duration<1.5,'HTTP probes run concurrently')
        cache=tmp/'runtime/status.json';old=json.loads(cache.read_text());old['checked_at']=int(time.time())-200;cache.write_text(json.dumps(old));s=request('status')[1]['status']
        expect(s['stale'] and s['tunnel']['state']=='unknown' and all(x['state']=='unknown' for x in s['services']),'Stale cache never remains green')
        # AF_UNIX is prohibited in this environment. Exercise identical cURL/JSON
        # behavior through a TCP fixture, replacing only the transport in the copy.
        # Actual socket permissions/transport still require on-server verification.
        server.terminate();server.wait(timeout=5)
        socket_marker=tmp/'docker.sock';socket_marker.touch()
        socket_lib=lib.replace("$socket='/var/run/docker.sock';",f"$socket='{socket_marker}';")
        socket_lib=socket_lib.replace("curl_init('http://localhost'.$path)",f"curl_init('{endpoint}'.$path)")
        socket_lib=socket_lib.replace('CURLOPT_UNIX_SOCKET_PATH=>$socket,','')
        (src/'lib.php').write_text(socket_lib)
        (tmp/'mode').write_text('failed') # Socket reads must work without the CLI.
        server=subprocess.Popen(args+['-S',f'127.0.0.1:{api_port}','-t',str(src)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try: request('status');break
            except urllib.error.URLError: time.sleep(.03)
        rows=request('containers')[1]['containers']
        expect([v['name'] for v in rows]==['Newt','Other'] and rows[0]['suggested'],'Docker API list parsing, slash removal and Newt priority')
        s=request('test',{})[1]['status'];expect(s['container']['state']=='up','Docker API inspect succeeds with CLI unavailable')
        Origin.docker_mode='missing';s=request('test',{})[1]['status'];expect(s['container']['state']=='down','Docker API 404 is a missing container')
        Origin.docker_mode='empty';expect(request('containers')[1]['containers']==[],'Empty Docker API list is successful')
        Origin.docker_mode='invalid';code,body=request('containers');expect(code==503 and 'ugyldigt svar' in body['error'],'Malformed Docker response does not silently produce an empty list')
        Origin.docker_mode='error';code,body=request('containers');expect(code==503 and 'HTTP 500' in body['error'],'Docker HTTP error produces actionable message')
        print(f'PASS: {count} HTTP/PHP integration checks (parallel sample {duration:.2f}s; proc_open disabled: {bool(os.environ.get("PM_TEST_DISABLE_PROC_OPEN"))})')
    finally:
        server.terminate();server.wait(timeout=5);origin.shutdown()
