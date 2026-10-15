"""Independent geometry, actual old-noise and compatibility controls for density v2."""
from pathlib import Path
import os,sys,ast,copy,importlib.util
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
from scanbench.common import *
from scanbench.camera import trajectory
from scanbench.scan import noise_for

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'
CANDIDATE=FOLDER/'candidate'


def functions(path):
    return {node.name:node for node in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}


def same(left,right):return ast.dump(left,include_attributes=False)==ast.dump(right,include_attributes=False)


class Normalize(ast.NodeTransformer):
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='verify_case_sampling_contract':return None
        return self.generic_visit(node)
    def visit_List(self,node):
        node=self.generic_visit(node)
        node.elts=[x for x in node.elts if not (isinstance(x,ast.Constant) and x.value in ['sampling_density.py','sampling_contract.json'])]
        return node
    def visit_Call(self,node):
        node=self.generic_visit(node)
        if isinstance(node.func,ast.Name) and node.func.id=='source_scan_settings':
            return ast.parse("cfg['scan']",mode='eval').body
        if isinstance(node.func,ast.Name) and node.func.id=='noise_frame_key':
            return ast.parse("camera['mother_frame_id']",mode='eval').body
        return node


def compatibility():
    rows=[]
    allowed={'scan.py':{'prepare_cameras','acquire_scans'},'cases.py':{'prepare_case'},'validate.py':{'physical_case_check','validation_fingerprint'},'supplemental.py':{'source_factors'},'export.py':{'export_case'}}
    for filename,changed in allowed.items():
        old=functions(ROOT/'src/scanbench'/filename)
        new=functions(CANDIDATE/'src/scanbench'/filename)
        assert set(old)==set(new),filename
        unchanged=[]
        for name in old.keys()-changed:
            assert same(old[name],new[name]),(filename,name)
            unchanged.append(name)
        rows.append({'module':filename,'identical_functions':sorted(unchanged),'reviewed_metadata_or_schedule_functions':sorted(changed)})
    for name in ['physical_case_check','validation_fingerprint']:
        old=functions(ROOT/'src/scanbench/validate.py')[name]
        new=Normalize().visit(copy.deepcopy(functions(CANDIDATE/'src/scanbench/validate.py')[name]))
        if name=='physical_case_check':
            # The only numeric expression changed is the source-specific interval lookup.
            assert same(old,new),name
        else:assert same(old,new),name
    old=functions(ROOT/'src/scanbench/scan.py')['acquire_scans']
    new=Normalize().visit(copy.deepcopy(functions(CANDIDATE/'src/scanbench/scan.py')['acquire_scans']))
    assert same(old,new),'acquisition arithmetic changed beyond declared scheduling, frame-key and fingerprint additions'
    source=(ROOT/'src/scanbench/export.py').read_text(encoding='utf-8')
    candidate=(CANDIDATE/'src/scanbench/export.py').read_text(encoding='utf-8')
    def rebuild_constant(text):
        return next(n.value.value for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REBUILD' for t in n.targets))
    assert rebuild_constant(source)==rebuild_constant(candidate)
    for name in ['reconstruct.py','observed_kernel.py','continuous_free_space.py','camera.py','observation_grid.py','contact_support.py']:
        frozen=load_json(ROOT/'reports/protocol_freeze.json')['code_sha256']
        assert file_hash(ROOT/'src/scanbench'/name)==frozen['src/scanbench/'+name]
    return rows


def main():
    started=time.time()
    ast_rows=compatibility()
    candidate_module=CANDIDATE/'src/scanbench/sampling_density.py'
    spec=importlib.util.spec_from_file_location('scanbench.sampling_density_candidate',candidate_module)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    controls=FOLDER/'controls';controls.mkdir(parents=True,exist_ok=True)
    fixture=controls/'fixture_policy.json'
    policy=load_json(CANDIDATE/'configs/sampling_density_v2.json');policy['status']='frozen'
    atomic_json(fixture,policy);module.POLICY_PATH=fixture
    cfg=config();base=cfg['scan']['intervals'];scan=module.source_scan_settings('245')
    assert scan['intervals']==768
    default_ids=[sid for sid in IDS if sid not in policy['source_intervals']]
    for sid in default_ids:assert module.source_scan_settings(sid)==cfg['scan']
    trajectory_rows=[]
    # Box with known exact dimensions; contact plane z=0, no source CAD read.
    vertices=np.array([[x,y,z] for x in [-10.,10.] for y in [-15.,15.] for z in [0.,10.]])
    T=np.eye(4)
    original=trajectory(vertices,T,cfg['scan'],96,0)
    for factor in [1,2,4,8]:
        settings={**cfg['scan'],'intervals':base*factor}
        cams=trajectory(vertices,T,settings,96,0)
        for j,old in enumerate(original):
            new=cams[j*factor]
            for field in ['K','T_object_from_camera','T_table_from_camera','near_mm','far_mm','resolution']:
                np.testing.assert_array_equal(old[field],new[field])
            assert module.noise_frame_key(new,settings)==j
        center=np.array([0.,0.,5.]);eyes=np.array([np.asarray(c['T_table_from_camera'])[:3,3] for c in cams])
        delta=eyes-center
        angles=np.unwrap(np.arctan2(delta[:,1],delta[:,0]));elevation=np.rad2deg(np.arctan2(delta[:,2],np.linalg.norm(delta[:,:2],axis=1)))
        assert abs(np.rad2deg(angles[-1]-angles[0])-1080)<1e-9
        assert np.all(np.diff(angles)>0) and np.all(np.diff(elevation)<0)
        assert abs(elevation[0]-75)<1e-10 and abs(elevation[-1]-5)<1e-10
        assert eyes[:,2].min()>0
        for cam in cams:
            C=np.asarray(cam['T_table_from_camera']);toward=center-C[:3,3];toward/=np.linalg.norm(toward)
            np.testing.assert_allclose(C[:3,2],toward,atol=1e-13)
        counts={level:sum(c['mother_frame_id']%entry['stride']==0 for c in cams) for level,entry in cfg['difficulty'].items()}
        assert counts=={level:base*factor//entry['stride']+1 for level,entry in cfg['difficulty'].items()}
        sets={level:{c['id'] for c in cams if c['mother_frame_id']%entry['stride']==0} for level,entry in cfg['difficulty'].items()}
        assert sets['hard']<=sets['medium']<=sets['easy']
        keys=[module.noise_frame_key(c,settings) for c in cams]
        assert len(set(map(lambda x:(type(x).__name__,x),keys)))==len(cams)
        trajectory_rows.append({'factor':factor,'intervals':base*factor,'frames':counts,'exact_old_positions':len(original),'complete_turns':3,'all_above_table':True,'old_noise_integer_keys_preserved':True,'all_frame_keys_unique':True})
    # Existing source 245: exact physical matrices and RNG identifiers at every old position.
    old_cameras=load_json(ROOT/'private/gt/245/cameras.json')['cameras']
    dense_cameras=load_json(ROOT/'reports/density_investigations/245/cameras_768.json')['cameras']
    dense={(c['placement_id'],c['mother_frame_id']):c for c in dense_cameras}
    for old in old_cameras:
        current=dense[(old['placement_id'],old['mother_frame_id']*4)]
        for field in ['K','T_object_from_camera','T_table_from_camera','near_mm','far_mm','resolution']:
            np.testing.assert_array_equal(old[field],current[field])
        key=module.noise_frame_key(current,scan)
        assert key==old['mother_frame_id']
        for seed in cfg['seeds']:
            assert stable_seed(scan['noise_algorithm'],'245',seed,current['placement_id'],key)==stable_seed(scan['noise_algorithm'],'245',seed,old['placement_id'],old['mother_frame_id'])
    paired=0;actual_noise=[]
    sigma=load_json(ROOT/'private/gt/245/cameras.json')['sigma_mm']
    for pid in range(3):
        for frame in [0,48,96,144,192]:
            camera_id=f'p{pid:02d}_f{frame:04d}'
            index=load_json(ROOT/f'private/scan_index/245/{camera_id}.json')
            path=ROOT/f'cache/clean/245/{camera_id}.npz'
            with np.load(path) as clean:
                select=np.arange(0,len(clean['pixel']),max(1,len(clean['pixel'])//512))
                pixel=clean['pixel'][select];ranges=clean['range_mm'][select]
            for seed in cfg['seeds']:
                observed=ROOT/'data'/index['seeds'][str(seed)]['observation']
                assert file_hash(observed)==index['seeds'][str(seed)]['file_sha256']
                with np.load(observed) as z:
                    np.testing.assert_array_equal(z['pixel'][select],pixel)
                    expected=z['range_mm'][select]
                key=module.noise_frame_key(dense[(pid,frame*4)],scan)
                stream=stable_seed(scan['noise_algorithm'],'245',seed,pid,key)
                actual=(ranges.astype(np.float64)+noise_for(pixel,stream,sigma)).astype(np.float32)
                np.testing.assert_array_equal(actual,expected)
                paired+=len(pixel)
            actual_noise.append({'camera':camera_id,'clean_sha256':file_hash(path),'sampled_pixels_per_seed':len(pixel)})
    # Reject tampering and undeclared physical settings rather than accepting stale metadata.
    negative=[]
    for label,change in [('candidate_not_frozen',{'status':'candidate'}),('coarser_density',{'source_intervals':{'245':96}}),('non_multiple_density',{'source_intervals':{'245':770}}),('unknown_source',{'source_intervals':{'999':768}}),('changed_quality_gate',{'overlap_p10_min':.1}),('wrong_base_config',{'base_config_sha256':'0'*64})]:
        atomic_json(fixture,{**policy,**change})
        try:module.source_scan_settings('245')
        except (AssertionError,RuntimeError):negative.append(label)
        else:raise AssertionError('invalid sampling policy accepted: '+label)
    atomic_json(fixture,policy)
    original_root=module.ROOT;fixture_root=controls/'freeze_binding_fixture';freeze_path=fixture_root/'reports/protocol_freeze.json'
    module.ROOT=fixture_root
    atomic_json(freeze_path,{'physical_sampling_policy':{'path':'configs/sampling_density_v2.json','sha256':file_hash(fixture)}})
    assert module.source_scan_settings('245')['intervals']==768
    changed={**policy,'source_intervals':{'245':1536}};atomic_json(fixture,changed)
    try:module.source_scan_settings('245')
    except AssertionError:negative.append('valid_but_unfrozen_density_change_rejected')
    else:raise AssertionError('policy mutation bypassed the physical freeze')
    atomic_json(fixture,policy)
    atomic_json(freeze_path,{'physical_sampling_policy':{'path':'configs/wrong_policy.json','sha256':file_hash(fixture)}})
    try:module.source_scan_settings('245')
    except AssertionError:negative.append('incorrect_frozen_policy_path_rejected')
    else:raise AssertionError('wrong frozen policy path accepted')
    module.ROOT=original_root
    out=controls/'public_contract';out.mkdir(exist_ok=True)
    contract=module.case_sampling_contract('245','hard',1)
    assert contract['mother_intervals']==768 and contract['frames_per_placement']==193
    assert 'source_id' not in contract and 'GT' not in contract
    atomic_json(out/'sampling_contract.json',contract)
    record={'source_id':'245','level':'hard','placement_count':1,'protocol':policy['protocol'],'sampling_contract_sha256':file_hash(out/'sampling_contract.json')}
    assert module.verify_case_sampling_contract(record,out)==contract
    atomic_json(out/'sampling_contract.json',{**contract,'mother_intervals':192})
    try:module.verify_case_sampling_contract(record,out)
    except AssertionError:negative.append('tampered_public_sampling_contract')
    else:raise AssertionError('tampered public sampling contract accepted')
    atomic_json(out/'sampling_contract.json',contract)
    density=load_json(ROOT/'reports/density_investigations/245/density_investigation.json')
    chosen=next(r for r in density['trials'] if r['intervals']==768)
    assert chosen['all_p10_pass'] and density['minimum_tested_passing_intervals']==768
    freeze=load_json(ROOT/'reports/protocol_freeze.json')
    assert all(file_hash(ROOT/n)==h for n,h in freeze['code_sha256'].items())
    report={'status':'pass','scope':'candidate controls only; frozen production core, formal scans and meshes remain unchanged','script_sha256':file_hash(Path(__file__)),'candidate_manifest_sha256':file_hash(FOLDER/'candidate_manifest.json'),'candidate_module_sha256':file_hash(candidate_module),'policy_template_sha256':file_hash(CANDIDATE/'configs/sampling_density_v2.json'),'AST_compatibility':ast_rows,'analytic_trajectory_controls':trajectory_rows,'actual_source245_old_camera_positions_verified':len(old_cameras),'actual_source245_bitwise_noise_samples':paired,'actual_noise_evidence':actual_noise,'negative_controls':negative,'density_trial_overlap_p10':{k:v['p10'] for k,v in chosen['levels'].items()},'default_source_settings_identical':default_ids,'current_frozen_core_unchanged':True,'seconds':time.time()-started,'time':time.time()}
    atomic_json(FOLDER/'candidate_controls.json',report)
    print(canonical_json({k:v for k,v in report.items() if k not in ['actual_noise_evidence','AST_compatibility','default_source_settings_identical']}))


if __name__=='__main__':main()
