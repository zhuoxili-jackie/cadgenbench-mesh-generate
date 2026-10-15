"""Independent numerical acceptance: reads outputs, never generates or repairs them."""
from pathlib import Path
import math
import numpy as np
import open3d as o3d
import trimesh
from scipy.spatial import cKDTree
from .common import *
from .observation_grid import FirstReturnGrid
from .sampling_density import source_scan_settings,verify_case_sampling_contract

def read_mesh(path):
    mesh=trimesh.load(path,process=False,force='mesh')
    if not len(mesh.faces) or not np.isfinite(mesh.vertices).all(): raise ValueError('empty/nonfinite mesh')
    if mesh.faces.min()<0 or mesh.faces.max()>=len(mesh.vertices): raise ValueError('illegal triangle indices')
    return mesh

def distance_scene(mesh):
    scene=o3d.t.geometry.RaycastingScene(nthreads=2)
    scene.add_triangles(o3d.core.Tensor(np.array(mesh.vertices,dtype=np.float32)),o3d.core.Tensor(np.array(mesh.faces,dtype=np.uint32)))
    return scene

def distances(scene,points): return scene.compute_distance(o3d.core.Tensor(np.asarray(points,dtype=np.float32)),nthreads=2).numpy()

def sample_area(mesh,count,seed):
    rng=np.random.Generator(np.random.PCG64(seed)); probs=mesh.area_faces/mesh.area
    faces=rng.choice(len(mesh.faces),size=count,p=probs)
    uv=rng.random((count,2)); reflected=uv.sum(axis=1)>1; uv[reflected]=1-uv[reflected]
    t=mesh.vertices[mesh.faces[faces]]
    return t[:,0]+uv[:,0,None]*(t[:,1]-t[:,0])+uv[:,1,None]*(t[:,2]-t[:,0]),faces

def mesh_statistics(mesh):
    edges=np.sort(np.concatenate([mesh.faces[:,[0,1]],mesh.faces[:,[1,2]],mesh.faces[:,[2,0]]]),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True); boundary=unique[counts==1]
    components=trimesh.graph.connected_components(mesh.face_adjacency,nodes=np.arange(len(mesh.faces)),min_len=1)
    areas=sorted([float(mesh.area_faces[c].sum()) for c in components],reverse=True)
    total=float(mesh.area); tiny=sum(a for a in areas if a<total*.001)
    om=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(mesh.vertices),o3d.utility.Vector3iVector(mesh.faces))
    return {'vertices':len(mesh.vertices),'faces':len(mesh.faces),'area_mm2':total,'boundary_edges':len(boundary),
            'boundary_length_mm':float(np.linalg.norm(mesh.vertices[boundary[:,0]]-mesh.vertices[boundary[:,1]],axis=1).sum()),
            'nonmanifold_edges':int((counts>2).sum()),'degenerate_faces':int((mesh.area_faces<1e-12).sum()),
            'nonmanifold_vertices':len(om.get_non_manifold_vertices()),
            'duplicate_faces':len(mesh.faces)-len(np.unique(np.sort(mesh.faces,axis=1),axis=0)),
            'component_count':len(areas),'component_areas_mm2':areas,'largest_component_area_fraction':areas[0]/total,
            'tiny_component_area_fraction':tiny/total,'winding_consistent':bool(mesh.is_winding_consistent)}

def sorted_facets(mesh):
    tri=mesh.triangles.astype(np.float32)
    order=np.lexsort((tri[:,:,2],tri[:,:,1],tri[:,:,0]),axis=1)
    tri=np.take_along_axis(tri,order[:,:,None],axis=1).reshape(-1,9)
    order=np.lexsort(tuple(tri[:,i] for i in range(8,-1,-1)))
    return tri[order]

