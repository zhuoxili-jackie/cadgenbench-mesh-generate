"""PRIVATE simulator: clean geometry is confined to acquisition and validation."""
import hashlib
import numpy as np
import open3d as o3d
from .common import *
from .camera import pixel_directions,trajectory
from .sampling_density import source_scan_settings,noise_frame_key

def scene_for(vertices,faces,threads=2):
    scene=o3d.t.geometry.RaycastingScene(nthreads=threads)
    scene.add_triangles(o3d.core.Tensor(np.asarray(vertices,dtype=np.float32)),o3d.core.Tensor(np.asarray(faces,dtype=np.uint32)))
    return scene

def raycast_frame(scene,camera,T_table_from_object,incidence_deg=75,epsilon_contact=1e-5):
    res=camera['resolution']; pixel=np.arange(res*res,dtype=np.uint32)
    local=pixel_directions(pixel,res,camera['K']); C=np.asarray(camera['T_object_from_camera']); T=np.asarray(T_table_from_object)
    direction=local@C[:3,:3].T; origin=C[:3,3]
    rays=np.empty((len(pixel),6),dtype=np.float32); rays[:,:3]=origin; rays[:,3:]=direction
    hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2)
    ranges=hit['t_hit'].numpy(); normal=hit['primitive_normals'].numpy()
    origin_table=origin@T[:3,:3].T+T[:3,3]; direction_z=direction@T[2,:3]
    tabletop=np.full(len(pixel),np.inf); downward=direction_z < -1e-12
    tabletop[downward]=-origin_table[2]/direction_z[downward]
    table_closer=tabletop<=ranges+epsilon_contact
    incidence=-np.einsum('ij,ij->i',direction,normal)
    valid=np.isfinite(ranges)&(ranges>camera['near_mm'])&(ranges<camera['far_mm'])&(~table_closer)&(incidence>=np.cos(np.deg2rad(incidence_deg)))
    stats={'valid_count':int(valid.sum()),'table_first_count':int((table_closer & np.isfinite(tabletop)).sum()),
           'incidence_rejected':int((np.isfinite(ranges)&(~table_closer)&(incidence<np.cos(np.deg2rad(incidence_deg)))).sum())}
    return pixel[valid],ranges[valid].astype(np.float32),stats

def splitmix(x):
    with np.errstate(over='ignore'):
        x=x+np.uint64(0x9E3779B97F4A7C15); x=(x^(x>>np.uint64(30)))*np.uint64(0xBF58476D1CE4E5B9)
        x=(x^(x>>np.uint64(27)))*np.uint64(0x94D049BB133111EB)
    return x^(x>>np.uint64(31))

def noise_for(pixel,key,sigma):
    x=np.asarray(pixel,dtype=np.uint64)^np.uint64(key)
    a=splitmix(x); b=splitmix(a)
    u=((a>>np.uint64(11)).astype(np.float64)+.5)/2**53
    v=((b>>np.uint64(11)).astype(np.float64)+.5)/2**53
    return np.clip(np.sqrt(-2*np.log(u))*np.cos(2*np.pi*v),-3,3)*sigma

def observation_hash(pixel,ranges):
    h=hashlib.sha256(b'observation_schema_v1_uint32_float32'); h.update(pixel.astype('<u4').tobytes()); h.update(ranges.astype('<f4').tobytes())
    return h.hexdigest()

def prepare_cameras(sid,state):
    gt=ROOT/f'private/gt/{sid}'; mesh=np.load(gt/'mesh.npz'); meta=load_json(gt/'metadata.json'); placements=load_json(gt/'placements.json')
    cfg=source_scan_settings(sid); features=load_json(gt/'features.json')
    D=meta['diagonal_mm']; sigma=float(np.clip(cfg['sigma_relative']*D,cfg['sigma_min_mm'],cfg['sigma_max_mm']))
    cylinders=[f for f in features if f['type']=='cylinder' and f['radius_mm']>0]
    # Private feature contract: smallest cylindrical surface with appreciable area, otherwise minimum overall thickness.
    substantial=[f for f in cylinders if f['area_mm2']>meta['area_mm2']*.0005 and f['u_range'][1]-f['u_range'][0]>=np.pi-1e-5]
    feature=min(substantial,key=lambda f:f['radius_mm']) if substantial else None
    size=2*feature['radius_mm'] if feature else min(np.ptp(mesh['vertices'],axis=0))
    chosen=cfg['allowed_resolutions'][-1]
    for r in cfg['allowed_resolutions']:
        probes=[trajectory(mesh['vertices'],p['T_table_from_object'],cfg,r,p['placement_id'])[0] for p in placements['placements']]
        spacing=max(probe['far_mm']/probe['K'][0][0] for probe in probes)
        if size>=6*spacing: chosen=r; break
    public={'schema':'camera_v1','unit':'mm','matrix_convention':'column vectors; T_target_from_source @ p_source',
            'camera_axes':'X right, Y down, Z forward; right handed','pixel_centers':'integer (u,v), top-left center=(0,0)',
            'range_definition':'Euclidean distance along unit ray, not camera-Z','resolution':chosen,'sigma_mm':sigma,
            'cameras':sum([trajectory(mesh['vertices'],p['T_table_from_object'],cfg,chosen,p['placement_id']) for p in placements['placements']],[])}
    private={'focus_feature':feature if feature else {'type':'overall_minimum_extent','size_mm':size},'focus_min_size_mm':size,
             'resolvable_feature_mm':6*spacing,'below_declared_sampling_resolution':size<6*spacing,'resolution':chosen,
             'small_features_not_guaranteed':True,'sigma_mm':sigma}
    path=gt/'cameras.json'; atomic_json(path,public); atomic_json(gt/'feature_contract.json',private)
    return public

