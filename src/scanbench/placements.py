"""Stable table contact from actual outer support planes, with COM margins."""
import numpy as np
import trimesh
from scipy.spatial import ConvexHull
from .common import *

def rotation_to_z(n):
    n=np.asarray(n,dtype=float); n/=np.linalg.norm(n)
    # Object outward support normal becomes world -Z.
    z=-n; helper=np.array([1.,0,0]) if abs(z[0])<.8 else np.array([0.,1,0])
    x=np.cross(helper,z); x/=np.linalg.norm(x); y=np.cross(z,x)
    return np.stack([x,y,z])

def candidates(vertices,faces,com,planar_features):
    vertices=np.asarray(vertices); faces=np.asarray(faces); com=np.asarray(com)
    D=float(np.linalg.norm(np.ptp(vertices,axis=0))); eps=max(1e-5,1e-6*D)
    tm=trimesh.Trimesh(vertices,faces,process=False); options=[]; seen=[]
    normals=[(np.asarray(f['normal']),f['face'],'CAD external plane') for f in planar_features if f['type']=='plane']
    # Hull facets add candidates; no unsupported facet can pass true contact-area check.
    if not normals:
        hull=ConvexHull(vertices)
        normals.extend((n[:3],None,'convex hull candidate') for n in hull.equations)
    for n,faceid,origin in normals:
        n=n/np.linalg.norm(n)
        if any(np.dot(n,m)>.999999 for m in seen): continue
        seen.append(n)
        R=rotation_to_z(n); vv=vertices@R.T; zmin=float(vv[:,2].min()); vv[:,2]-=zmin
        contact_ids=np.flatnonzero(vv[:,2]<=eps)
        if len(contact_ids)<3: continue
        xy=vv[contact_ids,:2]
        try: hull=ConvexHull(xy)
        except Exception: continue
        hull_xy=xy[hull.vertices]; cm=com@R.T; cm[2]-=zmin
        margins=-(hull.equations[:,:2]@cm[:2]+hull.equations[:,2])
        margin=float(margins.min())
        contact_faces=np.flatnonzero(np.max(vv[faces,2],axis=1)<=eps)
        area=float(tm.area_faces[contact_faces].sum())
        # Positive stable margin and finite real area: no tessellated cylinder facet stands in for a plane.
        if margin<=eps or area<=D*D*1e-10: continue
        T=np.eye(4); T[:3,:3]=R; T[2,3]=-zmin
        options.append({'T_table_from_object':T,'support_outward_object':n,'candidate_CAD_face':faceid,'candidate_origin':origin,
                        'actual_contact_area_mm2':area,'support_polygon_area_mm2':float(hull.volume),'support_polygon_table_xy':hull_xy,
                        'center_mass_table_mm':cm,'stability_margin_mm':margin,'epsilon_contact_mm':eps,'minimum_z_mm':float(vv[:,2].min()),
                        'contact_vertex_count':len(contact_ids),'contact_triangle_ids':contact_faces,'selection_reason':None})
    options.sort(key=lambda p:(-p['actual_contact_area_mm2'],-p['stability_margin_mm']))
    for i,p in enumerate(options): p['candidate_rank_by_contact']=i
    selected=[]
    if options:
        selected.append(options.pop(0)); selected[0]['selection_reason']='largest actual external contact area; positive COM stability margin'
    while options and len(selected)<3:
        def score(p):
            dots=[np.dot(p['support_outward_object'],s['support_outward_object']) for s in selected]
            # Different direction is mandatory; nearest orthogonal directions rank first.
            return (min(1-abs(d) for d in dots),1-max(dots),p['actual_contact_area_mm2'])
        options.sort(key=score,reverse=True); p=options.pop(0)
        if any(np.dot(p['support_outward_object'],s['support_outward_object'])>.9999 for s in selected): continue
        p['selection_reason']='distinct stable support direction; prioritise orthogonality then exposure of previous contact'
        selected.append(p)
    for i,p in enumerate(selected):
        p['placement_id']=i
        p['angles_to_prior_deg']=[float(np.rad2deg(np.arccos(np.clip(np.dot(p['support_outward_object'],s['support_outward_object']),-1,1)))) for s in selected[:i]]
    return {'placements':selected,'additional_candidates':options,'limited_placements':len(selected)<3,'uniform_density':True,'epsilon_contact_mm':eps}

def prepare_placements(sid,state):
    gt=ROOT/f'private/gt/{sid}'; meta=load_json(gt/'metadata.json')
    key=stage_hash([file_hash(gt/'mesh.npz'),file_hash(gt/'features.json'),meta['center_mass_object_mm']],{},['placements.py'],['numpy','scipy'])
    path=gt/'placements.json'
    if state.valid(sid,'placements',key): return load_json(path)
    state.begin(sid,'placements',key)
    with measured() as timing:
        mesh=np.load(gt/'mesh.npz')
        result=candidates(mesh['vertices'],mesh['faces'],meta['center_mass_object_mm'],load_json(gt/'features.json'))
        if not result['placements']: raise ValueError(f'{sid}: no verified area-contact stable pose; investigate CAD contacts before source decision')
        result['rigid_assembly_assumption']=meta['rigid_assembly_assumption']
        result['stage_hash']=key
        atomic_json(path,result)
    state.finish(sid,'placements',key,[path],timing)
    return result
