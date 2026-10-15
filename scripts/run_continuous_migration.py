"""Serial correction dispatcher; pilot stops for freeze, later work requires it."""
from pathlib import Path
import os,sys,argparse,subprocess,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.cases import case_id

p=argparse.ArgumentParser();p.add_argument('--pilot',action='store_true');p.add_argument('--remaining',action='store_true');args=p.parse_args();assert args.pilot!=args.remaining
folder=ROOT/'reports/protocol_amendments/r4_continuous_free_space'
records=[json.loads(s) for s in (folder/'cases_before.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
pilot=[case_id(s,l,n) for s in ['218','231','229'] for n in config()['seeds'] for l in ['hard','medium','easy']]
ids=pilot if args.pilot else [r['case_id'] for r in records if r['case_id'] not in pilot]
if args.remaining:assert load_json(ROOT/'reports/protocol_freeze.json')['implementation_revision']=='r4_continuous_free_space','Seal pilot evidence first'
done=[];started=time.time()
for cid in ids:
    audit=ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}/audit.json'
    if not audit.exists():print(canonical_json({'waiting_for_read_only_scope_audit':cid}),flush=True)
    while not audit.exists():
        atomic_json(folder/'migration_dispatch.json',{'status':'waiting_for_scope_audit','phase':'pilot' if args.pilot else 'remaining','current_case':cid,'done':done,'time':time.time()})
        live=False
        for process in psutil.process_iter(['name','cmdline']):
            try:
                if process.info['name']=='python.exe' and any('audit_continuous_free_space.py' in x for x in process.info['cmdline'] or []) and Path(process.cwd()).resolve()==ROOT:live=True
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        if not live:raise RuntimeError(f'{cid}: scope audit missing and no live auditor; resume only unaudited baseline cases before mutation')
        time.sleep(2)
    atomic_json(folder/'migration_dispatch.json',{'status':'migrating_case','phase':'pilot' if args.pilot else 'remaining','current_case':cid,'done':done,'time':time.time()})
    print(canonical_json({'migrating':cid,'completed_in_this_dispatch':len(done),'selected':len(ids)}),flush=True)
    with (ROOT/f'logs/continuous_migration_{cid}.log').open('a',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,str(ROOT/'scripts/migrate_continuous_case.py'),cid],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(f'{cid}: correction or acceptance failed; inspect its log, no exclusion')
    done.append(cid)
status='pilot_migrated_requires_current_code_tests_and_freeze' if args.pilot else 'all_existing_cases_migrated_requires_source_rollups_and_visual_review'
atomic_json(folder/('pilot_migration.json' if args.pilot else 'remaining_migration.json'),{'status':'pass','cases':done,'seconds':time.time()-started,'script_sha256':file_hash(Path(__file__))})
atomic_json(folder/'migration_dispatch.json',{'status':status,'done':done,'time':time.time()});print(canonical_json({'status':status,'count':len(done)}))
