"""Independent supplementary source/case audits. Read-only on delivered inputs."""
import numpy as np
import open3d as o3d
import trimesh
from .common import *
from .validate import distance_scene,read_mesh,distances,independent_backproject,geometry_reference

def source_factors(sid):
    gt=ROOT/f'private/gt/{sid}';ref,info=geometry_reference(sid);cams=load_json(gt/'cameras.json')['cameras'];poses=load_json(gt/'placements.json')['placements'];meta=load_json(gt/'metadata.json');vis=ref['camera_visibility'];contact=ref['contact'][0]
    rows=[]
    for placements,stride,kind in [(n,4,'fixed_49_frames_vary_placements') for n in range(1,len(poses)+1)]+[(1,s,'fixed_first_placement_vary_density') for s in [4,2,1]]:
        indices=[i for i,c in enumerate(cams) if c['placement_id']<placements and c['mother_frame_id']%stride==0];mask=vis[indices].any(0);ov=[]
        for pid in range(placements):
            ids=[i for i in indices if cams[i]['placement_id']==pid]
            ov.extend(float((vis[a]&vis[b]).sum()/max(1,vis[a].sum(),vis[b].sum())) for a,b in zip(ids[:-1],ids[1:]))
        rows.append({'factor':kind,'placements':placements,'frames_per_placement':193//stride+int(stride>1),'surface_fraction':float(mask.mean()),'initial_contact_visible_fraction':float(mask[contact].mean()) if contact.any() else None,'adjacent_overlap_p10':float(np.quantile(ov,.1))})
    scale={'millimetre':1.,'millimeter':1.,'metre':1000.,'meter':1000.,'centimetre':10.,'centimeter':10.,'inch':25.4,'foot':304.8}
    units=meta['source_length_units'];unknown=[u for u in units if u.lower() not in scale]
    if unknown:raise ValueError(f'unit conversion needs explicit interpretation: {unknown}')
    result={'status':'pass','source_id':sid,'source_sha256':meta['source_sha256'],'GT_sha256':file_hash(gt/'mesh.npz'),'camera_sha256':file_hash(gt/'cameras.json'),'actual_stable_placements':len(poses),'factor_checks':rows,'units':{'source_units':units,'source_unit_to_mm':[scale[u.lower()] for u in units],'import_system_unit_mm':meta['system_length_unit_mm'],'normalization_scale':1.,'normalization':'rigid translation only','basis':'STEP FileUnits declaration plus explicit OCP system length unit, not inferred from geometry'},'reference_sampling':info['method'],'not_three_poses':len(poses)<3}
    atomic_json(ROOT/f'reports/source_audits/{sid}.json',result);return result

def all_cylindrical_passages(sid,mesh,h):
    gt=ROOT/f'private/gt/{sid}';contract=load_json(gt/'feature_contract.json');features=load_json(gt/'features.json');gmesh=read_mesh(gt/'mesh.ply');gs=distance_scene(gmesh);ms=distance_scene(mesh);D=np.linalg.norm(gmesh.extents);limit=max(contract['resolvable_feature_mm'],6*h);seen=set();rows=[]
    for f in features:
        if f['type']!='cylinder' or f['u_range'][1]-f['u_range'][0]<np.pi-1e-5:continue
        r=f['radius_mm'];axis=np.array(f['axis_direction'],float);axis/=np.linalg.norm(axis)
        if axis[np.argmax(abs(axis))]<0:axis=-axis
        center=np.array(f['axis_point'],float);center-=axis*np.dot(axis,center)
        key=tuple(np.round(np.r_[axis,center,r],6))
        if key in seen:continue
        seen.add(key);record={'CAD_face':f['face'],'diameter_mm':2*r,'declared_and_working_resolution_limit_mm':limit,'resolvable':2*r>=limit}
        helper=np.eye(3)[np.argmin(abs(axis))];x=np.cross(axis,helper);x/=np.linalg.norm(x);y=np.cross(axis,x)
        uv=np.array([(u,v) for u in np.linspace(-.8,.8,25) for v in np.linspace(-.8,.8,25) if u*u+v*v<.8**2]);p=center-D*axis+r*(uv[:,0,None]*x+uv[:,1,None]*y);rays=np.column_stack([p,np.broadcast_to(axis,p.shape)]).astype(np.float32)
        gh=gs.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy();free=np.isinf(gh);record['gt_core_free_fraction']=float(free.mean())
        if free.mean()<.99:record.update(status='not_axial_through_passage',reason='actual GT obstructs the cylinder axis bundle; includes outer cylinders, blind bores and stepped bores')
        elif 2*r<limit:record.update(status='below_declared_resolution',reason='no preservation claim below the explicit sampling/working-spacing limit')
        else:
            mh=ms.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy();fraction=float(np.isinf(mh[free]).mean());record.update(status='pass' if fraction>=.99 else 'failed',mesh_core_free_fraction=fraction,core_rays=int(free.sum()))
            angle=np.linspace(0,2*np.pi,256,endpoint=False);ring=center-D*axis+1.5*r*(np.cos(angle)[:,None]*x+np.sin(angle)[:,None]*y);rr=np.column_stack([ring,np.broadcast_to(axis,ring.shape)]).astype(np.float32)
            gr=gs.cast_rays(o3d.core.Tensor(rr),nthreads=2)['t_hit'].numpy();mr=ms.cast_rays(o3d.core.Tensor(rr),nthreads=2)['t_hit'].numpy();valid=np.isfinite(gr);record['ring_material_hit_fraction']=float(np.isfinite(mr[valid]).mean()) if valid.any() else None
        rows.append(record)
    return {'status':'failed' if any(r['status']=='failed' for r in rows) else 'pass','features':rows,'method':'all distinct CAD cylindrical axes with >=pi parameter span; GT applicability first; independent axis bundle radius 0.8r and material ring 1.5r; 6h plus declared worst-pixel resolution. Noncylindrical slots additionally governed by all-mesh observation support/free-space tests; no claim of semantic slot enumeration.'}

def audit_case(cid):
    record=load_json(ROOT/f'private/annotations/{cid}/case.json');sid=record['source_id'];out=ROOT/record['input_path'];dest=ROOT/f'private/annotations/{cid}/supplemental.json';gt=ROOT/f'private/gt/{sid}'
    key=digest([file_hash(out/'mesh.ply'),file_hash(out/'observations.json'),file_hash(out/'cameras.json'),file_hash(out/'reconstruction.json'),file_hash(gt/'features.json'),file_hash(gt/'feature_contract.json'),file_hash(Path(__file__)),file_hash(Path(__file__).with_name('validate.py'))])
    if dest.exists() and load_json(dest).get('input_hash')==key:return load_json(dest)
    mesh=read_mesh(out/'mesh.ply');recon=load_json(out/'reconstruction.json');tol=recon['filtering']['support_tolerance_mm'];ref,refmeta=geometry_reference(sid);pts=ref['points'];covered=distances(distance_scene(mesh),pts)<=tol
    actual=load_json(out/'cameras.json')['cameras'];mother=load_json(gt/'cameras.json')['cameras'];ids={c['id'] for c in actual};indices=[i for i,c in enumerate(mother) if c['id'] in ids];visible=ref['camera_visibility'][indices].any(0);firsthit=ref['first_hit_visibility'][indices].any(0)
    observed=np.zeros(len(pts),bool);cmap={c['id']:c for c in actual}
    for frame in load_json(out/'observations.json')['frames']:
        cam=cmap[frame['camera_id']];d=np.load((out/frame['path']).resolve());pix=d['pixel'];ran=d['range_mm'];T=np.asarray(cam['T_object_from_camera']);K=np.asarray(cam['K']);p=(pts-T[:3,3])@T[:3,:3];uv=np.rint(p[:,:2]/p[:,2,None]*[K[0,0],K[1,1]]+[K[0,2],K[1,2]]).astype(np.int64);res=cam['resolution'];valid=(p[:,2]>0)&(uv>=0).all(1)&(uv<res).all(1);jj=np.flatnonzero(valid);targets=uv[jj,1]*res+uv[jj,0];ix=np.searchsorted(pix,targets);found=ix<len(pix);found[found]&=pix[ix[found]]==targets[found];jj=jj[found];ix=ix[found]
        measured=independent_backproject(pix[ix].astype(np.int64),ran[ix],cam);observed[jj]|=np.linalg.norm(measured-pts[jj],axis=1)<=tol
    contact=ref['contact'][:record['placement_count']].all(0);missing=~covered
    cause={'persistent_table_contact':missing&contact,'self_occlusion_or_finite_camera_inaccessibility':missing&~contact&~firsthit,'incidence_rejection':missing&~contact&firsthit&~visible,'finite_pixel_sampling_or_noise':missing&~contact&visible&~observed,'meshing_loss_after_observation':missing&~contact&visible&observed}
    assert np.array_equal(np.logical_or.reduce(list(cause.values())),missing)
    feature=all_cylindrical_passages(sid,mesh,recon['fusion']['h_mm'])
    result={'status':feature['status'],'case_id':cid,'input_hash':key,'mesh_sha256':file_hash(out/'mesh.ply'),'all_cylindrical_passages':feature,'missing_surface_attribution':{'n':len(pts),'tolerance_mm':tol,'fractions_of_total_GT_surface':{k:float(v.mean()) for k,v in cause.items()},'missing_total':float(missing.mean()),'finite_observation_support_fraction':float(observed.mean()),'method':'same fixed area samples; disjoint unmeshed categories in listed priority; observation support independently backprojects actual nearest projected pixel and tests Euclidean point distance; finite camera inaccessibility includes self-occlusion, near/far and frustum limitations'}}
    atomic_json(dest,result);return result
