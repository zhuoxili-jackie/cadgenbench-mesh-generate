"""Seal r4 only after its 18-case pilot, direct reviews and current-code tests pass."""
from pathlib import Path
import os,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
from scanbench.cases import case_id,mesh_stage_key
from scanbench.validate import validation_fingerprint
from scanbench.reporting import REQUIRED_TESTS
from audit_continuous_revision import audit_case

folder=ROOT/'reports/protocol_amendments/r4_continuous_free_space';before=load_json(folder/'freeze_before.json')
assert file_hash(ROOT/'reports/protocol_freeze.json')==file_hash(folder/'freeze_before.json'),'Preserve an already changed freeze; inspect before resealing'
assert digest(config())==before['protocol_config_sha256'] and file_hash(ROOT/'configs/quality_gates.yaml')==before['quality_gates_sha256']
installation=load_json(folder/'installation.json');assert installation['status']=='pass'
new={**installation['changed_modules_sha256'],**installation['added_modules_sha256']}
for name,h in {**before['code_sha256'],**new}.items():assert file_hash(ROOT/name)==h,name
controls_path=ROOT/'reports/free_space_revision/controls_candidate.json';controls=load_json(controls_path)
assert controls['status']=='pass' and controls['module_sha256']==file_hash(ROOT/'src/scanbench/continuous_free_space.py')
assert controls['test_script_sha256']==file_hash(ROOT/'scripts/test_continuous_free_space.py')
assert controls['actual_degenerate_pixel_cell_regressions']['independent_code_sha256']==file_hash(ROOT/'scripts/independent_cell_minimum.py')
assert controls['actual_degenerate_pixel_cell_regressions']['all_prior_false_conflicts_rejected'] and controls['random_convex_problems']==300
pilot_ids=[case_id(s,l,n) for s in ['218','231','229'] for n in config()['seeds'] for l in ['hard','medium','easy']]
pilot=load_json(folder/'pilot_migration.json');assert pilot['status']=='pass' and pilot['cases']==pilot_ids
gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text());state=State();pilot_cases=[]
evidence=[folder/x for x in ['freeze_before.json','code_before.zip','inventory_before.json','cases_before.jsonl','sources_before.jsonl','failures_before.jsonl','state_before.sqlite','installation.json','pilot_migration.json']]
evidence.extend(ROOT/p for p in ['reports/free_space_revision/controls_candidate.json','reports/free_space_revision/actual_frame_benchmark.npz','reports/free_space_revision/failing_case_trial.json','scripts/test_continuous_free_space.py','scripts/independent_cell_minimum.py','scripts/audit_continuous_revision.py','scripts/migrate_continuous_case.py','scripts/run_continuous_migration.py','scripts/record_continuous_installation.py','scripts/record_continuous_amendment.py'])
for sid in ['218','231','229']:
    review_path=ROOT/f'reports/visual_reviews/{sid}.json';review=load_json(review_path);assert review['status']=='pass'
    assert {x['level'] for x in review['cases']}=={'hard','easy'}
    for item in review['cases']:
        assert file_hash(ROOT/item['preview'])==item['preview_sha256'] and file_hash(ROOT/f'data/cases/{item["case_id"]}/input/mesh.ply')==item['mesh_sha256']
    evidence.append(review_path)
for cid in pilot_ids:
    rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path'];accept_path=ROOT/f'private/annotations/{cid}/acceptance.json';accept=load_json(accept_path)
    assert accept['status']=='pass' and accept['validation_hash']==validation_fingerprint(out,rec,gates)
    assert state.valid(cid,'mesh',mesh_stage_key(out,config()['reconstruction'])) and state.valid(cid,'validation',accept['validation_hash'])
    extra=load_json(ROOT/f'private/annotations/{cid}/supplemental.json');assert extra['status']=='pass' and extra['mesh_sha256']==file_hash(out/'mesh.ply')
    independent=audit_case(cid);assert independent['status']=='pass'
    migration=load_json(folder/f'cases/{cid}.json');assert migration['status']=='pass' and migration['new_mesh_sha256']==file_hash(out/'mesh.ply')
    pilot_cases.append({'case_id':cid,'source_id':rec['source_id'],'level':rec['level'],'seed':rec['seed'],'mesh_sha256':file_hash(out/'mesh.ply'),'acceptance_sha256':file_hash(accept_path),'removed_faces':migration['removed_faces'],'removed_area_fraction':migration['removed_area_fraction'],'observed_retention':accept['quality']['observation_mesh_retained_fraction'],'mesh_support':accept['quality']['mesh_observation_supported_fraction']})
    evidence.extend([folder/f'cases/{cid}.json',ROOT/f'reports/continuous_independent/{cid}.json',accept_path,ROOT/migration['scope_audit'],ROOT/migration['original_archive'],(ROOT/migration['original_archive']).with_suffix('.json')])
active_tests={name:f'reports/tests/{name}_r4.json' for name in ['no_gt_portable','full_case_reproduction','real_mesh_interruption','production_resume_and_dependencies','hole_contact_mesh']}
tests={}
for name in REQUIRED_TESTS:
    path=ROOT/active_tests.get(name,f'reports/tests/{name}.json');test=load_json(path);assert test.get('status')=='pass' or test.get('pass') is True,name
    tests[name]=file_hash(path);evidence.append(path)
