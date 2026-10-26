"""Standalone ZIP64 release verifier/extractor and isolated rebuild launcher."""
import argparse,hashlib,json,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def safe(name):
    p=PurePosixPath(name)
    if p.is_absolute() or str(p)!=name or '..' in p.parts or '\\' in name or ':' in name or any(x in {'.git','.runtime','.venv'} for x in p.parts):raise RuntimeError('Unsafe archive member')
    return p


def extract(archive,output,manifest=None):
    names=archive.namelist()
    if len(names)!=len(set(names)):raise RuntimeError('Duplicate archive members')
    for name in names:safe(name)
    if manifest and set(names)!=set(manifest['files'])|{'RELEASE-MANIFEST.json'}:raise RuntimeError('Release inventory differs')
    output.mkdir(parents=True,exist_ok=False)
    for name in names:
        dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();size=0
        with archive.open(name) as src,dest.open('xb') as target:
            for block in iter(lambda:src.read(4*1024*1024),b''):
                target.write(block);h.update(block);size+=len(block)
        if manifest and name!='RELEASE-MANIFEST.json':
            expected=manifest['files'][name]
            if h.hexdigest()!=expected['sha256'] or size!=expected['bytes']:raise RuntimeError('Release member differs: '+name)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rebuild-output',type=Path)
    a=p.parse_args()
    if digest(a.archive)!=a.sha256.lower():raise RuntimeError('Release ZIP checksum mismatch')
    with zipfile.ZipFile(a.archive) as archive:
        manifest=json.loads(archive.read('RELEASE-MANIFEST.json'))
        if manifest['kind']!='lak-final-release' or not manifest['verified_input_rebuild']:raise RuntimeError('Unexpected release manifest')
        extract(archive,a.output,manifest)
    tools=a.output/'tools'
    with zipfile.ZipFile(a.output/manifest['tooling_source']) as archive:extract(archive,tools)
    print('FINAL RELEASE EXTRACTED AND VERIFIED: '+str(a.output))
    if a.rebuild_output:
        # This starts only the isolated data restore. Its output provides the new directory.
        subprocess.run([sys.executable,str(tools/'scripts/phase13/restore_candidate.py'),
            '--candidate',str(a.output/'assets/verified-candidate.zip'),'--candidate-sha256',manifest['verified_candidate_sha256'],
            '--images',str(a.output/'assets/images/images.tar'),'--images-sha256',manifest['images_sha256'],
            '--data',str(a.output/'assets/data'),'--output',str(a.rebuild_output)],check=True)
        print('Next: run tools/scripts/phase13/bootstrap_rebuild.py --rebuild <directory printed above>.')


if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError,KeyError,zipfile.BadZipFile,subprocess.CalledProcessError) as exc:
        print('RELEASE INSTALL STOPPED: '+str(exc),file=sys.stderr);raise SystemExit(1)
