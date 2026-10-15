"""Continue authorized serial work after the corrected pilot freeze; stop on real errors."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
from scanbench.cases import mesh_stage_key
frozen=load_json(ROOT/'reports/protocol_freeze.json');assert frozen['implementation_revision']=='r4_continuous_free_space'
assert digest(config())==frozen['protocol_config_sha256']
for name,h in frozen['code_sha256'].items():assert file_hash(ROOT/name)==h,name
folder=ROOT/'reports/protocol_amendments/r4_continuous_free_space';state=State()

def run(label,args):
    atomic_json(ROOT/'state/r4_pipeline.json',{'status':'running','stage':label,'command':args,'time':time.time()})
    print(canonical_json({'begin':label,'time':time.time()}),flush=True)
    with (ROOT/f'logs/r4_pipeline_{label}.log').open('a',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,*args],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        atomic_json(ROOT/'state/r4_pipeline.json',{'status':'needs_investigation_not_exclusion','stage':label,'returncode':result.returncode,'log':f'logs/r4_pipeline_{label}.log','time':time.time()})
        raise SystemExit(f'{label} failed; preserve progress and diagnose its log')
    print(canonical_json({'completed':label,'time':time.time()}),flush=True)

run('remaining_migration',['scripts/run_continuous_migration.py','--remaining'])
run('independent_continuous',['scripts/audit_continuous_revision.py','--all','--inventory'])
records=[json.loads(s) for s in (ROOT/'manifests/cases.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
complete=[]
for sid in IDS:
    rows=[r for r in records if r['source_id']==sid]
    if len(rows)!=6:continue
    for r in rows:
        out=ROOT/r['input_path'];assert state.valid(r['case_id'],'mesh',mesh_stage_key(out,config()['reconstruction']))
        assert load_json(ROOT/f'private/annotations/{r["case_id"]}/acceptance.json')['status']=='pass'
    complete.append(sid)
run('source_rollups',['scripts/audit_monotonicity.py','--ids',*complete])
atomic_json(folder/'source_rollups.json',{'status':'pass','six_case_sources':complete,'mesh_sha256':{r['case_id']:file_hash(ROOT/r['input_path']/'mesh.ply') for r in records if r['source_id'] in complete},'time':time.time()})
run('remaining_sources',['scripts/run_full.py','--resume','--ids','243','244','245','246','247','248','249','250'])
atomic_json(ROOT/'state/r4_pipeline.json',{'status':'source_generation_finished_requires_visual_reviews_and_full_independent_acceptance','next':['Inspect every current hard/easy complete-surface preview and record actual reviews','Run validate --all, supplemental --all, final_audit.py','Generate and inspect consistent final documents; only then complete goal and stop'],'time':time.time()})
