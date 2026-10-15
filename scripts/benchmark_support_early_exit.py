from pathlib import Path
import sys,os,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.reconstruct import sample_triangles,support_in_camera_numpy
from scanbench.observed_kernel import range_support
path=ROOT/'src/scanbench/observed_kernel.py';source=path.read_text();block='        # Patch minimum cannot exceed its finite centre value.\n        if ran>=rr-tolerance: continue\n';assert block not in source
candidate=source.replace('        lo=np.inf; hi=-np.inf; allfinite=True\n',block+'        lo=np.inf; hi=-np.inf; allfinite=True\n');scope={};exec(compile(candidate.replace('cache=True','cache=False'),'early_exit_candidate','exec'),scope);fast=scope['range_support']
atomic_bytes(ROOT/'reports/pilot_comparison/observed_kernel_before_early_exit.py',path.read_bytes())
base=ROOT/'data/cases/case_2438b1a3fd780c63/input';cache=np.load(base/'.reconstruction_cache/bpa.npz');pts=sample_triangles(cache['vertices'],cache['faces'][::13]).reshape(-1,3);cams=load_json(base/'cameras.json')['cameras'];frames=load_json(base/'observations.json')['frames'];compared=0;oldtime=0;newtime=0
for j in [0,10,25,48]:
    d=np.load((base/frames[j]['path']).resolve());c=cams[j];res=c['resolution'];img=np.full(res*res,np.nan,np.float32);img[d['pixel']]=d['range_mm'];img=img.reshape(res,res);C=np.array(c['T_object_from_camera']);K=np.array(c['K']);args=(img,np.ascontiguousarray(C[:3,:3]),np.ascontiguousarray(C[:3,3]),K[0,0],K[1,1],K[0,2],K[1,2],1.367621134689279)
    range_support(pts[:10],*args);fast(pts[:10],*args);start=time.perf_counter();old=range_support(pts,*args);oldtime+=time.perf_counter()-start;start=time.perf_counter();new=fast(pts,*args);newtime+=time.perf_counter()-start;expected=support_in_camera_numpy(pts,img,c,1.367621134689279)
    for a,b,e in zip(old,new,expected):np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(b,e)
    compared+=len(pts)
atomic_json(ROOT/'reports/tests/support_early_exit_equivalence.json',{'status':'pass','sample_camera_pairs':compared,'old_compiled_new_compiled_and_independent_numpy_masks_exact':True,'original_kernel_sha256':file_hash(path),'candidate_kernel_sha256':hashlib.sha256(candidate.encode()).hexdigest(),'old_seconds':oldtime,'new_seconds':newtime,'proof':'3x3 patch includes centre rr, so its minimum <= rr; ran >= rr-tolerance logically precludes ran < patch_min-tolerance. No arithmetic or tolerance changed.'})
print(canonical_json(load_json(ROOT/'reports/tests/support_early_exit_equivalence.json')))
