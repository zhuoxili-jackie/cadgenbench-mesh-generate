"""Read-only independent localization of an actual surface/free-space conflict."""
from pathlib import Path
import os,sys,argparse,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.validate import read_mesh,sample_area
from scanbench.reconstruct import sample_triangles,support_in_camera,support_in_camera_numpy

p=argparse.ArgumentParser();p.add_argument('case_id');args=p.parse_args();cid=args.case_id
out=ROOT/f'data/cases/{cid}/input';destination=ROOT/f'reports/free_space_investigations/{cid}';destination.mkdir(parents=True,exist_ok=True)
mesh=read_mesh(out/'mesh.ply');samples,face_ids=sample_area(mesh,30000,2901)
refs=load_json(out/'observations.json')['frames'];cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']}
tol=load_json(out/'reconstruction.json')['filtering']['support_tolerance_mm'];witnesses=[];started=time.time()
for ordinal,frame in enumerate(refs):
    cam=cams[frame['camera_id']];res=cam['resolution'];K=np.asarray(cam['K']);T=np.asarray(cam['T_object_from_camera'])
    points=(samples-T[:3,3])@T[:3,:3];ranges=np.linalg.norm(points,axis=1)
    uv=np.rint(points[:,:2]/points[:,2,None]*[K[0,0],K[1,1]]+[K[0,2],K[1,2]]).astype(int)
    ids=np.flatnonzero((points[:,2]>0)&(uv[:,0]>=1)&(uv[:,0]<res-1)&(uv[:,1]>=1)&(uv[:,1]<res-1))
    with np.load((out/frame['path']).resolve()) as z:
        img=np.full(res*res,np.nan,np.float32);img[z['pixel']]=z['range_mm'];img=img.reshape(res,res)
    x,y=uv[ids].T;patch=np.stack([img[y+dy,x+dx] for dy in [-1,0,1] for dx in [-1,0,1]],axis=1)
    stable=np.isfinite(patch).all(axis=1)&(patch.max(1)-patch.min(1)<2*tol)
    bad=stable&(ranges[ids]<patch.min(1)-tol)
    for local in np.flatnonzero(bad):
        sample_id=int(ids[local]);fid=int(face_ids[sample_id]);tri=mesh.triangles[fid]
        lattice=sample_triangles(mesh.vertices,mesh.faces[[fid]]).reshape(-1,3)
        weights=np.asarray([(i/80,j/80,1-(i+j)/80) for i in range(81) for j in range(81-i)])
        dense=weights@tri
        one_numpy=support_in_camera_numpy(samples[[sample_id]],img,cam,tol)
        one_compiled=support_in_camera(samples[[sample_id]],img,cam,tol)
        lattice_ok,lattice_bad=support_in_camera(lattice,img,cam,tol)
        dense_ok,dense_bad=support_in_camera(dense,img,cam,tol)
        row={'sample_id':sample_id,'face_id':fid,'camera_id':frame['camera_id'],'frame_ordinal':ordinal,'pixel_xy':uv[sample_id].tolist(),'point_mm':samples[sample_id].tolist(),'triangle_vertices_mm':tri.tolist(),'triangle_area_mm2':float(mesh.area_faces[fid]),'range_mm':float(ranges[sample_id]),'observed_3x3_ranges_mm':patch[local].reshape(3,3).tolist(),'float32_patch_threshold_mm':float(patch[local].min()-tol),'float64_patch_threshold_mm':float(patch[local].min())-tol,'float64_conflict_margin_mm':float(patch[local].min())-tol-float(ranges[sample_id]),'numpy_point_conflict':bool(one_numpy[1][0]),'compiled_point_conflict':bool(one_compiled[1][0]),'lattice_conflicts':int(lattice_bad.sum()),'dense_count':len(dense),'dense_conflicts':int(dense_bad.sum()),'observation_file':str((out/frame['path']).resolve().relative_to(ROOT)).replace('\\','/'),'observation_sha256':file_hash((out/frame['path']).resolve())}
        witnesses.append(row);print(canonical_json(row),flush=True)
    if ordinal%100==0:print(canonical_json({'frame':ordinal,'frames':len(refs),'witnesses':len(witnesses)}),flush=True)
result={'status':'diagnostic_complete','case_id':cid,'mesh_sha256':file_hash(out/'mesh.ply'),'observations_sha256':file_hash(out/'observations.json'),'cameras_sha256':file_hash(out/'cameras.json'),'tolerance_mm':tol,'unique_conflicting_samples':len({r['sample_id'] for r in witnesses}),'witnesses':witnesses,'samples':30000,'sample_seed':2901,'no_geometry_modified':True,'no_gt_read':True,'script_sha256':file_hash(Path(__file__)),'seconds':time.time()-started}
atomic_json(destination/'witnesses.json',result)
print(canonical_json({'status':result['status'],'unique_samples':result['unique_conflicting_samples'],'witnesses':len(witnesses),'seconds':result['seconds']}))
