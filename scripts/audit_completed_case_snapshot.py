"""Audit newly completed sources without changing any source or Mesh payload."""
from pathlib import Path
import os,sys,argparse,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
from scanbench.common import *


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ids',nargs='+',required=True);args=parser.parse_args()
    state=State();selected=[];run=str(time.time_ns())
    for sid in args.ids:
        source_run=load_json(ROOT/f'state/source_runs/{sid}.json')
        assert source_run['status']=='six_cases_generated_and_accepted'
        for cid,body in state.db.execute("SELECT id,body FROM records WHERE kind='cases' ORDER BY id"):
            record=json.loads(body)
            if record['source_id']==sid and not (ROOT/f'reports/continuous_independent/{cid}.json').exists():
                assert record['validation_status']=='pass';selected.append(cid)
    completed=[];status='snapshot_complete'
    for cid in selected:
        if psutil.virtual_memory().available<3*2**30:status='deferred_remaining_to_final_audit_for_memory';break
        log=ROOT/f'logs/completed_continuous_{cid}_{run}.log';start=time.time()
        print(canonical_json({'independent_case_begin':cid}),flush=True)
        with log.open('w',encoding='utf-8') as stream:
            child=subprocess.run([sys.executable,'scripts/audit_continuous_revision.py','--case-ids',cid],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert child.returncode==0,('Independent case audit failed',cid,str(log))
        path=ROOT/f'reports/continuous_independent/{cid}.json';assert load_json(path)['status']=='pass'
        completed.append({'case_id':cid,'report_sha256':file_hash(path),'log':log.relative_to(ROOT).as_posix(),'log_sha256':file_hash(log),'seconds':time.time()-start})
        print(canonical_json(completed[-1]),flush=True)
    atomic_json(ROOT/f'reports/operations/completed_case_snapshot_{run}.json',{'status':status,'sources':args.ids,'selected':selected,'completed':completed,'no_source_observation_or_mesh_modified':True,'audit_script_sha256':file_hash(ROOT/'scripts/audit_continuous_revision.py'),'script_sha256':file_hash(Path(__file__)),'time':time.time()})
    print(canonical_json({'status':status,'completed':len(completed),'remaining':len(selected)-len(completed)}),flush=True)


if __name__=='__main__':main()
