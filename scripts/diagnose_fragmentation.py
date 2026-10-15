"""Independent diagnostic only; never used to create delivered meshes."""
from pathlib import Path
import sys,os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
import numpy as np
import trimesh,open3d as o3d
from scanbench.common import *
from scanbench.validate import read_mesh,distance_scene,distances,independent_backproject
from scanbench.render import atlas

cid=sys.argv[1];rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path'];sid=rec['source_id']
dest=ROOT/f'reports/fragmentation/{cid}';dest.mkdir(parents=True,exist_ok=True)
mesh=read_mesh(out/'mesh.ply');scene=distance_scene(mesh);raw=np.load(ROOT/f'private/gt/{sid}/mesh.npz');gt=trimesh.Trimesh(raw['vertices'],raw['faces'],process=False);gscene=distance_scene(gt)
cams=load_json(out/'cameras.json')['cameras'];places=load_json(ROOT/f'private/gt/{sid}/placements.json')['placements'];meta=load_json(ROOT/f'private/gt/{sid}/metadata.json');recon=load_json(out/'reconstruction.json')
comps=trimesh.graph.connected_components(mesh.face_adjacency,nodes=np.arange(len(mesh.faces)),min_len=1);comps=sorted(comps,key=lambda c:mesh.area_faces[c].sum(),reverse=True)
summary=[]
for c in comps[:8]:
    area=mesh.area_faces[c];p=mesh.triangles_center[c];summary.append({'area':float(area.sum()),'centroid':np.average(p,weights=area,axis=0),'bounds':[p.min(0),p.max(0)]})
print(canonical_json({'mesh_largest_components':summary}),flush=True)
# Seven independent intra-face samples classify the visible reference patch. This
# diagnostic does not claim exact visibility at subtriangle silhouettes.
w=np.array([[1/3]*3,[.8,.1,.1],[.1,.8,.1],[.1,.1,.8],[.45,.45,.1],[.1,.45,.45],[.45,.1,.45]])
pts=np.einsum('sk,nkj->nsj',w,gt.triangles).reshape(-1,3);normals=np.repeat(gt.face_normals,len(w),axis=0);visible=np.zeros(len(pts),bool)
for cam in cams:
    C=np.asarray(cam['T_object_from_camera']);v=pts-C[:3,3];ran=np.linalg.norm(v,axis=1);direction=v/ran[:,None];hit=gscene.cast_rays(o3d.core.Tensor(np.column_stack([np.broadcast_to(C[:3,3],pts.shape),direction]).astype(np.float32)),nthreads=2)['t_hit'].numpy()
    T=np.asarray(places[cam['placement_id']]['T_table_from_object']);eye=T[:3,:3]@C[:3,3]+T[:3,3];dz=direction@T[2,:3];table=np.full(len(pts),np.inf);down=dz<0;table[down]=-eye[2]/dz[down]
    visible|=(abs(hit-ran)<max(meta['diagonal_mm']*2e-6,1e-4))&(table>ran+places[cam['placement_id']]['epsilon_contact_mm'])&(-np.einsum('ij,ij->i',normals,direction)>=np.cos(np.deg2rad(75)))
face_visible=visible.reshape(-1,len(w)).any(1);patch=gt.submesh([np.flatnonzero(face_visible)],append=True,repair=False)
pc=trimesh.graph.connected_components(patch.face_adjacency,nodes=np.arange(len(patch.faces)),min_len=1);pa=sorted([float(patch.area_faces[c].sum()) for c in pc],reverse=True)
print(canonical_json({'visible_reference_component_areas':pa[:12],'visible_reference_area':float(patch.area)}),flush=True)
patch.export(dest/'visible_reference_patch.ply');atlas(dest/'visible_reference_patch.ply',meta['bounds_object_mm'],places[0]['support_outward_object'],dest/'visible_reference.png','DIAGNOSTIC: sampled visible GT faces; not reconstruction',color=(150,157,164))
organized=[];refs=load_json(out/'observations.json')['frames'];cammap={c['id']:c for c in cams}
for recframe in refs:
    cam=cammap[recframe['camera_id']];d=np.load((out/recframe['path']).resolve());pix=d['pixel'].astype(np.int64);p=independent_backproject(pix,d['range_mm'],cam);res=cam['resolution'];idx=np.full(res*res,-1,np.int32);idx[pix]=np.arange(len(pix));idx=idx.reshape(res,res)
    a=idx[:-1,:-1].ravel();b=idx[:-1,1:].ravel();c=idx[1:,:-1].ravel();e=idx[1:,1:].ravel();f=np.concatenate([np.column_stack([a,b,c]),np.column_stack([b,e,c])]);f=f[(f>=0).all(1)];tri=p[f];length=np.linalg.norm(tri-np.roll(tri,1,axis=1),axis=2);spacing=np.mean(d['range_mm'][f],axis=1)/cam['K'][0][0];keep=length.max(1)<4.5*spacing;tri=tri[keep]
    area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
    rng=np.random.default_rng(724);sel=rng.choice(len(tri),min(5000,len(tri)),replace=False,p=area/area.sum());dist=distances(scene,tri[sel].mean(1));tol=recon['filtering']['support_tolerance_mm']
    organized.append({'camera_id':cam['id'],'triangles':len(tri),'area_mm2':float(area.sum()),'n':len(sel),'fraction_centroids_within_tolerance_of_bpa':float((dist<=tol).mean()),'fraction_within_0_1h':float((dist<=.1*recon['fusion']['h_mm']).mean()),'distance_p95_mm':float(np.quantile(dist,.95))})
    if cam['id']==refs[0]['camera_id']:
        diagnostic=trimesh.Trimesh(p,f[keep],process=False);diagnostic.export(dest/'organized_first_frame.ply');atlas(dest/'organized_first_frame.ply',meta['bounds_object_mm'],places[0]['support_outward_object'],dest/'organized_first_frame.png','DIAGNOSTIC: one noisy range image, no cross-frame fusion')
result={'case_id':cid,'mesh_sha256':file_hash(out/'mesh.ply'),'mesh_components':summary,'visible_reference_component_areas_mm2':pa,'visible_reference_total_area_mm2':float(patch.area),'visible_reference_method':'7 barycentric samples per actual GT face; 49 actual cameras, first-hit/table/incidence; any visible sample retains face; diagnostic approximation only','organized_noisy_frame_comparison':organized,'organized_comparison_mean_retained':float(np.mean([a['fraction_centroids_within_tolerance_of_bpa'] for a in organized])),'status':'diagnostic_only_requires_interpretation'}
atomic_json(dest/'diagnosis.json',result);print(canonical_json({k:v for k,v in result.items() if k not in ['organized_noisy_frame_comparison','mesh_components','visible_reference_component_areas_mm2']}))
