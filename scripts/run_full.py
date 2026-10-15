"""Serial, restartable full-dataset driver; never treats an exception as exclusion."""
from pathlib import Path
import os,sys,subprocess,argparse,time,shutil,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
os.environ['PYTHONUTF8']='1';os.environ['PYTHONIOENCODING']='utf-8'
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *

def guard():
    policy=config()['resources'];free=shutil.disk_usage(ROOT).free/2**30
    if free<policy['reserve_gib']+2:raise RuntimeError(f'disk budget guard: free {free:.2f} GiB; preserve {policy["reserve_gib"]} GiB plus 2 GiB active-stage headroom')
    if psutil.virtual_memory().available<800*2**20:raise RuntimeError('resource guard: less than 800 MiB available RAM; checkpoint preserved')
    return {'free_disk_gib':free,'available_ram_gib':psutil.virtual_memory().available/2**30}

def prepare_reference(sid,state):
    """Continue documented native failures through the taskbook's reference tiers."""
    from scanbench.sources import prepare
    failure=None
    try:return prepare(sid,state)
    except RuntimeError as exc:
        if not str(exc).startswith(f'native tessellation failed for {sid};'):raise
        failure=str(exc)
    # Release the failed tessellation traceback/arrays before the isolated retry.
    __import__('gc').collect();guard()
    attempts=load_json(ROOT/f'private/gt/{sid}/native_attempts.json')
    assert len(attempts)==3 and all(a['status']=='failed' for a in attempts)
    event('source_reference_investigation',source=sid,reason=failure,automatic_exclusion=False)
    for flags in [['--trial','0.005','0.075'],['--official']]:
        guard()
        command=[sys.executable,str(ROOT/'scripts/investigate_source_reference.py'),sid,*flags,'--promote']
        result=subprocess.run(command,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode==0:
            reference=prepare(sid,state)
            event('source_reference_qualified',source=sid,tier=reference['status'],evidence=reference['evidence_summary'])
            return reference
        event('source_reference_alternative_not_qualified',source=sid,flags=flags,returncode=result.returncode)
    raise RuntimeError(f'{sid}: additional native and official reference routes are not qualified; inspect recorded evidence, not an automatic exclusion')

def case_worker(sid,level,seed):
    from scanbench.cases import generate_case
    from scanbench.validate import validate_case
    from scanbench.render_cached import preview
    from scanbench.supplemental import audit_case
    if sid not in IDS or level not in config()['difficulty'] or seed not in config()['seeds']:raise ValueError('case arguments outside the frozen dataset')
    state=State()
    guard();cid=generate_case(sid,level,seed,state);result=validate_case(cid,state);preview(cid,state)
    if result['status']=='investigation_required':
        subprocess.run([sys.executable,str(ROOT/'scripts/review_fragmentation_dispatch.py'),cid],check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));result=validate_case(cid,state)
    if result['status']!='pass':raise RuntimeError(f'{cid}: {result["status"]}: {result["failures"]}; stop for investigation')
    extra=audit_case(cid)
    if extra['status']!='pass':raise RuntimeError(f'{cid}: supplemental physical feature gate failed')
    event('full_case_accepted',source=sid,case=cid,level=level,seed=seed)

