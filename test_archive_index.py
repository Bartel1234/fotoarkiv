import asyncio
import importlib.util
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('index',Path(__file__).parent/'dashboard/archive_index.py')
index=importlib.util.module_from_spec(spec);spec.loader.exec_module(index)

def records(count=27000):
    for n in range(count):
        item='AF1Q'+str(n).zfill(36);album='album'+str(n%140)
        yield (item,'photo_'+str(n)+'.jpg','Bibliotek/2003/01/'+item+'.jpg',float(n),1000,'image','01/01/2003 00:00','google','photo_'+str(n)+'.jpg'),[{'id':album,'title':'Album '+str(n%140)}]

class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.target=self.root/'index.sqlite'
        with patch.object(index,'records',side_effect=lambda root:records()):index.rebuild(self.root,self.target)
    def tearDown(self):self.temp.cleanup()
    def test_indexed_pages_and_album_counts(self):
        rows,total,albums=index.query(self.target,'album0','',1)
        self.assertEqual(total,193);self.assertEqual(len(rows),48);self.assertEqual(len(albums),140)
        page2,_,_=index.query(self.target,'album0','',2)
        self.assertTrue(set(r[0] for r in rows).isdisjoint(r[0] for r in page2))
        self.assertEqual(index.query(self.target,'__none__','',1)[1],0)
        self.assertEqual(index.query(self.target,'','PHOTO_26999',1)[1],1)
        with sqlite3.connect(self.target) as db:
            plan=db.execute('EXPLAIN QUERY PLAN SELECT id,name FROM members WHERE album=? ORDER BY stamp DESC,id DESC,name DESC LIMIT 48',('album0',)).fetchall()
        self.assertTrue(any('members_page' in str(row) for row in plan))
        start=time.perf_counter()
        for n in range(140):index.query(self.target,'album'+str(n),'',1)
        print(f'140 album queries on 27,000 indexed media: {time.perf_counter()-start:.3f}s')
    def test_failed_refresh_keeps_previous_index(self):
        def failing(root):
            yield next(records())
            raise ValueError('interrupted scan')
        with patch.object(index,'records',side_effect=failing):
            with self.assertRaises(ValueError):index.rebuild(self.root,self.target)
        self.assertEqual(index.query(self.target,'','',1)[1],27000)
    def test_warm_switch_does_not_rescan(self):
        async def run():
            manager=index.ArchiveIndex(self.root);manager.target=lambda account:self.target
            manager.states['account']={'at':time.monotonic(),'signature':index.source_signature(self.root)}
            with patch.object(index,'rebuild',side_effect=AssertionError('Must not scan when switching albums')):
                for n in range(5):
                    target=await manager.ensure('account',self.root);index.query(target,'album'+str(n),'',1)
                await manager.close()
        asyncio.run(run())
    def test_background_refresh_serves_old_snapshot(self):
        async def run():
            manager=index.ArchiveIndex(self.root);manager.target=lambda account:self.target
            with patch.object(index,'records',side_effect=lambda root:records(1)):
                target=await manager.ensure('account',self.root)
                self.assertEqual(index.query(target,'','',1)[1],27000)
                await manager.close()
            self.assertEqual(index.query(target,'','',1)[1],1)
        asyncio.run(run())

if __name__=='__main__':unittest.main()
