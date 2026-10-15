"""Resume only missing original-mesh audits, pilot first, preserving completed evidence."""
from pathlib import Path
import os,sys,subprocess,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.cases import case_id
folder=ROOT/'reports/protocol_amendments/r4_continuous_free_space'
owned=[]
for p in psutil.process_iter(['pid','name','cmdline']):
    try:
        if p.info['name']=='python.exe' and any(Path(x).name=='audit_continuous_free_space.py' for x in p.info['cmdline'] or []) and Path(p.cwd()).resolve()==ROOT:owned.append(p)
    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
assert len(owned)<=2,[(p.pid,p.cmdline()) for p in owned]
for p in owned:
    try:p.kill()
    except psutil.NoSuchProcess:pass
gone,alive=psutil.wait_procs(owned,timeout=5);assert not alive
records=[json.loads(s) for s in (folder/'cases_before.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
pilot=[case_id(s,l,n) for s in ['218','231','229'] for n in config()['seeds'] for l in ['hard','medium','easy']]
all_ids=pilot+sorted({r['case_id'] for r in records}-set(pilot))
missing=[cid for cid in all_ids if not (ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}/audit.json').exists()]
proof={'status':'restarted_missing_audits_only','terminated_owned_read_only_pids':[p.pid for p in owned],'missing_case_ids':missing,'completed_original_audits_preserved':len(all_ids)-len(missing),'reason':'Complete original pilot scope first; no completed original-mesh audit may be rerun after migration.','time':time.time(),'script_sha256':file_hash(Path(__file__))}
atomic_json(folder/'scope_priority_resume.json',proof);print(canonical_json(proof),flush=True)
if missing:
    with (ROOT/'logs/continuous_free_space_audit_pilot_first.log').open('a',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,'scripts/audit_continuous_free_space.py','--case-ids',*missing],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,result.returncode
print(canonical_json({'status':'all_129_original_mesh_audits_complete','time':time.time()}))
