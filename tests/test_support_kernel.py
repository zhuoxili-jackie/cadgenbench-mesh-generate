import numpy as np
from scanbench.common import ROOT,load_json,atomic_json,file_hash
from scanbench.reconstruct import sample_triangles,support_in_camera,support_in_camera_numpy

def test_compiled_support_matches_numpy():
    base=ROOT/'data/cases/case_2438b1a3fd780c63/input'
    cache=np.load(base/'.reconstruction_cache/bpa.npz')
    pts=sample_triangles(cache['vertices'],cache['faces'][::13]).reshape(-1,3)
    cams=load_json(base/'cameras.json')['cameras']; frames=load_json(base/'observations.json')['frames']; compared=0
    for j in [0,10,25,48]:
        d=np.load((base/frames[j]['path']).resolve()); res=cams[j]['resolution']; img=np.full(res*res,np.nan,np.float32); img[d['pixel']]=d['range_mm']; img=img.reshape(res,res)
        expected=support_in_camera_numpy(pts,img,cams[j],1.367621134689279); got=support_in_camera(pts,img,cams[j],1.367621134689279)
        np.testing.assert_array_equal(got[0],expected[0]);np.testing.assert_array_equal(got[1],expected[1]); compared+=len(pts)
    atomic_json(ROOT/'reports/tests/compiled_support_equivalence.json',{'status':'pass','sample_camera_pairs':compared,'support_array_identical':True,'free_space_array_identical':True,'fastmath':False,'kernel_sha256':file_hash(ROOT/'src/scanbench/observed_kernel.py')})
