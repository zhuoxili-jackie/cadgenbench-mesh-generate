"""Run the real full-batch CLIs, preserve inputs, then perform independent audit."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
from batch_scope import complete_batch_cases

def inventory():
    return {str(path.relative_to(ROOT)).replace('\\','/'):{'bytes':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns} for directory in ['data','sources'] for path in (ROOT/directory).rglob('*') if path.is_file()}

def main():
    case_ids,eligible=complete_batch_cases(State());before=inventory()
    path=ROOT/'reports/operations/full_acceptance_commands.json'
    scripts={name:file_hash(ROOT/name) for name in ['scripts/scanbench.py','scripts/supplemental_audit.py','scripts/batch_scope.py','scripts/run_final_acceptance.py']}
    signature=digest([before,scripts])
    reused=False
    if path.exists():
        proof=load_json(path)
        reused=proof.get('status')=='pass' and proof.get('signature')==signature and all(file_hash(ROOT/row['log'])==row['log_sha256'] for row in proof['commands'])
    if not reused:
        rows=[];attempt=str(time.time_ns())
        for name,args in [('validate_all',['scripts/scanbench.py','validate','--all']),('supplemental_all',['scripts/supplemental_audit.py','--all'])]:
            log=ROOT/f'logs/final_{name}_{attempt}.log';start=time.time()
            print(canonical_json({'begin':name,'time':start}),flush=True)
            with log.open('w',encoding='utf-8') as stream:result=subprocess.run([sys.executable,*args],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise RuntimeError(f'{name} returned {result.returncode}; inspect {log}')
            assert inventory()==before,f'{name} changed a public input or source file'
            rows.append({'command':args,'exit_code':0,'seconds':time.time()-start,'log':str(log.relative_to(ROOT)).replace('\\','/'),'log_sha256':file_hash(log)})
        proof={'status':'pass','signature':signature,'commands':rows,'script_sha256':scripts,'source_conclusions':len(IDS),'case_count':len(case_ids),'eligible_sources':eligible,'public_and_source_files_unchanged':before,'unchanged_file_count':len(before),'time':time.time(),'scope':'Actual full --all CLIs; incomplete batches rejected before execution; all data/source sizes and mtimes unchanged. The following final audit rereads payload hashes and arrays independently.'}
        atomic_json(path,proof)
    else:print('Reuse verified full-CLI proof; files, scripts and original command logs unchanged.',flush=True)
    log=ROOT/f'logs/final_independent_audit_{time.time_ns()}.log'
    print(canonical_json({'begin':'final_independent_audit','log':str(log.relative_to(ROOT))}),flush=True)
    with log.open('w',encoding='utf-8') as stream:result=subprocess.run([sys.executable,'scripts/final_audit.py'],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(f'final independent audit returned {result.returncode}; inspect {log}')
    assert load_json(ROOT/'reports/final_audit.json')['status']=='pass'
    print(canonical_json({'status':'full_acceptance_passed_requires_delivery_documents','final_audit_sha256':file_hash(ROOT/'reports/final_audit.json'),'log':str(log.relative_to(ROOT)).replace('\\','/')}),flush=True)

if __name__=='__main__':main()
