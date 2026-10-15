"""Exercise real compatibility migration on copied 218 acquisition and one case.

This is a separate test runtime, with an immutable local baseline and its own
SQLite ledger. It never changes or adopts a formal production case.
"""
from pathlib import Path
import os,sys,shutil,sqlite3,zipfile,hashlib,argparse,subprocess,time,json
MAIN=Path(__file__).resolve().parents[1]
FOLDER=MAIN/'reports/protocol_amendments/r5_sampling_density'


def prepare():
    sys.path.insert(0,str(MAIN/'src'))
    from scanbench.common import load_json,atomic_json,file_hash,digest,State,canonical_json
    controls=load_json(FOLDER/'candidate_controls.json');assert controls['status']=='pass'
    runtime=FOLDER/'controls'/f'migration_{time.time_ns()}';runtime.mkdir(parents=True)
    revision=runtime/'reports/protocol_amendments/r5_sampling_density';revision.mkdir(parents=True)
    frozen=load_json(MAIN/'reports/protocol_freeze.json')
    for name in frozen['code_sha256']:
        src=MAIN/name;old=revision/'code_before'/name;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,old)
        target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True)
        candidate=FOLDER/'candidate'/name;shutil.copy2(candidate if candidate.exists() else src,target)
    shutil.copy2(FOLDER/'candidate/src/scanbench/sampling_density.py',runtime/'src/scanbench/sampling_density.py')
    for name in ['migrate_sampling_density_defaults.py','snapshot_sampling_density_v2.py','test_sampling_density_candidate.py']:
        target=runtime/'scripts'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN/'scripts'/name,target)
    for name in ['physical_scan_v1.yaml','quality_gates.yaml']:
        target=runtime/'configs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN/'configs'/name,target)
    policy=load_json(FOLDER/'candidate/configs/sampling_density_v2.json');policy['status']='frozen';atomic_json(runtime/'configs/sampling_density_v2.json',policy)
    atomic_json(revision/'freeze_before.json',frozen)
    sid='218';cid='case_2438b1a3fd780c63';state=State();selected=[]
    for row in state.db.execute('SELECT * FROM stages'):
        if row[0]==sid or row[0].startswith(sid+'/') or row[0]==cid:selected.append(row)
    paths=set()
    for row in selected:
        if row[3]=='complete':paths.update(json.loads(row[4]))
    for folder in [f'private/gt/{sid}',f'private/scan_index/{sid}',f'private/reference/{sid}',f'cache/clean/{sid}']:
        paths.update(p.relative_to(MAIN).as_posix() for p in (MAIN/folder).rglob('*') if p.is_file())
    paths.add(f'sources/{sid}/input.step')
    paths.update(p.relative_to(MAIN).as_posix() for p in (MAIN/f'data/cases/{cid}/input').iterdir() if p.is_file())
    paths.update(p.relative_to(MAIN).as_posix() for p in (MAIN/f'private/annotations/{cid}').rglob('*') if p.is_file())
    for count,name in enumerate(sorted(paths),1):
        target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN/name,target)
        if count%500==0:print(json.dumps({'fixture_copied_files':count}),flush=True)
    destination=sqlite3.connect(runtime/'state/state.sqlite') if (runtime/'state').exists() else None
    if destination is None:(runtime/'state').mkdir();destination=sqlite3.connect(runtime/'state/state.sqlite')
    state.db.backup(destination);destination.close()
    shutil.copy2(runtime/'state/state.sqlite',revision/'state_before.sqlite')
    archive_specs={
        'annotations':[n for n in paths if n.startswith('private/annotations/')],
        'reference_metadata':[n for n in paths if n.startswith('private/reference/') and n.endswith('.json')],
    };archives={}
    for kind,names in archive_specs.items():
        target=revision/(kind+'_before.zip');inventory={}
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name in sorted(names):
                path=runtime/name;z.write(path,name);st=path.stat();inventory[name]={'sha256':file_hash(path),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
        archives[kind]={'path':target.relative_to(runtime).as_posix(),'sha256':file_hash(target),'files':inventory}
    atomic_json(revision/'metadata_archives.json',archives)
    inventory={}
    for name in sorted(paths):
        if name.startswith('private/annotations/'):continue
        p=runtime/name;st=p.stat();inventory[name]={'sha256':file_hash(p),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
    atomic_json(revision/'inventory_before.json',{'files':inventory})
    baseline={'status':'isolated_test_baseline_not_formal_acceptance','eligible_sources':[sid],'affected_sources':[],'unaffected_accepted_cases':[cid],'inventory_before_sha256':file_hash(revision/'inventory_before.json'),'metadata_archives_sha256':file_hash(revision/'metadata_archives.json'),'state_database_sha256':file_hash(revision/'state_before.sqlite'),'freeze_before_sha256':file_hash(revision/'freeze_before.json')}
    atomic_json(revision/'baseline.json',baseline)
    installation={'active_code_sha256':{p.relative_to(runtime).as_posix():file_hash(p) for p in (runtime/'src/scanbench').glob('*.py')}}
    atomic_json(revision/'installation.json',installation)
    prepared={'runtime':runtime.relative_to(MAIN).as_posix(),'copied_files':len(paths),'copied_bytes':sum((runtime/name).stat().st_size for name in paths),'migration_script_sha256':file_hash(MAIN/'scripts/migrate_sampling_density_defaults.py'),'candidate_manifest_sha256':file_hash(FOLDER/'candidate_manifest.json'),'baseline_sha256':file_hash(revision/'baseline.json'),'original_formal_inputs_untouched':True,'time':time.time()}
    atomic_json(runtime/'prepared.json',prepared)
    return runtime


def worker(runtime):
    os.chdir(runtime);sys.path[:0]=[str(runtime/'src'),str(runtime/'scripts')]
    from scanbench.common import State,load_json,atomic_json,file_hash,digest
    from migrate_sampling_density_defaults import HistoricalInputs,numerical_compatibility,previous_validation_module,source_migration,case_migration
    from scanbench.validate import validate_case
    from scanbench.cases import generate_case
    from scanbench.supplemental import audit_case
    folder=runtime/'reports/protocol_amendments/r5_sampling_density'
    state=State();history=HistoricalInputs();ast_rows=numerical_compatibility();previous=previous_validation_module(history)
    sid='218';cid='case_2438b1a3fd780c63'
    source=source_migration(sid,state,history)
    case=case_migration(cid,state,history,previous)
    assert source['status']=='pass_unchanged_physical_payloads_adopted' and case['physical_result_exactly_equal']
    # Resume the actual normal case API after migration. It must use the adopted
    # input, Mesh and validation stages, preserving every original file timestamp.
    assert generate_case(sid,'hard',20261014,state)==cid
    assert validate_case(cid,state)['validation_hash']==case['current_validation_hash']
    assert audit_case(cid)['status']=='pass'
    before=file_hash(folder/f'default_cases/{cid}.json')
    source_migration(sid,state,history);case_migration(cid,state,history,previous)
    assert file_hash(folder/f'default_cases/{cid}.json')==before
    for name in history.inventory:
        if name.endswith('/reference.json'):continue
        history.unchanged(name)
    # Corrupt a copied input and prove the migration refuses it; restore bytes
    # and original timestamp before writing the final fixture evidence.
    target=runtime/f'data/cases/{cid}/input/points_for_meshing.ply';st=target.stat();original=target.read_bytes();damaged=bytearray(original);damaged[-1]^=1;target.write_bytes(damaged)
    rejected=False
    try:case_migration(cid,state,history,previous)
    except AssertionError:rejected=True
    finally:target.write_bytes(original);os.utime(target,ns=(st.st_atime_ns,st.st_mtime_ns))
    assert rejected,'Copied payload corruption incorrectly adopted'
    result={'status':'pass','scope':'isolated copied source 218 full acquisition and one hard case; formal production untouched','source_frames_adopted':len(source['frames']),'actual_original_files_preserved':len(history.inventory)-1,'physical_check_reexecuted_and_exactly_equal':True,'normal_generation_validation_and_supplemental_resumed_from_adopted_stages':True,'repeated_migration_receipt_unchanged':True,'corrupted_actual_input_rejected':rejected,'numerical_AST_compatibility':ast_rows,'case_proof_sha256':file_hash(folder/f'default_cases/{cid}.json'),'source_proof_sha256':file_hash(folder/f'default_sources/{sid}.json'),'time':time.time()}
    atomic_json(runtime/'result.json',result);print(json.dumps(result),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--runtime');parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    if args.worker:worker(Path(args.worker));return
    runtime=MAIN/args.runtime if args.runtime else prepare()
    if args.prepare_only:print(json.dumps({'status':'prepared','runtime':str(runtime.relative_to(MAIN))}),flush=True);return
    import psutil
    if psutil.virtual_memory().available<3*2**30:
        print(json.dumps({'status':'deferred_for_memory','runtime':str(runtime.relative_to(MAIN))}),flush=True);return
    started=time.time();log=runtime/'worker.log'
    command=[sys.executable,str(Path(__file__)),'--worker',str(runtime)]
    env=os.environ.copy()
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:env[name]='2'
    with log.open('w',encoding='utf-8') as stream:
        child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));peak=0
        while child.poll() is None:
            try:peak=max(peak,sum(p.memory_info().rss for p in [psutil.Process(child.pid),*psutil.Process(child.pid).children(recursive=True)]))
            except psutil.Error:pass
            time.sleep(.2)
    if child.returncode:print(log.read_text(encoding='utf-8')[-7000:]);raise SystemExit(child.returncode)
    sys.path.insert(0,str(MAIN/'src'))
    from scanbench.common import load_json,atomic_json,file_hash
    result=load_json(runtime/'result.json');result.update(runtime=runtime.relative_to(MAIN).as_posix(),prepared_sha256=file_hash(runtime/'prepared.json'),worker_log_sha256=file_hash(log),script_sha256=file_hash(Path(__file__)),migration_script_sha256=file_hash(MAIN/'scripts/migrate_sampling_density_defaults.py'),peak_process_tree_rss_bytes=peak,seconds=time.time()-started)
    atomic_json(FOLDER/'migration_controls.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='numerical_AST_compatibility'}),flush=True)


if __name__=='__main__':main()
