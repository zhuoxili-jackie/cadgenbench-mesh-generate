"""Check nonplanar hull candidates against actual CAD before calling poses limited."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
import numpy as np,trimesh
from scipy.spatial import ConvexHull
from hull_pose_proposals import propose
from scanbench.common import *
from scanbench.sources import read_step
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform,BRepBuilderAPI_MakeVertex
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.Bnd import Bnd_Box
from OCP.gp import gp_Trsf,gp_Pnt

sid=sys.argv[1];gt=ROOT/f'private/gt/{sid}';meta=load_json(gt/'metadata.json');raw=np.load(gt/'mesh.npz');mesh=trimesh.Trimesh(raw['vertices'],raw['faces'],process=False);chosen=load_json(gt/'placements.json')['placements'];shape,_=read_step(ROOT/f'sources/{sid}/input.step');D=meta['diagonal_mm'];eps=max(1e-5,1e-6*D);precise_contact=1e-7;robust_margin=max(eps,3*np.sqrt(2*D*precise_contact))
proposal_code=ROOT/'scripts/hull_pose_proposals.py'
proof_key=digest({'source':meta['source_sha256'],'mesh':file_hash(gt/'mesh.npz'),'placements':file_hash(gt/'placements.json'),'script':file_hash(Path(__file__)),'proposal_code':file_hash(proposal_code),'packages':{p:__import__('importlib.metadata',fromlist=['version']).version(p) for p in ['trimesh','cadquery-ocp','numpy','scipy']}})
proof_path=gt/'limited_pose_investigation.json'
if proof_path.exists() and load_json(proof_path).get('proof_key')==proof_key:
    existing=load_json(proof_path);print(canonical_json({k:v for k,v in existing.items() if k!='candidates'}));raise SystemExit(0 if existing['status']=='only_existing_poses_certified' else 2)
transforms,proposal_details=propose(mesh.vertices,meta['center_mass_object_mm']);probability=[None]*len(transforms)
atomic_json(gt/'candidate_pose_proposals.json',{'proof_key':proof_key,'proposal_details':proposal_details,'transforms':transforms})
progress_path=ROOT/f'state/pose_audits/{sid}.json'
prior=load_json(progress_path) if progress_path.exists() else {}
rows=prior.get('candidates',[]) if prior.get('proof_key')==proof_key else [];completed_ranks={r['rank'] for r in rows};seen=[]
print(canonical_json({'event':'pose_proposals_ready','source':sid,**proposal_details}),flush=True)
for rank,(T,prob) in enumerate(zip(transforms,probability)):
    n=-T[2,:3]
    if any(np.dot(n,p['support_outward_object'])>.9999 for p in chosen):continue
    if any(np.dot(n,q)>.999999 for q in seen):continue
    seen.append(n.copy())
    if rank in completed_ranks:continue
    full=T@np.array(meta['T_object_from_source_mm']);tr=gp_Trsf();tr.SetValues(*map(float,full[:3].ravel()));moved=BRepBuilderAPI_Transform(shape,tr,True).Shape();box=Bnd_Box();BRepBndLib.AddOptimal_s(moved,box,False,False);low=box.Get()[2]
    vv=transform(mesh.vertices,T);cm=transform(np.array([meta['center_mass_object_mm']]),T)[0];ids=np.flatnonzero(abs(vv[:,2]-low)<=precise_contact);margin=None;area=0.;hullxy=[];point_error=None
    if len(ids)>=3:
        try:
            hull=ConvexHull(vv[ids,:2]);hullxy=vv[ids[hull.vertices],:2];area=float(hull.volume);margin=float((-(hull.equations[:,:2]@cm[:2]+hull.equations[:,2])).min())
        except Exception:pass
    reliable=margin is not None and margin>robust_margin and abs(low)<=eps
    if reliable:
        errors=[]
        for idx in ids:
            p=mesh.vertices[idx]+(-np.asarray(meta['T_object_from_source_mm'])[:3,3]);vertex=BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float,p))).Vertex();distance=BRepExtrema_DistShapeShape(vertex,shape);distance.Perform();errors.append(distance.Value())
        point_error=max(errors);reliable=point_error<=precise_contact
    row={'rank':rank,'mesh_based_probability':None,'support_outward_object':n,'T_table_from_object_mesh_candidate':T,'exact_CAD_minimum_z_before_adjustment_mm':low,'native_vertices_at_exact_CAD_contact':len(ids),'support_hull_area_mm2':area,'COM_margin_mm':margin,'robust_contact_margin_threshold_mm':robust_margin,'max_contact_vertex_CAD_distance_mm':point_error,'certified_additional_candidate':bool(reliable),'reason':'exact CAD contact vertices span a robust polygon containing COM' if reliable else 'mesh hull candidate does not establish a robust polygon of exact CAD contacts; curved tessellation facets or point/line balance are not accepted as planar supports'}
    rows.append(row)
    atomic_json(progress_path,{'proof_key':proof_key,'candidates':rows,'proposal_count':len(transforms),'last_completed_rank':rank})
    if len(rows)%10==0:print(canonical_json({'event':'pose_candidates_checked','source':sid,'checked':len(rows),'rank':rank,'proposals':len(transforms)}),flush=True)
report={'status':'additional_certified_pose_requires_integration' if any(r['certified_additional_candidate'] for r in rows) else 'only_existing_poses_certified','source_id':sid,'source_sha256':meta['source_sha256'],'mesh_sha256':file_hash(gt/'mesh.npz'),'existing_certified_pose_count':len(chosen),'stable_hull_transforms_returned':len(transforms),'nonduplicate_nonplanar_candidates_checked':len(rows),'contact_coordinate_tolerance_mm':precise_contact,'geometric_contact_epsilon_mm':eps,'method':'Trimesh stable-hull proposals only; each checked with exact transformed BREP minimum and native vertices coincident with that exact CAD contact height; COM margin must exceed a conservative curvature/numerical-contact band; mesh facets are never called true CAD area contact','scope':'finite candidate audit, not a mathematical enumeration of every possible continuous rolling equilibrium; additional point/line candidates are not automatically reliable','candidates':rows}
report.update(proof_key=proof_key,placements_sha256=file_hash(gt/'placements.json'),script_sha256=file_hash(Path(__file__)),proposal_code_sha256=file_hash(proposal_code),proposal_details=proposal_details,method='Finite independent SciPy hull support proposals followed by unchanged exact CAD minimum/contact/COM verification; candidate geometry never replaces GT or reconstruction input')
atomic_json(proof_path,report);print(canonical_json({k:v for k,v in report.items() if k!='candidates'}))
if report['status']!='only_existing_poses_certified':raise SystemExit(2)
