"""Assemble exact verified inputs, current tooling/docs and a ZIP64 final release."""
import argparse,hashlib,json,shutil,sys,uuid,zipfile
from pathlib import Path
from datetime import datetime,timezone
from release import package,verify_package
from verify_final_evidence import verify


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def stage(src,dest,want=None):
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    actual=digest(dest)
    if want and actual!=want:raise RuntimeError('Asset checksum differs: '+src.name)
    return actual


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['candidate','images','data','output']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.resolve().is_relative_to(root):raise RuntimeError('Choose output outside source project')
    index=verify(root);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    bundle=a.output/('LAK-Final-'+stamp);bundle.mkdir(parents=True,exist_ok=False)
    print('Packaging current source, models, reports and verified evidence...',flush=True)
    candidate=package(root,bundle/'assets/tooling')
    print('Copying the exact verified candidate and Docker image archive...',flush=True)
    stage(a.candidate,bundle/'assets/verified-candidate.zip',index['candidate']['sha256']);verify_package(bundle/'assets/verified-candidate.zip')
    stage(a.images,bundle/'assets/images/images.tar',index['images_export']['sha256'])
    for item in index['data_export']['files']:
        stage(a.data/item['name'],bundle/'assets/data'/item['name'],item['sha256'])
    for name in ['candidate-summary.json','data-export.json','images-export.json']:
        dest=bundle/'metadata'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        stage(root/'docs/phase13/final/evidence'/name,dest)
    # Restore tools consume export.json, not the original Windows absolute paths.
    stage(root/'docs/phase13/final/evidence/data-export.json',bundle/'assets/data/export.json')
    stage(root/'scripts/phase13/install_release.py',bundle/'install_release.py')
    guide='''# LAK final release

This release contains the exact candidate, image and database snapshot bytes used in the verified isolated rebuild, plus current source/model/evidence and restore tooling. Same Docker engine with separate volumes/network/credentials/ports was tested; a separate physical machine was not tested. Final ZIP bytes were assembled after input-level rebuild verification.

Required: Windows/Python 3.11+ host, Git for creating a new candidate only, Docker Desktop Linux amd64 containers. Python restore/install tools use the standard library. Preserve the entire release ZIP, SHA-256 file and adjacent install_release.py. Allow space for images/archive/new volumes. Ports 13310/15435/18085/18501 must be free; stop a previous test copy through its project-specific Compose command without deleting volumes. Keep original project credentials private.

1. Read the SHA-256 sidecar. Run adjacent install_release.py with --archive <final.zip> --sha256 <hash> --output <new extraction directory> --rebuild-output <directory for new isolated projects>. It verifies ZIP64 and member hashes before running Docker restore. Do not rely on PowerShell Compress-Archive/Expand-Archive for the >2 GiB tar member.
2. After database/model restore passes, run: python <extraction>/tools/scripts/phase13/bootstrap_rebuild.py --rebuild <directory printed by restore>. This performs fresh CDC/ML/web checks and starts the isolated dashboard at http://localhost:18501.
3. Operational restart of an existing copy uses its recorded project name, its own .runtime/lak.env, all infra/compose.* files listed by restore_candidate.FILES, and the same profiles. Never run the default original-project ops.py against the copy. See tools/docs/phase13/final/README.md and tools/docs/phase13/rebuild-cdc.md.

The verified-candidate ZIP is intentionally preserved byte-for-byte, including historical stage-A false/pending flags. The tooling candidate is a source/model component, not an independent live database installer. RELEASE-MANIFEST.json at this top level describes the complete delivery and points to the latest tooling archive. Runtime verification is in tools/docs/phase13/final/evidence; earlier failed attempts are preserved. Secrets are regenerated during restore and are not included. Stored news is explicitly restored metadata, not a new live API fetch; preserve attribution and permitted use.
'''
    (bundle/'README-START-HERE.md').write_text(guide,encoding='utf-8')
    files={p.relative_to(bundle).as_posix():{'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(bundle.rglob('*')) if p.is_file()}
    manifest={'schema_version':1,'kind':'lak-final-release','phase13_complete':True,'verified_input_rebuild':True,'final_zip_reexecuted':False,'separate_physical_machine_verified':False,'verified_project':index['verified_project'],'created_at_utc':datetime.now(timezone.utc).isoformat(),'tooling_source':Path(candidate['candidate']).relative_to(bundle).as_posix(),'source_git_head':candidate['source_git_head'],'verified_candidate_sha256':index['candidate']['sha256'],'images_sha256':index['images_export']['sha256'],'files':files}
    (bundle/'RELEASE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    archive=bundle.with_suffix('.zip');print('Creating final ZIP64 release (includes the image archive)...',flush=True)
    partial=archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(partial,'x',zipfile.ZIP_STORED,allowZip64=True) as z:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():z.write(path,path.relative_to(bundle).as_posix())
    partial.rename(archive)
    checksum=digest(archive);archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n',encoding='ascii')
    installer=archive.with_name(archive.stem+'-install_release.py');stage(root/'scripts/phase13/install_release.py',installer)
    result={'phase':13,'passed':True,'phase13_complete':True,'release':str(archive),'bytes':archive.stat().st_size,'sha256':checksum,'installer':str(installer),'manifest':str(bundle/'RELEASE-MANIFEST.json'),'verified_input_rebuild':True,'final_zip_reexecuted':False}
    archive.with_suffix('.summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));print('PHASE 13 FINAL RELEASE CREATED AND CHECKSUMMED')


if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError,KeyError) as exc:
        print('FINAL RELEASE STOPPED: '+str(exc),file=sys.stderr);raise SystemExit(1)
