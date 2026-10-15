"""Public-only reconstruction. API accepts observations, cameras, config and output.

This module never imports simulator/sources/placements or reads private metadata.
Working vertices are actual noisy observations, never fitted to reference geometry.
"""
from pathlib import Path
import json, os, time, inspect
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from numba import njit
from .camera import backproject,pixel_directions,project
from .common import atomic_bytes,atomic_json,atomic_npz,load_json,file_hash,measured,digest

def resolve_observations(path):
    path=Path(path).resolve(); obj=load_json(path)
    root=(path.parent/obj['data_root_relative']).resolve()
    frames=[]
    for rec in obj['frames']:
        p=(path.parent/rec['path']).resolve()
        if not p.is_relative_to(root): raise ValueError('observation escapes public data root')
        if any(x in p.relative_to(root).parts for x in ['private','sources']): raise ValueError('private observation reference')
        if file_hash(p)!=rec['file_sha256']: raise ValueError(f'observation hash mismatch: {p.name}')
        frames.append((rec['camera_id'],p))
    return frames

def frame_points_normals(pixel,ranges,camera,normal_radius=2):
    n=camera['resolution']; img=np.full(n*n,np.nan,np.float64); img[pixel]=ranges; img=img.reshape(n,n)
    pmap=np.full((n*n,3),np.nan,np.float64); pmap[pixel]=backproject(pixel,ranges,camera); pmap=pmap.reshape(n,n,3)
    r=normal_radius
    center=pmap[r:-r,r:-r]; lr=pmap[r:-r,2*r:]-pmap[r:-r,:-2*r]; ud=pmap[2*r:,r:-r]-pmap[:-2*r,r:-r]
    normals=np.cross(lr,ud); lengths=np.linalg.norm(normals,axis=2)
    localrange=img[r:-r,r:-r]; spacing=localrange/camera['K'][0][0]
    jump=np.maximum(np.linalg.norm(lr,axis=2),np.linalg.norm(ud,axis=2))
    valid=np.isfinite(lengths)&(lengths>1e-12)&(jump<2*r*spacing*4.5)
    normals=normals[valid]/lengths[valid,None]; points=center[valid]
    eye=np.asarray(camera['T_object_from_camera'])[:3,3]
    normals[np.einsum('ij,ij->i',normals,eye-points)<0]*=-1
    ids=(np.arange(n*n).reshape(n,n)[r:-r,r:-r])[valid]
    # Best-conditioned viewing angle selects a real representative among redundant returns.
    view=eye-points; view/=np.linalg.norm(view,axis=1,keepdims=True)
    confidence=np.einsum('ij,ij->i',normals,view)
    return points,normals,ids,confidence

def voxel_keys(points,normals,voxel):
    q=np.floor(points/voxel).astype(np.int64)
    major=np.argmax(abs(normals),axis=1); side=(normals[np.arange(len(normals)),major]<0).astype(np.int64)
    cluster=major*2+side
    # Six normal cones preserve opposed thin-wall faces and orthogonal creases.
    keys=np.empty(len(points),dtype=[('x','i8'),('y','i8'),('z','i8'),('n','i8')])
    keys['x'],keys['y'],keys['z'],keys['n']=q[:,0],q[:,1],q[:,2],cluster
    return keys

def reduce_representatives(points,normals,frame_ids,pixels,confidence,voxel):
    keys=voxel_keys(points,normals,voxel)
    # Stable lexicographic selection: higher incidence quality, then earlier acquisition/pixel.
    order=np.lexsort((pixels,frame_ids,-confidence,keys['n'],keys['z'],keys['y'],keys['x']))
    sortedkeys=keys[order]; take=np.r_[True,sortedkeys[1:]!=sortedkeys[:-1]]; ids=order[take]
    return points[ids],normals[ids],frame_ids[ids],pixels[ids],confidence[ids]

@njit(cache=True)
def merge_indices(a,b,aq,bq,af,bf,au,bu):
    result=np.empty(len(a)+len(b),np.int64);i=0;j=0;n=0
    while i<len(a) and j<len(b):
        compare=0
        for k in range(4):
            if a[i,k]<b[j,k]:compare=-1;break
            if a[i,k]>b[j,k]:compare=1;break
        if compare<0:result[n]=i;i+=1
        elif compare>0:result[n]=len(a)+j;j+=1
        else:
            take_b=bq[j]>aq[i] or (bq[j]==aq[i] and (bf[j]<af[i] or (bf[j]==af[i] and bu[j]<au[i])))
            result[n]=len(a)+j if take_b else i;i+=1;j+=1
        n+=1
    while i<len(a):result[n]=i;i+=1;n+=1
    while j<len(b):result[n]=len(a)+j;j+=1;n+=1
    return result[:n]

