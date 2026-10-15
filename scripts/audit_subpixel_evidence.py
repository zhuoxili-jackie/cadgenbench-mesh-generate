"""Recompute local support from saved actual pixel/range witnesses for final audit."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
import numpy as np,trimesh
from scanbench.common import load_json,file_hash,canonical_json

def audit(cid):
    rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path']
    review=load_json(ROOT/f'private/annotations/{cid}/fragmentation_review.json')
    assert review['review_kind']=='quantified_subpixel_reference_region_join'
    assert review['mesh_sha256']==file_hash(out/'mesh.ply')
    for p,h in review['evidence_sha256'].items():assert file_hash(ROOT/p)==h
    folder=ROOT/f'reports/fragmentation/{cid}/subpixel_regions';raw=load_json(folder/'all_raw_support.json')
    mesh=trimesh.load_mesh(out/'mesh.ply',process=False)
    with np.load(folder/'measurements.npz') as z:ids=z['bridge_face_ids']
    with np.load(folder/'all_raw_support.npz') as z:
        points=z['triangle_lattice_points_mm'];claimed=z['nearest_noisy_return_distance_mm'];fi=z['nearest_frame_index'];pi=z['nearest_return_index']
    weights=np.array([(i/5,j/5,1-(i+j)/5) for i in range(6) for j in range(6-i)]+[(1/3,1/3,1/3)])
    actual_points=np.einsum('sk,nkj->nsj',weights,mesh.triangles[ids]).reshape(-1,3)
    assert np.array_equal(points,actual_points)
    refs=load_json(out/'observations.json')['frames'];cams={x['id']:x for x in load_json(out/'cameras.json')['cameras']}
    assert len(fi)==len(points) and np.all((fi>=0)&(fi<len(refs)))
    actual=np.full(len(points),np.inf)
    for i in np.unique(fi):
        fr=refs[int(i)];path=(out/fr['path']).resolve();assert file_hash(path)==fr['file_sha256']
        sel=np.flatnonzero(fi==i);cam=cams[fr['camera_id']];K=np.asarray(cam['K']);T=np.asarray(cam['T_object_from_camera'])
        with np.load(path) as z:
            assert np.all((pi[sel]>=0)&(pi[sel]<len(z['pixel'])))
            pixel=z['pixel'][pi[sel]].astype(np.float64);ran=z['range_mm'][pi[sel]].astype(np.float64)
        rays=np.column_stack(((pixel%cam['resolution']-K[0,2])/K[0,0],(np.floor(pixel/cam['resolution'])-K[1,2])/K[1,1],np.ones(len(sel))))
        rays=rays/np.linalg.norm(rays,axis=1)[:,None];observed=(rays*ran[:,None])@T[:3,:3].T+T[:3,3]
        actual[sel]=np.linalg.norm(observed-points[sel],axis=1)
    assert np.max(np.abs(actual-claimed))<1e-10
    tol=raw['support_tolerance_mm'];fraction=float(np.mean(actual<=tol));area=float(np.average((actual.reshape(len(ids),22)<=tol).mean(1),weights=mesh.area_faces[ids]))
    assert abs(fraction-review['bridge_original_observation_support_fraction'])<1e-12 and fraction>=.98
    assert abs(area-review['bridge_area_weighted_original_observation_support_fraction'])<1e-12 and area>=.98
    edge=np.linalg.norm(mesh.triangles[ids]-np.roll(mesh.triangles[ids],1,axis=1),axis=2)
    assert edge.max()<review['declared_feature_size_mm']
    return {'case_id':cid,'status':'pass','witnesses_recomputed_from_original_pixels':len(points),'bridge_area_fraction':float(mesh.area_faces[ids].sum()/mesh.area),'area_weighted_original_observation_support':area,'declared_pixel_step_mm':review['declared_pixel_step_mm'],'declared_feature_size_mm':review['declared_feature_size_mm'],'limitation':review['resolution_limitation'],'evidence':str((folder/'all_raw_support.json').relative_to(ROOT)).replace('\\','/')}

if __name__=='__main__':print(canonical_json(audit(sys.argv[1])))
