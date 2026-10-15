"""Install the tested candidate only after the immutable pre-install snapshot."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
from snapshot_sampling_density_v2 import active_source_workers

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'


def main():
    assert not active_source_workers(),'Do not change code while a source worker is live'
    baseline=load_json(FOLDER/'baseline.json');candidate=load_json(FOLDER/'candidate_manifest.json')
    assert baseline['status']=='immutable_snapshot_complete'
    assert file_hash(FOLDER/'candidate_manifest.json')==baseline['candidate_manifest_sha256']
    assert file_hash(FOLDER/'candidate_controls.json')==baseline['candidate_controls_sha256']
    assert file_hash(FOLDER/'runtime_controls.json')==baseline['runtime_controls_sha256']
    assert file_hash(FOLDER/'migration_controls.json')==baseline['migration_controls_sha256']
    assert file_hash(FOLDER/'inventory_before.json')==baseline['inventory_before_sha256']
    old=load_json(FOLDER/'freeze_before.json')
    assert file_hash(FOLDER/'freeze_before.json')==baseline['freeze_before_sha256']
    for name,h in old['code_sha256'].items():assert file_hash(FOLDER/'code_before'/name)==h,name
    installed=FOLDER/'installation.json'
    if installed.exists():
        receipt=load_json(installed)
        for name,h in receipt['active_code_sha256'].items():assert file_hash(ROOT/name)==h,name
        assert file_hash(ROOT/'configs/sampling_density_v2.json')==receipt['active_policy_sha256']
        print(canonical_json({'status':'already_installed_requires_recorded_next_phase','receipt_sha256':file_hash(installed)}));return
    atomic_json(ROOT/'state/sampling_density_v2.json',{'status':'installing_tested_candidate','production_permitted':False,'reason':'Do not invoke production until the current code, compatibility proofs and physical sampling policy are explicitly frozen','time':time.time()})
    names=list(candidate['candidate_sha256'])
    names.remove('src/scanbench/sampling_density.py');names.insert(0,'src/scanbench/sampling_density.py')
    for name in names:
        expected=candidate['candidate_sha256'][name];source=FOLDER/'candidate'/name;target=ROOT/name
        assert file_hash(source)==expected['candidate']
        if target.exists():assert file_hash(target) in [expected['before'],expected['candidate']],name
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists() or file_hash(target)!=expected['candidate']:shutil.copy2(source,target)
        assert file_hash(target)==expected['candidate']
    assert file_hash(FOLDER/'candidate/configs/sampling_density_v2.json')==candidate['policy_sha256']
    policy=load_json(FOLDER/'candidate/configs/sampling_density_v2.json');assert policy['status']=='candidate';policy['status']='frozen'
    path=ROOT/'configs/sampling_density_v2.json'
    if path.exists():assert load_json(path)==policy
    else:atomic_json(path,policy)
    active={name:file_hash(ROOT/name) for name in [*old['code_sha256'],'src/scanbench/sampling_density.py']}
    receipt={'status':'installed_requires_compatibility_migration_before_freeze','baseline_sha256':file_hash(FOLDER/'baseline.json'),'candidate_manifest_sha256':file_hash(FOLDER/'candidate_manifest.json'),'candidate_controls_sha256':file_hash(FOLDER/'candidate_controls.json'),'runtime_controls_sha256':file_hash(FOLDER/'runtime_controls.json'),'active_policy_sha256':file_hash(path),'active_code_sha256':active,'physical_protocol':policy['protocol'],'reconstruction_unchanged':all(active['src/scanbench/'+name]==old['code_sha256']['src/scanbench/'+name] for name in ['reconstruct.py','observed_kernel.py','continuous_free_space.py','camera.py']),'quality_gates_unchanged':file_hash(ROOT/'configs/quality_gates.yaml')==old['quality_gates_sha256'],'script_sha256':file_hash(Path(__file__)),'time':time.time()}
    assert receipt['reconstruction_unchanged'] and receipt['quality_gates_unchanged']
    atomic_json(installed,receipt)
    atomic_json(ROOT/'state/sampling_density_v2.json',{'status':receipt['status'],'installation_sha256':file_hash(installed),'next':'Prove and migrate unchanged acquisition/case/reference/acceptance metadata, prepare refined sources, then freeze the new explicit physical version','production_permitted':False,'time':time.time()})
    print(canonical_json({k:v for k,v in receipt.items() if k!='active_code_sha256'}),flush=True)


if __name__=='__main__':main()