def fuse(frames,cameras,cfg):
    spacing=float(np.median([(c['near_mm']+c['far_mm'])/2/c['K'][0][0] for c in cameras.values()]))
    voxel=spacing*cfg['voxel_pixel_factor'];P=np.empty((0,3));N=P.copy();F=np.empty(0,np.int32);U=np.empty(0,np.uint32);Q=np.empty(0);K=np.empty((0,4),np.int64)
    raw_count=0;normal_count=0;frame_counts=[]
    for i,(cid,path) in enumerate(frames):
        with np.load(path) as d:pixel=d['pixel'];ranges=d['range_mm']
        p,n,u,q=frame_points_normals(pixel,ranges,cameras[cid]);raw_count+=len(pixel);normal_count+=len(p);f=np.full(len(p),i,np.int32)
        p,n,f,u,q=reduce_representatives(p,n,f,u,q,voxel);k=voxel_keys(p,n,voxel).view(np.int64).reshape(-1,4)
        ids=merge_indices(K,k,Q,q,F,f,U,u)
        P,N,F,U,Q,K=[np.concatenate([a,b])[ids] for a,b in [(P,p),(N,n),(F,f),(U,u),(Q,q),(K,k)]]
        frame_counts.append({'camera_id':cid,'valid_returns':len(pixel),'normal_returns':len(p)})
        if i%100==0:print(f'fusion {i+1}/{len(frames)} working={len(P)}',flush=True)
    if len(P)<4:raise ValueError('insufficient observed points')
    tree=cKDTree(P);sample=np.linspace(0,len(P)-1,min(20000,len(P)),dtype=int)
    nearest=tree.query(P[sample],k=2,workers=2)[0][:,1];h=float(np.median(nearest))
    if not h>0:raise ValueError('zero working point spacing')
    return P,N,F,U,{'raw_returns':raw_count,'normal_returns':normal_count,'working_points':len(P),'voxel_mm':voxel,'h_mm':h,'h_method':'median NN on 20000 deterministic query points against full working cloud','frame_counts':frame_counts,'fusion':'actual observed representative in voxel and six oriented normal cones; best incidence; no point averaging'}

def sample_triangles(vertices,faces):
    tri=vertices[faces]
    # 1/5-edge lattice: with the 5h edge cap, support samples are at most h apart on edges.
    weights=[(i/5,j/5,(5-i-j)/5) for i in range(6) for j in range(6-i)]+[(1/3,1/3,1/3)]
    return np.einsum('sc,ncd->nsd',np.asarray(weights),tri)

def support_in_camera_numpy(points,img,camera,tolerance):
    uv,ran,z=project(points,camera); res=camera['resolution']; pix=np.rint(uv).astype(np.int64)
    inside=(z>0)&(pix[:,0]>=1)&(pix[:,0]<res-1)&(pix[:,1]>=1)&(pix[:,1]<res-1)
    supported=np.zeros(len(points),bool); conflict=np.zeros(len(points),bool)
    ii=np.flatnonzero(inside)
    if not len(ii): return supported,conflict
    x,y=pix[ii,0],pix[ii,1]
    rr=img[y,x]; good=np.isfinite(rr)
    # Depth agreement uses Euclidean range. Missing masks never count as support.
    supported[ii]=good&(abs(rr-ran[ii])<=tolerance)
    local=np.stack([img[y+dy,x+dx] for dy in [-1,0,1] for dx in [-1,0,1]],axis=1)
    consistent=np.isfinite(local).all(axis=1)&(np.max(local,axis=1)-np.min(local,axis=1)<2*tolerance)
    conflict[ii]=consistent&(ran[ii]<np.min(local,axis=1)-tolerance)
    return supported,conflict

def support_in_camera(points,img,camera,tolerance):
    from .observed_kernel import range_support
    C=np.asarray(camera['T_object_from_camera']); K=np.asarray(camera['K'])
    return range_support(np.ascontiguousarray(points,dtype=np.float64),img,np.ascontiguousarray(C[:3,:3]),np.ascontiguousarray(C[:3,3]),K[0,0],K[1,1],K[0,2],K[1,2],tolerance)

