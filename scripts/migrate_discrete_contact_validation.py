"""Reuse exact-compatible planar validation after real CAD contact branch tests."""
from pathlib import Path
import os,sys,shutil,ast,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.verified_placements import prepare_verified_placements
from scanbench.validate import validation_fingerprint
folder=ROOT/'reports/protocol_amendments/r3_discrete_contact';proof_path=ROOT/'reports/tests/discrete_contact_support.json';proof=load_json(proof_path);before=load_json(folder/'state_before.json');frozen=load_json(folder/'freeze_before.json');state=State()
assert proof['status']=='pass' and proof['compared_cases']==30 and proof['all_other_validator_numerical_functions_AST_unchanged']
for name,h in proof['code_sha256'].items():assert file_hash(ROOT/f'src/scanbench/{name}')==h
assert digest(config())==frozen['protocol_config_sha256'] and file_hash(ROOT/'configs/quality_gates.yaml')==frozen['quality_gates_sha256']
for name,(h,mtime) in load_json(folder/'inventory_before.json').items():assert [file_hash(ROOT/name),(ROOT/name).stat().st_mtime_ns]==[h,mtime],name
old_validate=file_hash(folder/'validate_before.py');new_validate=file_hash(ROOT/'src/scanbench/validate.py')
changed=['src/scanbench/placement_audit.py','src/scanbench/verified_placements.py','src/scanbench/validate.py']
for name,h in frozen['code_sha256'].items():
    if name not in changed:assert file_hash(ROOT/name)==h,name
for row in before['stages']:
    if row['subject'] in ['218','231','229','201','203'] and row['stage']=='gt':
        for name,h in json.loads(row['outputs']).items():assert file_hash(ROOT/name)==h,name
sources=[]
for sid in ['218','231','229','201','203']:
    gt=ROOT/f'private/gt/{sid}';prepare_verified_placements(sid,state)
    assert file_hash(gt/'placements.json')==file_hash(folder/f'prior_placements/{sid}/placements.json')
    marker=ROOT/f'private/reference/{sid}/reference.json';saved=folder/f'prior_placements/{sid}/reference_before.json'
    if not saved.exists():shutil.copy2(marker,saved)
    old=load_json(saved);inputs=[file_hash(gt/'mesh.npz'),file_hash(gt/'cameras.json'),file_hash(gt/'placements.json')];settings={'samples':30000,'incidence_deg':config()['scan']['incidence_deg']};packages=['numpy','open3d','trimesh']
    old_key=digest({'inputs':inputs,'settings':settings,'code':{'validate.py':old_validate},'environment':{p:importlib.metadata.version(p) for p in packages}})
    assert old['key']==old_key
    new_key=stage_hash(inputs,settings,['validate.py'],packages);updated=dict(old);updated['key']=new_key;atomic_json(marker,updated)
    evaluation=marker.with_name('evaluation.npz');sources.append({'source_id':sid,'reference_old_key':old_key,'reference_current_key':new_key,'unchanged_reference_npz':[file_hash(evaluation),evaluation.stat().st_mtime_ns],'unchanged_placements_sha256':file_hash(gt/'placements.json')})
gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text(encoding='utf-8'));cases=[]
for record in before['cases']:
    cid=record['case_id'];sid=record['source_id'];out=ROOT/record['input_path'];saved=folder/'prior_acceptance'/f'{cid}.json';old=load_json(saved)
    item=next(x for x in proof['prior_cases'] if x['case_id']==cid);assert file_hash(saved)==item['old_acceptance_sha256']
    assert old['status']=='pass' and digest(old['physical_scan'])==item['physical_result_sha256']
    key=validation_fingerprint(out,record,gates);updated=dict(old);updated['validation_hash']=key;acceptance=ROOT/f'private/annotations/{cid}/acceptance.json';atomic_json(acceptance,updated)
    state.finish(cid,'validation',key,[acceptance],{'reuse_only':True,'implementation_revision':'r3_discrete_contact','old_validation_hash':old['validation_hash'],'unchanged_numerical_results_and_actual_planar_physical_check':True,'original_performance':old['performance']})
    record.update(validation_status='pass',validation_hash=key);atomic_json(ROOT/f'private/annotations/{cid}/case.json',record);state.record('cases',cid,record)
    extra=ROOT/f'private/annotations/{cid}/supplemental.json';saved_extra=folder/'prior_acceptance'/f'{cid}_supplemental.json'
    if not saved_extra.exists():shutil.copy2(extra,saved_extra)
    old_extra=load_json(saved_extra);gt=ROOT/f'private/gt/{sid}';base=[file_hash(out/'mesh.ply'),file_hash(out/'observations.json'),file_hash(out/'cameras.json'),file_hash(out/'reconstruction.json'),file_hash(gt/'features.json'),file_hash(gt/'feature_contract.json'),file_hash(ROOT/'src/scanbench/supplemental.py')]
    assert old_extra['status']=='pass' and old_extra['input_hash']==digest(base+[old_validate])
    updated_extra=dict(old_extra);updated_extra['input_hash']=digest(base+[new_validate]);atomic_json(extra,updated_extra)
    cases.append({'case_id':cid,'old_validation_hash':old['validation_hash'],'current_validation_hash':key,'only_acceptance_dependency_hash_changed':True,'supplemental_numerical_functions_and_all_input_arrays_unchanged':True,'old_acceptance_sha256':file_hash(saved),'old_supplemental_sha256':file_hash(saved_extra)})
for name,(h,mtime) in load_json(folder/'inventory_before.json').items():assert [file_hash(ROOT/name),(ROOT/name).stat().st_mtime_ns]==[h,mtime],name
atomic_json(folder/'cache_reuse.json',{'status':'pass','proof_sha256':file_hash(proof_path),'sources':sources,'cases':cases,'public_file_count':len(load_json(folder/'inventory_before.json')),'all_public_hashes_and_mtimes_preserved':True,'scan_reconstruction_and_quality_numerics_unchanged':True,'script_sha256':file_hash(Path(__file__))})
print('Requalified 30 exact-compatible validations; preserved every public file hash/mtime.')
