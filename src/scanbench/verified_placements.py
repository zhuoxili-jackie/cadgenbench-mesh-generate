"""Accept existing proven poses, otherwise retry with exact external CAD planes."""
import numpy as np
from .common import *
from .placements import prepare_placements,candidates,rotation_to_z
from .placement_audit import audit_placements

def prepare_verified_placements(sid,state):
    gt=ROOT/f'private/gt/{sid}';key=stage_hash([file_hash(gt/'mesh.npz'),file_hash(gt/'features.json'),file_hash(gt/'metadata.json')],{},
                                         ['verified_placements.py','placement_audit.py','placements.py','contact_support.py'],['numpy','scipy','cadquery-ocp'])
    if state.valid(sid,'placements',key):return load_json(gt/'placements.json')
    if not (gt/'placements.json').exists():prepare_placements(sid,state)
    try:audit_placements(sid)
    except ValueError:
        from .sources import read_step
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.BRepBndLib import BRepBndLib
        from OCP.Bnd import Bnd_Box
        from OCP.gp import gp_Trsf
        meta=load_json(gt/'metadata.json');features=load_json(gt/'features.json');shape,_=read_step(ROOT/f'sources/{sid}/input.step')
        eps=max(1e-5,1e-6*meta['diagonal_mm']);certified=[];checks=[]
        for face in features:
            if face['type']!='plane':continue
            R=rotation_to_z(face['normal']);T=np.eye(4);T[:3,:3]=R;T[2,3]=-(R@np.asarray(face['centroid']))[2]
            full=T@np.asarray(meta['T_object_from_source_mm']);tr=gp_Trsf();tr.SetValues(*[float(x) for x in full[:3].ravel()])
            transformed=BRepBuilderAPI_Transform(shape,tr,True).Shape();box=Bnd_Box();BRepBndLib.AddOptimal_s(transformed,box,False,False);low=box.Get()[2]
            valid=abs(low)<=eps;checks.append({'face':face['face'],'BREP_min_z_if_that_plane_touches_mm':low,'outer_plane':valid})
            if valid:certified.append(face)
        atomic_json(gt/'outer_plane_audit.json',{'checks':checks,'method':'exact BREP bounding minimum after setting each CAD plane to table height'})
        if not certified:raise ValueError(f'{sid}: no verified planar support; needs explicit point/line/rolling-contact investigation, not exclusion')
        mesh=np.load(gt/'mesh.npz');result=candidates(mesh['vertices'],mesh['faces'],meta['center_mass_object_mm'],certified)
        if not result['placements']:raise ValueError(f'{sid}: external planar candidates lack positive COM support; requires further investigation')
        result.update(rigid_assembly_assumption=meta['rigid_assembly_assumption'],stage_hash=key,selection_precondition='exact BREP external-plane audit')
        atomic_json(gt/'placements.json',result);audit_placements(sid)
    state.begin(sid,'placements',key)
    outputs=[gt/'placements.json',gt/'placement_audit.json']
    if (gt/'outer_plane_audit.json').exists():outputs.append(gt/'outer_plane_audit.json')
    state.finish(sid,'placements',key,outputs,{'existing_pose_geometry_preserved_if_valid':True})
    return load_json(gt/'placements.json')
