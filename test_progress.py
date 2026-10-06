import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('progress',ROOT/'dashboard/progress.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ProgressTests(unittest.TestCase):
    def test_active_stage_and_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp)
            def read(log='',**kw):
                flags=dict(online=True,running=True,pending=False,stopping=False,login_active=False);flags.update(kw)
                return module.progress(state,log,**flags)
            (state/'phase').write_text('indexing')
            old='Albumindeksering: 27000 billeder, 140 albums\n'
            log=old+'Starter synkronisering: user@example.com\nHenter albums og Google-datoer\nAlbumindeksering: 500 billeder, 0 albums\nAlbumindeksering: 1000 billeder, 86 albums'
            self.assertEqual(read(log),{'phase':'indexing','indexed_items':1000,'indexed_albums':86})
            self.assertIsNone(read(old+'Starter synkronisering: user@example.com')['indexed_items'])
            self.assertIsNone(read(old+'Henter albums og Google-datoer')['indexed_items'])
            self.assertEqual(read(log,running=False)['phase'],'idle')
            self.assertEqual(read(log,online=False)['phase'],'offline')
            self.assertEqual(read(log,stopping=True)['phase'],'stopping')
            self.assertEqual(read(log,running=False,pending=True,login_active=True)['phase'],'waiting_login')
            for stage in ['starting','organizing','downloading']:
                (state/'phase').write_text(stage);self.assertEqual(read()['phase'],stage)
            (state/'phase').write_text('unknown');self.assertEqual(read()['phase'],'starting')
    def test_worker_reports_real_command_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);control=root/'control';control.mkdir();fake=root/'bin';fake.mkdir()
            dest=root/'download';(dest/'.fotoarkiv').mkdir(parents=True);(dest/'.fotoarkiv/metadata.json').write_text('{}')
            source=(ROOT/'account-worker.sh').read_text().replace('/control',str(control)).replace('/download',str(dest))
            script=root/'worker.sh';script.write_text(source)
            command=fake/'gphotos-cdp';command.write_text('#!/bin/sh\ncase "$*" in *-index-albums*) expected=indexing;; *) expected=downloading;; esac\nactual=$(cat "$TEST_CONTROL/phase")\n[ "$actual" = "$expected" ] || exit 90\necho "$actual" >> "$TEST_CONTROL/observed"\n');command.chmod(0o755)
            command=fake/'python3';command.write_text('#!/bin/sh\ncase "$1" in *library_tools.py|*operations.py) exit 0;; -c) echo 2; exit 0;; esac\ncase "$2" in begin) exit 0;; check) expected=checking;; *) expected=organizing;; esac\nactual=$(cat "$TEST_CONTROL/phase")\n[ "$actual" = "$expected" ] || exit 91\necho "$actual" >> "$TEST_CONTROL/observed"\n');command.chmod(0o755)
            env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'],TEST_CONTROL=str(control))
            subprocess.run(['/bin/sh',str(script),'legacy','--run','0'],env=env,check=True,capture_output=True)
            self.assertEqual((control/'observed').read_text().splitlines(),['checking','indexing','organizing','downloading','organizing','checking'])
            (control/'observed').unlink()
            subprocess.run(['/bin/sh',str(script),'legacy','--run','1'],env=env,check=True,capture_output=True)
            self.assertEqual((control/'observed').read_text().splitlines(),['checking','indexing','organizing','checking'])

if __name__=='__main__':unittest.main()

