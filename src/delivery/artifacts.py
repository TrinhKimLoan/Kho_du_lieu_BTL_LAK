import json
import platform
import shutil
import uuid
from pathlib import Path
import joblib
import numpy as np
from src.source.data import ROOT
from src.news.model import digest
from src.mining.artifacts import sha, write_json, write_csv
from src.mining.train import versions
from .features import CONTRACT, matrix, FEATURES
from .train import CONFIG, fit

FILES={'pipeline.joblib','metadata.json','evaluation.json','features.json','features.csv','predictions.json','predictions.csv','feature_contract.json','feature_explanation.md'}


def identity(snapshot):
    metadata={'algorithm':'random_forest_delivery','snapshot_id':snapshot,'contract':CONTRACT,'configuration':CONFIG,
              'libraries':versions(),'python':platform.python_version(),
              'code_sha256':{n:sha(Path(__file__).with_name(n)) for n in ['features.py','train.py','artifacts.py']}}
    return 'rf-delivery-'+digest(metadata)[:24],metadata


def validate(directory,expected_id):
    directory=Path(directory)
    if directory.is_symlink(): raise RuntimeError('Symlink artifact directory')
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest['model_id']!=expected_id or set(manifest['files'])!=FILES: raise RuntimeError('Unexpected artifact manifest')
    for name,value in manifest['files'].items():
        p=directory/name
        if not p.is_file() or p.is_symlink() or sha(p)!=value: raise RuntimeError('Artifact checksum differs: '+name)
    return manifest


def load(directory,model_id):
    directory=Path(directory);manifest=validate(directory,model_id)
    model=joblib.load(directory/'pipeline.joblib')
    def read(name):return json.loads((directory/name).read_text(encoding='utf-8'))
    rows=read('features.json');predictions=read('predictions.json')
    if [r['order_id'] for r in rows]!=[p['order_id'] for p in predictions] or not np.array_equal(model.predict(matrix(rows)),[p['predicted_hours'] for p in predictions]): raise RuntimeError('Saved predictions differ from frozen pipeline')
    return manifest,model,read('evaluation.json'),rows,predictions


def explain(report):
    lines=['# Giải thích đặc trưng dự đoán giao hàng','',
           'Điểm dự đoán: lúc giao đi. Nhãn: số giờ liên tục từ giao đi đến nhận. Đây là mô hình dữ liệu mô phỏng, chưa kiểm chứng trên vận tải thật.','',
           'Đặc trưng được phép: '+', '.join(FEATURES)+'. Đầu vào phải được biết tại lúc giao đi. Không đưa mốc thực nhận, dự kiến, mã khách, số điện thoại hoặc địa chỉ đầy đủ vào model.','',
           'Train: 2020–2023; validation: 2024; test: 2025. Chỉ dùng nhãn nhận trước mốc kết thúc từng kỳ. Tiền xử lý chỉ fit trên train.','',
           f"Test MAE: {report['test']['mae_hours']:.4f} giờ; RMSE: {report['test']['rmse_hours']:.4f} giờ.",
           f"Baseline trung vị theo loại giao: MAE {report['baselines']['test']['by_shipping_method']['mae_hours']:.4f} giờ.",
           'RF tốt hơn baseline theo MAE test: '+str(report['beats_shipping_baseline_test_mae'])+'.','',
           '## Permutation importance trên test','',
           'Mức tăng MAE khi xáo trộn từng đặc trưng; số âm hoặc gần 0 không chứng minh đặc trưng có ích. Các đặc trưng tương quan có thể chia sẻ ảnh hưởng. Không phải quan hệ nhân quả. Không dùng kết quả này để chọn lại model.','',
           '| Đặc trưng | Tăng MAE (giờ) | Độ lệch chuẩn |','| --- | ---: | ---: |']
    lines += [f"| {p['feature']} | {p['mae_increase_hours']:.4f} | {p['std_hours']:.4f} |" for p in sorted(report['permutation_importance_test'],key=lambda r:-r['mae_increase_hours'])]
    lines += ['', '## Giới hạn', '']+['- '+s for s in report['limitations']]
    return '\n'.join(lines)+'\n'


def build(snapshot,rows,base=None):
    base=Path(base or ROOT/'data/models/random_forest_delivery');base.mkdir(parents=True,exist_ok=True)
    model_id,metadata=identity(snapshot);directory=base/model_id
    if directory.exists():
        _,_,report,saved,predictions=load(directory,model_id)
        if saved!=rows: raise RuntimeError('Existing immutable dataset differs')
        return model_id,directory,metadata,report,predictions,True
    temp=base/('.build-'+uuid.uuid4().hex);temp.mkdir()
    try:
        model,report,predictions=fit(rows)
        joblib.dump(model,temp/'pipeline.joblib',compress=3)
        write_json(temp/'metadata.json',metadata);write_json(temp/'evaluation.json',report)
        write_json(temp/'features.json',rows);write_json(temp/'predictions.json',predictions);write_json(temp/'feature_contract.json',CONTRACT)
        write_csv(temp/'features.csv',[{k:v for k,v in r.items() if k!='features'}|r['features'] for r in rows])
        write_csv(temp/'predictions.csv',predictions)
        (temp/'feature_explanation.md').write_text(explain(report),encoding='utf-8')
        write_json(temp/'manifest.json',{'model_id':model_id,'snapshot_id':snapshot,'files':{n:sha(temp/n) for n in sorted(FILES)}})
        load(temp,model_id);temp.rename(directory)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return model_id,directory,metadata,report,predictions,False
