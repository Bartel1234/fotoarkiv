"""Test direct Chrome streaming and input isolation against a fake CDP endpoint."""
import asyncio, base64, json, sys, tempfile
from pathlib import Path
from aiohttp import ClientSession, web, WSMsgType
from aiohttp.test_utils import TestClient, TestServer
sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
from login_view import setup, input_command

async def main():
 for bad in ({'type':'Runtime.evaluate'},{'type':'mouse','event':'mousePressed','x':float('nan'),'y':0},{'type':'text','text':'x'*8193},{'type':'key','event':'keyDown','modifiers':16}):
  try:
   input_command(bad)
   raise AssertionError('Unsafe input accepted')
  except ValueError: pass
 with tempfile.TemporaryDirectory() as temp:
  control=Path(temp);(control/'login-active').write_text('first@example.com');calls=[];remote_headers=[]
  async def targets(request):
   return web.json_response([{'id':'test','type':'page','webSocketDebuggerUrl':'ws://ignored.example/devtools/page/test'}])
  async def chrome(request):
   remote_headers.append(dict(request.headers));ws=web.WebSocketResponse();await ws.prepare(request)
   async for message in ws:
    data=json.loads(message.data);calls.append(data);await ws.send_json({'id':data['id'],'result':{}})
    if data['method']=='Page.startScreencast':
     await ws.send_json({'method':'Page.screencastFrame','params':{'data':'ZmFrZS1qcGVn','sessionId':1,'metadata':{'deviceWidth':1280,'deviceHeight':800}}})
   return ws
  remote=web.Application();remote.router.add_get('/json/list',targets);remote.router.add_get('/devtools/page/test',chrome)
  async with TestServer(remote) as server:
   credential='Basic '+base64.b64encode(b'test:test-password').decode()
   @web.middleware
   async def auth(request,handler):
    if request.headers.get('Authorization')!=credential:raise web.HTTPUnauthorized()
    return await handler(request)
   app=web.Application(middlewares=[auth])
   async def session(app):
    app['session']=ClientSession();yield;await app['session'].close()
   app.cleanup_ctx.append(session)
   setup(app,control,lambda:['first@example.com','second@example.com'],'page-token',lambda t:t=='page-token',str(server.make_url('/')).rstrip('/'))
   async with TestClient(TestServer(app)) as client:
    path='/login/stream?account=first@example.com';headers={'Authorization':credential}
    for p in ['/login/','/login/login.js',path]:assert (await client.get(p)).status==401
    assert (await client.get('/login/?account=missing@example.com',headers=headers)).status==404
    response=await client.get('/login/?account=first@example.com',headers=headers)
    assert response.status==200 and 'frame-ancestors' in response.headers['Content-Security-Policy']
    assert 'page-token' in await response.text()
    assert (await client.get(path,headers={**headers,'Origin':'https://attacker.example'})).status==403
    origin=str(client.make_url('/')).rstrip('/')
    async with client.ws_connect(path,headers={**headers,'Origin':origin}) as ws:
     await ws.send_json({'token':'wrong'});assert (await ws.receive(timeout=2)).type==WSMsgType.CLOSE
    assert calls==[]
    async with client.ws_connect('/login/stream?account=second@example.com',headers={**headers,'Origin':origin}) as ws:
     await ws.send_json({'token':'page-token'});assert (await ws.receive_json(timeout=2))['type']=='waiting'
     await ws.send_json({'type':'text','text':'not sent'});await asyncio.sleep(.1);assert calls==[]
    async with client.ws_connect(path,headers={**headers,'Origin':origin}) as ws:
     await ws.send_json({'token':'page-token'})
     while True:
      data=await ws.receive_json(timeout=2)
      if data['type']=='frame':break
     assert data['image']=='ZmFrZS1qcGVn'
     await ws.send_json({'type':'ack','session':1})
     await ws.send_json({'type':'text','text':'test input'})
     await ws.send_json({'type':'mouse','event':'mousePressed','x':30,'y':40,'button':'left'})
     await ws.send_json({'type':'key','event':'keyDown','key':'Enter','code':'Enter','virtualKey':13})
     for _ in range(30):
      if any(c['method']=='Input.dispatchKeyEvent' for c in calls):break
      await asyncio.sleep(.02)
     assert any(c['method']=='Input.insertText' and c['params']['text']=='test input' for c in calls)
     assert any(c['method']=='Input.dispatchMouseEvent' for c in calls)
     assert any(c['method']=='Input.dispatchKeyEvent' for c in calls)
     assert all('Authorization' not in h for h in remote_headers)
     (control/'login-active').write_text('second@example.com')
     await ws.send_json({'type':'text','text':'must never cross accounts'})
     while (await ws.receive(timeout=2)).type==WSMsgType.TEXT:pass
     assert not any(c.get('params',{}).get('text')=='must never cross accounts' for c in calls)
 print('Direct Chrome streaming, origin/CSRF protection, restricted input and account isolation passed')
asyncio.run(main())
