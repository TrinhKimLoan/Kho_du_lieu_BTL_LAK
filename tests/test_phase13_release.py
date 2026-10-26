"""Artifact safety tests with a synthetic repository, not runtime evidence."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec=importlib.util.spec_from_file_location('lak_release',Path(__file__).resolve().parents[1]/'scripts/phase13/release.py')
release=importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name)
        self.root=self.parent/'project'
        self.root.mkdir()
        for name,data in {
            'src/app.py':b'print("fixture")\n',
            'docs/base.txt':b'baseline\n',
            'scripts/verify_phase12.py':b'print("synthetic fixture validator")\n',
            '.gitignore':b'.runtime/\ndata/models/\n',
            '.runtime/lak.env':b'FIXTURE_SECRET=must_not_be_archived\n',
            'data/models/family/version/pipeline.joblib':b'fixture model, never unpickled',
        }.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        locks=self.root/'infra/locks';locks.mkdir(parents=True)
        (locks/'phase12-source.json').write_text(json.dumps({'docs/base.txt':hashlib.sha256(b'baseline\n').hexdigest()}))
        model=self.root/'data/models/family/version/pipeline.joblib'
        (locks/'models.json').write_text(json.dumps({'bytes':model.stat().st_size,'files':[{'path':'family/version/pipeline.joblib','bytes':model.stat().st_size,'sha256':hashlib.sha256(model.read_bytes()).hexdigest()}]}))
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        self.git('add','.')
        self.commit()

    def git(self,*args):
        subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True)

    def commit(self):
        self.git('-c','user.name=Fixture','-c','user.email=fixture@invalid','commit','-qm','fixture')

    def test_candidate_excludes_credentials_and_detects_added_member(self):
        result=release.package(self.root,self.parent/'out')
        path=Path(result['candidate'])
        with zipfile.ZipFile(path) as archive:
            self.assertIn('data/models/family/version/pipeline.joblib',archive.namelist())
            self.assertNotIn('.runtime/lak.env',archive.namelist())
            self.assertFalse(json.loads(archive.read('RELEASE-MANIFEST.json'))['runtime_rebuild_verified'])
        with zipfile.ZipFile(path,'a') as archive:archive.writestr('extra.txt','extra')
        with self.assertRaisesRegex(RuntimeError,'inventory differs'):release.verify_package(path)

    def test_model_change_and_source_change_are_rejected(self):
        model=self.root/'data/models/family/version/pipeline.joblib'
        model.write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError,'Model differs'):release.check_local(self.root)
        (self.root/'docs/base.txt').write_text('modified')
        with self.assertRaisesRegex(RuntimeError,'uncommitted'):release.package(self.root,self.parent/'out')

    def test_tracked_secret_and_symlink_are_rejected(self):
        secret=self.root/'.env';secret.write_text('FIXTURE_SECRET=not_for_release')
        self.git('add','.env');self.commit()
        with self.assertRaisesRegex(RuntimeError,'Credential file'):release.package(self.root,self.parent/'out')
        secret.unlink();self.git('add','-u');self.commit()
        (self.root/'src/link.txt').symlink_to(self.root/'docs/base.txt')
        self.git('add','src/link.txt');self.commit()
        with self.assertRaisesRegex(RuntimeError,'Symlink'):release.package(self.root,self.parent/'out')

    def test_image_tag_repointing_is_rejected_without_pull(self):
        lock={'images':[{'tags':['fixture:locked'],'id':'sha256:expected'}]}
        (self.root/'infra/locks/images.json').write_text(json.dumps(lock))
        with patch.object(release.subprocess,'check_output',return_value='sha256:changed\n') as call:
            with self.assertRaisesRegex(RuntimeError,'Image ID differs'):release.check_images(self.root)
            self.assertEqual(call.call_args.args[0],['docker','image','inspect','fixture:locked','--format','{{.Id}}'])

    def test_untracked_source_and_unsafe_archive_paths_are_rejected(self):
        (self.root/'src/forgotten.py').write_text('fixture')
        with self.assertRaisesRegex(RuntimeError,'Untracked source'):release.package(self.root,self.parent/'out')
        for name in ['../escape','/absolute','C:/file','folder\\escape','.runtime/lak.env']:
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):release.safe_relative(name)


if __name__=='__main__':unittest.main()
