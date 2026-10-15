"""One-time immutable pre-install snapshot for the source-scoped density revision."""
from pathlib import Path
import os,sys,argparse,sqlite3,shutil,zipfile
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
from scanbench.cases import case_id

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'


def active_source_workers():
    found=[]
    for process in psutil.process_iter(['pid','name','cmdline','cwd']):
        try:
            if process.info['name'].lower()!='python.exe':continue
            arguments=process.info['cmdline'] or []
            working=process.info.get('cwd')
            if not working or Path(working).resolve()!=ROOT.resolve():continue
            if any(Path(arg).name in ['run_full.py','continue_unaffected_sources.py','run_r4_completion_pipeline.py'] for arg in arguments):
                found.append({'pid':process.pid,'command':arguments})
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return found


def preserve_file(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():assert file_hash(source)==file_hash(destination),f'Existing immutable snapshot differs: {destination}'
    else:shutil.copy2(source,destination)


def archive_metadata(name,paths):
    archive=FOLDER/name;inventory={}
    for path in sorted(paths):
        relative=path.relative_to(ROOT).as_posix();st=path.stat()
        inventory[relative]={'sha256':file_hash(path),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert set(z.namelist())==set(inventory)
            for path,entry in inventory.items():assert __import__('hashlib').sha256(z.read(path)).hexdigest()==entry['sha256']
    else:
        temporary=archive.with_name(archive.name+'.partial')
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for path in inventory:z.write(ROOT/path,path)
        os.replace(temporary,archive)
    return {'path':archive.relative_to(ROOT).as_posix(),'sha256':file_hash(archive),'files':inventory}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    active=active_source_workers()
    if args.check_only:
        print(canonical_json({'safe_to_snapshot':not active,'active_source_workers':active}));return
    assert not active,'Finish active source workers before any protocol installation or migration'
    assert not (FOLDER/'baseline.json').exists(),'R5 baseline is immutable and already exists; continue the recorded next phase instead of resealing'
    manifest=load_json(FOLDER/'candidate_manifest.json');controls=load_json(FOLDER/'candidate_controls.json');runtime=load_json(FOLDER/'runtime_controls.json')
    migration=load_json(FOLDER/'migration_controls.json')
    refined=load_json(FOLDER/'refined_preparation_controls.json')
    refresh=load_json(FOLDER/'freeze_guard_control_refresh.json')
    assert refresh['status']=='pass' and refresh['candidate_manifest_sha256']==file_hash(FOLDER/'candidate_manifest.json')
    for item in refresh['controls']:assert file_hash(FOLDER/(item['name']+'.json'))==item['report_sha256']
    assert all(item['status']=='pass' for item in [controls,runtime,migration,refined])
    assert migration['migration_script_sha256']==file_hash(ROOT/'scripts/migrate_sampling_density_defaults.py')
    assert refined['preparation_script_sha256']==file_hash(ROOT/'scripts/prepare_refined_sampling_source.py')
    assert controls['candidate_manifest_sha256']==file_hash(FOLDER/'candidate_manifest.json')
    policy=load_json(FOLDER/'candidate/configs/sampling_density_v2.json');overrides=set(policy['source_intervals'])
    assert file_hash(FOLDER/'candidate/configs/sampling_density_v2.json')==manifest['policy_sha256']
    frozen=load_json(ROOT/'reports/protocol_freeze.json')
    for name,h in frozen['code_sha256'].items():assert file_hash(ROOT/name)==h,name
    state=State();sources={sid:json.loads(body) for sid,body in state.db.execute("SELECT id,body FROM records WHERE kind='sources'")}
    records={cid:json.loads(body) for cid,body in state.db.execute("SELECT id,body FROM records WHERE kind='cases'")}
    assert set(sources)==set(IDS),'Every source must have a formal disposition before the final density revision is installed'
    eligible={sid for sid,r in sources.items() if r['status'] in ['eligible_native','eligible_official_mesh_approx']}
    assert overrides<=eligible
    unaffected=[]
    for sid in sorted(eligible-overrides):
        for level in config()['difficulty']:
            for seed in config()['seeds']:
                cid=case_id(sid,level,seed);assert cid in records,cid
                acceptance=load_json(ROOT/f'private/annotations/{cid}/acceptance.json')
                row=state.db.execute("SELECT input_hash,status,outputs FROM stages WHERE subject=? AND stage='validation'",(cid,)).fetchone()
                assert acceptance['status']=='pass' and row and row[1]=='complete' and row[0]==acceptance['validation_hash'],cid
                for name,h in json.loads(row[2]).items():assert file_hash(ROOT/name)==h,(cid,name)
                assert load_json(ROOT/f'private/annotations/{cid}/supplemental.json')['status']=='pass'
                unaffected.append(cid)
    for sid in overrides:
        basis=policy['basis'][sid];assert file_hash(ROOT/basis['path'])==basis['sha256']
        trial=load_json(ROOT/basis['path']);choice=next(t for t in trial['trials'] if t['intervals']==policy['source_intervals'][sid])
        assert trial['minimum_tested_passing_intervals']==choice['intervals'] and choice['all_p10_pass']
    atomic_json(ROOT/'state/sampling_density_v2.json',{'status':'snapshot_running','phase':'immutable_pre_install_inventory','time':time.time()})
    preserve_file(ROOT/'reports/protocol_freeze.json',FOLDER/'freeze_before.json')
    for name in frozen['code_sha256']:preserve_file(ROOT/name,FOLDER/'code_before'/name)
    for name in ['scripts/final_audit.py','scripts/write_delivery.py','scripts/render_physical_plan.py','scripts/run_full.py','configs/physical_scan_v1.yaml','configs/quality_gates.yaml']:
        preserve_file(ROOT/name,FOLDER/'code_before'/name)
    for name in ['sources','cases','failures']:
        path=ROOT/f'manifests/{name}.jsonl'
        if path.exists():preserve_file(path,FOLDER/f'{name}_before.jsonl')
    db_path=FOLDER/'state_before.sqlite'
    tables={table:state.db.execute(f'SELECT * FROM {table} ORDER BY '+('subject,stage' if table=='stages' else 'kind,id')).fetchall() for table in ['stages','records']}
    if db_path.exists():
        old=sqlite3.connect(db_path)
        for table,rows in tables.items():assert old.execute(f'SELECT * FROM {table} ORDER BY '+('subject,stage' if table=='stages' else 'kind,id')).fetchall()==rows
        old.close()
    else:
        temporary=db_path.with_name(db_path.name+'.partial');backup=sqlite3.connect(temporary);state.db.backup(backup);backup.close();os.replace(temporary,db_path)
    archives={
        'annotations':archive_metadata('annotations_before.zip',[p for p in (ROOT/'private/annotations').rglob('*') if p.is_file()]),
        'reference_metadata':archive_metadata('reference_metadata_before.zip',[p for p in (ROOT/'private/reference').rglob('*.json')]),
        'source_reports':archive_metadata('source_reports_before.zip',[p for directory in ['reports/source_audits','reports/monotonicity','reports/visual_reviews'] for p in (ROOT/directory).rglob('*') if p.is_file()]),
    }
    atomic_json(FOLDER/'metadata_archives.json',archives)
    folders=['data','sources','private/gt','private/scan_index','private/reference','cache/clean'];files={};total=0;started=time.time()
    for folder in folders:
        for path in sorted((ROOT/folder).rglob('*')):
            if not path.is_file():continue
            st=path.stat();name=path.relative_to(ROOT).as_posix()
            files[name]={'sha256':file_hash(path),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns};total+=st.st_size
            if len(files)%1000==0:print(canonical_json({'snapshot_files':len(files),'bytes_hashed':total,'seconds':time.time()-started}),flush=True)
    atomic_json(FOLDER/'inventory_before.json',{'files':files,'total_bytes':total,'time':time.time(),'scope':folders})
    baseline={'status':'immutable_snapshot_complete','source_dispositions':sources,'eligible_sources':sorted(eligible),'affected_sources':sorted(overrides),'unaffected_accepted_cases':sorted(unaffected),'all_existing_case_ids':sorted(records),'base_frozen_code_sha256':frozen['code_sha256'],'freeze_before_sha256':file_hash(FOLDER/'freeze_before.json'),'state_database_sha256':file_hash(db_path),'database_tables_digest':digest(tables),'metadata_archives_sha256':file_hash(FOLDER/'metadata_archives.json'),'inventory_before_sha256':file_hash(FOLDER/'inventory_before.json'),'candidate_manifest_sha256':file_hash(FOLDER/'candidate_manifest.json'),'candidate_controls_sha256':file_hash(FOLDER/'candidate_controls.json'),'runtime_controls_sha256':file_hash(FOLDER/'runtime_controls.json'),'migration_controls_sha256':file_hash(FOLDER/'migration_controls.json'),'script_sha256':file_hash(Path(__file__)),'file_count':len(files),'total_bytes':total,'time':time.time()}
    atomic_json(FOLDER/'baseline.json',baseline)
    atomic_json(ROOT/'state/sampling_density_v2.json',{'status':'snapshot_complete_requires_installation','baseline_sha256':file_hash(FOLDER/'baseline.json'),'next':'Install only the tested staged files, then perform explicit unchanged-stage migration and refined-source observation mapping before the new freeze','time':time.time()})
    print(canonical_json({k:v for k,v in baseline.items() if k not in ['source_dispositions','base_frozen_code_sha256','unaffected_accepted_cases','all_existing_case_ids']}),flush=True)


if __name__=='__main__':main()