def feature_check(sid,mesh,h):
    gt=ROOT/f'private/gt/{sid}'; contract=load_json(gt/'feature_contract.json'); focus=contract['focus_feature']
    if focus['type']!='cylinder': return {'status':'not_applicable','reason':'declared focus is overall thickness; no cylindrical focus selected','contract':contract}
    raw=np.load(gt/'mesh.npz'); gmesh=trimesh.Trimesh(raw['vertices'],raw['faces'],process=False); gscene=distance_scene(gmesh); mscene=distance_scene(mesh)
    axis=np.asarray(focus['axis_direction']); axis/=np.linalg.norm(axis); center=np.asarray(focus['axis_point']); r=focus['radius_mm']
    helper=np.eye(3)[np.argmin(abs(axis))]; x=np.cross(axis,helper); x/=np.linalg.norm(x); y=np.cross(axis,x)
    D=np.linalg.norm(gmesh.extents)
    uv=np.array([(u,v) for u in np.linspace(-.55,.55,15) for v in np.linspace(-.55,.55,15) if u*u+v*v<.55**2])
    origins=center-D*axis+r*(uv[:,0,None]*x+uv[:,1,None]*y)
    rays=np.column_stack([origins,np.broadcast_to(axis,origins.shape)]).astype(np.float32)
    gh=gscene.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy(); mh=mscene.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy()
    open_gt=np.isinf(gh); resolvable=2*r>=6*h and not contract['below_declared_sampling_resolution']
    if open_gt.mean()<.99: return {'status':'not_applicable','reason':'focus cylinder is not an unobstructed axial through-hole in actual source geometry','gt_free_fraction':float(open_gt.mean()),'diameter_mm':2*r,'resolvable':resolvable}
    angle=np.linspace(0,2*np.pi,128,endpoint=False); ring=center-D*axis+1.8*r*(np.cos(angle)[:,None]*x+np.sin(angle)[:,None]*y)
    rr=np.column_stack([ring,np.broadcast_to(axis,ring.shape)]).astype(np.float32)
    gr=gscene.cast_rays(o3d.core.Tensor(rr),nthreads=2)['t_hit'].numpy(); mr=mscene.cast_rays(o3d.core.Tensor(rr),nthreads=2)['t_hit'].numpy(); ringvalid=np.isfinite(gr)
    free=float(np.isinf(mh[open_gt]).mean()); ringret=float(np.isfinite(mr[ringvalid]).mean()) if ringvalid.any() else None
    return {'status':'pass' if (free>=.99 or not resolvable) else 'failed','feature':'axial through-hole','diameter_mm':2*r,'h_mm':h,'resolvable':resolvable,
            'gt_free_fraction':float(open_gt.mean()),'mesh_free_core_fraction':free,'annular_gt_rays':int(ringvalid.sum()),'annular_material_hit_fraction':ringret,
            'method':'independent axis rays through radius 0.55r and surrounding 1.8r ring, all mesh faces; GT verifies geometric applicability'}

