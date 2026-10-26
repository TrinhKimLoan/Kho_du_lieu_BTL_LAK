from src.source.data import ROOT
from src.mining.artifacts import sha,load as load_rfm
from src.delivery.artifacts import load as load_delivery


class Models:
    def __init__(self):self.cache={}
    def get(self,connection,model_id,kind):
        if model_id not in self.cache:
            row=connection.execute('SELECT * FROM ml.model_registry WHERE model_id=%s',(model_id,)).fetchone()
            expected='kmeans_rfm' if kind=='RFM' else 'random_forest_delivery'
            if not row or row['algorithm']!=expected or row['status']!='READY':raise RuntimeError('Pinned model missing or not READY')
            relative=('kmeans_rfm/' if kind=='RFM' else 'random_forest_delivery/')+model_id
            if row['artifact_relpath']!=relative:raise RuntimeError('Unexpected pinned artifact path')
            directory=ROOT/'data/models'/relative
            if sha(directory/'manifest.json')!=row['manifest_sha256']:raise RuntimeError('Pinned model manifest differs')
            model=load_rfm(directory,model_id)[0] if kind=='RFM' else load_delivery(directory,model_id)[1]
            self.cache[model_id]=model
        return self.cache[model_id]