def acquire_scans(sid,state):
    gt=ROOT/f'private/gt/{sid}'; cfg=config(); sc=source_scan_settings(sid); placements=load_json(gt/'placements.json')
    camera_key=stage_hash([file_hash(gt/'mesh.npz'),file_hash(gt/'placements.json'),file_hash(gt/'features.json')],sc,['camera.py','scan.py','sampling_density.py'],['numpy','open3d'])
    if not state.valid(sid,'trajectory',camera_key):
        state.begin(sid,'trajectory',camera_key)
        with measured() as timing: prepare_cameras(sid,state)
        state.finish(sid,'trajectory',camera_key,[gt/'cameras.json',gt/'feature_contract.json'],timing)
    camset=load_json(gt/'cameras.json'); meta=load_json(gt/'metadata.json'); mesh=np.load(gt/'mesh.npz')
    scene=None; inventory=[]
    for camera in camset['cameras']:
        label=f'{sid}/{camera["id"]}'; framekey=stage_hash([file_hash(gt/'mesh.npz'),camera],sc,['scan.py','camera.py','sampling_density.py'],['numpy','open3d'])
        index=ROOT/f'private/scan_index/{sid}/{camera["id"]}.json'
        if state.valid(label,'observations',framekey): inventory.append(load_json(index)); continue
        if scene is None: scene=scene_for(mesh['vertices'],mesh['faces'])
        state.begin(label,'observations',framekey)
        with measured() as timing:
            p=placements['placements'][camera['placement_id']]
            pixel,clean,stats=raycast_frame(scene,camera,p['T_table_from_object'],sc['incidence_deg'],p['epsilon_contact_mm'])
            outputs=[]; seeds={}; paired={}
            for seed in cfg['seeds']:
                stream=stable_seed(sc['noise_algorithm'],sid,seed,camera['placement_id'],noise_frame_key(camera,sc))
                noisy=(clean.astype(np.float64)+noise_for(pixel,stream,camset['sigma_mm'])).astype(np.float32)
                h=observation_hash(pixel,noisy); out=ROOT/f'data/observations/{h}.npz'
                if not out.exists(): atomic_npz(out,pixel=pixel,range_mm=noisy)
                outputs.append(out); seeds[str(seed)]={'observation':f'observations/{h}.npz','array_sha256':h,'file_sha256':file_hash(out),'count':len(pixel)}
                delta=noisy.astype(np.float64)-clean
                paired[str(seed)]={'n':len(delta),'sum':float(delta.sum()),'sum_squared':float(delta@delta),'abs_max_mm':float(np.max(np.abs(delta))) if len(delta) else 0}
            # Private finite clean evidence at quarter-density for factors and paired-ray audit.
            if camera['mother_frame_id']%4==0:
                cleanfile=ROOT/f'cache/clean/{sid}/{camera["id"]}.npz'; atomic_npz(cleanfile,pixel=pixel,range_mm=clean); outputs.append(cleanfile)
            item={'camera_id':camera['id'],'frame_hash':framekey,'seeds':seeds,'scan_stats':stats,'paired_noise':paired}
            atomic_json(index,item); outputs.append(index)
        state.finish(label,'observations',framekey,outputs,timing); inventory.append(item)
    atomic_json(ROOT/f'private/scan_index/{sid}/index.json',{'frames':inventory,'camera_hash':file_hash(gt/'cameras.json')})
    return inventory
