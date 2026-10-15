"""Read-only audit of physical sampling v2 and exact historical adoption evidence."""
from pathlib import Path
import os,sys,argparse,hashlib,sqlite3,zipfile
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
from scanbench.common import *
from migrate_sampling_density_defaults import HistoricalInputs,numerical_compatibility
from scanbench.sampling_density import sampling_policy,source_scan_settings,verify_case_sampling_contract,noise_frame_key
from scanbench.cases import case_id,mesh_stage_key
from scanbench.validate import physical_case_check,validation_fingerprint

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'
_history=None


def history():
    global _history
    if _history is None:_history=HistoricalInputs()
    return _history


def archived_metadata_verified(name,expected_hash,mtime_ns=None):
    """Resolve only explicitly superseded metadata to its actual archived bytes.

An unchanged old amendment stays immutable. This resolver never treats a changed
Mesh, observation payload or source as equivalent to its previous version.
"""
    if not (FOLDER/'baseline.json').exists():return False
    allowed=name.startswith('private/annotations/') or (name.startswith('private/reference/') and name.endswith('.json'))
    if not allowed:return False
    if name.startswith('private/annotations/'):
        cid=Path(name).parts[2]
        adopted=(FOLDER/f'default_cases/{cid}.json').exists()
        superseded=any((FOLDER/f'affected_sources/{sid}/prepared.json').exists() and cid in [item['case_id'] for item in load_json(FOLDER/f'affected_sources/{sid}/prepared.json')['superseded_failed_cases']] for sid in history().baseline['affected_sources'])
        if not (adopted or superseded):return False
    try:
        found=[item for item in history().archives.values() if name in item['files']]
        if len(found)!=1:return False
        entry=found[0]['files'][name]
        if entry['sha256']!=expected_hash or (mtime_ns is not None and entry['mtime_ns']!=mtime_ns):return False
        return hashlib.sha256(history().archive_bytes(name)).hexdigest()==expected_hash
    except (AssertionError,KeyError,OSError,zipfile.BadZipFile):return False


def evidence_file_verified(name,expected_hash):
    path=ROOT/name
    if path.is_file() and file_hash(path)==expected_hash:return True
    return archived_metadata_verified(name,expected_hash)


def audit_actual_control_artifacts(name,proof):
    if name=='candidate_controls':
        assert proof['candidate_manifest_sha256']==file_hash(FOLDER/'candidate_manifest.json')
        assert proof['script_sha256']==file_hash(ROOT/'scripts/test_sampling_density_candidate.py')
        return
    runtime=(ROOT/proof['runtime']).resolve()
    assert runtime.is_relative_to((FOLDER/'controls').resolve())
    assert file_hash(runtime/'prepared.json')==proof['prepared_sha256']
    assert file_hash(runtime/'worker.log')==proof['worker_log_sha256']
    script={'runtime_controls':'test_sampling_density_runtime.py','migration_controls':'test_sampling_density_migration.py','refined_preparation_controls':'test_refined_sampling_preparation.py'}[name]
    assert file_hash(ROOT/'scripts'/script)==proof['script_sha256']
    raw_path=runtime/('runtime_result.json' if name=='runtime_controls' else 'result.json')
    raw=load_json(raw_path);assert raw['status']=='pass' and all(proof[k]==v for k,v in raw.items())
    prepared=load_json(runtime/'prepared.json')
    for module in (runtime/'src/scanbench').glob('*.py'):assert file_hash(module)==file_hash(ROOT/'src/scanbench'/module.name),(name,module.name)
    if name=='runtime_controls':
        for path,expected in prepared['runtime_files_sha256'].items():assert file_hash(runtime/path)==expected,(name,path)
        for path,expected in prepared['original_inputs_sha256'].items():assert evidence_file_verified(path,expected),(name,path)
    else:
        revision=runtime/'reports/protocol_amendments/r5_sampling_density'
        local_baseline=load_json(revision/'baseline.json')
        assert file_hash(revision/'baseline.json')==prepared.get('baseline_sha256',file_hash(revision/'baseline.json'))
        assert file_hash(revision/'inventory_before.json')==local_baseline['inventory_before_sha256']
        assert file_hash(revision/'metadata_archives.json')==local_baseline['metadata_archives_sha256']
        assert file_hash(revision/'state_before.sqlite')==local_baseline['state_database_sha256']
        for path,entry in load_json(revision/'inventory_before.json')['files'].items():
            target=runtime/path
            if name=='migration_controls' and path=='private/reference/218/reference.json':
                item=load_json(target);assert item['sampling_revision']['evaluation_unchanged'];continue
            if not target.exists() or file_hash(target)!=entry['sha256']:
                target=revision/'affected_sources/245/archive'/path
            assert target.is_file() and file_hash(target)==entry['sha256'] and target.stat().st_mtime_ns==entry['mtime_ns'],(name,path)
        if name=='migration_controls':
            assert file_hash(revision/'default_cases/case_2438b1a3fd780c63.json')==proof['case_proof_sha256']
            assert file_hash(revision/'default_sources/218.json')==proof['source_proof_sha256']
        else:
            assert file_hash(revision/'affected_sources/245/prepared.json')==proof['prepared_source_receipt_sha256']
            assert file_hash(revision/'affected_sources/245/archive_inventory.json')==proof['archive_inventory_sha256']
            assert file_hash(runtime/'scripts/prepare_refined_sampling_source.py')==proof['preparation_script_sha256']
            if proof.get('runtime_script_updates_sha256'):assert file_hash(runtime/'script_updates.json')==proof['runtime_script_updates_sha256']


