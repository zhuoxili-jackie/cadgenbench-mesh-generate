"""Check finite proposals on two box controls and the diagnosed production source."""
from pathlib import Path
import os,sys,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
import numpy as np,trimesh
from scipy.spatial.transform import Rotation
from hull_pose_proposals import propose
from scanbench.common import *
rows=[]
for name,vertices,com in [('box',trimesh.creation.box(extents=[20,30,40]).vertices,np.zeros(3)),('rotated_offset_box',trimesh.creation.box(extents=[20,30,40]).vertices@Rotation.from_euler('xyz',[23,47,13],degrees=True).as_matrix().T+np.array([5,8,-9]),np.array([5,8,-9]))]:
    ts,details=propose(vertices,com);assert len(ts)==6
    for T in ts:
        w=vertices@T[:3,:3].T+T[:3,3];assert abs(w[:,2].min())<1e-10
        assert abs(np.linalg.det(T[:3,:3])-1)<1e-12
    rows.append({'control':name,'status':'pass',**details})
for sid in ['201','231']:
    raw=np.load(ROOT/f'private/gt/{sid}/mesh.npz');meta=load_json(ROOT/f'private/gt/{sid}/metadata.json');start=time.time();ts,details=propose(raw['vertices'],meta['center_mass_object_mm']);assert len(ts)>0
    chosen=load_json(ROOT/f'private/gt/{sid}/placements.json')['placements']
    assert all(any(np.dot(-T[2,:3],p['support_outward_object'])>.9999 for T in ts) for p in chosen)
    rows.append({'source':sid,'source_sha256':meta['source_sha256'],'mesh_sha256':file_hash(ROOT/f'private/gt/{sid}/mesh.npz'),'status':'pass','seconds':time.time()-start,'all_previously_certified_poses_proposed':True,**details})
result={'status':'pass','test_script_sha256':file_hash(Path(__file__)),'proposal_code_sha256':file_hash(ROOT/'scripts/hull_pose_proposals.py'),'tests':rows,'scope':'finite support proposal generation; exact CAD certification remains a separate unchanged stage'}
atomic_json(ROOT/'reports/tests/hull_pose_proposals.json',result);print(canonical_json(result))
