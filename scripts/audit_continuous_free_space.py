"""Read every selected Mesh and public observation; record continuous conflicts only."""
from pathlib import Path
import os,sys,argparse,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.validate import read_mesh
from continuous_free_space import conflicts_in_camera

def audit(cid):
    out=ROOT/f'data/cases/{cid}/input';folder=ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}';folder.mkdir(parents=True,exist_ok=True)
    paths=[out/name for name in ['mesh.ply','observations.json','cameras.json','reconstruction.json']]+[ROOT/'tools/continuous_free_space.py',Path(__file__)]
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in paths}
    key=digest(hashes);report_path=folder/'audit.json';artifact=folder/'conflicting_faces.npz'
    if report_path.exists() and artifact.exists():
        prior=load_json(report_path)
        if prior.get('key')==key and prior.get('artifact_sha256')==file_hash(artifact):
            print(canonical_json({'case_id':cid,'reused_read_only_audit':True,'conflicting_faces':prior['conflicting_faces']}),flush=True);return prior
    start=time.time();mesh=read_mesh(out/'mesh.ply');first=np.full(len(mesh.faces),-1,np.int32);pixels=np.full((len(mesh.faces),2),-1,np.int32)
    refs=load_json(out/'observations.json')['frames'];cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']};tol=load_json(out/'reconstruction.json')['filtering']['support_tolerance_mm']
    payloads={}
    for ordinal,frame in enumerate(refs):
        cam=cams[frame['camera_id']];path=(out/frame['path']).resolve();actual_hash=file_hash(path)
        assert actual_hash==frame['file_sha256'];payloads[str(path.relative_to(ROOT)).replace('\\','/')]=actual_hash
        with np.load(path) as z:
            img=np.full(cam['resolution']**2,np.nan,np.float32);img[z['pixel']]=z['range_mm'];img=img.reshape(cam['resolution'],cam['resolution'])
        bad,where=conflicts_in_camera(mesh.vertices,mesh.faces,img,cam,tol)
        fresh=bad&(first<0);first[fresh]=ordinal;pixels[fresh]=where[fresh]
        if ordinal%100==0:print(canonical_json({'case_id':cid,'frame':ordinal,'frames':len(refs),'conflicting_faces':int((first>=0).sum()),'seconds':time.time()-start}),flush=True)
    ids=np.flatnonzero(first>=0);atomic_npz(artifact,face_ids=ids,first_frame=first[ids],pixels=pixels[ids])
    result={'status':'continuous_audit_complete','case_id':cid,'key':key,'inputs_sha256':hashes,'public_observation_files_sha256':payloads,'vertices':len(mesh.vertices),'faces':len(mesh.faces),'frames':len(refs),'conflicting_faces':len(ids),'conflicting_area_mm2':float(mesh.area_faces[ids].sum()),'conflicting_area_fraction':float(mesh.area_faces[ids].sum()/mesh.area),'tolerance_mm':tol,'artifact':'reports/free_space_revision/current_mesh_audit/'+cid+'/conflicting_faces.npz','artifact_sha256':file_hash(artifact),'seconds':time.time()-start,'no_gt_read':True,'no_geometry_modified':True}
    atomic_json(report_path,result);print(canonical_json({k:v for k,v in result.items() if k not in ['inputs_sha256','public_observation_files_sha256']}),flush=True);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case-ids',nargs='+');p.add_argument('--all',action='store_true');args=p.parse_args()
    if args.all:
        ids=[json.loads(s)['case_id'] for s in (ROOT/'manifests/cases.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
        first=['case_b104fc2cd648b353','case_2438b1a3fd780c63'];ids=[x for x in first if x in ids]+sorted(set(ids)-set(first))
    elif args.case_ids:ids=args.case_ids
    else:raise SystemExit('Choose explicit cases or --all')
    for cid in ids:audit(cid)