def worker(sid,reference_retries=0):
    from scanbench.verified_placements import prepare_verified_placements
    from scanbench.scan import acquire_scans
    from scanbench.cases import generate_case
    from scanbench.validate import validate_case
    from scanbench.render_cached import preview
    from scanbench.supplemental import source_factors,audit_case
    state=State();started=time.time();event('full_source_begin',source=sid,resources=guard())
    try:
        source=prepare_reference(sid,state)
        if source['status']=='source_excluded':
            assert source.get('reason') and len(source.get('attempts',[]))>=2
            for path,h in source['evidence_sha256'].items():assert file_hash(ROOT/path)==h,f'exclusion evidence changed: {path}'
            event('full_source_excluded_verified',source=sid,evidence_summary=source['evidence_summary'],formal_case_count=0)
            return
        poses=prepare_verified_placements(sid,state)
        if len(poses['placements'])<3:
            command=[sys.executable,str(ROOT/'scripts/investigate_limited_poses.py'),sid]
            check=subprocess.run(command,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if check.returncode==2:
                proof=load_json(ROOT/f'private/gt/{sid}/limited_pose_investigation.json')
                assert proof['status']=='additional_certified_pose_requires_integration'
                subprocess.run([sys.executable,str(ROOT/'scripts/integrate_discrete_poses.py'),sid],check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                poses=prepare_verified_placements(sid,state)
                if len(poses['placements'])<3:subprocess.run(command,check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            elif check.returncode:raise subprocess.CalledProcessError(check.returncode,command)
        boundary_result=subprocess.run([sys.executable,str(ROOT/'scripts/qualify_boundary_audits.py'),sid],stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if boundary_result.returncode:
            boundary_path=ROOT/f'reports/source_boundary_audits/{sid}.json'
            boundary=load_json(boundary_path) if boundary_path.exists() else {}
            if reference_retries or boundary.get('status')!='reference_precision_requires_investigation' or boundary.get('reference_sha256')!=file_hash(ROOT/f'private/gt/{sid}/mesh.npz'):
                raise RuntimeError(f'{sid}: independent boundary qualification failed; inspect the actual evidence before continuing')
            event('boundary_reference_retry',source=sid,sampled_max_mm=boundary['sampled_max_mm'],bound_mm=boundary['native_or_approx_bound_mm'],scan_started=False)
            for flags in [['--trial','0.01','0.075'],['--trial','0.02','0.3'],['--trial','0.005','0.075'],['--official']]:
                if flags[0]=='--trial' and (float(flags[1]),float(flags[2]))==(source['chord_mm'],source['angle_rad']):continue
                guard()
                result=subprocess.run([sys.executable,str(ROOT/'scripts/investigate_boundary_reference.py'),sid,*flags,'--promote'],stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode==0:return worker(sid,reference_retries+1)
            raise RuntimeError(f'{sid}: all recorded boundary reference alternatives require investigation; no source was excluded')
        acquire_scans(sid,state);preview(sid,state,True);source_factors(sid)
        for seed in config()['seeds']:
            for level in ['hard','medium','easy']:
                guard()
                subprocess.run([sys.executable,str(Path(__file__)), '--case-worker',sid,level,str(seed)],check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        subprocess.run([sys.executable,str(ROOT/'scripts/audit_monotonicity.py'),'--ids',sid],check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        subprocess.run([sys.executable,str(ROOT/'scripts/render_physical_plan.py'),sid],check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result={'status':'six_cases_generated_and_accepted','source_id':sid,'finished':time.time(),'elapsed_this_resume_seconds':time.time()-started,'resources_after':guard()}
        previous=state.db.execute("SELECT body FROM records WHERE kind='failures' AND id=?",(sid,)).fetchone()
        if previous:
            resolved=json.loads(previous[0]);resolved.update(status='resolved',resolution=result);state.record('failures',sid,resolved)
        atomic_json(ROOT/f'state/source_runs/{sid}.json',result);event('full_source_complete',**result)
    except Exception as exc:
        detail={'source_id':sid,'status':'needs_investigation_not_excluded','time':time.time(),'exception':repr(exc),'traceback':traceback.format_exc(),'next_action':'diagnose the recorded failing stage; preserve qualified upstream outputs and resume the same source'}
        atomic_json(ROOT/f'state/source_runs/{sid}.json',detail);state.record('failures',sid,detail);event('full_source_failed',source=sid,error=repr(exc));raise

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker');p.add_argument('--case-worker',nargs=3,metavar=('SOURCE','LEVEL','SEED'));p.add_argument('--ids',nargs='+');p.add_argument('--resume',action='store_true');args=p.parse_args()
    if config()['status']!='frozen':raise SystemExit('full batch requires a frozen pilot protocol')
    if not (ROOT/'reports/protocol_freeze.json').exists():raise SystemExit('missing verified pilot freeze evidence')
    frozen=load_json(ROOT/'reports/protocol_freeze.json')
    if frozen['protocol_config_sha256']!=digest(config()):raise SystemExit('current settings differ from frozen pilot')
    if args.case_worker:return case_worker(args.case_worker[0],args.case_worker[1],int(args.case_worker[2]))
    if args.worker:return worker(args.worker)
    selected=args.ids or ['218','231','229']+[s for s in IDS if s not in ['218','231','229']]
    for sid in selected:
        if sid not in IDS:raise ValueError(f'not an official source: {sid}')
        guard();log=ROOT/f'logs/full_{sid}.log'
        with open(log,'a',encoding='utf-8') as f:
            result=subprocess.run([sys.executable,str(Path(__file__)), '--worker',sid],stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise SystemExit(f'source {sid} needs investigation, log {log}; no source was excluded')
        subprocess.run([sys.executable,str(ROOT/'scripts/report_progress.py')],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    event('all_requested_source_jobs_accepted',sources=selected,remaining='independent full audit, visual inspection, final report')

if __name__=='__main__':main()
