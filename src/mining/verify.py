import json
from pathlib import Path
import numpy as np
from src.source.data import ROOT
from .rfm import row_payload,validate as validate_features,FEATURES
from .artifacts import load,sha
from .train import matrix,choose,profiles as make_profiles
from src.news.model import digest


def verify(connection,model_id):
    model=connection.execute('SELECT * FROM ml.model_registry WHERE model_id=%s',(model_id,)).fetchone()
    if not model or model['algorithm']!='kmeans_rfm' or model['status']!='READY':raise RuntimeError('Requested READY KMeans model not found')
    root=ROOT/'data/models';directory=root/model['artifact_relpath']
    if not directory.resolve().is_relative_to(root.resolve()):raise RuntimeError('Model artifact path escapes model root')
    if sha(directory/'manifest.json')!=model['manifest_sha256']:raise RuntimeError('Database manifest checksum differs')
    pipeline,report,profiles,assignments=load(directory,model_id)
    if model['metadata'].get('evaluation')!=report:raise RuntimeError('Registry evaluation differs from frozen artifact report')
    rows=connection.execute('SELECT * FROM ml.rfm_features WHERE snapshot_id=%s ORDER BY customer_id',(model['snapshot_id'],)).fetchall()
    validate_features(rows)
    snapshot=connection.execute('SELECT * FROM ml.feature_snapshots WHERE snapshot_id=%s',(model['snapshot_id'],)).fetchone()
    if snapshot['row_count']!=len(rows) or digest([dict(row_payload(r),split=r['split']) for r in rows])!=snapshot['dataset_sha256']:
        raise RuntimeError('Feature dataset checksum differs from immutable snapshot')
    if any(r['row_sha256']!=digest(row_payload(r)) for r in rows):raise RuntimeError('Feature row checksum differs')
    train=[r for r in rows if r['split']=='train'];test_ids={r['customer_id'] for r in rows if r['split']=='test'}
    train_ids={r['customer_id'] for r in train};val_ids={r['customer_id'] for r in rows if r['split']=='validation'}
    if train_ids&test_ids or train_ids&val_ids or test_ids&val_ids:raise RuntimeError('Customer split overlap')
    prep=pipeline.named_steps['rfm']
    expected_lower=np.quantile(matrix(train),.01,axis=0);expected_upper=np.quantile(matrix(train),.99,axis=0)
    expected_logged=np.log1p(np.clip(matrix(train),expected_lower,expected_upper))
    if prep.fit_rows_!=len(train) or not np.array_equal(prep.lower_,expected_lower) or not np.array_equal(prep.upper_,expected_upper):raise RuntimeError('Preprocessing bounds were not fitted only on train')
    if not np.allclose(prep.scaler_.mean_,expected_logged.mean(axis=0),rtol=0,atol=1e-12):raise RuntimeError('Scaler mean differs from train-only mean')
    if choose(report['candidates'])!=report['selected_k'] or report['test_used_for_selection'] or report['refit_on_all_customers']:raise RuntimeError('Selection protocol differs')
    predicted=pipeline.predict(matrix(rows))
    stored=connection.execute('''SELECT c.customer_id,s.cluster_id,s.distance,s.business_segment FROM ml.customer_segments s
        JOIN dw.dim_customer c USING(customer_key) WHERE s.model_id=%s ORDER BY c.customer_id''',(model_id,)).fetchall()
    if len(stored)!=len(rows) or [s['customer_id'] for s in stored]!=[r['customer_id'] for r in rows] or not np.array_equal(predicted,[s['cluster_id'] for s in stored]):raise RuntimeError('Database assignments differ from pipeline')
    if len(assignments)!=len(stored) or any(any(s[k]!=a[k] for k in ['customer_id','cluster_id','business_segment']) for s,a in zip(stored,assignments)):raise RuntimeError('Artifact/database assignment mismatch')
    distances=pipeline.transform(matrix(rows)).min(axis=1)
    if not np.allclose(distances,[s['distance'] for s in stored],rtol=0,atol=1e-12):raise RuntimeError('Stored cluster distances differ')
    saved_profiles=connection.execute('SELECT cluster_id,customer_count,profile FROM ml.segment_profiles WHERE model_id=%s ORDER BY cluster_id',(model_id,)).fetchall()
    if len(saved_profiles)!=len(profiles) or sum(p['customer_count'] for p in saved_profiles)!=len(rows):raise RuntimeError('Segment profile counts differ')
    if [p['profile'] for p in saved_profiles]!=profiles or make_profiles(rows,predicted,train)!=profiles:raise RuntimeError('Segment profiles do not match assigned feature rows')
    snapshot=connection.execute('SELECT * FROM ml.feature_snapshots WHERE snapshot_id=%s',(model['snapshot_id'],)).fetchone()
    return {'passed':True,'model_id':model_id,'snapshot_id':model['snapshot_id'],'customers':len(rows),
            'split_counts':report['split_counts'],'selected_k':report['selected_k'],'validation_selected':next(c['validation'] for c in report['candidates'] if c['k']==report['selected_k']),
            'test':report['test'],'business_baseline':report['business_baseline'],'profiles':profiles,
            'preprocessing_train_only':True,'predictions_reproduce':True,'artifact_checksums_valid':True,
            'active':model['active'],'manifest_sha256':model['manifest_sha256'],'artifact_relpath':model['artifact_relpath'],
            'snapshot_observations':snapshot['observations'],'future_behavior_validated':False}
