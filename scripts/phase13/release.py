"""Phase 13A: check locks and package source/models/evidence, without database access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import uuid
import zipfile


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, encoding='utf-8')


def safe_relative(name):
    path = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or str(path) != name:
        raise RuntimeError('Unsafe archive path: '+name)
    if any(p in {'.git', '.runtime', '.venv', '__pycache__'} for p in path.parts):
        raise RuntimeError('Excluded directory: '+name)
    if path.name == '.env' or path.name.endswith('.env') or (path.name.startswith('.env.') and path.name != '.env.example'):
        raise RuntimeError('Credential file cannot be packaged: '+name)
    if path.name.lower().endswith(('.pem', '.key', '.pfx', '.p12')):
        raise RuntimeError('Private key file cannot be packaged: '+name)
    return path


def local_file(root, name):
    relative = safe_relative(name)
    path = root/Path(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError('File escapes root: '+name)
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise RuntimeError('Symlink cannot be packaged: '+name)
    return path


def check_local(root):
    guard = read(root/'infra/locks/phase12-source.json')
    for name, expected in guard.items():
        path = local_file(root, name)
        actual = sha(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            raise RuntimeError('Validated Phase 12 input changed: '+name)
    inventory = read(root/'infra/locks/models.json')
    for item in inventory['files']:
        path = local_file(root, 'data/models/'+item['path'])
        data = path.read_bytes()
        if len(data) != item['bytes'] or sha(data) != item['sha256']:
            raise RuntimeError('Model differs: '+item['path'])
    subprocess.run([sys.executable, str(root/'scripts/verify_phase12.py'), '--target', str(root)], check=True)
    print('PHASE 13 LOCAL INPUTS VERIFIED')
    return {'model_files':len(inventory['files']), 'model_bytes':inventory['bytes'], 'phase12_inputs_verified':True}


def check_images(root):
    lock = read(root/'infra/locks/images.json')
    checked = []
    for image in lock['images']:
        tag = image['tags'][0]
        actual = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
        if actual != image['id']:
            raise RuntimeError('Image ID differs from inventory: '+tag+'; no pull/build attempted')
        checked.append({'tag':tag, 'id':actual})
    print('PHASE 13 IMAGE LOCKS VERIFIED')
    return {'images':checked, 'pull_or_build_performed':False}


def verify_package(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError('Duplicate archive member')
        for name in names:
            safe_relative(name)
        metadata = json.loads(archive.read('RELEASE-MANIFEST.json'))
        if metadata['kind'] != 'source-model-evidence-candidate' or metadata['phase13_complete']:
            raise RuntimeError('Unexpected candidate kind/status')
        expected = metadata['files']
        if set(names) != set(expected)|{'RELEASE-MANIFEST.json'}:
            raise RuntimeError('Archive inventory differs')
        for name, item in expected.items():
            data = archive.read(name)
            if len(data) != item['bytes'] or sha(data) != item['sha256']:
                raise RuntimeError('Archive checksum mismatch: '+name)
    print('PHASE 13 CANDIDATE CONTENTS VERIFIED')
    return metadata


def package(root, output):
    if output.resolve().is_relative_to(root.resolve()):
        raise RuntimeError('Choose an output directory outside the project')
    if git(root, 'diff', '--name-only', 'HEAD').strip():
        raise RuntimeError('Tracked files have uncommitted changes; no candidate created')
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
    unexpected = [p for p in untracked if p and not p.startswith('evidence/')]
    if unexpected:
        raise RuntimeError('Untracked source requires review: '+unexpected[0])
    check_local(root)
    paths = [p for p in git(root, 'ls-files', '-z').split('\0') if p]
    models = read(root/'infra/locks/models.json')['files']
    paths += ['data/models/'+item['path'] for item in models]
    if len(paths) != len(set(paths)) or 'RELEASE-MANIFEST.json' in paths:
        raise RuntimeError('Duplicate or reserved source path')
    # Resolve all inputs before creating any deliverable.
    sources = [(name, local_file(root, name)) for name in sorted(paths)]
    for name, path in sources:
        if not path.is_file():
            raise RuntimeError('Missing source file: '+name)
    head = git(root, 'rev-parse', 'HEAD').strip()
    name = 'LAK-Candidate-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]+'.zip'
    output.mkdir(parents=True, exist_ok=True)
    dest = output/name
    temporary = dest.with_suffix('.zip.partial')
    manifest = {'schema_version':1, 'kind':'source-model-evidence-candidate', 'phase':13,
                'phase13_complete':False, 'source_git_head':head, 'platform':'linux/amd64',
                'database_snapshot_included':False, 'docker_image_bytes_included':False,
                'secrets_included':False, 'runtime_rebuild_verified':False,
                'created_at_utc':datetime.now(timezone.utc).isoformat(), 'files':{}}
    try:
        with zipfile.ZipFile(temporary, 'x', zipfile.ZIP_DEFLATED) as archive:
            for relative, path in sources:
                data = path.read_bytes()
                manifest['files'][relative] = {'bytes':len(data), 'sha256':sha(data)}
                archive.writestr(relative, data)
            archive.writestr('RELEASE-MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        if git(root, 'rev-parse', 'HEAD').strip() != head or git(root, 'diff', '--name-only', 'HEAD').strip():
            raise RuntimeError('Source changed during packaging')
        # Model/source guard catches changes while files were being copied.
        check_local(root)
        verify_package(temporary)
        temporary.rename(dest)
    finally:
        temporary.unlink(missing_ok=True)
    digest = sha(dest.read_bytes())
    dest.with_suffix('.zip.sha256').write_text(digest+'  '+dest.name+'\n', encoding='utf-8')
    summary = {k:v for k,v in manifest.items() if k!='files'}
    summary.update(candidate=str(dest), sha256=digest, file_count=len(manifest['files']), archive_bytes=dest.stat().st_size)
    dest.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print('PHASE 13 CANDIDATE CREATED')
    print(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check-local','check-images','package','verify-package'])
    parser.add_argument('--target', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
    args = parser.parse_args()
    root = args.target.resolve()
    if args.command=='check-local':
        result = check_local(root)
    elif args.command=='check-images':
        result = check_images(root)
    elif args.command=='package':
        if args.output is None:
            parser.error('--output is required')
        result = package(root, args.output)
    else:
        if args.archive is None:
            parser.error('--archive is required')
        data = verify_package(args.archive)
        result = {'archive':str(args.archive),'files':len(data['files']),'runtime_rebuild_verified':False}
    if args.evidence_dir:
        args.evidence_dir.mkdir(parents=True,exist_ok=True)
        path = args.evidence_dir/(args.command+'.json')
        if path.exists():
            raise RuntimeError('Evidence already exists: '+str(path))
        path.write_text(json.dumps({'phase':13,'stage':'A','command':args.command,'passed':True,
                        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'result':result},indent=2)+'\n',encoding='utf-8')
        print('Evidence: '+str(path))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError,OSError,ValueError,KeyError,subprocess.CalledProcessError,zipfile.BadZipFile) as exc:
        print('PHASE 13 STOPPED: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
