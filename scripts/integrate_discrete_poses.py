"""Integrate exact-CAD-certified separated contacts before any source observations."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.contact_support import KIND,CONTACT_TOL_MM,audit_discrete_placement
from scanbench.verified_placements import prepare_verified_placements
from scipy.spatial import ConvexHull
sid=sys.argv[1];gt=ROOT/f'private/gt/{sid}';state=State()
assert not (ROOT/f'private/scan_index/{sid}/index.json').exists(),'Pose changes after acquisition require an explicit observation invalidation plan.'
report=load_json(gt/'limited_pose_investigation.json');places=load_json(gt/'placements.json');meta=load_json(gt/'metadata.json')
assert report['status']=='additional_certified_pose_requires_integration' and report['placements_sha256']==file_hash(gt/'placements.json')
assert report['source_sha256']==meta['source_sha256'] and report['mesh_sha256']==file_hash(gt/'mesh.npz')
assert report['script_sha256']==file_hash(ROOT/'scripts/investigate_limited_poses.py') and report['proposal_code_sha256']==file_hash(ROOT/'scripts/hull_pose_proposals.py')
folder=ROOT/f'reports/source_investigations/{sid}/discrete_contacts';folder.mkdir(parents=True,exist_ok=True)
for name in ['placements.json','limited_pose_investigation.json','candidate_pose_proposals.json','placement_audit.json']:
    if not (folder/name).exists():shutil.copy2(gt/name,folder/name)
with np.load(gt/'mesh.npz') as raw:vertices=raw['vertices']
selected=places['placements'];proposals=[r for r in report['candidates'] if r['certified_additional_candidate']];certificates=[]
while proposals and len(selected)<3:
    def score(p):
        dots=[np.dot(p['support_outward_object'],s['support_outward_object']) for s in selected]
        return (min(1-abs(d) for d in dots),1-max(dots),p['COM_margin_mm'])
    proposals.sort(key=score,reverse=True);candidate=proposals.pop(0);normal=np.asarray(candidate['support_outward_object'])
    if any(np.dot(normal,p['support_outward_object'])>.9999 for p in selected):continue
    T=np.asarray(candidate['T_table_from_object_mesh_candidate']);vv=transform(vertices,T);ids=np.flatnonzero(abs(vv[:,2])<=CONTACT_TOL_MM+1e-12);hull=ConvexHull(vv[ids,:2]);cm=transform([meta['center_mass_object_mm']],T)[0];margin=float((-(hull.equations[:,:2]@cm[:2]+hull.equations[:,2])).min())
    p={'placement_id':len(selected),'T_table_from_object':T,'support_outward_object':normal,'candidate_CAD_face':None,'candidate_origin':'finite hull proposal independently certified with exact CAD contacts','contact_kind':KIND,'contact_vertex_ids':ids,'contact_vertex_count':len(ids),'actual_contact_area_mm2':0.,'support_polygon_area_mm2':float(hull.volume),'support_polygon_table_xy':vv[ids[hull.vertices],:2],'center_mass_table_mm':cm,'stability_margin_mm':margin,'epsilon_contact_mm':places['epsilon_contact_mm'],'minimum_z_mm':float(vv[:,2].min()),'contact_triangle_ids':[],'candidate_rank_by_contact':len(selected),'proposal_rank':candidate['rank'],'selection_reason':'distinct separated CAD point/line contacts with strict positive COM support; no contact area is invented','angles_to_prior_deg':[float(np.rad2deg(np.arccos(np.clip(np.dot(normal,s['support_outward_object']),-1,1)))) for s in selected]}
    proof=audit_discrete_placement(sid,p);assert proof['status']=='pass',proof
    selected.append(p);certificates.append(proof)
assert certificates,'No additional actual CAD contacts could be integrated.'
places.update(placements=selected,limited_placements=len(selected)<3,discrete_contact_integration=str((folder/'integration.json').relative_to(ROOT)).replace('\\','/'))
atomic_json(gt/'placements.json',places);prepare_verified_placements(sid,state)
evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in folder.iterdir() if p.name!='integration.json'}
proof={'status':'pass','source_id':sid,'source_sha256':meta['source_sha256'],'old_pose_count':report['existing_certified_pose_count'],'actual_pose_count':len(selected),'new_discrete_contact_certificates':certificates,'placements_sha256':file_hash(gt/'placements.json'),'evidence_sha256':evidence,'script_sha256':file_hash(Path(__file__)),'contact_code_sha256':file_hash(ROOT/'src/scanbench/contact_support.py'),'observations_existed_before_integration':False}
atomic_json(folder/'integration.json',proof)
row=state.db.execute("SELECT input_hash,outputs,metrics FROM stages WHERE subject=? AND stage='placements'",(sid,)).fetchone();outputs=[ROOT/p for p in json.loads(row[1])]+[folder/'integration.json']+[ROOT/p for p in evidence]
state.finish(sid,'placements',row[0],outputs,{'certified_discrete_contact_integration':True,'actual_pose_count':len(selected)})
print(canonical_json({'source':sid,'actual_pose_count':len(selected),'new_contact_count':len(certificates),'status':'pass'}))
