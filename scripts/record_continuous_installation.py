"""Bind the small r4 implementation change and prove upstream numerical code unchanged."""
from pathlib import Path
import os,sys,ast
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *

folder=ROOT/'reports/protocol_amendments/r4_continuous_free_space';before=load_json(folder/'freeze_before.json')
changed=['src/scanbench/reconstruct.py','src/scanbench/cases.py','src/scanbench/export.py','src/scanbench/reporting.py'];added=['src/scanbench/continuous_free_space.py']
for name,h in before['code_sha256'].items():
    if name not in changed:assert file_hash(ROOT/name)==h,name
def functions(path):return {x.name:ast.dump(x,include_attributes=False) for x in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
old=functions(folder/'before/src/scanbench/reconstruct.py');new=functions(ROOT/'src/scanbench/reconstruct.py')
preserved=[]
for name,tree in old.items():
    if name!='reconstruct':assert tree==new[name],name;preserved.append(name)
old_cases=functions(folder/'before/src/scanbench/cases.py');new_cases=functions(ROOT/'src/scanbench/cases.py')
assert old_cases['prepare_case']==new_cases['prepare_case'] and old_cases['case_id']==new_cases['case_id']
assert digest(config())==before['protocol_config_sha256'] and file_hash(ROOT/'configs/quality_gates.yaml')==before['quality_gates_sha256']
control=load_json(ROOT/'reports/free_space_revision/controls_candidate.json');trial=load_json(ROOT/'reports/free_space_revision/failing_case_trial.json')
assert control['status']=='pass' and control['module_sha256']==file_hash(ROOT/added[0])==file_hash(ROOT/'tools/continuous_free_space.py')
assert trial['status']=='pass' and trial['reconstruction_code_sha256']==file_hash(ROOT/changed[0])
result={'status':'pass','revision':'r4_continuous_free_space','changed_modules_sha256':{name:file_hash(ROOT/name) for name in changed},'added_modules_sha256':{name:file_hash(ROOT/name) for name in added},'unchanged_original_reconstruction_functions_AST':preserved,'prepare_case_and_case_id_AST_unchanged':True,'source_scan_pose_noise_code_unchanged':True,'protocol_config_and_quality_gates_unchanged':True,'new_behavior':'After unchanged fusion, BPA, 22-point observation support filtering and orientation, remove only triangles whose continuous pixel-cell intersection violates the existing stable 3x3 foreground free-space rule; split any resulting disconnected vertex fans using the unchanged connectivity routine. No new geometric position or face is added.','additional_changes':['Explicit stage dependency on continuous_free_space.py and public continuous_veto.json evidence','Copy the new observation-only module into portable exports','Report only cases with the current reconstruction-stage key and select explicitly versioned current test reports','Preserve identical point provenance bytes/mtime when reusing valid upstream stages','Set a two-thread Numba default in the public CLI and exported entry point'],'controls_sha256':file_hash(ROOT/'reports/free_space_revision/controls_candidate.json'),'failing_case_trial_sha256':file_hash(ROOT/'reports/free_space_revision/failing_case_trial.json'),'script_sha256':file_hash(Path(__file__))}
atomic_json(folder/'installation.json',result);print(canonical_json(result))
