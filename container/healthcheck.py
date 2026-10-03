"""Probe the portal, private login service and legacy worker without logging secrets."""
import base64
import os
import time
import urllib.request
from pathlib import Path

def check():
    token = base64.b64encode(('health:' + os.environ['APP_PASSWORD']).encode()).decode()
    request = urllib.request.Request('http://127.0.0.1:8787/api/status', headers={'Authorization': 'Basic ' + token})
    with urllib.request.urlopen(request, timeout=4) as response:
        if response.status != 200:
            raise RuntimeError('Portal unavailable')
    with urllib.request.urlopen('http://127.0.0.1:6080/vnc.html', timeout=4) as response:
        if response.status != 200:
            raise RuntimeError('Login service unavailable')
    if time.time() - int(Path('/control/heartbeat').read_text()) > 45:
        raise RuntimeError('Worker heartbeat expired')
    if time.time() - int(Path('/control/login-heartbeat').read_text()) > 15:
        raise RuntimeError('Login heartbeat expired')
    if not Path('/tmp/.X11-unix/X99').exists():
        raise RuntimeError('Display unavailable')

if __name__ == '__main__':
    try:
        check()
    except Exception:
        raise SystemExit(1)
