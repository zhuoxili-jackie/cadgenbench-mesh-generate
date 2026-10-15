"""Seal the exact CAD contact extension and preserved-data compatibility evidence."""
from pathlib import Path
import os,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
folder=ROOT/'reports/protocol_amendments/r3_discrete_contact';before=load_json(folder/'freeze_before.json');control_path=ROOT/'reports/tests/discrete_contact_support.json';control=load_json(control_path);reuse=load_json(folder/'cache_reuse.json');resume_path=ROOT/'reports/tests/discrete_contact_production_resume.json';resume=load_json(resume_path)
assert control['status']=='pass' and control['compared_cases']==30 and len(control['controls'])==9
assert reuse['status']=='pass' and reuse['all_public_hashes_and_mtimes_preserved'] and resume['status']=='pass' and resume['all_qualified_hashes_and_mtimes_unchanged']
assert digest(config())==before['protocol_config_sha256'] and file_hash(ROOT/'configs/quality_gates.yaml')==before['quality_gates_sha256']
new={f'src/scanbench/{name}':h for name,h in control['code_sha256'].items()}
for path,h in new.items():assert file_hash(ROOT/path)==h
for path,h in before['code_sha256'].items():
    if path not in new:assert file_hash(ROOT/path)==h,path
for path,(h,mtime) in load_json(folder/'inventory_before.json').items():assert [file_hash(ROOT/path),(ROOT/path).stat().st_mtime_ns]==[h,mtime],path
for path,(h,mtime) in resume['files'].items():assert [file_hash(ROOT/path),(ROOT/path).stat().st_mtime_ns]==[h,mtime],path
integration_path=ROOT/'reports/source_investigations/204/discrete_contacts/integration.json';integration=load_json(integration_path)
assert integration['status']=='pass' and integration['actual_pose_count']==2 and integration['placements_sha256']==file_hash(ROOT/'private/gt/204/placements.json')
assert load_json(ROOT/'private/gt/204/limited_pose_investigation.json')['status']=='only_existing_poses_certified'
evidence_paths=[control_path,resume_path,folder/'cache_reuse.json',folder/'inventory_before.json',folder/'state_before.json',integration_path,ROOT/'private/gt/204/placement_audit.json',ROOT/'private/gt/204/limited_pose_investigation.json',ROOT/'scripts/test_discrete_contacts.py',ROOT/'scripts/test_discrete_contact_resume.py',ROOT/'scripts/migrate_discrete_contact_validation.py',ROOT/'scripts/integrate_discrete_poses.py']
evidence_paths+=[ROOT/c['shape_path'] for c in control['controls']]+list((folder/'prior_acceptance').glob('*.json'))+list((folder/'prior_placements').rglob('*.json'))+[ROOT/p for p in integration['evidence_sha256']]
evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in evidence_paths}
amendment={'status':'passed_implementation_correction','revision':'r3_discrete_contact','category':'missing_taskbook_contact_mode','time':time.time(),'parent_freeze_sha256':file_hash(folder/'freeze_before.json'),'parent_code_snapshot_sha256':file_hash(folder/'code_before.zip'),'physical_protocol_or_quality_gates_changed':False,'previous_implementation_positive_planar_area_restriction_removed_for_certified_discrete_contacts':True,'defect':'The initial implementation rejected every zero-area contact, although the taskbook explicitly permits separately evidenced point/line support. Source 204 has four separated exact CAD contacts with a large positive COM margin.','correction':'Accept only an explicitly recorded discrete contact kind with at least three noncollinear real CAD contacts on z=0, exact BREP above the table, and independently calculated COM support margin exceeding the conservative numerical/curvature band. Preserve actual contact area 0; never substitute support polygon area. Single/collinear/rolling numerical supports fail.','old_planar_behavior':'All 30 existing actual-case physical outputs and five source planar audits are numerically identical. All other validator numerical functions have identical AST; observation generation and reconstruction are unchanged.','tests':{'real_CAD_controls':9,'old_cases_exact':30,'unchanged_public_files':reuse['public_file_count'],'current_production_resume_files':resume['qualified_files']},'changed_or_added_code_sha256':new,'same_configs_sha256':{'protocol':digest(config()),'quality_gates':file_hash(ROOT/'configs/quality_gates.yaml')},'evidence_sha256':evidence}
ap=folder/'amendment.json';atomic_json(ap,amendment);snapshot=ROOT/'reports/frozen_protocol_code_r3.zip';tmp=snapshot.with_suffix('.zip.partial')
with zipfile.ZipFile(folder/'code_before.zip') as prior,zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
    for name in prior.namelist():
        if name in new:z.write(ROOT/name,name)
        else:z.writestr(name,prior.read(name))
    for name in new:
        if name not in prior.namelist():z.write(ROOT/name,name)
    for path,name in [(ap,'implementation_amendment_r3.json'),(control_path,'discrete_contact_support.json'),(resume_path,'discrete_contact_production_resume.json'),(folder/'cache_reuse.json','discrete_contact_cache_reuse.json')]:z.write(path,name)
os.replace(tmp,snapshot)
active=dict(before);active['code_sha256']={**before['code_sha256'],**new};active.update(implementation_revision='r3_discrete_contact',code_snapshot_path=str(snapshot.relative_to(ROOT)).replace('\\','/'),code_snapshot_sha256=file_hash(snapshot),implementation_amendments=[*before.get('implementation_amendments',[]),{'path':str(ap.relative_to(ROOT)).replace('\\','/'),'sha256':file_hash(ap)}],implementation_tests_sha256={**before.get('implementation_tests_sha256',{}),str(control_path.relative_to(ROOT)).replace('\\','/'):file_hash(control_path),str(resume_path.relative_to(ROOT)).replace('\\','/'):file_hash(resume_path)})
atomic_json(ROOT/'reports/protocol_freeze.json',active);print(canonical_json({'revision':'r3_discrete_contact','status':'passed_implementation_correction','existing_cases_preserved':30,'source_204_certified_poses':2}))
