"""Compare the isolated merge against the original sorter and real cached fusion."""
from pathlib import Path
import os,sys,time,argparse
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
import numpy as np
from scanbench.common import *
from scanbench.reconstruct import reduce_representatives,voxel_keys,resolve_observations
from fusion_merge_candidate import merge_indices,fuse
p=argparse.ArgumentParser();p.add_argument('--cases',nargs='+',default=['case_b8270b4dd4a3b70f']);p.add_argument('--all-existing',action='store_true');args=p.parse_args()
if args.all_existing:args.cases=[p.parent.parent.parent.name for p in sorted((ROOT/'data/cases').glob('*/input/.reconstruction_cache/fusion.npz'))]
rng=np.random.default_rng(7613);checks=[]
for iteration in range(80):
    parts=[]
    for side in range(2):
        count=0 if iteration%11==side else 3000
        xyz=rng.integers(-10,11,(count,3)).astype(float)+rng.random((count,3))*.2
        normal=np.eye(3)[rng.integers(0,3,count)]*rng.choice([-1,1],(count,1))
        frames=rng.integers(0,6,count,dtype=np.int32);pixels=rng.integers(0,768**2,count,dtype=np.uint32);confidence=rng.integers(0,5,count).astype(float)/4
        if count:part=reduce_representatives(xyz,normal,frames,pixels,confidence,1.)
        else:part=(xyz,normal,frames,pixels,confidence)
        parts.append(part)
    a,b=parts
    if not len(a[0]) and not len(b[0]):continue
    ka=voxel_keys(a[0],a[1],1.).view(np.int64).reshape(-1,4);kb=voxel_keys(b[0],b[1],1.).view(np.int64).reshape(-1,4)
    ids=merge_indices(ka,kb,a[4],b[4],a[2],b[2],a[3],b[3]);joined=[np.concatenate([x,y]) for x,y in zip(a,b)];actual=[x[ids] for x in joined]
    expected=reduce_representatives(*joined,1.)
    for x,y in zip(actual,expected):np.testing.assert_array_equal(x,y)
    checks.append(iteration)
for cid in args.cases:
    folder=ROOT/f'data/cases/{cid}/input';fm=load_json(folder/'.reconstruction_cache/fusion.json');fp=folder/'.reconstruction_cache/fusion.npz';assert file_hash(fp)==fm['file_hash']
    report_path=ROOT/f'reports/tests/fusion_merge_candidate/{cid}.json'
    bindings={'original_fusion_npz_sha256':file_hash(fp),'observations_sha256':file_hash(folder/'observations.json'),'cameras_sha256':file_hash(folder/'cameras.json'),'candidate_code_sha256':file_hash(ROOT/'scripts/fusion_merge_candidate.py'),'original_code_sha256':file_hash(ROOT/'src/scanbench/reconstruct.py')}
    prior=load_json(report_path) if report_path.exists() else {}
    if prior.get('status')=='pass' and all(prior.get(k)==v for k,v in bindings.items()):
        print(canonical_json({'case_id':cid,'status':'reuse_exact_fusion_equivalence_proof'}),flush=True);continue
    cams={c['id']:c for c in load_json(folder/'cameras.json')['cameras']};frames=resolve_observations(folder/'observations.json');start=time.perf_counter();P,N,F,U,metrics=fuse(frames,cams,config()['reconstruction']);elapsed=time.perf_counter()-start
    with np.load(fp) as prior:
        for key,arr in zip(['P','N','F','U'],[P,N,F,U]):np.testing.assert_array_equal(arr,prior[key])
    assert metrics==fm['metrics']
    result={'status':'pass','case_id':cid,'random_tie_negative_key_empty_input_controls':len(checks),'all_float64_points_normals_frame_pixel_order_and_metrics_exact':True,'seconds':elapsed,'frames':len(frames),'working_points':len(P),'original_fusion_npz_sha256':file_hash(fp),'observations_sha256':file_hash(folder/'observations.json'),'cameras_sha256':file_hash(folder/'cameras.json'),'candidate_code_sha256':file_hash(ROOT/'scripts/fusion_merge_candidate.py'),'original_code_sha256':file_hash(ROOT/'src/scanbench/reconstruct.py')}
    atomic_json(report_path,result);print(canonical_json(result),flush=True)
