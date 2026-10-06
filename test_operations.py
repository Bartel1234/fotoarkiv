import asyncio, json, os, sqlite3, sys, tempfile, time, unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
os.environ['APP_PASSWORD']='operations-test-password'
import operations as op
import backup_state as b
import app as portal
from archive_index import rebuild,query
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
import archive

CONFIG={'enabled':True,'host':'smtp.example.com','port':587,'security':'starttls','username':'user','password':'secret','sender':'backup@example.com','recipient':'recipient@example.com','language':'da'}
class Tests(unittest.TestCase):
 def test_tls_and_secret_policy(self):
  client=MagicMock();client.__enter__.return_value=client
  with patch('smtplib.SMTP',return_value=client) as factory:
   op.send_mail(CONFIG,'Test','body')
   factory.assert_called_once_with('smtp.example.com',587,timeout=15)
   names=[c[0] for c in client.method_calls]
   self.assertLess(names.index('starttls'),names.index('login'));self.assertLess(names.index('login'),names.index('send_message'))
  self.assertNotIn('password',op.smtp_public(CONFIG))
  self.assertEqual(op.smtp_validate({**CONFIG,'password':''},CONFIG)['password'],'secret')
  for changes in [{'security':'none'},{'sender':'a@example.com\r\nBcc:x@example.com'},{'recipient':'a@example.com,b@example.com'},{'port':True}]:
   with self.assertRaises(ValueError):op.smtp_validate({**CONFIG,**changes})
 def test_completed_counts_email_modes_and_redaction(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'media';root.mkdir();state=Path(temp)/'control/accounts/user@example.com';state.mkdir(parents=True)
   op.smtp_save(op.smtp_path(state),CONFIG)
   b.atomic(state/'settings.json',{'email_enabled':True,'email_mode':'all','notify_url':'https://ntfy.sh/secret'})
   b.begin(root,state,'backup')
   events=[{'id':'a','name':'a.jpg','bytes':10,'kind':'image'},{'id':'b','name':'b.mp4','bytes':100,'kind':'video'},{'id':'a','name':'a.jpg','bytes':10,'kind':'image'}]
   (state/'downloads.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events)+'{partial')
   b.atomic(state/'storage.json',{'free':1024**3})
   with patch.object(op,'send_mail') as send: entry=b.finish(root,state,0)
   self.assertEqual((entry['downloaded_files'],entry['downloaded_bytes'],entry['downloaded_images'],entry['downloaded_videos']),(2,110,1,1))
   self.assertIn('user@example.com',send.call_args.args[2]);self.assertNotIn('a.jpg',send.call_args.args[2]);self.assertNotIn('secret',send.call_args.args[2]);self.assertTrue(b.load(state/'email-status.json',{})['ok'])
   document=op.diagnostics(state,'beta-test');text=json.dumps(document)
   for secret in ['user@example.com','a.jpg','smtp.example.com','secret']:self.assertNotIn(secret,text)
   b.atomic(state/'settings.json',{'email_enabled':True,'email_mode':'errors'})
   b.begin(root,state,'backup')
   with patch.object(op,'send_mail',side_effect=AssertionError('Success should not notify')):b.finish(root,state,0)
   b.begin(root,state,'backup')
   with patch.object(op,'send_mail',side_effect=OSError('private remote error')):entry=b.finish(root,state,1)
   self.assertEqual(entry['result'],1);self.assertFalse(b.load(state/'email-status.json',{})['ok']);self.assertNotIn('private',json.dumps(b.load(state/'email-status.json',{})))
 def test_cache_and_failure_age(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);state=root/'control';state.mkdir()
   b.atomic(root/'.fotoarkiv/metadata.json',{'complete':True,'updated':datetime.now(timezone.utc).isoformat()})
   self.assertFalse(op.index_due(root,state));self.assertTrue(op.index_due(root,state,True))
   b.atomic(state/'settings.json',{'index_hours':0});self.assertTrue(op.index_due(root,state))
   for data,result in [({'retryable':True,'at':time.time()},True),({'retryable':True,'at':time.time()-300},False),({'retryable':False,'at':time.time()},False)]:b.atomic(state/'download-failure.json',data);self.assertEqual(op.retryable(state),result)
 def test_email_api_and_favorites_isolation(self):asyncio.run(self.api_checks())
 async def api_checks(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);portal.CONTROL=root/'control';portal.CONTROL.mkdir();portal.ACCOUNT_LIST=portal.CONTROL/'accounts.txt';portal.ACCOUNT_LIST.write_text('first@example.com\nsecond@example.com\n');media=root/'photos';media.mkdir()
   for account in ['first@example.com','second@example.com']:
    folder=media/account/('AF1Q'+'a'*36);folder.mkdir(parents=True);(folder/'a.jpg').write_bytes(b'original')
   application=web.Application();application['account_lock']=asyncio.Lock();application.router.add_get('/api/email',portal.email_settings);application.router.add_post('/api/email/{action}',portal.email_settings);application.router.add_post('/api/diagnostics/{email}',portal.diagnostic_download)
   archive.setup(application,media,root/'thumb',portal.account_names,lambda supplied:supplied==portal.TOKEN)
   async with TestClient(TestServer(application)) as client:
    r=await client.post('/api/email/save',json={'token':'wrong','settings':CONFIG});self.assertEqual(r.status,403)
    r=await client.post('/api/email/save',json={'token':portal.TOKEN,'settings':CONFIG});self.assertEqual(r.status,200);self.assertNotIn('secret',await r.text())
    self.assertEqual((portal.CONTROL/'smtp.json').stat().st_mode&0o777,0o600)
    r=await client.get('/api/email');self.assertNotIn('secret',await r.text())
    with patch.object(portal,'send_mail',side_effect=OSError('credential-secret')):
     r=await client.post('/api/email/test',json={'token':portal.TOKEN});self.assertEqual(r.status,502);self.assertNotIn('credential-secret',await r.text())
    r=await client.post('/api/diagnostics/first@example.com',json={'token':'bad'});self.assertEqual(r.status,403)
    r=await client.post('/api/diagnostics/first@example.com',json={'token':portal.TOKEN});self.assertEqual(r.status,200);self.assertNotIn('example.com',await r.text())
    data={'account':'first@example.com','id':'AF1Q'+'a'*36,'name':'a.jpg','favorite':True,'token':portal.TOKEN}
    r=await client.post('/api/archive/favorite',json={**data,'token':'bad'});self.assertEqual(r.status,403)
    r=await client.post('/api/archive/favorite',json=data);self.assertEqual(r.status,200)
    r=await client.get('/api/archive?account=first@example.com&favorites=1');self.assertEqual((await r.json())['total'],1)
    r=await client.get('/api/archive?account=second@example.com&favorites=1');self.assertEqual((await r.json())['total'],0)
    r=await client.get('/api/archive?account=first@example.com&anniversary=99-99');self.assertEqual(r.status,400)
    r=await client.post('/api/archive/favorite',json={**data,'favorite':False});self.assertEqual(r.status,200)
    r=await client.get('/api/archive?account=first@example.com&favorites=1');self.assertEqual((await r.json())['total'],0)
 def test_date_search_and_memories(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);db=root/'index';now=datetime.now();day=now.strftime('%m-%d')
   rows=[(('AF1Q'+'a'*36,'old.jpg','old.jpg',0,10,'image',now.replace(year=now.year-1).strftime('%d/%m/%Y %H:%M'),'google','old.jpg'),[]),(('AF1Q'+'b'*36,'new.jpg','new.jpg',1,10,'image',now.strftime('%d/%m/%Y %H:%M'),'google','new.jpg'),[])]
   with patch('archive_index.records',return_value=iter(rows)):rebuild(root,db)
   self.assertEqual(query(db,'','',1,anniversary=day)[1],1)
   self.assertEqual(query(db,'',str(now.year-1)+'-'+day,1)[1],1)

if __name__=='__main__':unittest.main()
