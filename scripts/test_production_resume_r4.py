"""Real no-change CLI-stage resume and actual recorded dependency-hash checks."""
from pathlib import Path
import os,sys,copy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
from scanbench.sources import prepare
from scanbench.verified_placements import prepare_verified_placements
from scanbench.scan import acquire_scans
from scanbench.cases import generate_case,case_id
from scanbench.validate import validate_case,validation_fingerprint

state=State();sid='218';cfg=config();cids=[case_id(sid,l,s) for s in cfg['seeds'] for l in ['hard','medium','easy']];subjects={sid,*cids};files=set()
for subject,stage,status,outputs in state.db.execute('SELECT subject,stage,status,outputs FROM stages'):
    if status=='complete' and (subject in subjects or subject.startswith(sid+'/')):
        files.update(ROOT/p for p in json.loads(outputs))
before={str(p.relative_to(ROOT)):[file_hash(p),p.stat().st_mtime_ns] for p in files}
prepare(sid,state);prepare_verified_placements(sid,state);acquire_scans(sid,state)
for seed in cfg['seeds']:
    for level in ['hard','medium','easy']:
        cid=generate_case(sid,level,seed,state);assert validate_case(cid,state)['status']=='pass'
after={str(p.relative_to(ROOT)):[file_hash(p),p.stat().st_mtime_ns] for p in files}
assert before==after,'A qualified output was rewritten on no-change resume'
gt=ROOT/f'private/gt/{sid}';cam=load_json(gt/'cameras.json')['cameras'][0];out=ROOT/f'data/cases/{cids[0]}/input';rec=load_json(ROOT/f'private/annotations/{cids[0]}/case.json');gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text())
scan_key=stage_hash([file_hash(gt/'mesh.npz'),cam],cfg['scan'],['scan.py','camera.py'],['numpy','open3d']);assert state.valid(f'{sid}/{cam["id"]}','observations',scan_key)
mesh_key=stage_hash([file_hash(out/'observations.json'),file_hash(out/'cameras.json')],cfg['reconstruction'],['reconstruct.py','camera.py','observed_kernel.py','continuous_free_space.py'],['numpy','open3d','scipy','numba']);assert state.valid(cids[0],'mesh',mesh_key)
changed_recon=copy.deepcopy(cfg['reconstruction']);changed_recon['support_h']+=.1
new_mesh_key=stage_hash([file_hash(out/'observations.json'),file_hash(out/'cameras.json')],changed_recon,['reconstruct.py','camera.py','observed_kernel.py','continuous_free_space.py'],['numpy','open3d','scipy','numba']);assert not state.valid(cids[0],'mesh',new_mesh_key);assert state.valid(f'{sid}/{cam["id"]}','observations',scan_key)
changed_scan=copy.deepcopy(cfg['scan']);changed_scan['sigma_relative']*=1.01
new_scan_key=stage_hash([file_hash(gt/'mesh.npz'),cam],changed_scan,['scan.py','camera.py'],['numpy','open3d']);assert not state.valid(f'{sid}/{cam["id"]}','observations',new_scan_key)
validation_key=validation_fingerprint(out,rec,gates);assert state.valid(cids[0],'validation',validation_key);changed_gates=copy.deepcopy(gates);changed_gates['evaluation_surface_samples']+=1;new_validation_key=validation_fingerprint(out,rec,changed_gates);assert not state.valid(cids[0],'validation',new_validation_key);assert state.valid(cids[0],'mesh',mesh_key)
result={'status':'pass','actual_prepare_scan_generate_validate_resume_executed':True,'source_id':sid,'cases':cids,'all_qualified_hashes_and_mtimes_unchanged':True,'tracked_files':len(files),'before_after_digest':digest(before),'actual_ledger_dependency_checks':{'reconstruction_setting_invalidates_mesh_only':new_mesh_key!=mesh_key,'scan_setting_invalidates_observations':new_scan_key!=scan_key,'validation_setting_invalidates_validation_only':new_validation_key!=validation_key},'scope':'no-change path executed end to end; changed-setting tests compare real production stage keys against actual complete ledger rows, without generating unnecessary variant data'}
atomic_json(ROOT/'reports/tests/production_resume_and_dependencies_r4.json',result);print(canonical_json(result))