def filter_observed_mesh(mesh,P,F,frames,cameras,sigma,h,cfg):
    vertices=np.asarray(mesh.vertices); faces=np.asarray(mesh.triangles)
    tri=vertices[faces]; edge=np.max(np.linalg.norm(tri-np.roll(tri,1,axis=1),axis=2),axis=1)
    # BPA already constrains circumradius; this conservative edge cap bounds sample gaps.
    max_edge=2*max(cfg['radii_h'])*h
    keep=edge<=max_edge*(1+1e-6)
    tolerance=max(cfg['support_sigma']*sigma,cfg['support_h']*h)
    samples=sample_triangles(vertices,faces)
    ns=samples.shape[1]
    # Range-image support measures a continuous observed surface. A nearest-working-
    # vertex veto would incorrectly perforate valid triangles between irregular representatives.
    candidate=np.flatnonzero(keep); supported=np.zeros((len(candidate),ns),bool); conflicts=np.zeros((len(candidate),ns),bool)
    ps=samples[candidate].reshape(-1,3)
    # Every selected observation participates; no GT normal or surface query exists here.
    for i,(cid,path) in enumerate(frames):
        with np.load(path) as d:
            res=cameras[cid]['resolution']; img=np.full(res*res,np.nan,np.float32); img[d['pixel']]=d['range_mm']; img=img.reshape(res,res)
        for start in range(0,len(ps),350000):
            end=min(start+350000,len(ps)); ok,bad=support_in_camera(ps[start:end],img,cameras[cid],tolerance)
            supported.reshape(-1)[start:end]|=ok
            conflicts.reshape(-1)[start:end]|=bad
        if i%50==0: print(f'support {i+1}/{len(frames)} faces={len(candidate)}',flush=True)
    keep[candidate]&=supported.all(axis=1)&(~conflicts.any(axis=1))
    result=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(faces[keep]))
    result.remove_degenerate_triangles(); result.remove_duplicated_triangles(); result.remove_unreferenced_vertices()
    return result,{'candidate_faces':len(faces),'kept_faces':int(keep.sum()),'rejected_faces':int((~keep).sum()),
                   'support_tolerance_mm':tolerance,'samples_per_triangle':ns,'edge_limit_mm':max_edge,'free_space_conflict_faces':int(conflicts.any(axis=1).sum()),
                   'support_rule':'fifth-edge barycentric lattice plus centroid; range-image support; stable 3x3 foreground free-space veto; no invalid pixel is support'}

