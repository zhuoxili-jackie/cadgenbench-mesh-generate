"""Find a first stable pose using unchanged r3 CAD-contact certificates, before scanning."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.contact_support import KIND,CONTACT_TOL_MM,audit_discrete_placement
from scanbench.verified_placements import prepare_verified_placements
from scanbench.placements import candidates
from scanbench.sources import read_step
from hull_pose_proposals import propose
from audit_reference_boundary import boundary,distance
from scipy.spatial import ConvexHull

sid=sys.argv[1];gt=ROOT/f'private/gt/{sid}';state=State();folder=ROOT/f'reports/source_investigations/{sid}/initial_discrete_contacts';folder.mkdir(exist_ok=True)
assert not (ROOT/f'private/scan_index/{sid}/index.json').exists()
assert not (gt/'placements.json').exists(),'Never replace an existing pose set through this initial-pose route.'
meta=load_json(gt/'metadata.json');features=load_json(gt/'features.json')
with np.load(gt/'mesh.npz') as z:vertices=z['vertices'];faces=z['faces']
initial=candidates(vertices,faces,meta['center_mass_object_mm'],features);assert not initial['placements']
atomic_json(folder/'empty_planar_candidates.json',initial)
transforms,proposal_details=propose(vertices,meta['center_mass_object_mm']);shape,_=read_step(ROOT/f'sources/{sid}/input.step');surface=boundary(shape)
rows=[];qualified=[];eps=initial['epsilon_contact_mm']
for rank,T in enumerate(transforms):
    vv=transform(vertices,T);ids=np.flatnonzero(abs(vv[:,2])<=CONTACT_TOL_MM+1e-12);row={'rank':rank,'T_table_from_object':T,'contact_vertex_ids':ids,'status':'not_certified'}
    if len(ids)>=3:
        try:
            hull=ConvexHull(vv[ids,:2]);cm=transform([meta['center_mass_object_mm']],T)[0];margin=float((-(hull.equations[:,:2]@cm[:2]+hull.equations[:,2])).min())
            p={'placement_id':0,'T_table_from_object':T,'support_outward_object':-T[2,:3],'candidate_CAD_face':None,'candidate_origin':'finite hull proposal; initial separated-contact pose','contact_kind':KIND,'contact_vertex_ids':ids,'contact_vertex_count':len(ids),'actual_contact_area_mm2':0.,'support_polygon_area_mm2':float(hull.volume),'support_polygon_table_xy':vv[ids[hull.vertices],:2],'center_mass_table_mm':cm,'stability_margin_mm':margin,'epsilon_contact_mm':eps,'minimum_z_mm':float(vv[:,2].min()),'contact_triangle_ids':[],'candidate_rank_by_contact':rank,'proposal_rank':rank,'selection_reason':'separated exact CAD contacts; contact area stays zero','angles_to_prior_deg':[]}
            certificate=audit_discrete_placement(sid,p);points=transform(vertices[ids],meta['T_source_mm_from_object']);distances=[distance(point,surface)[0] for point in points]
            valid=certificate['status']=='pass' and max(distances)<=CONTACT_TOL_MM and vv[:,2].min()>=-eps
            row.update(status='certified' if valid else 'not_certified',certificate=certificate,boundary_distances_mm=distances,mesh_minimum_z_mm=float(vv[:,2].min()))
            if valid:qualified.append((p,certificate))
        except Exception as exc:row['error']=repr(exc)
    rows.append(row)
diagnostic=folder/'candidate_certificates.json';atomic_json(diagnostic,{'source_id':sid,'source_sha256':meta['source_sha256'],'mesh_sha256':file_hash(gt/'mesh.npz'),'proposal_details':proposal_details,'candidates':rows,'script_sha256':file_hash(Path(__file__)),'proposal_code_sha256':file_hash(ROOT/'scripts/hull_pose_proposals.py'),'contact_code_sha256':file_hash(ROOT/'src/scanbench/contact_support.py'),'method':'Contact vertices are selected at actual table z=0, then checked by unchanged r3 exact-CAD/COM certificate and separate boundary-only distances. Conservative BREP-box padding is not mistaken for contact-point height.'})
assert qualified,'No independently certified contact pose found; no source exclusion is made.'
selected=[];certificates=[]
while qualified and len(selected)<3:
    def score(item):
        p=item[0]
        if not selected:return (0.,0.,p['stability_margin_mm'])
        dots=[np.dot(p['support_outward_object'],s['support_outward_object']) for s in selected]
        return (min(1-abs(d) for d in dots),1-max(dots),p['stability_margin_mm'])
    qualified.sort(key=score,reverse=True);p,certificate=qualified.pop(0)
    if any(np.dot(p['support_outward_object'],s['support_outward_object'])>.9999 for s in selected):continue
    p['placement_id']=len(selected);p['angles_to_prior_deg']=[float(np.rad2deg(np.arccos(np.clip(np.dot(p['support_outward_object'],s['support_outward_object']),-1,1)))) for s in selected]
    selected.append(p);certificates.append(certificate)
integration_path=folder/'integration.json'
places={**initial,'placements':selected,'limited_placements':len(selected)<3,'rigid_assembly_assumption':meta['rigid_assembly_assumption'],'discrete_contact_integration':str(integration_path.relative_to(ROOT)).replace('\\','/')}
atomic_json(gt/'placements.json',places);prepare_verified_placements(sid,state)
snapshot=folder/Path(__file__).name;shutil.copy2(Path(__file__),snapshot)
evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [diagnostic,folder/'empty_planar_candidates.json',snapshot,ROOT/'scripts/hull_pose_proposals.py']}
proof={'status':'pass','source_id':sid,'source_sha256':meta['source_sha256'],'old_pose_count':0,'actual_pose_count':len(selected),'new_discrete_contact_certificates':certificates,'placements_sha256':file_hash(gt/'placements.json'),'evidence_sha256':evidence,'script':str(Path(__file__).relative_to(ROOT)).replace('\\','/'),'script_sha256':file_hash(Path(__file__)),'contact_code_sha256':file_hash(ROOT/'src/scanbench/contact_support.py'),'observations_existed_before_integration':False,'frozen_physical_certificate_unchanged':True}
atomic_json(integration_path,proof)
row=state.db.execute("SELECT input_hash,outputs FROM stages WHERE subject=? AND stage='placements'",(sid,)).fetchone();outputs=[ROOT/p for p in json.loads(row[1])]+[integration_path]+[ROOT/p for p in evidence]
state.finish(sid,'placements',row[0],outputs,{'certified_discrete_contact_integration':True,'actual_pose_count':len(selected),'initial_planar_pose_count':0})
print(canonical_json({'source':sid,'actual_pose_count':len(selected),'qualified_candidates':sum(x['status']=='certified' for x in rows),'status':'pass'}))
