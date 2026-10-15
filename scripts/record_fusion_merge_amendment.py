"""Seal exact optimization evidence and current-code independent reconstruction tests."""
from pathlib import Path
import os,sys,zipfile,ast
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
folder=ROOT/'reports/protocol_amendments/r2_fusion_merge';before=load_json(folder/'freeze_before.json');installation=load_json(folder/'installation.json');reuse=load_json(folder/'cache_reuse.json');cfg=config()
assert digest(cfg)==before['protocol_config_sha256']
assert file_hash(ROOT/'configs/quality_gates.yaml')==before['quality_gates_sha256']
for name,h in before['code_sha256'].items():
    if name!='src/scanbench/reconstruct.py':assert file_hash(ROOT/name)==h,name
assert file_hash(ROOT/'src/scanbench/reconstruct.py')==installation['new_code_sha256']
assert reuse['status']=='pass' and reuse['candidate_and_installed_fusion_AST_equivalent'] and reuse['all_other_numerical_functions_unchanged']
inventory=load_json(folder/'inventory_before.json');proofs=[];evidence={}
ties=ROOT/'reports/tests/fusion_merge_ties.json';t=load_json(ties);assert t['status']=='pass' and t['candidate_code_sha256']==installation['candidate_code_sha256'] and t['script_sha256']==file_hash(ROOT/'scripts/test_fusion_merge_ties.py');evidence[str(ties.relative_to(ROOT)).replace('\\','/')]=file_hash(ties)
for cid,item in inventory.items():
    p=ROOT/item['proof_path'];assert file_hash(p)==item['proof_sha256'];proof=load_json(p)
    assert proof['status']=='pass' and proof['all_float64_points_normals_frame_pixel_order_and_metrics_exact']
    proofs.append(proof);evidence[item['proof_path']]=file_hash(p)
for item in reuse['cases']:
    for path,(h,mtime) in item['unchanged_public_and_numeric_cache_files'].items():assert file_hash(ROOT/path)==h and (ROOT/path).stat().st_mtime_ns==mtime,path
cid='case_2438b1a3fd780c63';out=ROOT/f'data/cases/{cid}/input';mh=file_hash(out/'mesh.ply');oh=file_hash(out/'observations.json');ch=file_hash(ROOT/'src/scanbench/reconstruct.py')
for name,sig in [('no_gt_portable',digest([mh,ch,oh])),('full_case_reproduction',digest([mh,oh,ch])),('real_mesh_interruption',digest([mh,ch]))]:
    p=ROOT/f'reports/tests/{name}.json';test=load_json(p);assert test['status']=='pass' and test['signature']==sig,name;evidence[str(p.relative_to(ROOT)).replace('\\','/')]=file_hash(p)
p=ROOT/'reports/tests/production_resume_and_dependencies.json';test=load_json(p);assert test['status']=='pass' and test['all_qualified_hashes_and_mtimes_unchanged'];evidence[str(p.relative_to(ROOT)).replace('\\','/')]=file_hash(p)
equivalence={'status':'pass','revision':'r2_fusion_merge','compared_cases':len(proofs),'compared_frames':sum(p['frames'] for p in proofs),'all_float64_points_normals_frame_pixel_order_metrics_exact':True,'all_public_mesh_points_provenance_and_observation_files_hash_mtime_preserved':True,'cases':[{k:p[k] for k in ['case_id','frames','working_points','seconds','original_fusion_npz_sha256']} for p in proofs],'candidate_and_installed_fusion_AST_equivalent':True,'new_reconstruction_sha256':ch,'proof_sha256':{item['proof_path']:item['proof_sha256'] for item in inventory.values()},'current_code_independent_no_GT_full_STEP_and_actual_interruption_tests_pass':True}
eqpath=ROOT/'reports/tests/fusion_merge_equivalence.json';atomic_json(eqpath,equivalence)
for p in [eqpath,folder/'cache_reuse.json',folder/'installation.json',folder/'inventory_before.json']:evidence[str(p.relative_to(ROOT)).replace('\\','/')]=file_hash(p)
amendment={'status':'passed_implementation_correction','category':'performance_optimization','revision':'r2_fusion_merge','time':time.time(),'parent_freeze_sha256':file_hash(folder/'freeze_before.json'),'parent_code_snapshot_sha256':file_hash(folder/'code_before.zip'),'changed_module':'src/scanbench/reconstruct.py','old_module_sha256':installation['old_code_sha256'],'new_module_sha256':ch,'physical_protocol_or_quality_gates_changed':False,'defect':'Repeated full sorting of an already sorted cumulative working cloud dominated dense-case fusion time.','correction':'Merge two sorted unique voxel/normal-cone sets in linear time; use the identical confidence, earlier-frame and earlier-pixel ordering, stable old-first exact ties; retain an actual observation representative without averaging.','scope':'Computational implementation only. Every already generated case has exact points/normals/provenance/order/metrics equivalence; all existing numerical payloads and formal Mesh hashes/mtimes are preserved. New code passed fresh no-GT, STEP-to-Mesh, actual interruption and production no-change-resume checks.','same_configs_sha256':{'protocol':digest(cfg),'quality_gates':file_hash(ROOT/'configs/quality_gates.yaml')},'evidence_sha256':evidence}
ap=folder/'amendment.json';atomic_json(ap,amendment)
snapshot=ROOT/'reports/frozen_protocol_code_r2.zip';tmp=snapshot.with_suffix('.zip.partial')
with zipfile.ZipFile(folder/'code_before.zip') as prior,zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
    for name in prior.namelist():
        if name=='src/scanbench/reconstruct.py':z.write(ROOT/name,name)
        elif name=='requirements.lock':z.write(ROOT/name,name)
        else:z.writestr(name,prior.read(name))
    z.write(ap,'implementation_amendment_r2.json');z.write(eqpath,'fusion_merge_equivalence.json');z.write(folder/'cache_reuse.json','fusion_merge_cache_reuse.json')
os.replace(tmp,snapshot)
active=dict(before);active['code_sha256']=dict(before['code_sha256']);active['code_sha256']['src/scanbench/reconstruct.py']=ch
active.update(implementation_revision='r2_fusion_merge',code_snapshot_path=str(snapshot.relative_to(ROOT)).replace('\\','/'),code_snapshot_sha256=file_hash(snapshot),implementation_amendments=[*before.get('implementation_amendments',[]),{'path':str(ap.relative_to(ROOT)).replace('\\','/'),'sha256':file_hash(ap)}],implementation_tests_sha256={**before.get('implementation_tests_sha256',{}),str(eqpath.relative_to(ROOT)).replace('\\','/'):file_hash(eqpath)})
atomic_json(ROOT/'reports/protocol_freeze.json',active);print(canonical_json({'status':amendment['status'],'revision':amendment['revision'],'existing_cases_exact_and_preserved':len(proofs),'physical_settings_unchanged':True}))