def independent_backproject(pix,ran,cam):
    res=cam['resolution']; K=np.asarray(cam['K']); T=np.asarray(cam['T_object_from_camera'])
    d=np.column_stack(((pix%res-K[0,2])/K[0,0],(pix//res-K[1,2])/K[1,1],np.ones(len(pix))))
    d/=np.sqrt(np.sum(d*d,axis=1))[:,None]
    return (d*ran[:,None])@T[:3,:3].T+T[:3,3]

def physical_case_check(record,out):
    sid=record['source_id']; gt=ROOT/f'private/gt/{sid}'; meta=load_json(gt/'metadata.json'); places=load_json(gt/'placements.json')['placements']
    public=load_json(out/'cameras.json'); mother={c['id']:c for c in load_json(gt/'cameras.json')['cameras']}; actual=public['cameras']; cfg=config()
    expected_place=min(cfg['difficulty'][record['level']]['placements'],len(places)); stride=cfg['difficulty'][record['level']]['stride']
    verify_case_sampling_contract(record,out)
    expected_frames=source_scan_settings(sid)['intervals']//stride+1
    assert len(actual)==expected_place*expected_frames
    minheight=np.inf; minclear=np.inf; aim_error=0.; roundtrip=0.; gaps=[];frame_margin=np.inf
    raw=np.load(gt/'mesh.npz'); vertices=raw['vertices']
    for pid in range(expected_place):
        selected=[c for c in actual if c['placement_id']==pid]; assert len(selected)==expected_frames
        T=np.asarray(places[pid]['T_table_from_object']); vv=vertices@T[:3,:3].T+T[:3,3]; center=(vv.max(0)+vv.min(0))/2
        assert vv[:,2].min()>=-places[pid]['epsilon_contact_mm']
        if places[pid]['actual_contact_area_mm2']<=0:
            from .contact_support import audit_discrete_placement
            assert audit_discrete_placement(sid,places[pid])['status']=='pass'
        assert places[pid]['stability_margin_mm']>0
        lo=vv.min(0);hi=vv.max(0);corners=np.array([[x,y,z] for x in [lo[0],hi[0]] for y in [lo[1],hi[1]] for z in [lo[2],hi[2]]])
        angles=[]; heights=[]
        for cam in selected:
            C=np.asarray(cam['T_object_from_camera']); np.testing.assert_array_equal(C,np.asarray(mother[cam['id']]['T_object_from_camera']))
            np.testing.assert_array_equal(cam['K'],mother[cam['id']]['K'])
            TC=T@C; eye=TC[:3,3]; direction=center-eye; direction/=np.linalg.norm(direction)
            aim_error=max(aim_error,float(np.linalg.norm(direction-TC[:3,2]))); minheight=min(minheight,float(eye[2]));
            sphere=np.linalg.norm(vv.max(0)-vv.min(0))/2;minclear=min(minclear,float(np.linalg.norm(eye-center)-sphere))
            roundtrip=max(roundtrip,float(abs(T@np.linalg.inv(T)-np.eye(4)).max()))
            cc=(corners-eye)@TC[:3,:3];K=np.asarray(cam['K']);uv=cc[:,:2]/cc[:,2,None]*[K[0,0],K[1,1]]+[K[0,2],K[1,2]]
            margin=min(float(uv.min()),float(cam['resolution']-1-uv.max()));frame_margin=min(frame_margin,margin)
            assert margin>=0 and np.all(cc[:,2]>0)
            assert np.linalg.norm(cc,axis=1).min()>=cam['near_mm'] and np.linalg.norm(cc,axis=1).max()<=cam['far_mm']
            delta=eye-center;angles.append(np.arctan2(delta[1],delta[0]));heights.append(np.rad2deg(np.arctan2(delta[2],np.linalg.norm(delta[:2]))))
        angles=np.unwrap(angles); increments=np.rad2deg(np.diff(angles));gaps.extend(increments.tolist())
        assert abs(np.rad2deg(angles[-1]-angles[0])-360*cfg['scan']['turns'])<1e-6
        assert np.all(np.diff(heights)<0) and abs(heights[0]-cfg['scan']['beta_top_deg'])<1e-6 and abs(heights[-1]-cfg['scan']['beta_bottom_deg'])<1e-6
        assert max(increments)-min(increments)<1e-6
    assert aim_error<1e-10 and minheight>0 and minclear>0
    return {'status':'pass','actual_placements':expected_place,'actual_frames_per_placement':expected_frames,'turns_per_placement':cfg['scan']['turns'],
            'max_adjacent_azimuth_deg':max(gaps),'camera_min_table_height_mm':minheight,'min_sphere_clearance_mm':minclear,'minimum_bbox_projection_margin_px':frame_margin,'max_look_at_error':aim_error,'max_transform_roundtrip_error':roundtrip,
            'contact_areas_mm2':[p['actual_contact_area_mm2'] for p in places[:expected_place]],'support_margins_mm':[p['stability_margin_mm'] for p in places[:expected_place]]}

def independently_paired_noise(record,out):
    sigma=load_json(out/'cameras.json')['sigma_mm']; source=record['source_id']; arrays=[];total=0;sums=0.;squares=0.;maximum=0.;ulp=0.
    for rec in load_json(out/'observations.json')['frames']:
        clean_path=ROOT/f'cache/clean/{source}/{rec["camera_id"]}.npz'
        if not clean_path.exists():continue
        with np.load(clean_path) as clean, np.load((out/rec['path']).resolve()) as noisy:
            np.testing.assert_array_equal(clean['pixel'],noisy['pixel'])
            delta=noisy['range_mm'].astype(np.float64)-clean['range_mm'].astype(np.float64)
            if len(delta):ulp=max(ulp,float(np.spacing(np.max(clean['range_mm']))))
        total+=len(delta);sums+=float(delta.sum());squares+=float(delta@delta)
        if len(delta):maximum=max(maximum,float(abs(delta).max()))
    if total<100000:raise ValueError('insufficient independent paired noise evidence')
    mean=sums/total;std=math.sqrt(squares/total-mean*mean)
    assert abs(mean)<.05*sigma and .9<std/sigma<1.1 and maximum<=3*sigma+2*ulp
    return {'status':'pass','paired_returns':total,'sigma_mm':sigma,'mean_mm':mean,'std_mm':std,'max_abs_mm':maximum,'float32_ulp_allowance_mm':2*ulp,'method':'independent subtraction of actual private clean range from public noisy range on matching pixels; quarter-density cache subset'}

def observed_evaluation(obs_path,camera_path,mesh_samples,tolerance,sample_count):
    obj=load_json(obs_path); cams={c['id']:c for c in load_json(camera_path)['cameras']}; root=(obs_path.parent/obj['data_root_relative']).resolve()
    spacing=np.median([(c['near_mm']+c['far_mm'])/2/c['K'][0][0] for c in cams.values()])
    supported=np.zeros(len(mesh_samples),bool); free_conflict=np.zeros(len(mesh_samples),bool); vox=spacing;grid=FirstReturnGrid(vox)
    working=o3d.io.read_point_cloud(str(obs_path.parent/'points_for_meshing.ply'));work_points=np.asarray(working.points)
    provenance=np.load(obs_path.parent/'point_provenance.npz');frame_index=provenance['frame_index'];work_pixels=provenance['pixel']
    assert len(work_points)==len(frame_index)==len(work_pixels)
    assert frame_index.min()>=0 and frame_index.max()<len(obj['frames'])
    trace_max=0.;traced=0
    raw_count=0
    for ordinal,frame in enumerate(obj['frames']):
        path=(obs_path.parent/frame['path']).resolve()
        if not path.is_relative_to(root): raise ValueError('reference outside public root')
        if file_hash(path)!=frame['file_sha256']: raise ValueError('observation file corrupted')
        with np.load(path) as a:
            pixel=a['pixel']; ran=a['range_mm']
            if pixel.dtype!=np.uint32 or ran.dtype!=np.float32: raise ValueError('observation dtype mismatch')
            if not np.isfinite(ran).all() or len(pixel)!=len(ran): raise ValueError('invalid observation array')
            if len(pixel) and (np.any(np.diff(pixel.astype(np.int64))<=0) or pixel.max()>=cams[frame['camera_id']]['resolution']**2):raise ValueError('invalid/duplicate pixel IDs')
        cam=cams[frame['camera_id']]; points=independent_backproject(pixel.astype(np.int64),ran,cam); raw_count+=len(points)
        selected=np.flatnonzero(frame_index==ordinal)
        if len(selected):
            idx=np.searchsorted(pixel,work_pixels[selected]);assert np.all(idx<len(pixel));np.testing.assert_array_equal(pixel[idx],work_pixels[selected])
            trace_max=max(trace_max,float(np.linalg.norm(work_points[selected]-points[idx],axis=1).max()));traced+=len(selected)
        # Every valid observed point contributes to the spatial stratification, including boundary/no-normal returns.
        grid.add(points)
        unresolved=np.arange(len(mesh_samples))
        if len(unresolved):
            T=np.asarray(cam['T_object_from_camera']); p=(mesh_samples-T[:3,3])@T[:3,:3]
            norm=np.linalg.norm(p,axis=1); K=np.asarray(cam['K']); res=cam['resolution']
            uv=np.rint(p[:,:2]/p[:,2,None]*[K[0,0],K[1,1]]+[K[0,2],K[1,2]]).astype(int)
            good=(p[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<res)&(uv[:,1]>=0)&(uv[:,1]<res)
            ix=np.flatnonzero(good); targetpixel=uv[ix,1]*res+uv[ix,0]
            where=np.searchsorted(pixel,targetpixel); exists=where<len(pixel); exists[exists]&=pixel[where[exists]]==targetpixel[exists]
            ix=ix[exists]; where=where[exists]
            supported[unresolved[ix]]|=abs(norm[ix]-ran[where])<=tolerance
            interior=(p[:,2]>0)&(uv[:,0]>=1)&(uv[:,0]<res-1)&(uv[:,1]>=1)&(uv[:,1]<res-1)
            jj=np.flatnonzero(interior);xx=uv[jj,0];yy=uv[jj,1]
            img=np.full(res*res,np.nan,np.float32);img[pixel]=ran;img=img.reshape(res,res)
            patch=np.stack([img[yy+dy,xx+dx] for dy in [-1,0,1] for dx in [-1,0,1]],axis=1)
            stable=np.isfinite(patch).all(axis=1)&(patch.max(1)-patch.min(1)<2*tolerance)
            free_conflict[jj]|=stable&(norm[jj]<patch.min(1)-tolerance)
    # Randomly select voxels with fixed seed after complete stratification, not only meshing survivors.
    representatives=grid.result()
    rng=np.random.Generator(np.random.PCG64(1703)); selected=rng.choice(len(representatives),min(sample_count,len(representatives)),replace=False)
    assert traced==len(work_points) and trace_max<1e-7
    return representatives[selected],supported,{'all_valid_returns':raw_count,'spatial_cells':len(representatives),'sampling':'one real point per fixed pixel-scale spatial cell, all valid pixels; fixed PCG64 selection','voxel_mm':vox,'n':len(selected),
             'working_points_traced_to_actual_noisy_returns':traced,'trace_max_mm':trace_max,'sampled_mesh_free_space_conflicts':int(free_conflict.sum())}

def geometry_reference(sid):
    folder=ROOT/f'private/reference/{sid}'; gt=ROOT/f'private/gt/{sid}'
    meta=load_json(gt/'metadata.json'); cameras=load_json(gt/'cameras.json')['cameras']; placements=load_json(gt/'placements.json')['placements']; sc=config()['scan']
    key=stage_hash([file_hash(gt/'mesh.npz'),file_hash(gt/'cameras.json'),file_hash(gt/'placements.json')],{'samples':30000,'incidence_deg':sc['incidence_deg']},['validate.py'],['numpy','open3d','trimesh'])
    marker=folder/'reference.json'
    if marker.exists() and load_json(marker).get('key')==key and (folder/'evaluation.npz').exists(): return np.load(folder/'evaluation.npz'),load_json(marker)
    raw=np.load(gt/'mesh.npz'); mesh=trimesh.Trimesh(raw['vertices'],raw['faces'],process=False); scene=distance_scene(mesh)
    pts,face=sample_area(mesh,30000,410218); normals=mesh.face_normals[face]
    masks=[]; contacts=[]; firstvisible=[]; perspectivevalid=[]
    for place in placements:
        T=np.asarray(place['T_table_from_object']); pp=pts@T[:3,:3].T+T[:3,3]
        contacts.append(abs(pp[:,2])<=place['epsilon_contact_mm'])
    for cam in cameras:
        C=np.asarray(cam['T_object_from_camera']); eye=C[:3,3]; toward=pts-eye; r=np.linalg.norm(toward,axis=1); dirs=toward/r[:,None]
        rays=np.column_stack((np.broadcast_to(eye,dirs.shape),dirs)).astype(np.float32)
        hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy()
        first=abs(hit-r)<max(meta['diagonal_mm']*2e-6,1e-4)
        p=(pts-eye)@C[:3,:3]; K=np.asarray(cam['K']); uv=p[:,:2]/p[:,2,None]*[K[0,0],K[1,1]]+[K[0,2],K[1,2]]
        inframe=(p[:,2]>0)&(uv.min(axis=1)>=0)&(uv.max(axis=1)<cam['resolution'])&(r>=cam['near_mm'])&(r<=cam['far_mm'])
        T=np.asarray(placements[cam['placement_id']]['T_table_from_object']); eyet=eye@T[:3,:3].T+T[:3,3]; dz=dirs@T[2,:3]
        table=np.full(len(pts),np.inf); down=dz<-1e-12; table[down]=-eyet[2]/dz[down]
        unblocked=table>r+placements[cam['placement_id']]['epsilon_contact_mm']
        incidence=-np.einsum('ij,ij->i',dirs,normals)>=np.cos(np.deg2rad(sc['incidence_deg']))
        masks.append(first&inframe&unblocked&incidence); firstvisible.append(first&unblocked&inframe)
    masks=np.array(masks); firstvisible=np.array(firstvisible); reference=masks.any(axis=0)
    perlevel={}; overlap={}
    for level,d in config()['difficulty'].items():
        selected=np.array([c['placement_id']<d['placements'] and c['mother_frame_id']%d['stride']==0 for c in cameras]); perlevel[level]=masks[selected].any(axis=0)
        ov=[]
        for pid in range(min(d['placements'],len(placements))):
            idx=[i for i,c in enumerate(cameras) if c['placement_id']==pid and selected[i]]
            for a,b in zip(idx[:-1],idx[1:]):
                if masks[a].sum() and masks[b].sum(): ov.append(float((masks[a]&masks[b]).sum()/max(masks[a].sum(),masks[b].sum())))
        overlap[level]={'p10':float(np.quantile(ov,.1)),'min':min(ov),'median':float(np.median(ov)),'n':len(ov),'method':'min of two directional ratios on same fixed area-distributed GT sample; foreground surfaces only'}
    assert np.all(~perlevel['hard']|perlevel['medium']) and np.all(~perlevel['medium']|perlevel['easy'])
    atomic_npz(folder/'evaluation.npz',points=pts,face=face,normals=normals,camera_visibility=masks,first_hit_visibility=firstvisible,contact=np.array(contacts),reference=reference,**{f'visible_{k}':v for k,v in perlevel.items()})
    report={'key':key,'method':'finite exact first-hit rays from the actual dense mother camera positions to 30000 fixed area surface samples; subpixel reference, not omniscient cavity access','n':len(pts),'camera_count':len(cameras),'reference_fraction':float(reference.mean()),'overlap':overlap,'geometric_nested_sets':True,'coverage':{k:float(v.mean()) for k,v in perlevel.items()}}
    atomic_json(marker,report)
    return np.load(folder/'evaluation.npz'),report

def current_fragmentation_review(out,record):
    path=ROOT/f'private/annotations/{record["case_id"]}/fragmentation_review.json'
    if not path.exists():return None
    review=load_json(path)
    # A geometry change invalidates a previous interpretation; it does not make
    # the new geometry permanently unreviewable. The old evidence stays on disk.
    if review['mesh_sha256']!=file_hash(out/'mesh.ply') or review['source_sha256']!=record['source_sha256']:return None
    for p,h in review['evidence_sha256'].items():
        if file_hash(ROOT/p)!=h:raise ValueError('fragmentation evidence changed')
    return review

def validation_fingerprint(out,record,gates):
    """Hash actual referenced payloads too: a stale manifest is never a cache hit."""
    verify_case_sampling_contract(record,out)
    files=['mesh.ply','mesh.stl','points_for_meshing.ply','observations.json','cameras.json','reconstruction_config.json','reconstruction.json','README.json','point_provenance.npz','sampling_contract.json']
    public={f:file_hash(out/f) for f in files}
    refs=load_json(out/'observations.json');root=(out/refs['data_root_relative']).resolve();payloads={}
    for frame in refs['frames']:
        path=(out/frame['path']).resolve()
        if not path.is_relative_to(root):raise ValueError('reference escapes public root')
        actual=file_hash(path)
        if actual!=frame['file_sha256']:raise ValueError(f'corrupt observation payload: {path.name}')
        payloads[frame['path']]=actual
    gt=ROOT/f'private/gt/{record["source_id"]}'
    private={f:file_hash(gt/f) for f in ['mesh.npz','metadata.json','placements.json','cameras.json','feature_contract.json']}
    actual_source=file_hash(ROOT/f'sources/{record["source_id"]}/input.step')
    if actual_source!=record['source_sha256']:raise ValueError('source STEP no longer matches official provenance')
    private['source_sha256']=actual_source
    audit=gt/'placement_audit.json'
    if not audit.exists() or load_json(audit).get('status')!='pass':raise ValueError('exact BREP placement audit required')
    private['placement_audit.json']=file_hash(audit)
    review=ROOT/f'private/annotations/{record["case_id"]}/fragmentation_review.json'
    if current_fragmentation_review(out,record) is not None:
        private['fragmentation_review.json']=file_hash(review)
    return stage_hash({'public':public,'observations':payloads,'private':private},gates,['validate.py','observation_grid.py','contact_support.py','sampling_density.py'],['numpy','open3d','trimesh','scipy'])

def validate_case(cid,state):
    record=load_json(ROOT/f'private/annotations/{cid}/case.json'); out=ROOT/record['input_path']; gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text())
    files=['mesh.ply','mesh.stl','points_for_meshing.ply','observations.json','cameras.json','reconstruction_config.json','reconstruction.json','README.json']
    for f in files:
        if not (out/f).is_file(): raise ValueError(f'{cid}: missing {f}')
    key=validation_fingerprint(out,record,gates)
    path=ROOT/f'private/annotations/{cid}/acceptance.json'
    if state.valid(cid,'validation',key):
        result=load_json(path)
        if record.get('validation_status')!=result['status']:
            record['validation_status']=result['status'];record['validation_hash']=key
            atomic_json(ROOT/f'private/annotations/{cid}/case.json',record);state.record('cases',cid,record)
        return result
    state.begin(cid,'validation',key)
    with measured() as timing:
        physical=physical_case_check(record,out);paired_noise=independently_paired_noise(record,out)
        mesh=read_mesh(out/'mesh.ply'); stl=read_mesh(out/'mesh.stl'); stats=mesh_statistics(mesh)
        # Check every facet geometrically after STL's unshared vertex encoding.
        np.testing.assert_allclose(sorted_facets(mesh),sorted_facets(stl),atol=1e-5,rtol=1e-7)
        recon=load_json(out/'reconstruction.json'); tol=recon['filtering']['support_tolerance_mm']; count=gates['evaluation_surface_samples']
        samples,_=sample_area(mesh,count,2901); obs,supported,denominator=observed_evaluation(out/'observations.json',out/'cameras.json',samples,tol,count)
        meshscene=distance_scene(mesh); obs_dist=distances(meshscene,obs)
        work=np.asarray(o3d.io.read_point_cloud(str(out/'points_for_meshing.ply')).points)
        vertex_original_distance=cKDTree(work).query(mesh.vertices,workers=2)[0]
        assert vertex_original_distance.max()<1e-7
        gt_raw=np.load(ROOT/f'private/gt/{record["source_id"]}/mesh.npz'); gtmesh=trimesh.Trimesh(gt_raw['vertices'],gt_raw['faces'],process=False); gtscene=distance_scene(gtmesh)
        scan_to_gt=distances(gtscene,samples); reference,refmeta=geometry_reference(record['source_id']); gt_to_mesh=distances(meshscene,reference['points'])
        covered=gt_to_mesh<=tol; reachable=reference['reference']; geometric=reference['visible_'+record['level']]
        quality={'mesh_observation_supported_fraction':float(supported.mean()),'observation_mesh_retained_fraction':float((obs_dist<=tol).mean()),'observation_denominator':denominator,
                 'tolerance_mm':tol,'total_gt_surface_mesh_coverage':float(covered.mean()),'reference_reachable_mesh_coverage':float(covered[reachable].mean()),
                 'geometric_scan_coverage':float(geometric.mean()),'meshing_loss_on_geometrically_visible':float((~covered&geometric).sum()/max(1,geometric.sum())),
                 'mesh_to_gt_distance':{'unit':'mm','method':'fixed independent area samples to triangle distance','n':count,'mean':float(scan_to_gt.mean()),'p95':float(np.quantile(scan_to_gt,.95)),'max_sampled':float(scan_to_gt.max()),'not_global_hausdorff':True},
                 'observation_to_mesh_distance':{'unit':'mm','n':len(obs),'p95':float(np.quantile(obs_dist,.95)),'max_sampled':float(obs_dist.max())},
                 'adjacent_overlap':refmeta['overlap'][record['level']]}
        feature=feature_check(record['source_id'],mesh,recon['fusion']['h_mm'])
        failures=[]
        if stats['nonmanifold_edges']>gates['nonmanifold_edges_max']: failures.append('nonmanifold edges')
        if stats['nonmanifold_vertices']>0: failures.append('nonmanifold vertices')
        if feature['status']=='failed': failures.append('resolvable through-hole bridged')
        if stats['degenerate_faces']>0 or stats['duplicate_faces']>0: failures.append('illegal degenerate/duplicate faces')
        if not stats['winding_consistent']: failures.append('inconsistent winding')
        if quality['mesh_observation_supported_fraction']<gates['mesh_supported_surface_min']: failures.append('mesh observation support < gate')
        if quality['observation_mesh_retained_fraction']<gates['observation_retention_min']: failures.append('observed surface retention < gate')
        if denominator['sampled_mesh_free_space_conflicts']>0:failures.append('mesh surface samples conflict with observed foreground free space')
        if quality['adjacent_overlap']['p10']<gates['adjacent_overlap_p10_min']: failures.append('adjacent scan overlap requires investigation')
        investigations=[]
        if stats['largest_component_area_fraction']<.85 or stats['tiny_component_area_fraction']>.03: investigations.append('fragmentation requires evidence-based investigation')
        natural_separation=None
        if investigations:
            evidence=current_fragmentation_review(out,record)
            if evidence is not None:
                if evidence['status']=='pass_natural_separation' and all(evidence['checks'].values()):
                    assert stats['tiny_component_area_fraction']<=.03 and quality['observation_mesh_retained_fraction']>=.95
                    assert all(x['reference_component_purity']>=.99 for x in evidence['component_correspondence'])
                    natural_separation=evidence;investigations=[]
        result={'case_id':cid,'status':'failed' if failures else ('investigation_required' if investigations else 'pass'),'failures':failures,'investigations':investigations,
                'natural_separation_evidence':natural_separation,
                'mesh':stats,'quality':quality,'mesh_vertex_to_original_observation_max_mm':float(vertex_original_distance.max()),'physical_scan':physical,'paired_noise':paired_noise,'focus_feature':feature,'stl_ply_roundtrip':'sorted geometric facets compared, preserving triangle connectivity','validation_hash':key,'performance':timing}
    result['performance']=timing; atomic_json(path,result)
    record['validation_status']=result['status']; record['validation_hash']=key
    atomic_json(ROOT/f'private/annotations/{cid}/case.json',record); state.record('cases',cid,record)
    state.finish(cid,'validation',key,[path],timing)
    event('validation_result',case=cid,status=result['status'],quality=quality,failures=failures,investigations=investigations)
    return result
