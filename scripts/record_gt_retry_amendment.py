"""Register a tested implementation correction while preserving original freeze evidence."""
from pathlib import Path
import os,sys,ast,zipfile,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *

folder=ROOT/'reports/protocol_amendments/r1_gt_retry';before=load_json(folder/'freeze_before.json');cfg=config()
assert digest(cfg)==before['protocol_config_sha256']
assert file_hash(ROOT/'configs/quality_gates.yaml')==before['quality_gates_sha256']
old_hash=file_hash(folder/'sources_before.py');new_hash=file_hash(ROOT/'src/scanbench/sources.py')
assert before['code_sha256']['src/scanbench/sources.py']==old_hash
for name,h in before['code_sha256'].items():
    if name!='src/scanbench/sources.py':assert file_hash(ROOT/name)==h,name
def other_functions(path):
    tree=ast.parse(path.read_text(encoding='utf-8'));tree.body=[n for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name!='prepare'];return ast.dump(tree,include_attributes=False)
assert other_functions(folder/'sources_before.py')==other_functions(ROOT/'src/scanbench/sources.py')
proof_path=ROOT/'reports/tests/gt_retry_compatibility.json';proof=load_json(proof_path)
assert proof['status']=='pass' and proof['new_sources_py_sha256']==new_hash
expected_signature=digest([new_hash,{sid:file_hash(ROOT/f'private/gt/{sid}/mesh.npz') for sid in ['218','231','229']}]);assert proof['signature']==expected_signature
state=State();preserved=[];environment={p:importlib.metadata.version(p) for p in ['cadquery-ocp','numpy','trimesh']}
for sid in ['218','231','229']:
    gt=ROOT/f'private/gt/{sid}';fresh=ROOT/proof['experiment_directory']/f'private/gt/{sid}/mesh.npz'
    with np.load(gt/'mesh.npz') as a,np.load(fresh) as b:
        np.testing.assert_array_equal(a['vertices'],b['vertices']);np.testing.assert_array_equal(a['faces'],b['faces'])
    input_hash=file_hash(ROOT/f'sources/{sid}/input.step');old_key=digest({'inputs':input_hash,'settings':cfg['gt'],'code':{'sources.py':old_hash},'environment':environment})
    new_key=stage_hash(input_hash,cfg['gt'],['sources.py'],list(environment))
    assert state.valid(sid,'gt',old_key) or state.valid(sid,'gt',new_key),sid
    row=state.db.execute('SELECT outputs,metrics FROM stages WHERE subject=? AND stage=?',(sid,'gt')).fetchone();paths=[ROOT/p for p in json.loads(row[0])]
    old_files={str(p.relative_to(ROOT)).replace('\\','/'):[file_hash(p),p.stat().st_mtime_ns] for p in paths}
    if not state.valid(sid,'gt',new_key):state.finish(sid,'gt',new_key,paths,{'reuse_only':True,'implementation_revision':'r1_gt_retry','original_generation_stage_key':old_key,'prior_numerical_stage_metrics':json.loads(row[1])})
    new_files={str(p.relative_to(ROOT)).replace('\\','/'):[file_hash(p),p.stat().st_mtime_ns] for p in paths};assert old_files==new_files
    preserved.append({'source_id':sid,'original_generation_stage_key':old_key,'qualified_current_stage_key':new_key,'unchanged_files':old_files,'metadata_stage_hash_remains_original_generation_provenance':True})
meta201=load_json(ROOT/'private/gt/201/metadata.json');attempts=load_json(ROOT/'private/gt/201/native_attempts.json')
assert meta201['status']=='eligible_native' and meta201['chord_mm']==.01 and len(attempts)==2 and attempts[0]['status']=='failed' and attempts[1]['status']=='pass'
assert meta201['accuracy_check']['max_sampled_mm']<=max(.021,meta201['chord_mm']*1.1)
with np.load(ROOT/'private/gt/201/mesh.npz') as a,np.load(ROOT/'reports/source_investigations/201/native_0.01_0.075.npz') as b:
    np.testing.assert_array_equal(a['vertices'],b['vertices']);np.testing.assert_array_equal(a['faces'],b['faces'])
reuse_path=folder/'cache_reuse.json';atomic_json(reuse_path,{'status':'pass','sources':preserved,'fresh_native_rebuild_proof_sha256':file_hash(proof_path)})
amendment={'status':'passed_implementation_correction','revision':'r1_gt_retry','time':time.time(),'initial_freeze_sha256':file_hash(folder/'freeze_before.json'),'initial_code_snapshot_sha256':file_hash(folder/'code_before.zip'),'changed_module':'src/scanbench/sources.py','old_module_sha256':old_hash,'new_module_sha256':new_hash,
 'defect':'Precision and geometric-degeneracy checks occurred after the candidate retry loop, so an accuracy failure never tried the already prescribed alternative parameters.',
 'correction':'Run the unchanged acceptance checks inside the unchanged candidate loop; preserve every failed accuracy value, limit, exception and elapsed time.',
 'physical_protocol_or_quality_gates_changed':False,'parameter_sequence_changed':False,'same_configs_sha256':{'protocol':digest(cfg),'quality_gates':file_hash(ROOT/'configs/quality_gates.yaml')},
 'affected_scope':'201 and any future source whose early native candidate fails an existing acceptance check. Three prior successful source references are exactly compatible and retain every artifact hash/mtime; no prior observation or mesh needs regeneration.',
 'source_201':{'first_sampled_max_mm':attempts[0]['accuracy_check']['max_sampled_mm'],'first_limit_mm':attempts[0]['accuracy_limit_mm'],'accepted_chord_mm':.01,'accepted_angle_rad':.075,'accepted_sampled_max_mm':meta201['accuracy_check']['max_sampled_mm'],'fresh_production_GT_equals_independent_trial':True},
 'evidence_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [proof_path,reuse_path,ROOT/'private/gt/201/native_attempts.json',ROOT/'reports/source_investigations/201/native_accuracy_trials.json']}}
amend_path=folder/'amendment.json';atomic_json(amend_path,amendment)
snapshot=ROOT/'reports/frozen_protocol_code_r1.zip';tmp=snapshot.with_suffix('.zip.partial')
with zipfile.ZipFile(folder/'code_before.zip') as prior,zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
    for item in prior.infolist():z.writestr(item,(ROOT/item.filename).read_bytes() if item.filename=='src/scanbench/sources.py' else prior.read(item.filename))
    z.write(amend_path,'implementation_amendment_r1.json');z.write(proof_path,'gt_retry_compatibility.json');z.write(reuse_path,'gt_retry_cache_reuse.json')
os.replace(tmp,snapshot)
current=dict(before);current['code_sha256']=dict(before['code_sha256']);current['code_sha256']['src/scanbench/sources.py']=new_hash
current.update(implementation_revision='r1_gt_retry',initial_freeze_sha256=file_hash(folder/'freeze_before.json'),code_snapshot_path=str(snapshot.relative_to(ROOT)).replace('\\','/'),code_snapshot_sha256=file_hash(snapshot),implementation_amendments=[{'path':str(amend_path.relative_to(ROOT)).replace('\\','/'),'sha256':file_hash(amend_path)}],implementation_tests_sha256={str(proof_path.relative_to(ROOT)).replace('\\','/'):file_hash(proof_path)})
atomic_json(ROOT/'reports/protocol_freeze.json',current)
print(canonical_json({'status':amendment['status'],'revision':amendment['revision'],'prior_sources_reused':3,'source_201_native_precision_mm':meta201['accuracy_check']['max_sampled_mm'],'settings_unchanged':True}))
