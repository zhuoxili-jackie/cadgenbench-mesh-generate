"""Measure local bridge support against every original noisy return, without fusion."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='2'
import numpy as np
from scipy.spatial import cKDTree
from scanbench.common import *
from scanbench.validate import read_mesh,independent_backproject
cid=sys.argv[1];rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path'];folder=ROOT/f'reports/fragmentation/{cid}/subpixel_regions'
proof=load_json(folder/'diagnosis.json');mesh=read_mesh(out/'mesh.ply')
with np.load(folder/'measurements.npz') as z:ids=z['bridge_face_ids']
weights=np.array([(i/5,j/5,1-(i+j)/5) for i in range(6) for j in range(6-i)]+[(1/3,1/3,1/3)])
points=np.einsum('sk,nkj->nsj',weights,mesh.triangles[ids]).reshape(-1,3)
distance=np.full(len(points),np.inf);frame_index=np.full(len(points),-1,np.int32);point_index=np.full(len(points),-1,np.int32)
refs=load_json(out/'observations.json')['frames'];cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']};hashes={};count=0
for i,fr in enumerate(refs):
    path=(out/fr['path']).resolve();h=file_hash(path);assert h==fr['file_sha256'];hashes[str(path.relative_to(ROOT)).replace('\\','/')]=h
    with np.load(path) as z:observed=independent_backproject(z['pixel'],z['range_mm'],cams[fr['camera_id']])
    count+=len(observed)
    d,k=cKDTree(observed).query(points);better=d<distance
    distance[better]=d[better];frame_index[better]=i;point_index[better]=k[better]
tol=proof['unchanged_support_tolerance_mm'];fraction=float(np.mean(distance<=tol))
atomic_npz(folder/'all_raw_support.npz',triangle_lattice_points_mm=points,nearest_noisy_return_distance_mm=distance,nearest_frame_index=frame_index,nearest_return_index=point_index)
result={'status':'pass' if fraction>=.98 else 'unresolved','case_id':cid,'mesh_sha256':file_hash(out/'mesh.ply'),'script_sha256':file_hash(Path(__file__)),'samples':len(points),'original_noisy_returns':count,'frames':len(refs),'support_tolerance_mm':tol,'supported_fraction':fraction,'maximum_distance_mm':float(distance.max()),'p95_distance_mm':float(np.quantile(distance,.95)),'method':'Exact Euclidean nearest noisy return over every valid pixel of every referenced camera, using independent backprojection; no fused-point subset or private geometry','observation_sha256':hashes,'measurement_sha256':file_hash(folder/'all_raw_support.npz'),'working_point_subset_result_retained_in':'diagnosis.json'}
atomic_json(folder/'all_raw_support.json',result)
print(canonical_json({k:v for k,v in result.items() if k!='observation_sha256'}))
