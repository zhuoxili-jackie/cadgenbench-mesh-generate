"""Exact CAD certificate for separated point/line contacts; never a reconstruction input."""
import numpy as np
from scipy.spatial import ConvexHull
from .common import *

KIND='certified_discrete_CAD_contacts'
CONTACT_TOL_MM=1e-7

def certify_contact(shape,T_table_from_source,points_source,epsilon_mm,diagonal_mm):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform,BRepBuilderAPI_MakeVertex
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.gp import gp_Trsf,gp_Pnt
    T=np.asarray(T_table_from_source,dtype=float);points=np.asarray(points_source,dtype=float)
    result={'status':'failed','reasons':[],'contact_coordinate_tolerance_mm':CONTACT_TOL_MM,'epsilon_contact_mm':epsilon_mm,'actual_contact_area_mm2':0.0,'method':'Exact BREP global minimum and individual point-to-BREP distances; independent COM projected into the convex hull of separated actual contact points. The support hull is not contact area.'}
    if T.shape!=(4,4) or not np.isfinite(T).all() or not np.allclose(T[3],[0,0,0,1],atol=1e-12,rtol=0) or not np.allclose(T[:3,:3].T@T[:3,:3],np.eye(3),atol=1e-10,rtol=0) or abs(np.linalg.det(T[:3,:3])-1)>1e-10:
        result['reasons'].append('not a finite proper rigid transform');return result
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<3 or not np.isfinite(points).all():
        result['reasons'].append('fewer than three finite noncollinear contact points');return result
    tr=gp_Trsf();tr.SetValues(*map(float,T[:3].ravel()));moved=BRepBuilderAPI_Transform(shape,tr,True).Shape();box=Bnd_Box();BRepBndLib.AddOptimal_s(moved,box,False,False);minimum=box.Get()[2]
    props=GProp_GProps();BRepGProp.VolumeProperties_s(shape,props);c=props.CentreOfMass();com=transform([[c.X(),c.Y(),c.Z()]],T)[0];table=transform(points,T)
    distances=[]
    for point in points:
        vertex=BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float,point))).Vertex();query=BRepExtrema_DistShapeShape(vertex,shape);query.Perform()
        if not query.IsDone():result['reasons'].append('exact point-to-CAD query did not finish');return result
        distances.append(query.Value())
    band=max(epsilon_mm,3*np.sqrt(2*diagonal_mm*CONTACT_TOL_MM))
    result.update(exact_CAD_minimum_z_mm=float(minimum),contact_points_source_mm=points,contact_points_table_mm=table,point_CAD_distances_mm=distances,max_contact_vertex_CAD_distance_mm=max(distances),max_contact_height_abs_mm=float(np.max(np.abs(table[:,2]))),center_mass_table_mm=com,robust_contact_margin_threshold_mm=float(band),support_polygon_area_mm2=0.0,stability_margin_mm=None)
    if abs(minimum)>epsilon_mm:result['reasons'].append('exact CAD floats above or penetrates the table')
    if max(distances)>CONTACT_TOL_MM:result['reasons'].append('claimed support points are not exact CAD surface points')
    if np.max(np.abs(table[:,2]))>CONTACT_TOL_MM+1e-12:result['reasons'].append('claimed support points do not touch the table')
    try:
        hull=ConvexHull(table[:,:2]);margin=float(np.min(-(hull.equations[:,:2]@com[:2]+hull.equations[:,2])))
        result.update(support_polygon_area_mm2=float(hull.volume),support_polygon_table_xy=table[hull.vertices,:2],stability_margin_mm=margin)
        if margin<=band:result['reasons'].append('COM support margin does not exceed the numerical/curvature contact band')
    except Exception:result['reasons'].append('contact points lack a noncollinear support polygon')
    result['status']='pass' if not result['reasons'] else 'failed'
    return result

def audit_discrete_placement(sid,placement):
    from .sources import read_step
    gt=ROOT/f'private/gt/{sid}';meta=load_json(gt/'metadata.json')
    if placement.get('contact_kind')!=KIND:raise ValueError('missing explicit discrete CAD contact kind')
    if placement['actual_contact_area_mm2']!=0:raise ValueError('point/line support must not invent a positive contact area')
    with np.load(gt/'mesh.npz') as raw:
        ids=np.asarray(placement['contact_vertex_ids'],dtype=np.int64)
        if len(np.unique(ids))<3 or ids.min()<0 or ids.max()>=len(raw['vertices']):raise ValueError('invalid contact vertex provenance')
        points=transform(raw['vertices'][ids],meta['T_source_mm_from_object'])
    shape,units=read_step(ROOT/f'sources/{sid}/input.step')
    result=certify_contact(shape,np.asarray(placement['T_table_from_object'])@np.asarray(meta['T_object_from_source_mm']),points,placement['epsilon_contact_mm'],meta['diagonal_mm'])
    result.update(source_sha256=file_hash(ROOT/f'sources/{sid}/input.step'),contact_vertex_ids=ids,rigid_assembly_assumption=meta['rigid_assembly_assumption'])
    if result['status']=='pass':
        if abs(result['stability_margin_mm']-placement['stability_margin_mm'])>1e-7 or not np.allclose(result['center_mass_table_mm'],placement['center_mass_table_mm'],rtol=0,atol=1e-7):
            result['reasons'].append('stored COM or support margin differs from independent CAD calculation');result['status']='failed'
    return result
