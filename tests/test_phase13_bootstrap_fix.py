"""Verify real subprocess stdin and guarded recovery of the pre-SQL failure."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

scripts=Path(__file__).resolve().parents[1]/'scripts/phase13'
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location('bootstrap_fix',scripts/'bootstrap_rebuild.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class BootstrapFixTests(unittest.TestCase):
    def test_subprocess_receives_actual_sql_bytes(self):
        payload="SELECT 'fixture tiếng Việt';\n"
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'test.log'
            def child(args,log,stream):
                out=subprocess.check_output([sys.executable,'-c','import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],stdin=stream)
                self.assertEqual(out,payload.encode('utf-8'))
            with patch.object(module,'checked',side_effect=child):module.send_sql([],log,payload)

    def fixture(self,root,**updates):
        folder=root/'cdc';folder.mkdir()
        data={'project':'lak-rebuild-0123456789','passed':False,'error_type':'UnsupportedOperation','safe_message':'fileno'}
        data.update(updates);(folder/'bootstrap.json').write_text(json.dumps(data))
        (folder/'bootstrap.log').write_text('fixture log')
        return folder

    def test_exact_pre_sql_failure_is_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=self.fixture(root)
            module.prepare_evidence_folder(folder,'lak-rebuild-0123456789')
            self.assertEqual(list(folder.iterdir()),[])
            archives=list(root.glob('cdc-failed-fileno-*'));self.assertEqual(len(archives),1)
            self.assertEqual((archives[0]/'bootstrap.log').read_text(),'fixture log')

    def test_epoch_plan_or_other_project_blocks_retry(self):
        for changed in ['epoch','project']:
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);folder=self.fixture(root,**({'project':'lak-analytics'} if changed=='project' else {}))
                if changed=='epoch':(folder/'epoch-plan.json').write_text('{}')
                with self.assertRaises(RuntimeError):module.prepare_evidence_folder(folder,'lak-rebuild-0123456789')
                self.assertTrue((folder/'bootstrap.json').exists())


if __name__=='__main__':unittest.main()
