"""Serial continuation through actual v2 migration, affected cases and acceptance.

Direct visual review remains an operator action. This coordinator waits for its
current image hashes; it never creates or substitutes a visual-review approval.
"""
from pathlib import Path
import os,sys,subprocess,traceback,sqlite3
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
from scanbench.common import *
from snapshot_sampling_density_v2 import active_source_workers
FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'


def status(phase,**fields):
    item={'status':'running','phase':phase,'coordinator_pid':os.getpid(),'time':time.time(),**fields}
    atomic_json(ROOT/'state/sampling_completion_pipeline.json',item);print(canonical_json(item),flush=True)


def passed(path,status_value='pass'):
    return path.exists() and load_json(path).get('status')==status_value


def run(label,arguments):
    log=ROOT/f'logs/sampling_completion_{label}_{time.time_ns()}.log'
    status(label,command=arguments,log=log.relative_to(ROOT).as_posix())
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,*arguments],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(f'{label} failed ({result.returncode}); preserve evidence and inspect {log.relative_to(ROOT)}')
    return log


def review_current(sid):
    path=ROOT/f'reports/visual_reviews/{sid}.json'
    if not path.exists():return False
    review=load_json(path)
    if review.get('status')!='pass' or len(review.get('cases',[]))!=2:return False
    for item in review['cases']:
        if file_hash(ROOT/item['preview'])!=item['preview_sha256']:return False
        if file_hash(ROOT/f'data/cases/{item["case_id"]}/input/mesh.ply')!=item['mesh_sha256']:return False
    return {item['level'] for item in review['cases']}=={'hard','easy'}


def main():
    try:
        if not (FOLDER/'baseline.json').exists():
            last=0
            while True:
                previous=load_json(ROOT/'state/r4_pipeline.json')
                if previous.get('status')=='needs_investigation_not_exclusion':raise RuntimeError('Unchanged-source pipeline requires investigation; density revision not installed')
                ready=previous.get('status')=='unaffected_sources_finished_density245_pending' and not active_source_workers()
                refresh=FOLDER/'freeze_guard_control_refresh.json'
                controls=passed(refresh) and load_json(refresh)['candidate_manifest_sha256']==file_hash(FOLDER/'candidate_manifest.json')
                if ready and controls:break
                if time.time()-last>=30:
                    status('waiting_for_original_source_workers_and_current_controls',original_pipeline_status=previous.get('status'),controls_current=controls);last=time.time()
                time.sleep(5)
            run('immutable_snapshot',['scripts/snapshot_sampling_density_v2.py'])
        if not (FOLDER/'installation.json').exists():run('install_tested_candidate',['scripts/install_sampling_density_v2.py'])
        if not passed(FOLDER/'default_migration.json','pass_all_unchanged_sources_migrated'):
            run('adopt_unchanged_cases',['scripts/migrate_sampling_density_defaults.py'])
        baseline=load_json(FOLDER/'baseline.json')
        for sid in baseline['affected_sources']:
            if not (FOLDER/f'affected_sources/{sid}/prepared.json').exists():run('prepare_refined_'+sid,['scripts/prepare_refined_sampling_source.py',sid])
        if not passed(FOLDER/'pre_freeze_independent_audit.json'):
            run('independent_migration_audit',['scripts/audit_sampling_density_revision.py','--before-freeze'])
        frozen=load_json(ROOT/'reports/protocol_freeze.json')
        if frozen.get('physical_protocol_revision')!='physical_scan_v2_overlap_density':run('freeze_sampling_v2',['scripts/freeze_sampling_density_v2.py'])
        frozen=load_json(ROOT/'reports/protocol_freeze.json')
        for name,h in frozen['code_sha256'].items():assert file_hash(ROOT/name)==h,name
        for sid in baseline['affected_sources']:
            complete=ROOT/f'state/source_runs/{sid}.json'
            if not passed(complete,'six_cases_generated_and_accepted'):
                run('generate_refined_'+sid,['scripts/run_full.py','--resume','--ids',sid])
        if not passed(ROOT/'reports/operations/delivery_export_command_sampling_v2.json'):
            run('actual_sampling_v2_public_export',['scripts/verify_delivery_export_sampling_v2.py'])
        last=0
        while not all(review_current(sid) for sid in baseline['eligible_sources']):
            if time.time()-last>=30:
                status('waiting_for_actual_current_hard_easy_image_review',missing_sources=[sid for sid in baseline['eligible_sources'] if not review_current(sid)],next='Operator must display the actual GT/hard/easy images and record their current hashes');last=time.time()
            time.sleep(5)
        run('actual_full_acceptance',['scripts/run_final_acceptance.py'])
        final=load_json(ROOT/'reports/final_audit.json');assert final['status']=='pass'
        result={'status':'full_acceptance_passed_requires_final_documents','phase':'actual_full_acceptance_passed','all32_sources':final['source_count'],'actual_cases':final['actual_case_count'],'final_audit_sha256':file_hash(ROOT/'reports/final_audit.json'),'next':'Write final delivery documents with actual goal timing; verify document/index consistency; only then complete goal','time':time.time()}
        atomic_json(ROOT/'state/sampling_completion_pipeline.json',result);print(canonical_json(result),flush=True)
    except Exception as exc:
        item={'status':'needs_investigation_not_excluded','exception':repr(exc),'traceback':traceback.format_exc(),'next':'Locate the failing stage in its immutable log, fix the program or missing evidence, then resume without repeating valid stages','time':time.time()}
        atomic_json(ROOT/'state/sampling_completion_pipeline.json',item);print(canonical_json(item),flush=True);raise


if __name__=='__main__':main()