def audit(before_freeze=False):
    started=time.time();h=history();baseline=h.baseline;state=State();policy=sampling_policy()
    installed=load_json(FOLDER/'installation.json');migration=load_json(FOLDER/'default_migration.json')
    assert migration['status']=='pass_all_unchanged_sources_migrated'
    assert migration['baseline_sha256']==file_hash(FOLDER/'baseline.json') and migration['installation_sha256']==file_hash(FOLDER/'installation.json')
    assert installed['active_policy_sha256']==file_hash(ROOT/'configs/sampling_density_v2.json')
    for name,value in installed['active_code_sha256'].items():assert file_hash(ROOT/name)==value,name
    compatibility=numerical_compatibility()
    controls={}
    for name in ['candidate_controls','runtime_controls','migration_controls','refined_preparation_controls']:
        path=FOLDER/(name+'.json');proof=load_json(path);assert proof['status']=='pass',name
        audit_actual_control_artifacts(name,proof)
        controls[path.relative_to(ROOT).as_posix()]=file_hash(path)
    assert load_json(FOLDER/'migration_controls.json')['migration_script_sha256']==file_hash(ROOT/'scripts/migrate_sampling_density_defaults.py')
    assert load_json(FOLDER/'refined_preparation_controls.json')['preparation_script_sha256']==file_hash(ROOT/'scripts/prepare_refined_sampling_source.py')
    refresh=load_json(FOLDER/'freeze_guard_control_refresh.json')
    assert refresh['status']=='pass' and refresh['candidate_manifest_sha256']==file_hash(FOLDER/'candidate_manifest.json')
    for item in refresh['controls']:assert file_hash(FOLDER/(item['name']+'.json'))==item['report_sha256']
    comparison_fix=load_json(FOLDER/'diagnostic_comparison_fix.json')
    assert comparison_fix['status']=='fixed_and_actual_recovery_test_passed' and comparison_fix['exact_camera_records']==2307
    comparison_proof=ROOT/comparison_fix.get('passing_control_report','reports/protocol_amendments/r5_sampling_density/refined_preparation_controls.json')
    assert comparison_fix['passing_control_sha256']==file_hash(comparison_proof) and load_json(comparison_proof)['status']=='pass'
    for name,expected in comparison_fix['old_failure_logs'].items():assert file_hash(ROOT/name)==expected
    sources=baseline['eligible_sources'];affected=set(baseline['affected_sources']);unaffected=sorted(set(sources)-affected)
    assert set(migration['source_ids'])==set(unaffected)
    assert set(migration['case_ids'])==set(baseline['unaffected_accepted_cases'])
    preserved=0;archive_checked=0;payload_bytes=0;metadata=0
    # Independently resolve every original geometry/acquisition/cache artifact.
    # The only replaced original public case belongs to an evidenced failed
    # affected source. Its original files must all exist in the bounded archive.
    for count,(name,entry) in enumerate(h.inventory.items(),1):
        parts=Path(name).parts;affected_source=None
        if name.startswith(('private/gt/','private/scan_index/','private/reference/','cache/clean/')):
            affected_source=parts[2]
        elif name.startswith('data/cases/'):
            record=h.old_json(f'private/annotations/{parts[2]}/case.json');affected_source=record['source_id']
        replacement=False
        if affected_source in affected:
            replacement=name.startswith(('private/scan_index/','private/reference/','cache/clean/','data/cases/')) or (name.startswith('private/gt/') and Path(name).name in ['cameras.json','feature_contract.json'])
        if replacement:
            path=FOLDER/f'affected_sources/{affected_source}/archive'/name
            assert path.is_file() and h.actual_hash(path)==entry['sha256'] and path.stat().st_mtime_ns==entry['mtime_ns'],('affected original archive mismatch',name)
            archive_checked+=1
        elif name.startswith('private/reference/') and name.endswith('/reference.json'):
            assert archived_metadata_verified(name,entry['sha256'],entry['mtime_ns']),name
            metadata+=1
        else:
            h.unchanged(name);preserved+=1;payload_bytes+=entry['bytes']
        if count%2000==0:print(canonical_json({'sampling_independent_inventory_files':count,'seconds':time.time()-started}),flush=True)
    frames_adopted=0;cases=[];source_summaries=[]
    for sid in unaffected:
        proof_path=FOLDER/f'default_sources/{sid}.json';source=load_json(proof_path)
        assert file_hash(proof_path)==migration['sources'][sid]
        assert source['status']=='pass_unchanged_physical_payloads_adopted' and source['actual_intervals']==192
        assert source['exact_regenerated_camera_bytes'] and source['exact_regenerated_feature_contract_bytes']
        gt=ROOT/f'private/gt/{sid}';settings=source_scan_settings(sid);mesh_hash=h.actual_hash(gt/'mesh.npz')
        trajectory=stage_hash([h.actual_hash(gt/name) for name in ['mesh.npz','placements.json','features.json']],settings,['camera.py','scan.py','sampling_density.py'],['numpy','open3d'])
        assert state.valid(sid,'trajectory',trajectory) and trajectory==source['trajectory']['current_key']
        mapping={item['camera_id']:item for item in source['frames']}
        cameras=load_json(gt/'cameras.json')['cameras'];assert set(mapping)=={c['id'] for c in cameras}
        for cam in cameras:
            item=mapping[cam['id']];old=h.old_row(f'{sid}/{cam["id"]}','observations')
            assert item['old_key']==old[2] and item['old_stage_digest']==digest(old)
            assert old[2]==h.stage_hash([mesh_hash,cam],settings,['scan.py','camera.py'],['numpy','open3d'])
            key=stage_hash([mesh_hash,cam],settings,['scan.py','camera.py','sampling_density.py'],['numpy','open3d'])
            assert key==item['current_key'] and state.valid(f'{sid}/{cam["id"]}','observations',key)
            index=load_json(ROOT/f'private/scan_index/{sid}/{cam["id"]}.json');assert index['frame_hash']==old[2]
            assert noise_frame_key(cam,settings)==cam['mother_frame_id']
        frames_adopted+=len(cameras)
        reference=load_json(ROOT/f'private/reference/{sid}/reference.json');old_reference=h.old_json(f'private/reference/{sid}/reference.json')
        assert {k:v for k,v in reference.items() if k not in ['key','sampling_revision']}=={k:v for k,v in old_reference.items() if k!='key'}
        assert reference['key']==source['reference_current_key'] and h.actual_hash(ROOT/f'private/reference/{sid}/evaluation.npz')==source['evaluation_sha256']
        source_summaries.append({'source_id':sid,'mother_intervals':192,'mother_frames_per_placement':193,'original_frames_adopted':len(cameras),'observations_and_meshes_regenerated':False})
    gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text())
    for cid in baseline['unaffected_accepted_cases']:
        proof_path=FOLDER/f'default_cases/{cid}.json';case=load_json(proof_path)
        assert file_hash(proof_path)==migration['cases'][cid]
        record=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/record['input_path']
        contract=verify_case_sampling_contract(record,out);assert contract['mother_intervals']==192
        old=h.old_json(f'private/annotations/{cid}/acceptance.json');current=load_json(ROOT/f'private/annotations/{cid}/acceptance.json')
        assert {k:v for k,v in current.items() if k not in ['validation_hash','sampling_revision']}=={k:v for k,v in old.items() if k!='validation_hash'}
        assert current['status']=='pass' and physical_case_check(record,out)==old['physical_scan']
        key=validation_fingerprint(out,record,gates)
        assert key==case['current_validation_hash']==current['validation_hash'] and state.valid(cid,'validation',key)
        assert mesh_stage_key(out,config()['reconstruction'])==case['mesh_stage_hash_unchanged'] and state.valid(cid,'mesh',case['mesh_stage_hash_unchanged'])
        assert file_hash(ROOT/f'private/annotations/{cid}/acceptance.json')==case['current_acceptance_sha256']
        assert file_hash(ROOT/f'private/annotations/{cid}/supplemental.json')==case['current_supplemental_sha256']
        old_extra=h.old_json(f'private/annotations/{cid}/supplemental.json');extra=load_json(ROOT/f'private/annotations/{cid}/supplemental.json')
        assert {k:v for k,v in extra.items() if k not in ['input_hash','sampling_revision']}=={k:v for k,v in old_extra.items() if k!='input_hash'}
        cases.append({'case_id':cid,'physical_check_reexecuted_exact':True,'original_numerical_results_and_actual_mesh_unchanged':True})
    refined=[]
    for sid in sorted(affected):
        folder=FOLDER/f'affected_sources/{sid}';proof=load_json(folder/'prepared.json')
        assert proof['status']=='ready_for_frozen_dense_acquisition' and proof['original_source_geometry_unchanged']
        assert file_hash(ROOT/f'private/gt/{sid}/cameras.json')==proof['dense_cameras_sha256']
        assert file_hash(folder/'archive_inventory.json')==proof['archive_inventory_sha256']
        archive_inventory=load_json(folder/'archive_inventory.json')
        for name,entry in archive_inventory.items():
            path=folder/'archive'/name;assert h.actual_hash(path)==entry['sha256'] and path.stat().st_mtime_ns==entry['mtime_ns'],name
        old=load_json(folder/f'archive/private/gt/{sid}/cameras.json')['cameras'];new=load_json(ROOT/f'private/gt/{sid}/cameras.json')['cameras']
        newmap={c['id']:c for c in new};oldmap={c['id']:c for c in old};factor=proof['refinement_factor'];settings=source_scan_settings(sid)
        assert len(old)==proof['original_cameras'] and len(new)==proof['dense_cameras']
        for item in proof['old_to_new_camera_mapping']:
            a=oldmap[item['old_camera_id']];b=newmap[item['new_camera_id']]
            assert b['mother_frame_id']==factor*a['mother_frame_id'] and b['placement_id']==a['placement_id']
            for name in ['K','T_object_from_camera','T_table_from_camera','near_mm','far_mm','resolution']:np.testing.assert_array_equal(a[name],b[name])
            assert noise_frame_key(b,settings)==a['mother_frame_id']
            for seed,entry in item['seeds'].items():
                h.unchanged('data/'+entry['observation'])
                if not before_freeze:
                    actual=load_json(ROOT/f'private/scan_index/{sid}/{b["id"]}.json')['seeds'][seed]
                    assert actual==entry,('old noisy payload not reused at the same physical position',sid,a['id'],seed)
        for item in proof['translated_complete_clean_frames']:
            target=ROOT/f'cache/clean/{sid}/{item["new_camera_id"]}.npz'
            assert h.actual_hash(target)==item['clean_sha256']
        if not before_freeze:
            for camera in new:
                key=stage_hash([h.actual_hash(ROOT/f'private/gt/{sid}/mesh.npz'),camera],settings,['scan.py','camera.py','sampling_density.py'],['numpy','open3d'])
                assert state.valid(f'{sid}/{camera["id"]}','observations',key)
            for level in config()['difficulty']:
                for seed in config()['seeds']:
                    cid=case_id(sid,level,seed);record=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/record['input_path']
                    contract=verify_case_sampling_contract(record,out);assert contract['mother_intervals']==settings['intervals']
                    result=load_json(ROOT/f'private/annotations/{cid}/acceptance.json')
                    assert result['status']=='pass' and result['quality']['adjacent_overlap']['p10']>=.5
                    assert physical_case_check(record,out)==result['physical_scan']
                    assert state.valid(cid,'validation',validation_fingerprint(out,record,gates))
        refined.append({'source_id':sid,'mother_intervals':settings['intervals'],'old_mother_intervals':192,'old_physical_positions_and_noise_payloads_preserved':len(old),'translated_clean_frames':len(proof['translated_complete_clean_frames']),'new_observation_acquisition_complete':not before_freeze,'actual_cases_verified':0 if before_freeze else 6})
    result={'status':'pass','phase':'before_physical_version_freeze' if before_freeze else 'full_current_batch','baseline_sha256':file_hash(FOLDER/'baseline.json'),'installation_sha256':file_hash(FOLDER/'installation.json'),'default_migration_sha256':file_hash(FOLDER/'default_migration.json'),'policy_sha256':file_hash(ROOT/'configs/sampling_density_v2.json'),'physical_protocol':policy['protocol'],'unchanged_source_count':len(unaffected),'unchanged_case_count':len(cases),'old_frames_adopted_without_reacquisition':frames_adopted,'baseline_file_count':len(h.inventory),'original_files_hash_and_mtime_preserved':preserved,'original_affected_files_archived':archive_checked,'original_reference_metadata_archived':metadata,'preserved_payload_bytes':payload_bytes,'all_original_inventory_entries_resolved':preserved+archive_checked+metadata==len(h.inventory),'default_source_summaries':source_summaries,'refined_sources':refined,'control_reports_sha256':controls,'actual_control_inputs_outputs_logs_and_archives_reread':True,'numerical_AST_compatibility':compatibility,'base_config_and_quality_gates_unchanged':True,'script_sha256':file_hash(Path(__file__)),'seconds':time.time()-started,'time':time.time()}
    assert result['all_original_inventory_entries_resolved']
    target=FOLDER/('pre_freeze_independent_audit.json' if before_freeze else 'full_independent_audit.json')
    atomic_json(target,result);print(canonical_json({k:v for k,v in result.items() if k not in ['default_source_summaries','numerical_AST_compatibility']}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--before-freeze',action='store_true');args=parser.parse_args();audit(args.before_freeze)
