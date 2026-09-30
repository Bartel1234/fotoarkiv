import asyncio
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('organize',Path(__file__).parent/'login/organize.py')
organize=importlib.util.module_from_spec(spec);spec.loader.exec_module(organize)
ID='AF1Q'+('a'*36)
ALBUM='album123456789'

class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        (self.root/'.fotoarkiv').mkdir(); (self.root/ID).mkdir()
        self.source=self.root/ID/'test.jpg';self.source.write_bytes(b'original media bytes')
        self.metadata={'version':1,'complete':True,'items':{ID:{'timestamp':1041379200000,'offset':0,'albums':[ALBUM]}},'albums':{ALBUM:{'title':'Familie / 2003'}}}
        self.save()
    def tearDown(self): self.temp.cleanup()
    def save(self): (self.root/'.fotoarkiv/metadata.json').write_text(json.dumps(self.metadata))
    def row(self):
        with sqlite3.connect(self.root/'.fotoarkiv/catalog.sqlite') as db:
            return db.execute('SELECT path,timestamp,albums FROM files').fetchone()
    def test_migration_idempotence_and_dates(self):
        organize.organize(self.root); path,stamp,albums=self.row(); canonical=self.root/path
        self.assertEqual(canonical.read_bytes(),b'original media bytes');self.assertFalse(self.source.exists())
        self.assertIn('Bibliotek/2003/01/',path);self.assertEqual(canonical.stat().st_mtime,1041379200)
        album=self.root/json.loads(albums)[0]['path'];self.assertEqual(album.stat().st_ino,canonical.stat().st_ino)
        organize.organize(self.root);self.assertEqual(len(list((self.root/'Bibliotek').rglob('*.jpg'))),1)
    def test_conflict_preserves_original(self):
        target=self.root/'Bibliotek/2003/01'/('test--'+ID+'.jpg');target.parent.mkdir(parents=True);target.write_bytes(b'conflict')
        with self.assertRaises(ValueError): organize.organize(self.root)
        self.assertEqual(self.source.read_bytes(),b'original media bytes');self.assertEqual(target.read_bytes(),b'conflict')
    def test_incomplete_metadata_preserves_original(self):
        self.metadata['complete']=False;self.save()
        with self.assertRaises(ValueError):organize.organize(self.root)
        self.assertTrue(self.source.exists())
    def test_unknown_item_preserved(self):
        self.metadata['items']={};self.save();organize.organize(self.root);self.assertTrue(self.source.exists())
    def test_copy_fallback(self):
        original=os.link
        def cross_disk(src,dst):
            if not Path(src).name.startswith('.'): raise OSError('cross device')
            return original(src,dst)
        with patch.object(organize.os,'link',side_effect=cross_disk):organize.organize(self.root)
        path,_,albums=self.row();self.assertEqual((self.root/path).read_bytes(),b'original media bytes')
        report=json.loads((self.root/'.fotoarkiv/organization.json').read_text());self.assertEqual(report['copies'],1)
    def test_per_download_organizing(self):
        organize.organize(self.root,ID);self.assertFalse(self.source.exists())
        path,_,_=self.row();self.assertTrue((self.root/path).is_file())
        self.assertFalse((self.root/'.fotoarkiv/downloaded.json').exists())
        organize.organize(self.root);self.assertIn(ID,json.loads((self.root/'.fotoarkiv/downloaded.json').read_text()))
    def test_symlink_target_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root/'Bibliotek').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):organize.organize(self.root)
            self.assertTrue(self.source.exists());self.assertEqual(list(Path(outside).iterdir()),[])

if __name__=='__main__':unittest.main()
