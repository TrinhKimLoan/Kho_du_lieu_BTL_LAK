import hashlib
import importlib.metadata
from pathlib import Path
import numpy as np
from sklearn.cluster import KMeans
from sklearn.pipeline import Pipeline
from sklearn.metrics import silhouette_score,davies_bouldin_score,adjusted_rand_score
from .preprocess import RFMPreprocessor
from .rfm import FEATURES

CONFIG={'k_values':list(range(2,9)),'random_state':42,'n_init':20,'stability_seeds':[7,23,71],
        'min_train_fraction':.03,'min_validation_fraction':.02,'min_stability_ari':.6,
        'selection':'highest validation silhouette, then lower validation DBI, then smaller K; eligible candidates only',
        'refit_after_selection':False,'clip_quantiles':[.01,.99]}


def versions():
    return {p:importlib.metadata.version(p) for p in ['numpy','scipy','scikit-learn','joblib','threadpoolctl']}


def matrix(rows):return np.asarray([[float(r[k]) for k in FEATURES] for r in rows],dtype=np.float64)


def metrics(X,labels,k=None):
    labels=np.asarray(labels);unique,counts=np.unique(labels,return_counts=True)
    valid=1<len(unique)<len(labels)
    sizes={str(int(a)):int(b) for a,b in zip(unique,counts)}
    if k is not None:
        for cluster in range(k):sizes.setdefault(str(cluster),0)
    return {'silhouette':float(silhouette_score(X,labels,sample_size=min(2000,len(labels)),random_state=42)) if valid else None,
            'davies_bouldin':float(davies_bouldin_score(X,labels)) if valid else None,'cluster_sizes':sizes,
            'minimum_cluster_fraction':min(sizes.values())/len(labels),'metric_space':'train-fitted clipped log1p standardized RFM'}


def choose(candidates):
    eligible=[r for r in candidates if r['eligible']]
    if not eligible:raise RuntimeError('No candidate K passed predeclared size/stability checks; inspect candidate report')
    return min(eligible,key=lambda r:(-r['validation']['silhouette'],r['validation']['davies_bouldin'],r['k']))['k']


def profiles(rows,labels,train):
    thresholds=np.quantile(matrix(train),[1/3,2/3],axis=0)
    result=[]
    for cluster in sorted(set(labels.tolist())):
        group=[r for r,label in zip(rows,labels) if label==cluster]
        medians=np.median(matrix(group),axis=0)
        r,f,m=[0 if v<thresholds[0,i] else 2 if v>thresholds[1,i] else 1 for i,v in enumerate(medians)]
        name=['Gần đây','Mức gần đây trung bình','Lâu chưa quay lại'][r]+'; '+['mua ít','tần suất trung bình','mua thường xuyên'][f]+'; '+['chi tiêu thấp','chi tiêu trung bình','chi tiêu cao'][m]
        result.append({'cluster_id':int(cluster),'name':name,'customers':len(group),'share':len(group)/len(rows),
                       'median_R_days':float(medians[0]),'median_F_orders':float(medians[1]),'median_M_vnd':float(medians[2]),
                       'monetary_total_vnd':format(sum(r['monetary'] for r in group),'.2f'),
                       'split_counts':{s:sum(r['split']==s for r in group) for s in ['train','validation','test']}})
    return result


def fit(rows):
    partitions={s:[r for r in rows if r['split']==s] for s in ['train','validation','test']}
    train=partitions['train'];validation=partitions['validation'];test=partitions['test']
    if min(map(len,partitions.values()))<5:raise ValueError('Split is too small')
    Xtrain=matrix(train);Xval=matrix(validation)
    prep=RFMPreprocessor().fit(Xtrain);T=prep.transform(Xtrain);V=prep.transform(Xval)
    candidates=[];models={}
    for k in CONFIG['k_values']:
        model=KMeans(n_clusters=k,random_state=42,n_init=20,algorithm='lloyd').fit(T)
        models[k]=model;train_labels=model.predict(T);val_labels=model.predict(V)
        tm=metrics(T,train_labels,k);vm=metrics(V,val_labels,k)
        stability=[]
        for seed in CONFIG['stability_seeds']:
            alternate=KMeans(n_clusters=k,random_state=seed,n_init=20,algorithm='lloyd').fit(T)
            stability.append(float(adjusted_rand_score(train_labels,alternate.predict(T))))
        ari=float(np.median(stability))
        eligible=vm['silhouette'] is not None and tm['minimum_cluster_fraction']>=.03 and vm['minimum_cluster_fraction']>=.02 and ari>=.6
        candidates.append({'k':k,'train':tm,'validation':vm,'stability_ari':stability,'median_stability_ari':ari,'eligible':eligible})
    selected=choose(candidates)
    pipeline=Pipeline([('rfm',prep),('kmeans',models[selected])])
    # Test is transformed/evaluated only after selection. No fit on validation/test/full data.
    E=prep.transform(matrix(test));test_labels=pipeline.predict(matrix(test))
    baseline_thresholds=np.median(Xtrain,axis=0)
    def baseline(X):
        return ((X[:,0]<=baseline_thresholds[0]).astype(int)*4+(X[:,1]>=baseline_thresholds[1]).astype(int)*2+(X[:,2]>=baseline_thresholds[2]).astype(int))
    all_X=matrix(rows);labels=pipeline.predict(all_X)
    repeat=KMeans(n_clusters=selected,random_state=42,n_init=20,algorithm='lloyd').fit(T)
    if not np.array_equal(repeat.predict(T),models[selected].predict(T)):raise RuntimeError('Selected KMeans fit is not reproducible with fixed seed')
    report={'configuration':CONFIG,'selected_k':selected,'candidates':candidates,
            'test':metrics(E,test_labels,selected),'split_counts':{s:len(v) for s,v in partitions.items()},
            'preprocessing':{'fit_rows':prep.fit_rows_,'lower':prep.lower_.tolist(),'upper':prep.upper_.tolist(),
                             'scaler_mean':prep.scaler_.mean_.tolist(),'scaler_scale':prep.scaler_.scale_.tolist()},
            'business_baseline':{'rule':'three median thresholds fitted on train: recent R, frequent F, high M, eight bit-pattern groups',
                                 'thresholds':baseline_thresholds.tolist(),'validation':metrics(V,baseline(Xval)),
                                 'test':metrics(E,baseline(matrix(test)))},
            'repeat_fit_same_labels':True,'test_used_for_selection':False,'refit_on_all_customers':False,
            'future_evaluation':'No observations after primary reference 2026-01-01; no future-behavior claim.',
            'limitations':['Simulated transactions; no true VIP/loyalty labels.','Cluster IDs are arbitrary, not a customer-value ranking.',
                           'Internal geometric scores do not establish business impact or supervised accuracy.']}
    assignments=[{'customer_id':r['customer_id'],'cluster_id':int(label),'distance':float(distance),'business_segment':int(base)}
                 for r,label,distance,base in zip(rows,labels,pipeline.transform(all_X).min(axis=1),baseline(all_X))]
    return pipeline,report,profiles(rows,labels,train),assignments
