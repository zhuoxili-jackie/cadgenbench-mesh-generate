"""Independent exact-BREP checks prevent tessellated curved facets becoming fake supports."""
import numpy as np
from .common import *

def audit_placements(sid):
    from .sources import read_step
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.gp import gp_Trsf
    gt=ROOT/f'private/gt/{sid}';meta=load_json(gt/'metadata.json');placements=load_json(gt/'placements.json')['placements'];features=load_json(gt/'features.json')
    key=stage_hash([file_hash(ROOT/f'sources/{sid}/input.step'),file_hash(gt/'placements.json'),file_hash(gt/'features.json')],{},['placement_audit.py','contact_support.py'],['cadquery-ocp','numpy'])
    path=gt/'placement_audit.json'
    if path.exists() and load_json(path).get('key')==key and load_json(path).get('status')=='pass':return load_json(path)
    shape,units=read_step(ROOT/f'sources/{sid}/input.step');results=[]
    for p in placements:
        T=np.asarray(p['T_table_from_object']);full=T@np.asarray(meta['T_object_from_source_mm'])
        tr=gp_Trsf();tr.SetValues(*[float(x) for x in full[:3].ravel()])
        transformed=BRepBuilderAPI_Transform(shape,tr,True).Shape();box=Bnd_Box();BRepBndLib.AddOptimal_s(transformed,box,False,False)
        bounds=np.asarray(box.Get()).reshape(2,3);eps=p['epsilon_contact_mm'];actual_faces=[]
        for f in features:
            if f['type']!='plane':continue
            n=T[:3,:3]@np.asarray(f['normal']);c=T[:3,:3]@np.asarray(f['centroid'])+T[:3,3]
            if np.dot(n,[0,0,-1])>1-1e-8 and abs(c[2])<=eps:actual_faces.append(f)
        actual_area=sum(f['area_mm2'] for f in actual_faces)
        reasons=[]
        if bounds[0,2]<-eps:reasons.append('exact BREP penetrates table (mesh facets are not exact curved supports)')
        if abs(bounds[0,2])>eps:reasons.append('exact BREP lacks contact with table')
        discrete=None
        if actual_area<=0:
            from .contact_support import KIND,audit_discrete_placement
            if p.get('contact_kind')==KIND:
                discrete=audit_discrete_placement(sid,p)
                if discrete['status']!='pass':reasons.extend(discrete['reasons'])
            else:reasons.append('no actual external CAD planar contact area; point/line/rolling support requires separate treatment')
        if p['stability_margin_mm']<=eps:reasons.append('COM support margin not strictly positive')
        results.append({'placement_id':p['placement_id'],'status':'pass' if not reasons else 'failed','reasons':reasons,'exact_BREP_table_min_z_mm':bounds[0,2],
                        'actual_CAD_contact_faces':[f['face'] for f in actual_faces],'actual_CAD_contact_area_mm2':actual_area,
                        'mesh_contact_area_mm2':p['actual_contact_area_mm2'],'support_polygon_area_mm2':p['support_polygon_area_mm2'],'stability_margin_mm':p['stability_margin_mm'],
                        'candidate_face_is_only_direction_seed':p['candidate_CAD_face'],'rigid_uniform_density_assumption':True})
        if discrete is not None:results[-1]['discrete_contact_certificate']=discrete
    report={'status':'pass' if all(p['status']=='pass' for p in results) else 'failed','key':key,'source_id':sid,'placements':results,
            'method':'independent exact BREP transformed to table; optimal bounds without triangulation; actual co-planar CAD face area and contact identity; existing COM-in-support-hull proof'}
    atomic_json(path,report)
    if report['status']!='pass':raise ValueError(f'{sid}: exact BREP placement audit failed; inspect {path}')
    return report
