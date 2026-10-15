"""Freeze explicit sampling v2 only after controls, adoption and independent audit."""
from pathlib import Path
import os,sys,zipfile,hashlib
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
from scanbench.sampling_density import sampling_policy,verify_case_sampling_contract
from scanbench.validate import physical_case_check,validation_fingerprint
from snapshot_sampling_density_v2 import active_source_workers

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'


def main():
    assert not active_source_workers()
    baseline=load_json(FOLDER/'baseline.json');installed=load_json(FOLDER/'installation.json')
    audit=load_json(FOLDER/'pre_freeze_independent_audit.json');old=load_json(FOLDER/'freeze_before.json')
    assert audit['status']=='pass' and audit['phase']=='before_physical_version_freeze'
    assert audit['script_sha256']==file_hash(ROOT/'scripts/audit_sampling_density_revision.py')
    assert audit['baseline_sha256']==file_hash(FOLDER/'baseline.json')
    assert audit['installation_sha256']==file_hash(FOLDER/'installation.json')
    assert audit['default_migration_sha256']==file_hash(FOLDER/'default_migration.json')
    policy=sampling_policy();assert audit['policy_sha256']==file_hash(ROOT/'configs/sampling_density_v2.json')==installed['active_policy_sha256']
    assert digest(config())==old['protocol_config_sha256']
    assert file_hash(ROOT/'configs/quality_gates.yaml')==old['quality_gates_sha256']
    for name,h in installed['active_code_sha256'].items():assert file_hash(ROOT/name)==h,name
    state=State();gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text());pilot=[]
    assert len(old['active_pilot_cases'])==18 and {c['source_id'] for c in old['active_pilot_cases']}=={'218','229','231'}
    for item in old['active_pilot_cases']:
        cid=item['case_id'];record=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/record['input_path']
        contract=verify_case_sampling_contract(record,out);assert contract['mother_intervals']==192
        result=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');proof=load_json(FOLDER/f'default_cases/{cid}.json')
        assert file_hash(out/'mesh.ply')==item['mesh_sha256']
        assert proof['original_acceptance_sha256']==item['acceptance_sha256']
        assert physical_case_check(record,out)==result['physical_scan'] and result['status']=='pass'
        assert state.valid(cid,'validation',validation_fingerprint(out,record,gates))
        pilot.append({**item,'acceptance_sha256':file_hash(ROOT/f'private/annotations/{cid}/acceptance.json'),'sampling_contract_sha256':file_hash(out/'sampling_contract.json'),'original_r4_acceptance_sha256':item['acceptance_sha256'],'adoption_proof_sha256':file_hash(FOLDER/f'default_cases/{cid}.json')})
    evidence_names=['baseline.json','freeze_before.json','state_before.sqlite','inventory_before.json','metadata_archives.json','candidate_manifest.json','candidate_controls.json','runtime_controls.json','migration_controls.json','refined_preparation_controls.json','freeze_guard_control_refresh.json','diagnostic_comparison_fix.json','installation.json','default_migration.json','pre_freeze_independent_audit.json']
    evidence={str((FOLDER/name).relative_to(ROOT)).replace('\\','/'):file_hash(FOLDER/name) for name in evidence_names}
    for sid in baseline['affected_sources']:
        for name in ['prepared.json','archive_inventory.json']:
            p=FOLDER/f'affected_sources/{sid}/{name}';evidence[p.relative_to(ROOT).as_posix()]=file_hash(p)
    scripts=['stage_sampling_density_v2.py','test_sampling_density_candidate.py','test_sampling_density_runtime.py','test_sampling_density_migration.py','test_refined_sampling_preparation.py','refresh_sampling_candidate_controls.py','snapshot_sampling_density_v2.py','install_sampling_density_v2.py','migrate_sampling_density_defaults.py','prepare_refined_sampling_source.py','audit_sampling_density_revision.py','freeze_sampling_density_v2.py','verify_delivery_export_sampling_v2.py']
    for name in scripts:evidence['scripts/'+name]=file_hash(ROOT/'scripts'/name)
    archive=ROOT/'reports/frozen_protocol_code_sampling_v2.zip'
    names=[*installed['active_code_sha256'],'configs/physical_scan_v1.yaml','configs/quality_gates.yaml','configs/sampling_density_v2.json']
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert set(z.namelist())==set(names)
            for name in names:assert hashlib.sha256(z.read(name)).hexdigest()==file_hash(ROOT/name)
    else:
        temporary=archive.with_name(archive.name+'.partial')
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name in names:z.write(ROOT/name,name)
        os.replace(temporary,archive)
    amendment={'status':'passed_controlled_physical_sampling_revision','revision':'r5_sampling_density','physical_protocol':policy['protocol'],'base_protocol_config_sha256':digest(config()),'base_scan_geometry_and_noise_settings_changed':False,'reconstruction_changed':False,'quality_gates_changed':False,'physical_sampling_schedule_changed':True,'default_mother_intervals':192,'source_interval_overrides':policy['source_intervals'],'all_current_cases_require_public_sampling_contract':True,'same_uniform_complete_descending_three_turn_path':True,'original_observations_preserved_at_exact_old_positions_with_integer_noise_keys':True,'unaffected_current_cases':len(baseline['unaffected_accepted_cases']),'inherited_pilot_cases':18,'affected_sources_require_six_new_fully_validated_cases':baseline['affected_sources'],'evidence_sha256':evidence,'new_code_snapshot_sha256':file_hash(archive),'script_sha256':file_hash(Path(__file__)),'time':time.time()}
    amendment_path=FOLDER/'amendment.json'
    if amendment_path.exists():
        previous=load_json(amendment_path)
        assert {k:v for k,v in previous.items() if k!='time'}=={k:v for k,v in amendment.items() if k!='time'}
        amendment=previous
    else:atomic_json(amendment_path,amendment)
    frozen={**old,'physical_protocol_revision':policy['protocol'],'physical_sampling_policy':{'path':'configs/sampling_density_v2.json','sha256':file_hash(ROOT/'configs/sampling_density_v2.json')},'physical_sampling_amendment':{'path':amendment_path.relative_to(ROOT).as_posix(),'sha256':file_hash(amendment_path)},'previous_physical_freeze':{'path':(FOLDER/'freeze_before.json').relative_to(ROOT).as_posix(),'sha256':file_hash(FOLDER/'freeze_before.json')},'code_sha256':installed['active_code_sha256'],'code_snapshot_path':archive.relative_to(ROOT).as_posix(),'code_snapshot_sha256':file_hash(archive),'active_pilot_cases':pilot,'settings_change':'Explicit physical sampling v2: default 192 intervals unchanged; evidenced uniform source overrides in the frozen policy. All old physical positions and noise remain identical. Reconstruction and quality gates unchanged.','next_actions':'Generate and validate all six affected-source cases, then full independent acceptance and consistent delivery.'}
    frozen.update(previous_delivery_export_evidence=old['delivery_export_evidence'],delivery_export_evidence='reports/operations/delivery_export_command_sampling_v2.json')
    atomic_json(ROOT/'reports/protocol_freeze.json',frozen)
    atomic_json(ROOT/'state/sampling_density_v2.json',{'status':'frozen_ready_for_affected_source_generation','production_permitted':True,'freeze_sha256':file_hash(ROOT/'reports/protocol_freeze.json'),'amendment_sha256':file_hash(amendment_path),'remaining_sources':baseline['affected_sources'],'time':time.time()})
    print(canonical_json({'status':'frozen_ready_for_affected_source_generation','physical_protocol':policy['protocol'],'pilot_cases':18,'current_core_modules':len(installed['active_code_sha256']),'affected_sources':baseline['affected_sources']}),flush=True)


if __name__=='__main__':main()