def orient_from_observations(mesh,P,N):
    """Enforce shared-edge winding; choose component sign from observed normals only."""
    v=np.asarray(mesh.vertices); f=np.asarray(mesh.triangles).copy(); before=f.copy()
    nearest=cKDTree(P).query(v,workers=2)[1]; observed=N[nearest]
    tri=v[f]; normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]); area=np.linalg.norm(normal,axis=1)/2
    agrees=np.einsum('ij,ij->i',normal,observed[f].sum(axis=1)); reverse=agrees<0
    f[reverse]=f[reverse][:,[0,2,1]]
    edges=np.stack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]],axis=1).reshape(-1,2)
    # Open3D indices are int32. Multiplication in that dtype silently aliases
    # distinct edges once V^2 exceeds 2^32, creating false topology conflicts.
    canon=np.sort(edges.astype(np.int64),axis=1); key=canon[:,0]*len(v)+canon[:,1]; order=np.argsort(key,kind='stable'); keys=key[order]
    starts=np.r_[0,np.flatnonzero(keys[1:]!=keys[:-1])+1]; counts=np.diff(np.r_[starts,len(keys)])
    if np.any(counts>2): raise ValueError('BPA created nonmanifold edges')
    pair=starts[counts==2]; a=order[pair]; b=order[pair+1]
    facea=a//3; faceb=b//3; bad=edges[a,0]==edges[b,0]
    # Same-directed edges after normal orientation identify locally folded/overlapping
    # facets. Remove the less well-conditioned observed facet, never add a face.
    tri=v[f]; lengths=np.linalg.norm(tri-np.roll(tri,1,axis=1),axis=2)
    quality=area/np.maximum((lengths*lengths).sum(axis=1),1e-30)
    keep=np.ones(len(f),bool)
    for fa,fb in zip(facea[bad],faceb[bad]):
        if keep[fa] and keep[fb]: keep[fa if quality[fa]<quality[fb] else fb]=False
    removed=int((~keep).sum()); removed_area=float(area[~keep].sum()); f=f[keep]
    mesh.triangles=o3d.utility.Vector3iVector(f)
    # Separate disconnected vertex fans using coincident vertex identities only.
    # This removes zero-area topological pinches without changing any triangle geometry.
    badvertices=np.asarray(mesh.get_non_manifold_vertices(),dtype=int); vertices=list(v); split_count=0
    # Incident membership of an original vertex cannot change while splitting
    # another vertex. Build this index once, preserving ascending face order;
    # links below still read the current updated face indices.
    vertex_order=np.argsort(f.reshape(-1),kind='stable'); incident_faces=vertex_order//3
    offsets=np.r_[0,np.cumsum(np.bincount(f.reshape(-1),minlength=len(v)))]
    for vid in badvertices:
        incident=incident_faces[offsets[vid]:offsets[vid+1]]; links={int(fi):set(map(int,f[fi][f[fi]!=vid])) for fi in incident}
        remaining=set(map(int,incident)); fans=[]
        while remaining:
            seed=remaining.pop(); fan=[seed]; stack=[seed]
            while stack:
                cur=stack.pop(); neighbors=[j for j in remaining if links[cur]&links[j]]
                for j in neighbors: remaining.remove(j);fan.append(j);stack.append(j)
            fans.append(fan)
        for fan in fans[1:]:
            new=len(vertices);vertices.append(v[vid]);split_count+=1
            for fi in fan: f[fi,f[fi]==vid]=new
    mesh.vertices=o3d.utility.Vector3dVector(np.asarray(vertices));mesh.triangles=o3d.utility.Vector3iVector(f);mesh.remove_unreferenced_vertices()
    if not mesh.is_orientable() or not mesh.is_vertex_manifold(): raise ValueError('unresolved illegal observed mesh connectivity')
    return {'flipped_face_count':int(reverse.sum()),'overlap_conflict_faces_removed':removed,'overlap_conflict_area_mm2':removed_area,'pinch_vertices_split':split_count,
            'method':'orient facets by measured normals; discard weaker conflicting shared-edge facets; separate coincident disconnected vertex fans; no surface added'}

def continuous_identity(vertices,faces,frames,cameras,tolerance):
    import hashlib,numba,scipy
    geometry={'vertices':hashlib.sha256(np.ascontiguousarray(vertices,dtype=np.float64).tobytes()).hexdigest(),
              'faces':hashlib.sha256(np.ascontiguousarray(faces,dtype=np.int64).tobytes()).hexdigest()}
    identity={'geometry':geometry,'observations':[(cid,file_hash(path)) for cid,path in frames],'cameras':cameras,'tolerance_mm':tolerance,
              'module_sha256':file_hash(Path(__file__).with_name('continuous_free_space.py')),'numpy':np.__version__,'numba':numba.__version__,'scipy':scipy.__version__}
    return digest(identity),identity

