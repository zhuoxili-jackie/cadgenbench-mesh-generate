from pathlib import Path
import sys,os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
import numpy as np,trimesh,open3d as o3d
from scanbench.common import *
from scanbench.validate import *
cid=sys.argv[1];rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path'];dest=ROOT/f'reports/fragmentation/{cid}'
mesh=read_mesh(out/'mesh.ply');patch=read_mesh(dest/'visible_reference_patch.ply');scene=distance_scene(patch)
comps=trimesh.graph.connected_components(patch.face_adjacency,nodes=np.arange(len(patch.faces)),min_len=1);comps=sorted(comps,key=lambda c:patch.area_faces[c].sum(),reverse=True);labels=np.full(len(patch.faces),-1)
for i,c in enumerate(comps):labels[c]=i
mcomps=trimesh.graph.connected_components(mesh.face_adjacency,nodes=np.arange(len(mesh.faces)),min_len=1);mcomps=sorted(mcomps,key=lambda c:mesh.area_faces[c].sum(),reverse=True);result=[]
for i,c in enumerate(mcomps):
    if mesh.area_faces[c].sum()<.01*mesh.area:continue
    sub=mesh.submesh([c],append=True,repair=False);pts,_=sample_area(sub,10000,710+i);closest=scene.compute_closest_points(o3d.core.Tensor(pts.astype(np.float32)),nthreads=2);labs=labels[closest['primitive_ids'].numpy()];dist=np.linalg.norm(closest['points'].numpy()-pts,axis=1)
    result.append({'mesh_component':i,'reference_component':int(np.bincount(labs).argmax()),'reference_component_purity':float(np.bincount(labs).max()/len(labs)),'distance_p95':float(np.quantile(dist,.95)),'area_mm2':float(sub.area)})
print(canonical_json(result));atomic_json(dest/'component_correspondence.json',result)
