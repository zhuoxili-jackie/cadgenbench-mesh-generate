"""Compare every real representative against the original stable-union method."""
from pathlib import Path
import os,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.validate import independent_backproject
from scanbench.observation_grid import FirstReturnGrid
cid=sys.argv[1];out=ROOT/f'data/cases/{cid}/input';cameras={c['id']:c for c in load_json(out/'cameras.json')['cameras']};refs=load_json(out/'observations.json')['frames'];voxel=np.median([(c['near_mm']+c['far_mm'])/2/c['K'][0][0] for c in cameras.values()]);old=np.empty((0,3));grid=FirstReturnGrid(voxel);oldtime=0;newtime=0;count=0
for i,frame in enumerate(refs):
    d=np.load((out/frame['path']).resolve());points=independent_backproject(d['pixel'].astype(np.int64),d['range_mm'],cameras[frame['camera_id']]);count+=len(points)
    start=time.perf_counter();allpoints=np.concatenate([old,points]);keys=np.floor(allpoints/voxel).astype(np.int32);_,ix=np.unique(keys,axis=0,return_index=True);old=allpoints[ix];oldtime+=time.perf_counter()-start
    start=time.perf_counter();grid.add(points);newtime+=time.perf_counter()-start
    if i%50==0:print(f'grid equivalence {i+1}/{len(refs)} cells={len(old)}',flush=True)
start=time.perf_counter();new=grid.result();newtime+=time.perf_counter()-start;np.testing.assert_array_equal(old,new)
result={'status':'pass','case_id':cid,'observations_sha256':file_hash(out/'observations.json'),'cameras_sha256':file_hash(out/'cameras.json'),'grid_code_sha256':file_hash(ROOT/'src/scanbench/observation_grid.py'),'all_valid_returns':count,'spatial_cells':len(old),'every_float64_representative_and_lexicographic_order_identical':True,'representative_array_sha256':hashlib.sha256(old.astype('<f8').tobytes()).hexdigest(),'old_repeated_union_seconds':oldtime,'new_incremental_seconds':newtime,'voxel_mm':voxel,'scope':'all real noisy frames, including both placements; preserves earliest frame/pixel representative and final lexicographic order, so fixed PCG64 sampling is unchanged'}
atomic_json(ROOT/'reports/tests/observation_grid_equivalence.json',result);print(canonical_json(result))
