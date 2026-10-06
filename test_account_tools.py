import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).parent
__import__("sys").path.insert(0,str(ROOT/"dashboard"))
spec=importlib.util.spec_from_file_location('backup_state',ROOT/'dashboard/backup_state.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
spec=importlib.util.spec_from_file_location('archive_index',ROOT/'dashboard/archive_index.py')
idx=importlib.util.module_from_spec(spec);spec.loader.exec_module(idx)

class AccountTests(unittest.TestCase):
    def test_schedule_pause_and_weekdays(self):
        config={'enabled':True,'hour':3,'days':[0,4]}
        # Monday after the scheduled hour -> Friday; Friday before the hour -> today.
        first=datetime.fromtimestamp(b.next_run(config,datetime(2026,10,5,22)))
        self.assertEqual(first,datetime(2026,10,9,3))
        self.assertEqual(datetime.fromtimestamp(b.next_run(config,datetime(2026,10,9,1))),datetime(2026,10,9,3))
        self.assertEqual(b.next_run({**config,'enabled':False}),0)
        for changes in [{'days':[]},{'days':[7]},{'days':[True]},{'hour':24},{'enabled':'yes'},{'notify_url':'file:///etc/passwd'},{'notify_url':'https://user:pass@ntfy.sh/a'}]:
            with self.assertRaises(ValueError):b.validate({**config,**changes})
    def test_missing_empty_repair_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'media';state=Path(temp)/'state';(root/'.fotoarkiv').mkdir(parents=True)
            item1='AF1Q'+'a'*36;item2='AF1Q'+'b'*36;item3='AF1Q'+'c'*36
            good=root/'Bibliotek/2003/01/a.jpg';good.parent.mkdir(parents=True);good.write_bytes(b'original media')
            empty=root/'Bibliotek/2003/01/b.jpg';empty.touch()
            album=root/'Albums/test/b.jpg';album.parent.mkdir(parents=True);album.hardlink_to(empty)
            with sqlite3.connect(root/'.fotoarkiv/catalog.sqlite')as db:
                db.execute('CREATE TABLE files(id,name,path,timestamp,albums,date_label)')
                db.executemany('INSERT INTO files VALUES(?,?,?,?,?,?)',[(item1,'a.jpg','Bibliotek/2003/01/a.jpg',0,'[]','01/01/2003 00:00'),(item1,'gone.jpg','Bibliotek/2003/01/gone.jpg',0,'[]','01/01/2003 00:00'),(item2,'b.jpg','Bibliotek/2003/01/b.jpg',0,json.dumps([{'path':'Albums/test/b.jpg'}]),'01/01/2003 00:00')])
            b.atomic(root/'.fotoarkiv/metadata.json',{'complete':True,'items':{item1:{},item2:{},item3:{}}})
            report=b.check(root,state);self.assertEqual((report['checked'],report['missing'],report['empty']),(3,1,1))
            self.assertEqual(report['unbacked_items'],2)
            # A missing second component invalidates the whole item, not just one file.
            self.assertEqual(b.load(root/'.fotoarkiv/downloaded.json',None),{})
            b.prepare_repair(root);self.assertTrue(good.is_file());self.assertEqual(good.read_bytes(),b'original media')
            self.assertFalse(empty.exists());self.assertFalse(album.exists())
            self.assertEqual(len(list((root/'.fotoarkiv/quarantine').glob('*/*'))),2)
            b.begin(root,state,'check');b.finish(root,state,0)
            self.assertFalse((state/'last-success.json').exists())
            b.begin(root,state,'backup');new=good.with_name('new.jpg');new.write_bytes(b'new')
            entry=b.finish(root,state,0);self.assertEqual(entry['new_files'],1);self.assertEqual(entry['new_bytes'],3)
            self.assertEqual(b.load(state/'last-success.json',{})['result'],0)
            b.begin(root,state,'backup');b.finish(root,state,130)
            self.assertEqual(len(b.load(state/'history.json',[])),3)
            self.assertEqual(b.load(state/'last-success.json',{})['result'],0)
    def test_notification_payload_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'media';root.mkdir();state=Path(temp)/'private@example.com';state.mkdir()
            b.atomic(state/'settings.json',{'enabled':True,'hour':3,'days':[0],'notify_url':'https://ntfy.sh/test','notify_success':True})
            b.begin(root,state,'backup')
            calls=[]
            def fail(req,**kwargs):calls.append(req);raise OSError('offline')
            with patch('urllib.request.urlopen',side_effect=fail):entry=b.finish(root,state,0)
            self.assertEqual(entry['result'],0);self.assertFalse(b.load(state/'notification-status.json',{})['ok'])
            self.assertNotIn(b'private@example.com',calls[0].data)
            b.begin(root,state,'check')
            with patch('urllib.request.urlopen',side_effect=AssertionError('Check should not notify')):b.finish(root,state,0)
    def test_google_calendar_filters_and_album_search(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=root/'index.sqlite'
            rows=[(('AF1Q'+'a'*36,'old.jpg','a.jpg',0,100,'image','31/12/2003 23:59','google','old.jpg'),[{'id':'holiday','title':'Summer Holiday'}]),(('AF1Q'+'b'*36,'movie.mp4','b.mp4',1,200,'video','01/01/2026 00:00','google','movie.mp4'),[])]
            with patch.object(idx,'records',return_value=iter(rows)):idx.rebuild(root,target)
            self.assertEqual(idx.query(target,'','',1,2003,12,'image')[1],1)
            self.assertEqual(idx.query(target,'','',1,2003,1,'image')[1],0)
            self.assertEqual(idx.query(target,'','',1,0,0,'video')[1],1)
            self.assertEqual(idx.query(target,'','HOLIDAY',1)[1],1)
            self.assertEqual(idx.query(target,'','',1,sort='oldest')[0][0][1],'old.jpg')
            self.assertEqual(idx.query(target,'','',1)[0][0][1],'movie.mp4')

if __name__=='__main__':unittest.main()