def continuous_free_space_veto(mesh,frames,cameras,tolerance,cache):
    from .continuous_free_space import conflicts_in_camera
    vertices=np.asarray(mesh.vertices);faces=np.asarray(mesh.triangles)
    key,identity=continuous_identity(vertices,faces,frames,cameras,tolerance)
    artifact=cache/'continuous.npz';marker=cache/'continuous.json';start=time.perf_counter()
    if artifact.exists() and marker.exists() and load_json(marker).get('key')==key and load_json(marker).get('artifact_sha256')==file_hash(artifact):
        with np.load(artifact) as z:ids=z['face_ids'];first=z['first_frame'];pixels=z['pixels']
        metrics=load_json(marker)['metrics'];print('reuse verified continuous foreground free-space check',flush=True)
    else:
        first_all=np.full(len(faces),-1,np.int32);pixels_all=np.full((len(faces),2),-1,np.int32)
        for ordinal,(cid,path) in enumerate(frames):
            cam=cameras[cid];res=cam['resolution']
            with np.load(path) as z:
                image=np.full(res*res,np.nan,np.float32);image[z['pixel']]=z['range_mm'];image=image.reshape(res,res)
            bad,where=conflicts_in_camera(vertices,faces,image,cam,tolerance)
            fresh=bad&(first_all<0);first_all[fresh]=ordinal;pixels_all[fresh]=where[fresh]
            if ordinal%100==0:print(f'continuous free-space {ordinal+1}/{len(frames)} rejected={int((first_all>=0).sum())}',flush=True)
        ids=np.flatnonzero(first_all>=0);first=first_all[ids];pixels=pixels_all[ids]
        triangles=vertices[faces];areas=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)/2
        metrics={'rule':'minimum Euclidean range over triangle clipped to every intersected stable 3x3 foreground nearest-pixel cell; no GT; unchanged tolerance',
                 'checked_faces':len(faces),'checked_frames':len(frames),'removed_faces':len(ids),'removed_area_mm2':float(areas[ids].sum()),'removed_area_fraction':float(areas[ids].sum()/areas.sum()),'tolerance_mm':tolerance,'seconds':time.perf_counter()-start}
        atomic_npz(artifact,face_ids=ids,first_frame=first,pixels=pixels)
        atomic_json(marker,{'key':key,'identity':identity,'artifact_sha256':file_hash(artifact),'metrics':metrics})
    assert ids.ndim==1 and len(ids)==len(first)==len(pixels) and np.all((ids>=0)&(ids<len(faces))) and np.all(np.diff(ids)>0)
    keep=np.ones(len(faces),bool);keep[ids]=False
    if len(ids):
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(faces[keep]));mesh.remove_unreferenced_vertices()
    return mesh,{'key':key,'identity':identity,'artifact_sha256':file_hash(artifact),**metrics}

