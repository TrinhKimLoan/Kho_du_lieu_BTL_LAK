"""Train on original supplied LAK Excel; does not validate PostgreSQL or Docker."""
import argparse
import json
from pathlib import Path
from src.source.data import prepare
from src.delivery.features import construct,identity
from src.delivery.artifacts import build


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    source=prepare()['orders']
    mapping={'Giao hàng nhanh':'FAST','Giao hàng bình thường':'NORMAL','Giao hàng chậm':'SLOW'}
    source=[dict(r,shipping_method=mapping.get(r['shipping_method'],'UNKNOWN')) for r in source]
    rows,counts=construct(source);snapshot=identity(rows)
    result=build(snapshot,rows,args.output)
    report={'phase':9,'offline_original_lak':True,'postgres_validated':False,'docker_validated':False,
            'observations':counts,'model_id':result[0],'evaluation':result[3]}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'offline-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'observations':counts,'test':result[3]['test'],'baseline_test':result[3]['baselines']['test'],
                      'selected_candidate':result[3]['selected_candidate'],'beats_baseline':result[3]['beats_shipping_baseline_test_mae']},indent=2))


if __name__=='__main__':main()
