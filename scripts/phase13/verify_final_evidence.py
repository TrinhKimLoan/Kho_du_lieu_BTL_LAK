"""Verify frozen user evidence for the final release; no live database access."""
import hashlib,json
from pathlib import Path


def verify(root):
    index=json.loads((root/'docs/phase13/final/release.json').read_text(encoding='utf-8'))
    for item in index['evidence_files']:
        path=(root/item['path']).resolve()
        if not path.is_relative_to(root/'docs/phase13/final/evidence'):raise RuntimeError('Unsafe evidence index')
        data=path.read_bytes()
        if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise RuntimeError('Evidence changed: '+item['path'])
    base=root/'docs/phase13/final/evidence'
    def get(name):return json.loads((base/name).read_text(encoding='utf-8-sig'))
    for group,files in [('rebuilt-project/restore',['restore','source-restored','mart-restored','kmeans-restored','rf-restored','dashboard-checks']),('rebuilt-project/cdc',['bootstrap','cdc-verified','new-epoch-reconciliation','new-cdc-demo','ml-init','ml-seed','ml-finish','ml-cleanup','mart-refreshed','dashboard-checks'])]:
        for name in files:
            if not get(group+'/'+name+'.json')['passed']:raise RuntimeError('Unsuccessful accepted evidence: '+name)
    boot=get('rebuilt-project/cdc/bootstrap.json');cdc=get('rebuilt-project/cdc/cdc-verified.json')
    if not (boot['cdc_bootstrap_verified'] and boot['fresh_source_to_ml_insert_update_delete_verified'] and boot['dashboard_pages_verified']==8 and cdc['historical_facts_unchanged'] and cdc['model_registry_unchanged'] and cdc['new_epoch_checkpoint_rows']>0):raise RuntimeError('Rebuild invariant differs')
    plan=get('rebuilt-project/cdc/epoch-plan.json')
    after=get('rebuilt-project/cdc/new-epoch-reconciliation.json')['result']
    if plan['baseline']['fact_state_sha256']!=after['fact_state_sha256']:raise RuntimeError('Fact state differs after CDC bootstrap')
    if get('candidate-summary.json')['sha256']!=get('original-project/stage-a-20261026T093024Z-4d645ea9/package.json')['result']['sha256']:raise RuntimeError('Candidate provenance mismatch')
    print('PHASE 13 REBUILD EVIDENCE VERIFIED')
    return index


if __name__=='__main__':verify(Path(__file__).resolve().parents[2])