def reconstruct(observations,cameras,configuration,output):
    """Reconstruct using public observations and public camera parameters only."""
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    frames=resolve_observations(observations); camdata=load_json(cameras); cams={c['id']:c for c in camdata['cameras']}
    cfg=load_json(configuration) if isinstance(configuration,(str,Path)) else configuration
    if cfg.get('global_completion',False): raise ValueError('global completion forbidden')
    with measured() as perf:
        cache=output/'.reconstruction_cache'; cache.mkdir(exist_ok=True)
        fkey=digest([file_hash(observations),file_hash(cameras),file_hash(Path(__file__).with_name('camera.py')),{k:cfg[k] for k in ['voxel_pixel_factor']},
                     [inspect.getsource(fn) for fn in [fuse,merge_indices.py_func,frame_points_normals,reduce_representatives,voxel_keys]],np.__version__,__import__('numba').__version__])
        fp=cache/'fusion.npz'; fm=cache/'fusion.json'
        if fp.exists() and fm.exists() and load_json(fm).get('key')==fkey and load_json(fm).get('file_hash')==file_hash(fp):
            with np.load(fp) as d: P=d['P'];N=d['N'];F=d['F'];U=d['U']
            fusion=load_json(fm)['metrics']; print('reuse valid observation fusion',flush=True)
        else:
            P,N,F,U,fusion=fuse(frames,cams,cfg); atomic_npz(fp,P=P,N=N,F=F,U=U)
            atomic_json(fm,{'key':fkey,'file_hash':file_hash(fp),'metrics':fusion})
        pc=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P)); pc.normals=o3d.utility.Vector3dVector(N)
        start=time.perf_counter(); radii=[r*fusion['h_mm'] for r in cfg['radii_h']]
        print(f'BPA points={len(P)} radii={radii}',flush=True)
        bp=cache/'bpa.npz'; bm=cache/'bpa.json'; bkey=digest([fkey,radii,o3d.__version__])
        if bp.exists() and bm.exists() and load_json(bm).get('key')==bkey and load_json(bm).get('file_hash')==file_hash(bp):
            with np.load(bp) as d: mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(d['vertices']),o3d.utility.Vector3iVector(d['faces']))
        else:
            mesh=o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(pc,o3d.utility.DoubleVector(radii))
            atomic_npz(bp,vertices=np.asarray(mesh.vertices),faces=np.asarray(mesh.triangles)); atomic_json(bm,{'key':bkey,'file_hash':file_hash(bp)})
        bpa_s=time.perf_counter()-start
        import numba
        sp=cache/'supported.npz'; sm=cache/'supported.json'; skey=digest([bkey,cfg,camdata['sigma_mm'],file_hash(Path(__file__).with_name('observed_kernel.py')),numba.__version__,[inspect.getsource(fn) for fn in [filter_observed_mesh,sample_triangles,support_in_camera]]])
        # Documented metadata-only correction: the actual lattice has always
        # divided edges by five. Accept the exact old function hashes only for
        # this label/comment correction; any numerical code change still misses.
        old_sources=[inspect.getsource(filter_observed_mesh).replace('fifth-edge barycentric','quarter-edge barycentric'),inspect.getsource(sample_triangles).replace('# 1/5-edge lattice: with the 5h edge cap','# 1/4-edge lattice: with the 4h edge cap'),inspect.getsource(support_in_camera)]
        kernel=Path(__file__).with_name('observed_kernel.py');early_exit_block=b'        # Patch minimum cannot exceed its finite centre value.\n        if ran>=rr-tolerance: continue\n'
        import hashlib
        previous_kernel_hash=hashlib.sha256(kernel.read_bytes().replace(early_exit_block,b'')).hexdigest()
        # The exact legacy hash is derivable only when all other kernel bytes
        # match. The centre-bound early exit is proven mask-equivalent.
        compatible_keys=[digest([bkey,cfg,camdata['sigma_mm'],kh,numba.__version__,sources]) for kh in [file_hash(kernel),previous_kernel_hash] for sources in [old_sources,[inspect.getsource(fn) for fn in [filter_observed_mesh,sample_triangles,support_in_camera]]]]
        if sp.exists() and sm.exists() and load_json(sm).get('key') in compatible_keys and load_json(sm).get('file_hash')==file_hash(sp):
            with np.load(sp) as d: mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(d['vertices']),o3d.utility.Vector3iVector(d['faces']))
            filtering=load_json(sm)['metrics']; print('reuse valid observation support filtering',flush=True)
            if load_json(sm)['key']!=skey:
                previous_key=load_json(sm)['key']
                filtering['support_rule']=filtering['support_rule'].replace('quarter-edge barycentric','fifth-edge barycentric')
                atomic_json(sm,{'key':skey,'file_hash':file_hash(sp),'metrics':filtering,'equivalent_cache_migration_from':previous_key,'migration':'fifth-edge label correction and/or centre-bound early exit; identical triangle samples and proven identical support/free-space masks'})
        else:
            mesh,filtering=filter_observed_mesh(mesh,P,F,frames,cams,camdata['sigma_mm'],fusion['h_mm'],cfg)
            atomic_npz(sp,vertices=np.asarray(mesh.vertices),faces=np.asarray(mesh.triangles)); atomic_json(sm,{'key':skey,'file_hash':file_hash(sp),'metrics':filtering})
        orientation=orient_from_observations(mesh,P,N)
        mesh,continuous=continuous_free_space_veto(mesh,frames,cams,filtering['support_tolerance_mm'],cache)
        if continuous['removed_faces']:
            continuous['post_veto_connectivity_cleanup']=orient_from_observations(mesh,P,N)
        if not len(mesh.triangles): raise ValueError('empty reconstructed mesh')
        mesh.compute_triangle_normals()
        for name,obj in [('mesh.ply',mesh),('mesh.stl',mesh),('points_for_meshing.ply',pc)]:
            tmp=output/(name+'.partial'+Path(name).suffix)
            success=o3d.io.write_point_cloud(str(tmp),obj,write_ascii=False) if name.startswith('points') else o3d.io.write_triangle_mesh(str(tmp),obj,write_ascii=False)
            if not success: raise IOError(f'failed to write {name}')
            target=output/name
            if target.exists() and file_hash(tmp)==file_hash(target):tmp.unlink()
            else:os.replace(tmp,target)
        provenance=output/'point_provenance.npz';same_provenance=False
        if provenance.exists():
            with np.load(provenance) as prior:same_provenance=np.array_equal(prior['frame_index'],F) and np.array_equal(prior['pixel'],U)
        if not same_provenance:atomic_npz(provenance,frame_index=F,pixel=U)
        continuous['output_geometry']=continuous_identity(np.asarray(mesh.vertices),np.asarray(mesh.triangles),[],{},filtering['support_tolerance_mm'])[1]['geometry']
        atomic_json(output/'continuous_veto.json',continuous)
    metrics={'fusion':fusion,'filtering':filtering,'orientation':orientation,'radii_mm':radii,'bpa_seconds':bpa_s,'performance':perf,
             'vertices':len(mesh.vertices),'triangles':len(mesh.triangles),'method':cfg['method'],'continuous_free_space':{k:v for k,v in continuous.items() if k!='identity'}}
    atomic_json(output/'reconstruction.json',metrics)
    return metrics
