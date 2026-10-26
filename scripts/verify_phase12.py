"""Verify the frozen Phase 12 evidence archive; does not run runtime tests."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.target.resolve()
    def read(path):
        return json.loads(path.read_text(encoding='utf-8-sig'))
    report = read(root/'docs/phase12/release.json')
    files = report['evidence_files']
    if len(files) != 53 or len({x['archive_path'] for x in files}) != len(files):
        raise RuntimeError('Evidence inventory differs')
    paths = {}
    for item in files:
        relative = Path(item['archive_path'])
        path = (root/relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root/'docs/phase12/evidence'):
            raise RuntimeError('Unsafe evidence path')
        data = path.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise RuntimeError('Evidence differs: '+item['archive_path'])
        paths[item['original_path']] = path
    def evidence(suffix):
        matches = [p for original,p in paths.items() if original.endswith(suffix)]
        if len(matches) != 1:
            raise RuntimeError('Ambiguous or missing evidence: '+suffix)
        return read(matches[0])
    accepted = report['accepted_runs']
    m = evidence(accepted['measurement']+'/measurement.json')
    samples = evidence(accepted['measurement']+'/latency-samples.json')
    q = evidence(accepted['measurement']+'/query-benchmark.json')
    if not (m['passed'] and m['historical_facts_unchanged'] and m['no_retraining']):
        raise RuntimeError('Measurement failed')
    if len(samples) != 60 or any(sum(x['operation']==op for x in samples)!=20 for op in ['insert','update','delete']):
        raise RuntimeError('Measurement sample counts differ')
    if len(q['queries'])!=6 or not all(x['equal_results'] for x in q['queries']):
        raise RuntimeError('Query benchmark differs')
    for label in ['quality-before','quality-after','constraints-retry','scd2-type1','snapshot-reconciliation','cdc-replay']:
        if not evidence(accepted['quality_replay']+'/'+label+'.json')['passed']:
            raise RuntimeError('Quality/replay failed: '+label)
    before = evidence(accepted['quality_replay']+'/quality-before.json')['result']
    after = evidence(accepted['quality_replay']+'/quality-after.json')['result']
    for data in [before,after]:
        if data['error_findings']!=0 or data['warning_findings']!=998:
            raise RuntimeError('Quality summary differs')
        if data['reconciliation']['warehouse']['fact_state_sha256']!=report['historical_fact_sha256']:
            raise RuntimeError('Historical facts differ')
    mart = evidence(accepted['mart']+'/mart-integration.json')
    if not (mart['passed'] and mart['result']['fixtures']['passed'] and mart['result']['source_facts_and_news_unchanged']):
        raise RuntimeError('Mart integration failed')
    for label in ['kmeans-verify','rf-verify','dashboard-checks']:
        if not evidence(accepted['ml_web']+'/'+label+'.json')['passed']:
            raise RuntimeError('Model/web failed: '+label)
    web = evidence(accepted['ml_web']+'/dashboard-checks.json')
    if len(web['app']['pages_executed'])!=8 or not web['app']['cold_import_verified'] or not web['queries']['current_fact_matches_mart']:
        raise RuntimeError('Dashboard checks differ')
    for suffix in ['collector-recovered.json','applier-recovered.json']:
        result = evidence(suffix)
        if not result['passed'] or not result['result']['source_change_during_worker_downtime_recovered']:
            raise RuntimeError('Worker recovery failed')
    ml = evidence(accepted['inference_recovery']+'/checks.json')
    if not ml['passed'] or not all(ml['result'][key] for key in ['durable_queue_survived_worker_restart','queue_replay_idempotent','historical_business_facts_unchanged','no_retraining']):
        raise RuntimeError('ML recovery failed')
    print('PHASE 12 EVIDENCE AND REPORTS VERIFIED')
    print('53 archived files; runtime results supplied by user; no runtime tests rerun.')
    print('Quality: 0 errors; 998 documented warnings.')
    print('Phase 12: PASSED WITH DOCUMENTED LIMITATIONS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
