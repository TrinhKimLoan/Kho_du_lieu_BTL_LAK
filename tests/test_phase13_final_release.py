"""Artifact-level end-to-end final bundle tests using small synthetic assets."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

scripts=Path(__file__).resolve().parents[1]/'scripts/phase13';sys.path.insert(0,str(scripts))
import finalize_release as final
import install_release as install


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate(path):
    path.parent.mkdir(parents=True,exist_ok=True);data=b'fixture source'
    meta={'kind':'source-model-evidence-candidate','phase13_complete':False,'files':{'README.md':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}
    with zipfile.ZipFile(path,'w',allowZip64=True) as z:
        with z.open('README.md','w',force_zip64=True) as f:f.write(data)
        z.writestr('RELEASE-MANIFEST.json',json.dumps(meta))


class FinalBundleTests(unittest.TestCase):
    def build(self,root,wrong=False):
        source=root/'candidate.zip';candidate(source);image=root/'images.tar';image.write_bytes(b'fixture image'*100)
        data=root/'data';data.mkdir();items=[]
        for name in ['mysql-source.sql','warehouse.dump','warehouse-toc.txt']:
            p=data/name;p.write_bytes(('fixture '+name).encode());items.append({'name':name,'bytes':p.stat().st_size,'sha256':digest(p)})
        index={'candidate':{'sha256':digest(source)},'images_export':{'sha256':('0'*64 if wrong else digest(image))},'data_export':{'files':items},'verified_project':'fixture-isolated'}
        def fake_package(project,output):
            path=output/'tooling.zip';candidate(path)
            return {'candidate':str(path),'source_git_head':'fixture-head'}
        argv=['finalize','--candidate',str(source),'--images',str(image),'--data',str(data),'--output',str(root/'out')]
        with patch.object(sys,'argv',argv),patch.object(final,'verify',return_value=index),patch.object(final,'package',side_effect=fake_package),redirect_stdout(io.StringIO()):final.main()
        return next((root/'out').glob('*.zip'))

    def test_final_bundle_roundtrip_and_component_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=self.build(root);dest=root/'unpacked'
            with patch.object(sys,'argv',['install','--archive',str(archive),'--sha256',digest(archive),'--output',str(dest)]),redirect_stdout(io.StringIO()):install.main()
            self.assertEqual((dest/'assets/images/images.tar').read_bytes(),(root/'images.tar').read_bytes())
            self.assertTrue((dest/'tools/README.md').exists())
            manifest=json.loads((dest/'RELEASE-MANIFEST.json').read_text())
            self.assertTrue(manifest['phase13_complete']);self.assertFalse(manifest['final_zip_reexecuted'])
            self.assertTrue(archive.with_suffix('.zip.sha256').exists())

    def test_wrong_image_prevents_final_zip_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(RuntimeError,'Asset checksum'):self.build(root,True)
            self.assertEqual(list((root/'out').glob('*.zip')),[])

    def test_extra_member_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=self.build(root)
            with zipfile.ZipFile(archive,'a') as z:z.writestr('unexpected.txt','fixture')
            output=root/'unpacked'
            with patch.object(sys,'argv',['install','--archive',str(archive),'--sha256',digest(archive),'--output',str(output)]):
                with self.assertRaisesRegex(RuntimeError,'inventory differs'):install.main()
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
