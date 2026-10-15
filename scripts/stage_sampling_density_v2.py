"""Prepare a reviewable candidate; leave the running frozen production untouched."""
from pathlib import Path
import os,sys,difflib
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'
CANDIDATE=FOLDER/'candidate'


def replace_once(source,old,new):
    assert source.count(old)==1,old
    return source.replace(old,new,1)


def main():
    frozen=load_json(ROOT/'reports/protocol_freeze.json')
    for name,h in frozen['code_sha256'].items():assert file_hash(ROOT/name)==h,name
    changed={}
    source=(ROOT/'src/scanbench/scan.py').read_text(encoding='utf-8')
    source=replace_once(source,'from .camera import pixel_directions,trajectory','from .camera import pixel_directions,trajectory\nfrom .sampling_density import source_scan_settings,noise_frame_key')
    source=replace_once(source,"cfg=config()['scan']; features=load_json(gt/'features.json')","cfg=source_scan_settings(sid); features=load_json(gt/'features.json')")
    source=replace_once(source,"gt=ROOT/f'private/gt/{sid}'; cfg=config(); sc=cfg['scan']; placements=load_json(gt/'placements.json')","gt=ROOT/f'private/gt/{sid}'; cfg=config(); sc=source_scan_settings(sid); placements=load_json(gt/'placements.json')")
    source=replace_once(source,"['camera.py','scan.py'],['numpy','open3d']","['camera.py','scan.py','sampling_density.py'],['numpy','open3d']")
    source=replace_once(source,"['scan.py','camera.py'],['numpy','open3d']","['scan.py','camera.py','sampling_density.py'],['numpy','open3d']")
    source=replace_once(source,"stream=stable_seed(sc['noise_algorithm'],sid,seed,camera['placement_id'],camera['mother_frame_id'])","stream=stable_seed(sc['noise_algorithm'],sid,seed,camera['placement_id'],noise_frame_key(camera,sc))")
    changed['src/scanbench/scan.py']=source

    source=(ROOT/'src/scanbench/cases.py').read_text(encoding='utf-8')
    source=replace_once(source,'from .common import *','from .common import *\nfrom .sampling_density import case_sampling_contract')
    source=replace_once(source,"key=stage_hash([frames,publiccam,digest(cfg)],cfg['reconstruction'],['cases.py'],['numpy'])","sampling=case_sampling_contract(sid,level,count)\n    key=stage_hash([frames,publiccam,digest(cfg),sampling],cfg['reconstruction'],['cases.py','sampling_density.py'],['numpy'])")
    source=replace_once(source,"atomic_json(out/'reconstruction_config.json',cfg['reconstruction'])","atomic_json(out/'reconstruction_config.json',cfg['reconstruction'])\n        atomic_json(out/'sampling_contract.json',sampling)")
    source=replace_once(source,"out/'reconstruction_config.json',out/'README.json'],{})","out/'reconstruction_config.json',out/'README.json',out/'sampling_contract.json'],{})")
    source=replace_once(source,"'resolution':allcams['resolution'],'protocol':cfg['protocol'],","'resolution':allcams['resolution'],'protocol':sampling['protocol'],")
    source=replace_once(source,"'limited_placements':placements['limited_placements']}","'limited_placements':placements['limited_placements'],'sampling_contract_sha256':file_hash(out/'sampling_contract.json')}")
    changed['src/scanbench/cases.py']=source

    source=(ROOT/'src/scanbench/validate.py').read_text(encoding='utf-8')
    source=replace_once(source,'from .observation_grid import FirstReturnGrid','from .observation_grid import FirstReturnGrid\nfrom .sampling_density import source_scan_settings,verify_case_sampling_contract')
    source=replace_once(source,"expected_frames=cfg['scan']['intervals']//stride+1","verify_case_sampling_contract(record,out)\n    expected_frames=source_scan_settings(sid)['intervals']//stride+1")
    source=replace_once(source,'    """Hash actual referenced payloads too: a stale manifest is never a cache hit."""','    """Hash actual referenced payloads too: a stale manifest is never a cache hit."""\n    verify_case_sampling_contract(record,out)')
    source=replace_once(source,"'README.json','point_provenance.npz']","'README.json','point_provenance.npz','sampling_contract.json']")
    source=replace_once(source,"['validate.py','observation_grid.py','contact_support.py'],['numpy','open3d','trimesh','scipy']","['validate.py','observation_grid.py','contact_support.py','sampling_density.py'],['numpy','open3d','trimesh','scipy']")
    changed['src/scanbench/validate.py']=source

    source=(ROOT/'src/scanbench/supplemental.py').read_text(encoding='utf-8')
    source=replace_once(source,'    rows=[]\n    for placements,stride,kind in [(n,4,\'fixed_49_frames_vary_placements\')',"    rows=[];intervals=max(c['mother_frame_id'] for c in cams)\n    for placements,stride,kind in [(n,4,f'fixed_{intervals//4+1}_frames_vary_placements')")
    source=replace_once(source,"'frames_per_placement':193//stride+int(stride>1)","'frames_per_placement':intervals//stride+1")
    changed['src/scanbench/supplemental.py']=source

    source=(ROOT/'src/scanbench/export.py').read_text(encoding='utf-8')
    source=replace_once(source,"    if not observations_only: names+=", "    if (source/'sampling_contract.json').exists(): names.append('sampling_contract.json')\n    if not observations_only: names+=")
    changed['src/scanbench/export.py']=source

    source=(ROOT/'scripts/render_physical_plan.py').read_text(encoding='utf-8')
    source=replace_once(source,"ax.set_title('All 193 mother positions; sampled sight lines to centre\\nwire box = object bounds, support plane z = 0')","ax.set_title(f'All {len(eyes)} mother positions; sampled sight lines to centre\\nwire box = object bounds, support plane z = 0')")
    changed['scripts/render_physical_plan.py']=source

    diffs=[];hashes={}
    for name,source in changed.items():
        compile(source,name,'exec')
        target=CANDIDATE/name;target.parent.mkdir(parents=True,exist_ok=True)
        atomic_bytes(target,source.encode('utf-8'))
        hashes[name]={'before':file_hash(ROOT/name),'candidate':file_hash(target)}
        diffs.extend(difflib.unified_diff((ROOT/name).read_text(encoding='utf-8').splitlines(keepends=True),source.splitlines(keepends=True),fromfile=name,tofile='candidate/'+name))
    module=CANDIDATE/'src/scanbench/sampling_density.py';compile(module.read_text(encoding='utf-8'),str(module),'exec')
    hashes['src/scanbench/sampling_density.py']={'before':None,'candidate':file_hash(module)}
    atomic_bytes(FOLDER/'candidate_diff.patch',''.join(diffs).encode('utf-8'))
    policy={'schema':'uniform_sampling_density_v2','status':'candidate','protocol':'physical_scan_v2_overlap_density','base_config_sha256':digest(config()),'base_intervals':config()['scan']['intervals'],'allowed_multipliers':[1,2,4,8],'source_intervals':{'245':768},'overlap_p10_min':.5,'quality_gates_changed':False,'noise_frame_parameterization':'exact rational parameter on original mother grid; original integer stream IDs preserved','affected_geometry_or_acquisition_sources':['245'],'basis':{'245':{'path':'reports/density_investigations/245/density_investigation.json','sha256':file_hash(ROOT/'reports/density_investigations/245/density_investigation.json')}},'note':'All other qualified sources retain exactly their existing 192-interval trajectories and observations. New protocol version and public per-case sampling contracts make the density explicit.'}
    atomic_json(CANDIDATE/'configs/sampling_density_v2.json',policy)
    atomic_json(FOLDER/'candidate_manifest.json',{'status':'staged_not_installed','candidate_sha256':hashes,'policy_sha256':file_hash(CANDIDATE/'configs/sampling_density_v2.json'),'current_frozen_core_unchanged':True,'script_sha256':file_hash(Path(__file__)),'time':time.time()})
    print(canonical_json({'status':'staged_not_installed','changed_paths':list(hashes),'current_frozen_core_unchanged':all(file_hash(ROOT/n)==h for n,h in frozen['code_sha256'].items())}))


if __name__=='__main__':main()
