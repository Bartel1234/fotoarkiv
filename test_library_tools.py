import importlib.util
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT/'dashboard'))
import library_tools as tools
import archive_index as index
from backup_state import atomic, load, validate
spec = importlib.util.spec_from_file_location('organize', ROOT/'login/organize.py')
organizer = importlib.util.module_from_spec(spec); spec.loader.exec_module(organizer)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)/'media'; self.state = Path(self.temp.name)/'state'
        (self.root/'.fotoarkiv').mkdir(parents=True); self.state.mkdir()
    def tearDown(self): self.temp.cleanup()
    def media(self, number, name='photo.jpg', content=None):
        item = 'AF1Q'+str(number).zfill(36); folder = self.root/item; folder.mkdir()
        path = folder/name
        if content is None: Image.new('RGB',(20,10),'blue').save(path)
        else: path.write_bytes(content)
        return item,path
    def test_storage_boundaries(self):
        atomic(self.state/'settings.json', {'min_free_gb':1,'min_free_percent':10})
        with patch.object(shutil,'disk_usage',return_value=shutil._ntuple_diskusage(20*1024**3,19*1024**3,1024**3)):
            report=tools.storage(self.root,self.state);self.assertTrue(report['low']);self.assertEqual(report['reserve'],2*1024**3)
        for value in [-1, float('nan'), float('inf'), True]:
            with self.assertRaises(ValueError): validate({'enabled':True,'hour':3,'days':[0],'min_free_gb':value})
    def test_coverage_dates_and_album_only_items(self):
        item,path=self.media(1); absent='AF1Q'+str(2).zfill(36)
        metadata={'complete':True,'updated':'2026-10-06','albums':{'a':{'title':'Holiday'}},'items':{
            item:{'timestamp':1072911600000,'offset':7200,'albums':['a']},absent:{'timestamp':946684800000,'offset':0,'albums':['a']}}}
        atomic(self.root/'.fotoarkiv/metadata.json',metadata)
        report=tools.coverage(self.root,self.state)
        self.assertEqual((report['indexed'],report['local'],report['missing']),(2,1,1))
        self.assertEqual(report['albums'][0]['missing'],1)
        self.assertEqual({r['year']:r['missing'] for r in report['years']},{'2000':1,'2004':0})
    def test_content_baseline_changed_bytes_and_hardlinks(self):
        first,p=self.media(1);second,q=self.media(2);third,link=self.media(3)
        link.unlink();link.hardlink_to(p)
        tools.content_check(self.root,self.state,True)
        report=load(self.state/'content.json',{});self.assertEqual(report['decode_errors'],0)
        duplicates=load(self.state/'duplicates.json',{});self.assertEqual(duplicates['group_count'],1);self.assertEqual(duplicates['extra_files'],1)
        Image.new('RGB',(20,10),'red').save(q)
        tools.content_check(self.root,self.state,True)
        self.assertEqual(load(self.state/'content.json',{})['changed'],1)
        self.assertEqual(load(self.state/'duplicates.json',{})['group_count'],0)
        q.write_bytes(b'broken JPEG')
        tools.content_check(self.root,self.state,True)
        self.assertEqual(load(self.state/'content.json',{})['decode_errors'],1)
        # Rechecks do not silently replace the first checksum baseline.
        tools.content_check(self.root,self.state,False)
        self.assertEqual(load(self.state/'content.json',{})['changed'],1)
    def test_album_review_preserves_primary_and_quarantines_refs(self):
        item,p=self.media(1);original=p.read_bytes()
        metadata={'version':1,'complete':True,'updated':'first','items':{item:{'timestamp':946684800000,'offset':0,'albums':['a','b']}},'albums':{'a':{'title':'Old title'},'b':{'title':'Removed'}}}
        atomic(self.root/'.fotoarkiv/metadata.json',metadata);organizer.organize(self.root);tools.album_snapshot(self.root,self.state)
        with sqlite3.connect(self.root/'.fotoarkiv/catalog.sqlite')as db: old=json.loads(db.execute('SELECT albums FROM files').fetchone()[0])
        metadata['albums']={'a':{'title':'New title'}};metadata['items'][item]['albums']=['a'];metadata['updated']='second'
        atomic(self.root/'.fotoarkiv/metadata.json',metadata);organizer.organize(self.root)
        review=tools.album_review(self.root,self.state);self.assertEqual(len(review['changes']),2);self.assertEqual(review['obsolete'],2)
        with self.assertRaises(ValueError):tools.approve_albums(self.root,self.state,'old-revision')
        self.assertTrue(all((self.root/a['path']).exists() for a in old))
        self.assertEqual(tools.approve_albums(self.root,self.state,review['revision']),2)
        with sqlite3.connect(self.root/'.fotoarkiv/catalog.sqlite')as db: primary=self.root/db.execute('SELECT path FROM files').fetchone()[0]
        self.assertEqual(primary.read_bytes(),original)
        retained=list((self.root/'.fotoarkiv/album-history').rglob('*.jpg'));self.assertEqual(len(retained),2)
        self.assertTrue(all(p.read_bytes()==original for p in retained))
    def test_date_range_preserves_google_calendar_and_includes_all_pages(self):
        target=self.state/'index.sqlite'
        rows=[(('AF1Q'+str(n).zfill(36),str(n)+'.jpg',str(n)+'.jpg',n,100,'image','31/12/2003 23:59','google',str(n)),[]) for n in range(60)]
        with patch.object(index,'records',return_value=iter(rows)):index.rebuild(self.root,target)
        self.assertEqual(len(index.range_members(target,2003,12)),60)
        self.assertEqual(len(index.range_members(target,start='2003-12-31',end='2003-12-31')),60)
        self.assertEqual(index.range_members(target,start='2004-01-01',end='2004-01-02'),[])
        self.assertEqual(index.query(target,'','',1,start='2004-01-01')[1],0)


if __name__=='__main__':unittest.main()
