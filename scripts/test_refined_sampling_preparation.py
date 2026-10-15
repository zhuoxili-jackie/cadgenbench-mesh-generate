"""Real copied 245 archive/translation interruption and resume control."""
from pathlib import Path
import os,sys,shutil,sqlite3,zipfile,json,time,argparse,subprocess
MAIN=Path(__file__).resolve().parents[1]
FOLDER=MAIN/'reports/protocol_amendments/r5_sampling_density'


def prepare():
    sys.path.insert(0,str(MAIN/'src'))
    from scanbench.common import State,load_json,file_hash,atomic_json
    runtime=FOLDER/'controls'/f'refined_prepare_{time.time_ns()}';runtime.mkdir(parents=True)
    revision=runtime/'reports/protocol_amendments/r5_sampling_density';revision.mkdir(parents=True)
    frozen=load_json(MAIN/'reports/protocol_freeze.json')
    for name in frozen['code_sha256']:
        old=revision/'code_before'/name;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN/name,old)
        destination=runtime/name;destination.parent.mkdir(parents=True,exist_ok=True)
        candidate=FOLDER/'candidate'/name;shutil.copy2(candidate if candidate.exists() else MAIN/name,destination)
    shutil.copy2(FOLDER/'candidate/src/scanbench/sampling_density.py',runtime/'src/scanbench/sampling_density.py')
    for name in ['prepare_refined_sampling_source.py','migrate_sampling_density_defaults.py','snapshot_sampling_density_v2.py']:
        target=runtime/'scripts'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN/'scripts'/name,target)
    for name in ['physical_scan_v1.yaml','quality_gates.yaml']:
        target=runtime/'configs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN/'configs'/name,target)
    policy=load_json(FOLDER/'candidate/configs/sampling_density_v2.json');policy['status']='frozen';atomic_json(runtime/'configs/sampling_density_v2.json',policy)
    atomic_json(revision/'freeze_before.json',frozen)
    sid='245';cid='case_9a0e4b631d694e54';state=State();paths=set()
    for row in state.db.execute('SELECT * FROM stages'):
        if (row[0]==sid or row[0].startswith(sid+'/') or row[0]==cid) and row[3]=='complete':paths.update(json.loads(row[4]))
    for directory in [f'private/gt/{sid}',f'private/scan_index/{sid}',f'private/reference/{sid}',f'cache/clean/{sid}',f'data/cases/{cid}',f'private/annotations/{cid}',f'reports/density_investigations/{sid}']:
        paths.update(p.relative_to(MAIN).as_posix() for p in (MAIN/directory).rglob('*') if p.is_file())
    paths.add(f'sources/{sid}/input.step')
    for name in [f'reports/private_previews/{cid}.png',f'reports/private_previews/{cid}.json']:
        if (MAIN/name).exists():paths.add(name)
    for count,name in enumerate(sorted(paths),1):
        target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN/name,target)
        if count%500==0:print(json.dumps({'refined_fixture_copied_files':count}),flush=True)
    (runtime/'state').mkdir(exist_ok=True);destination=sqlite3.connect(runtime/'state/state.sqlite');state.db.backup(destination);destination.close()
    shutil.copy2(runtime/'state/state.sqlite',revision/'state_before.sqlite')
    archives={}
    for kind,names in {'annotations':[n for n in paths if n.startswith('private/annotations/')],'reference_metadata':[n for n in paths if n.startswith('private/reference/') and n.endswith('.json')]}.items():
        archive=revision/(kind+'_before.zip');inventory={}
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name in sorted(names):
                p=runtime/name;z.write(p,name);st=p.stat();inventory[name]={'sha256':file_hash(p),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
        archives[kind]={'path':archive.relative_to(runtime).as_posix(),'sha256':file_hash(archive),'files':inventory}
    atomic_json(revision/'metadata_archives.json',archives)
    inventory={}
    for name in sorted(paths):
        if name.startswith('private/annotations/'):continue
        p=runtime/name;st=p.stat();inventory[name]={'sha256':file_hash(p),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
    atomic_json(revision/'inventory_before.json',{'files':inventory})
    baseline={'status':'isolated_test_baseline_not_formal_acceptance','eligible_sources':[sid],'affected_sources':[sid],'all_existing_case_ids':[cid],'unaffected_accepted_cases':[],'inventory_before_sha256':file_hash(revision/'inventory_before.json'),'metadata_archives_sha256':file_hash(revision/'metadata_archives.json'),'state_database_sha256':file_hash(revision/'state_before.sqlite'),'freeze_before_sha256':file_hash(revision/'freeze_before.json')}
    atomic_json(revision/'baseline.json',baseline)
    atomic_json(revision/'installation.json',{'active_code_sha256':{p.relative_to(runtime).as_posix():file_hash(p) for p in (runtime/'src/scanbench').glob('*.py')}})
    atomic_json(runtime/'prepared.json',{'scope':'copied 245 inputs only; no formal data modified','runtime':runtime.relative_to(MAIN).as_posix(),'copied_files':len(paths),'copied_bytes':sum((runtime/n).stat().st_size for n in paths),'preparation_script_sha256':file_hash(MAIN/'scripts/prepare_refined_sampling_source.py'),'snapshot_script_sha256':file_hash(MAIN/'scripts/snapshot_sampling_density_v2.py'),'time':time.time()})
    return runtime


def worker(runtime):
    os.chdir(runtime);sys.path[:0]=[str(runtime/'src'),str(runtime/'scripts')]
    from scanbench.common import State,load_json,file_hash,atomic_json
    from migrate_sampling_density_defaults import HistoricalInputs
    import prepare_refined_sampling_source as preparation
    sys.argv=[str(runtime/'scripts/prepare_refined_sampling_source.py'),'245']
    # Stop after real archival and ledger invalidation, then run the actual
    # preparation entry point again. This exercises the partial-state branch.
    original=preparation.prepare_cameras
    def interrupt(*args,**kwargs):raise RuntimeError('intentional copied-runtime stop after archive before trajectory')
    preparation.prepare_cameras=interrupt
    try:preparation.main()
    except RuntimeError as exc:assert 'intentional copied-runtime stop' in str(exc)
    else:raise AssertionError('planned interruption was not reached')
    preparation.prepare_cameras=original
    preparation.main()
    folder=runtime/'reports/protocol_amendments/r5_sampling_density/affected_sources/245'
    proof=load_json(folder/'prepared.json');assert proof['original_cameras']==579 and proof['dense_cameras']==2307
    assert len(proof['translated_complete_clean_frames'])==147
    state=State();history=HistoricalInputs()
    for name in proof['old_observation_payloads']:history.unchanged(name)
    for entry in proof['translated_complete_clean_frames']:
        subject='245/'+entry['new_camera_id'];assert state.valid(subject,'observations',entry['new_frame_key'])
        target=runtime/f'cache/clean/245/{entry["new_camera_id"]}.npz'
        old=folder/f'archive/cache/clean/245/{entry["old_camera_id"]}.npz'
        assert file_hash(target)==file_hash(old)==entry['clean_sha256'] and target.stat().st_mtime_ns==old.stat().st_mtime_ns
    assert state.db.execute("SELECT COUNT(*) FROM stages WHERE subject LIKE '245/%' AND stage='observations'").fetchone()[0]==147
    for case in proof['superseded_failed_cases']:
        assert not (runtime/f'data/cases/{case["case_id"]}').exists()
        assert (folder/f'archive/data/cases/{case["case_id"]}/input/mesh.ply').is_file()
    receipt_sha=file_hash(folder/'prepared.json');preparation.main();assert file_hash(folder/'prepared.json')==receipt_sha
    for name in ['mesh.npz','metadata.json','placements.json','features.json','placement_audit.json']:
        history.unchanged('private/gt/245/'+name)
    result={'status':'pass','scope':'actual archive/translation and entry-point interruption/resume on copied source 245; no formal data changed','original_cameras_preserved_in_archive':579,'new_cameras':2307,'old_camera_matrices_and_integer_noise_keys_exact':True,'translated_clean_frames':147,'old_payload_files_preserved':len(proof['old_observation_payloads']),'interrupted_after_archive_then_resumed':True,'second_resume_no_receipt_changes':True,'original_source_geometry_and_stable_placements_unchanged':True,'prepared_source_receipt_sha256':receipt_sha,'archive_inventory_sha256':file_hash(folder/'archive_inventory.json'),'time':time.time()}
    atomic_json(runtime/'result.json',result);print(json.dumps(result),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--runtime');parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    if args.worker:worker(Path(args.worker));return
    runtime=MAIN/args.runtime if args.runtime else prepare()
    if args.runtime:
        assert runtime.resolve().is_relative_to((FOLDER/'controls').resolve())
        sys.path.insert(0,str(MAIN/'src'))
        from scanbench.common import load_json,atomic_json,file_hash
        updates_path=runtime/'script_updates.json';updates=load_json(updates_path) if updates_path.exists() else []
        name='scripts/prepare_refined_sampling_source.py';target=runtime/name
        if file_hash(target)!=file_hash(MAIN/name):
            archive=runtime/f'failed_script_attempts/{len(updates)+1}/prepare_refined_sampling_source.py';archive.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,archive)
            updates.append({'script':name,'before_sha256':file_hash(target),'after_sha256':file_hash(MAIN/name),'previous_script':archive.relative_to(runtime).as_posix(),'reason':'Compare complete production camera payload while keeping the independent trial-only labels explicit','time':time.time()})
            shutil.copy2(MAIN/name,target);atomic_json(updates_path,updates)
    if args.prepare_only:print(json.dumps({'status':'prepared','runtime':runtime.relative_to(MAIN).as_posix()}));return
    import psutil
    if psutil.virtual_memory().available<3*2**30:print(json.dumps({'status':'deferred_for_memory','runtime':runtime.relative_to(MAIN).as_posix()}));return
    started=time.time();log=runtime/'worker.log';env=os.environ.copy()
    if log.exists():
        previous=runtime/f'worker_attempt_{time.time_ns()}.log';log.replace(previous)
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:env[name]='2'
    with log.open('w',encoding='utf-8') as stream:
        child=subprocess.Popen([sys.executable,str(Path(__file__)),'--worker',str(runtime)],stdout=stream,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));peak=0
        while child.poll() is None:
            try:peak=max(peak,sum(p.memory_info().rss for p in [psutil.Process(child.pid),*psutil.Process(child.pid).children(recursive=True)]))
            except psutil.Error:pass
            time.sleep(.2)
    if child.returncode:print(log.read_text(encoding='utf-8')[-7000:]);raise SystemExit(child.returncode)
    sys.path.insert(0,str(MAIN/'src'))
    from scanbench.common import load_json,atomic_json,file_hash
    result=load_json(runtime/'result.json');result.update(runtime=runtime.relative_to(MAIN).as_posix(),prepared_sha256=file_hash(runtime/'prepared.json'),worker_log_sha256=file_hash(log),script_sha256=file_hash(Path(__file__)),preparation_script_sha256=file_hash(MAIN/'scripts/prepare_refined_sampling_source.py'),peak_process_tree_rss_bytes=peak,seconds=time.time()-started)
    if (runtime/'script_updates.json').exists():result['runtime_script_updates_sha256']=file_hash(runtime/'script_updates.json')
    atomic_json(FOLDER/'refined_preparation_controls.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
