import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from .features import NUMERIC, CATEGORICAL, FEATURES, matrix

CONFIG = {'seed':42, 'n_estimators':150, 'depths':[6,None], 'min_leaves':[5,20], 'permutation_repeats':5,
          'selection':'minimum validation MAE, then RMSE, then candidate order', 'refit_train_validation':False}


def scores(actual, predicted):
    actual=np.asarray(actual,dtype=float);predicted=np.asarray(predicted,dtype=float)
    if not len(actual) or not np.isfinite(predicted).all() or (predicted<0).any(): raise ValueError('Invalid regression predictions')
    errors=predicted-actual
    return {'count':len(actual),'mae_hours':float(np.mean(np.abs(errors))),'rmse_hours':float(np.sqrt(np.mean(errors**2))),
            'bias_hours':float(np.mean(errors))}


def baseline_fit(rows):
    global_median=float(np.median([r['target_hours'] for r in rows]))
    methods=sorted({r['features']['shipping_method'] or '__MISSING__' for r in rows})
    return {'global_median':global_median,'by_shipping_method':{m:float(np.median([r['target_hours'] for r in rows if (r['features']['shipping_method'] or '__MISSING__')==m])) for m in methods}}


def baseline_predict(baseline,rows,grouped=True):
    return np.array([baseline['by_shipping_method'].get(r['features']['shipping_method'] or '__MISSING__',baseline['global_median']) if grouped else baseline['global_median'] for r in rows])


def estimator(depth,leaf):
    prep=ColumnTransformer([
        ('numeric',SimpleImputer(strategy='median',keep_empty_features=True),list(range(len(NUMERIC)))),
        ('categorical',OneHotEncoder(handle_unknown='ignore',sparse_output=False),list(range(len(NUMERIC),len(FEATURES))))])
    return Pipeline([('preprocess',prep),('forest',RandomForestRegressor(n_estimators=CONFIG['n_estimators'],max_depth=depth,
        min_samples_leaf=leaf,random_state=CONFIG['seed'],n_jobs=1))])


def fit(rows):
    parts={s:[r for r in rows if r['split']==s] for s in ['train','validation','test']}
    train,validation,test=[parts[s] for s in ['train','validation','test']]
    if min(map(len,parts.values()))<30: raise ValueError('Insufficient chronological holdout')
    X=matrix(train); y=np.array([r['target_hours'] for r in train]); V=matrix(validation)
    baseline=baseline_fit(train); candidates=[]; models=[]
    for depth in CONFIG['depths']:
        for leaf in CONFIG['min_leaves']:
            model=estimator(depth,leaf).fit(X,y);models.append(model)
            candidates.append({'max_depth':depth,'min_samples_leaf':leaf, 'validation':scores([r['target_hours'] for r in validation],model.predict(V))})
    selected=min(range(len(candidates)),key=lambda i:(candidates[i]['validation']['mae_hours'],candidates[i]['validation']['rmse_hours'],i))
    model=models[selected]; E=matrix(test); actual=np.array([r['target_hours'] for r in test]); predicted=model.predict(E)
    baseline_values=baseline_predict(baseline,test)
    report={'configuration':CONFIG,'candidates':candidates,'selected_candidate':selected,'split_counts':{s:len(v) for s,v in parts.items()},
            'test':scores(actual,predicted),'baseline':baseline,
            'baselines':{s:{'global':scores([r['target_hours'] for r in part],baseline_predict(baseline,part,False)),
                            'by_shipping_method':scores([r['target_hours'] for r in part],baseline_predict(baseline,part))} for s,part in [('validation',validation),('test',test)]},
            'test_used_for_selection':False,'preprocessing_fit_rows':len(train),'refit_on_holdout':False,
            'split_ranges':{s:{'dispatch_min':v[0]['dispatched_at'],'dispatch_max':v[-1]['dispatched_at'],'received_max':max(r['received_at'] for r in v)} for s,v in parts.items()}}
    report['beats_shipping_baseline_test_mae']=report['test']['mae_hours']<report['baselines']['test']['by_shipping_method']['mae_hours']
    report['test_error_groups']={}
    for field in ['delivery_district','shipping_method','quantity_band']:
        groups=[]
        for group in sorted({r['features'][field] or '__MISSING__' for r in test}):
            idx=[i for i,r in enumerate(test) if (r['features'][field] or '__MISSING__')==group]
            groups.append({'group':group,'forest':scores(actual[idx],predicted[idx]),'baseline':scores(actual[idx],baseline_values[idx]),'small_group':len(idx)<30})
        report['test_error_groups'][field]=groups
    importance=permutation_importance(model,E,actual,scoring='neg_mean_absolute_error',n_repeats=CONFIG['permutation_repeats'],random_state=42,n_jobs=1)
    report['permutation_importance_test']=[{'feature':f,'mae_increase_hours':float(m),'std_hours':float(s)} for f,m,s in zip(FEATURES,importance.importances_mean,importance.importances_std)]
    report['limitations']=['Simulated historical orders; no evidence of real-world predictive validity.',
        'Feature availability at dispatch is an assumption; Excel contains no input-time audit.',
        'Current historical warehouse rows are used; post-hoc corrections cannot be reconstructed as-of original prediction time.',
        'No confidence interval or guaranteed delivery deadline; performance may reflect the data generator.',
        'Permutation importance is descriptive on test, not used to select features or retune the model. Correlated predictors can share importance.']
    all_predictions=model.predict(matrix(rows));all_baseline=baseline_predict(baseline,rows)
    predictions=[{'order_id':r['order_id'],'split':r['split'],'actual_hours':r['target_hours'],'predicted_hours':float(p),
                  'baseline_hours':float(b),'error_hours':float(p-r['target_hours'])} for r,p,b in zip(rows,all_predictions,all_baseline)]
    return model,report,predictions