for name in ['run_portability_r4.py','run_reproduction_r4.py','run_mesh_resume_r4.py','test_production_resume_r4.py']:evidence.append(ROOT/'scripts'/name)
evidence.append(ROOT/'tests/control_mesh_experiment_r4.py')
out=ROOT/f'data/cases/{pilot_ids[0]}/input';mh=file_hash(out/'mesh.ply');oh=file_hash(out/'observations.json');ch=digest([file_hash(ROOT/'src/scanbench/reconstruct.py'),file_hash(ROOT/'src/scanbench/continuous_free_space.py')])
for name,signature in [('no_gt_portable',digest([mh,ch,oh])),('full_case_reproduction',digest([mh,oh,ch])),('real_mesh_interruption',digest([mh,ch]))]:assert load_json(ROOT/active_tests[name])['signature']==signature
assert load_json(ROOT/active_tests['real_mesh_interruption'])['actual_owned_process_tree_killed']
assert load_json(ROOT/active_tests['production_resume_and_dependencies'])['all_qualified_hashes_and_mtimes_unchanged']
export_path=ROOT/'reports/operations/delivery_export_command_r4.json';export=load_json(export_path)
assert export['status']=='pass' and export['source_mesh_sha256']==mh and export['continuous_module_sha256']==file_hash(ROOT/'src/scanbench/continuous_free_space.py')
evidence.extend([export_path,ROOT/'scripts/verify_delivery_export_r4.py'])
pilot_path=folder/'pilot_acceptance_r4.json';atomic_json(pilot_path,{'status':'pass','cases':pilot_cases,'physical_settings_and_quality_gates_unchanged':True,'independent_removed_face_witnesses_checked':True});evidence.append(pilot_path)
amendment={'status':'passed_implementation_correction','revision':'r4_continuous_free_space','category':'continuous_observed_free_space_correctness','time':time.time(),'parent_freeze_sha256':file_hash(folder/'freeze_before.json'),'parent_code_snapshot_sha256':file_hash(folder/'code_before.zip'),'physical_protocol_or_quality_gates_changed':False,'defect':'The independent 30000-point area test on source 243 easy seed 20261014 found one real foreground free-space conflict inside a triangle, missed by the original 22-point lattice.','correction':'Uniformly remove triangles intersecting foreground free space by continuous perspective pixel-cell clipping and minimum Euclidean range, after the unchanged observation-only reconstruction. No surface is added or moved; no GT inputs are used.','candidate_regression':'A degenerate clipped-polygon false positive was caught by independent testing and corrected before formal migration; rejected candidate evidence is preserved.','pilot_cases':pilot_cases,'same_configs_sha256':{'protocol':digest(config()),'quality_gates':file_hash(ROOT/'configs/quality_gates.yaml')},'changed_or_added_code_sha256':new,'active_test_reports':active_tests,'existing_case_migration_requirement':{'original_cases':129,'baseline_manifest':'reports/protocol_amendments/r4_continuous_free_space/cases_before.jsonl','pilot_completed':18,'remaining_cases_must_be_migrated_and_independently_accepted_before_final_completion':True},'evidence_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in evidence}}
ap=folder/'amendment.json';atomic_json(ap,amendment)
code={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in sorted((ROOT/'src/scanbench').glob('*.py'))};assert len(code)==20
snapshot=ROOT/'reports/frozen_protocol_code_r4.zip';tmp=snapshot.with_suffix('.zip.partial')
with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
    for name in [*code,'configs/physical_scan_v1.yaml','configs/quality_gates.yaml','requirements.lock']:z.write(ROOT/name,name)
    for path in [ap,pilot_path,*[ROOT/active_tests[n] for n in active_tests]]:z.write(path,str(path.relative_to(ROOT)).replace('\\','/'))
os.replace(tmp,snapshot)
active=dict(before);active.update(implementation_revision='r4_continuous_free_space',implementation_revision_time=time.time(),code_sha256=code,code_snapshot_path=str(snapshot.relative_to(ROOT)).replace('\\','/'),code_snapshot_sha256=file_hash(snapshot),active_test_reports=active_tests,active_pilot_cases=pilot_cases,tests_sha256_at_r4_freeze=tests,delivery_export_evidence='reports/operations/delivery_export_command_r4.json',implementation_amendments=[*before['implementation_amendments'],{'path':str(ap.relative_to(ROOT)).replace('\\','/'),'sha256':file_hash(ap)}],implementation_tests_sha256={**before['implementation_tests_sha256'],str(controls_path.relative_to(ROOT)).replace('\\','/'):file_hash(controls_path)},next_actions='Migrate remaining 111 baseline cases without rescanning; finish all 32 source conclusions and six cases for every eligible source; independent full audit and actual delivery.')
atomic_json(ROOT/'reports/protocol_freeze.json',active);atomic_json(folder/'status.json',{'status':'r4_frozen_after_current_18_case_pilot','remaining_work':active['next_actions'],'time':time.time()})
print(canonical_json({'status':'r4_frozen_after_current_18_case_pilot','pilot_cases':len(pilot_cases),'core_modules':len(code)}))
