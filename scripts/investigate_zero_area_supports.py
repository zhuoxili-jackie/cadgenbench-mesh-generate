"""Read-only exact-CAD investigation when the initial planar candidate set is empty."""
from pathlib import Path
import os, sys, time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import read_step
from scanbench.placements import candidates, rotation_to_z
from scanbench.contact_support import CONTACT_TOL_MM
from hull_pose_proposals import propose
from scipy.spatial import ConvexHull
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.gp import gp_Trsf

sid=sys.argv[1];gt=ROOT/f'private/gt/{sid}';folder=ROOT/f'reports/source_investigations/{sid}';folder.mkdir(exist_ok=True)
meta=load_json(gt/'metadata.json');features=load_json(gt/'features.json')
with np.load(gt/'mesh.npz') as z:vertices=z['vertices'];faces=z['faces']
assert not (ROOT/f'private/scan_index/{sid}/index.json').exists()
initial=candidates(vertices,faces,meta['center_mass_object_mm'],features)
assert not initial['placements'],'This diagnostic is for the zero-planar-pose failure only.'
shape,_=read_step(ROOT/f'sources/{sid}/input.step');eps=initial['epsilon_contact_mm'];D=meta['diagonal_mm'];band=max(eps,3*np.sqrt(2*D*CONTACT_TOL_MM))
key=digest([meta['source_sha256'],file_hash(gt/'mesh.npz'),file_hash(Path(__file__)),file_hash(ROOT/'scripts/hull_pose_proposals.py')])
out=folder/'zero_area_supports.json';prior=load_json(out) if out.exists() else {}
if prior.get('key')==key and prior.get('status')=='diagnostic_complete':
    print(canonical_json({k:v for k,v in prior.items() if k not in ['plane_candidates','hull_candidates']}));raise SystemExit()

def inspect(T):
    full=T@np.asarray(meta['T_object_from_source_mm']);tr=gp_Trsf();tr.SetValues(*map(float,full[:3].ravel()))
    moved=BRepBuilderAPI_Transform(shape,tr,True).Shape();box=Bnd_Box();BRepBndLib.AddOptimal_s(moved,box,False,False);low=box.Get()[2]
    vv=transform(vertices,T);com=transform([meta['center_mass_object_mm']],T)[0]
    ids=np.flatnonzero(abs(vv[:,2]-low)<=CONTACT_TOL_MM);margin=None;area=0.
    if len(ids)>=3:
        try:
            h=ConvexHull(vv[ids,:2]);margin=float((-(h.equations[:,:2]@com[:2]+h.equations[:,2])).min());area=float(h.volume)
        except Exception:pass
    return {'T_table_from_object':T,'exact_CAD_minimum_z_mm':low,'mesh_minimum_z_mm':float(vv[:,2].min()),'contact_vertex_ids':ids,'contact_count':len(ids),'support_hull_area_mm2':area,'COM_margin_mm':margin,'preliminary_discrete_candidate':bool(margin is not None and margin>band and abs(low)<=eps)}

planes=[]
for face in features:
    if face['type']!='plane':continue
    T=np.eye(4);T[:3,:3]=rotation_to_z(face['normal']);T[2,3]=-(T[:3,:3]@np.asarray(face['centroid']))[2]
    planes.append({'face':face['face'],'planar_area_mm2':face['area_mm2'],**inspect(T)})
transforms,details=propose(vertices,meta['center_mass_object_mm'])
report={'status':'diagnostic_running','source_id':sid,'source_sha256':meta['source_sha256'],'mesh_sha256':file_hash(gt/'mesh.npz'),'key':key,'script_sha256':file_hash(Path(__file__)),'proposal_code_sha256':file_hash(ROOT/'scripts/hull_pose_proposals.py'),'plane_candidates':planes,'proposal_details':details,'contact_tolerance_mm':CONTACT_TOL_MM,'epsilon_contact_mm':eps,'robust_margin_mm':band,'hull_candidates':[],'source_or_topology_modifications':False,'method':'Exact transformed BREP extrema and COM; finite independent hull proposals. No candidate is promoted by this diagnostic.'}
for rank,T in enumerate(transforms):
    report['hull_candidates'].append({'rank':rank,**inspect(T)})
    atomic_json(out,report)
    if rank%10==0:print(canonical_json({'source':sid,'checked':rank+1,'total':len(transforms)}),flush=True)
report['status']='diagnostic_complete';report['preliminary_candidates']=[x['rank'] for x in report['hull_candidates'] if x['preliminary_discrete_candidate']];atomic_json(out,report)
print(canonical_json({k:v for k,v in report.items() if k not in ['plane_candidates','hull_candidates']}))
