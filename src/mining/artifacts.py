import csv
import hashlib
import json
import platform
import shutil
import uuid
from pathlib import Path
import joblib
import numpy as np
from src.source.data import ROOT
from src.news.model import digest
from .rfm import CONTRACT,row_payload
from .train import CONFIG,versions,fit,matrix


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(snapshot):
    code={name:sha(Path(__file__).with_name(name)) for name in ['rfm.py','preprocess.py','train.py','artifacts.py']}
    metadata={'algorithm':'kmeans_rfm','snapshot_id':snapshot,'feature_contract':CONTRACT,'configuration':CONFIG,
              'libraries':versions(),'python':platform.python_version(),'code_sha256':code}
    return 'km-rfm-'+digest(metadata)[:24],metadata


def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')


def write_csv(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def validate(directory,expected_id=None):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    if expected_id and manifest['model_id']!=expected_id:raise RuntimeError('Model identity differs')
    allowed={'pipeline.joblib','metadata.json','evaluation.json','profiles.json','assignments.csv','assignments.json','features.csv','feature_contract.json'}
    if set(manifest['files'])!=allowed:raise RuntimeError('Artifact manifest has unexpected/missing files')
    for name,checksum in manifest['files'].items():
        path=directory/name
        if not path.is_file() or path.is_symlink() or sha(path)!=checksum:raise RuntimeError('Artifact checksum mismatch: '+name)
    return manifest


def load(directory,model_id):
    validate(directory,model_id)
    return (joblib.load(directory/'pipeline.joblib'),json.loads((directory/'evaluation.json').read_text()),
            json.loads((directory/'profiles.json').read_text()),json.loads((directory/'assignments.json').read_text()))


def build(snapshot,rows,base=None):
    base=Path(base or ROOT/'data/models/kmeans_rfm');base.mkdir(parents=True,exist_ok=True)
    model_id,metadata=identity(snapshot);directory=base/model_id
    if directory.exists():
        pipeline,report,profiles,assignments=load(directory,model_id)
        if [a['customer_id'] for a in assignments]!=[r['customer_id'] for r in rows] or not np.array_equal(pipeline.predict(matrix(rows)),[a['cluster_id'] for a in assignments]):
            raise RuntimeError('Saved assignments do not match frozen pipeline/current feature snapshot')
        return model_id,directory,metadata,report,profiles,assignments,True
    temporary=base/('.build-'+uuid.uuid4().hex);temporary.mkdir()
    try:
        pipeline,report,profiles,assignments=fit(rows)
        joblib.dump(pipeline,temporary/'pipeline.joblib',compress=3)
        restored=joblib.load(temporary/'pipeline.joblib')
        if not np.array_equal(pipeline.predict(matrix(rows)),restored.predict(matrix(rows))):raise RuntimeError('Joblib roundtrip changed predictions')
        write_json(temporary/'metadata.json',metadata);write_json(temporary/'evaluation.json',report)
        write_json(temporary/'profiles.json',profiles);write_json(temporary/'assignments.json',assignments)
        write_json(temporary/'feature_contract.json',CONTRACT)
        write_csv(temporary/'features.csv',[dict(snapshot_id=snapshot,**row_payload(r),split=r['split']) for r in rows])
        write_csv(temporary/'assignments.csv',assignments)
        files={p.name:sha(p) for p in sorted(temporary.iterdir())}
        write_json(temporary/'manifest.json',{'model_id':model_id,'snapshot_id':snapshot,'files':files})
        validate(temporary,model_id)
        temporary.rename(directory)
    finally:
        if temporary.exists():shutil.rmtree(temporary)
    return model_id,directory,metadata,report,profiles,assignments,False
