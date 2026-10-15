"""Independent geometry/witness/archive audit of every continuous-veto result.

The witness solver enumerates 2D barycentric half-plane intersections rather than
using the production 3D polygon clipping code. This never writes Mesh geometry.
"""
from pathlib import Path
import os,sys,hashlib,zipfile,io,argparse,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.validate import read_mesh
from scanbench.cases import mesh_stage_key
from independent_cell_minimum import minimum_range

FOLDER=ROOT/'reports/protocol_amendments/r4_continuous_free_space'

def geometry_hash(v,f):
    return {'vertices':hashlib.sha256(np.ascontiguousarray(v,dtype=np.float64).tobytes()).hexdigest(),'faces':hashlib.sha256(np.ascontiguousarray(f,dtype=np.int64).tobytes()).hexdigest()}

def normalized_triangles(v,f):
    tri=v[f];order=np.lexsort((tri[:,:,2],tri[:,:,1],tri[:,:,0]),axis=1)
    return np.take_along_axis(tri,order[:,:,None],axis=1)

def independent_witnesses(v,f,ids,first,pixels,refs,cams,tol,out):
    witnesses=[]
    for ordinal in np.unique(first):
        frame=refs[int(ordinal)];cam=cams[frame['camera_id']];path=(out/frame['path']).resolve();assert file_hash(path)==frame['file_sha256']
        with np.load(path) as z:
            image=np.full(cam['resolution']**2,np.nan,np.float32);image[z['pixel']]=z['range_mm'];image=image.reshape(cam['resolution'],cam['resolution'])
        K=np.asarray(cam['K']);T=np.asarray(cam['T_object_from_camera'])
        for index in np.flatnonzero(first==ordinal):
            fid=int(ids[index]);x,y=map(int,pixels[index]);assert 0<x<cam['resolution']-1 and 0<y<cam['resolution']-1
            patch=image[y-1:y+2,x-1:x+2];assert np.isfinite(patch).all() and (patch.max()-patch.min())<2*tol
            tri=(v[f[fid]]-T[:3,3])@T[:3,:3]
            minimum,weights=minimum_range(tri,(x-.5-K[0,2])/K[0,0],(x+.5-K[0,2])/K[0,0],(y-.5-K[1,2])/K[1,1],(y+.5-K[1,2])/K[1,1])
            limit=max(float(patch.min())-tol,float(patch.min()-tol));assert minimum<limit,(out.parent.name,fid,minimum,limit)
            witnesses.append({'face_id':fid,'frame':int(ordinal),'pixel':[x,y],'minimum_mm':minimum,'threshold_mm':limit,'margin_mm':limit-minimum})
    return witnesses

def audit_scope(cid):
    import trimesh
    out=ROOT/f'data/cases/{cid}/input';scope_path=ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}/audit.json';scope=load_json(scope_path)
    assert scope['status']=='continuous_audit_complete' and scope['inputs_sha256']['tools/continuous_free_space.py']==file_hash(ROOT/'src/scanbench/continuous_free_space.py')
    artifact=ROOT/scope['artifact'];assert file_hash(artifact)==scope['artifact_sha256']
    signature=digest([file_hash(scope_path),file_hash(artifact),file_hash(Path(__file__)),file_hash(ROOT/'scripts/independent_cell_minimum.py')])
    report_path=ROOT/f'reports/continuous_independent_scope/{cid}.json'
    if report_path.exists() and load_json(report_path).get('signature')==signature and load_json(report_path).get('status')=='pass':return load_json(report_path)
    name=f'data/cases/{cid}/input/mesh.ply';data=(out/'mesh.ply').read_bytes();expected=scope['inputs_sha256'][name]
    if hashlib.sha256(data).hexdigest()!=expected:
        with zipfile.ZipFile(FOLDER/f'original_meshes/{cid}.zip') as z:data=z.read(name)
    assert hashlib.sha256(data).hexdigest()==expected
    mesh=trimesh.load(io.BytesIO(data),file_type='ply',process=False,force='mesh')
    for name in ['cameras.json','observations.json']:assert file_hash(out/name)==scope['inputs_sha256'][f'data/cases/{cid}/input/{name}']
    refs=load_json(out/'observations.json')['frames'];cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']}
    with np.load(artifact) as z:ids=z['face_ids'];first=z['first_frame'];pixels=z['pixels']
    assert len(ids)==scope['conflicting_faces']
    witnesses=independent_witnesses(np.asarray(mesh.vertices),np.asarray(mesh.faces),ids,first,pixels,refs,cams,scope['tolerance_mm'],out)
    result={'status':'pass','case_id':cid,'signature':signature,'scope_sha256':file_hash(scope_path),'original_mesh_sha256':expected,'independently_verified_conflicting_faces':len(witnesses),'witnesses':witnesses,'no_formal_mesh_changed':True,'no_gt_used':True}
    atomic_json(report_path,result);return result

def archived_original(cid):
    import trimesh
    migration=load_json(FOLDER/f'cases/{cid}.json');archive=ROOT/migration['original_archive'];meta_path=archive.with_suffix('.json');meta=load_json(meta_path)
    assert migration['status']=='pass' and file_hash(archive)==migration['original_archive_sha256']==meta['archive_sha256']
    assert file_hash(meta_path)==migration['archive_inventory_sha256']
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist())==set(meta['files'])
        for name,entry in meta['files'].items():
            data=z.read(name);assert hashlib.sha256(data).hexdigest()==entry['sha256'] and len(data)==entry['bytes']
            if name==f'data/cases/{cid}/input/mesh.ply':mesh=trimesh.load(io.BytesIO(data),file_type='ply',process=False,force='mesh')
    scope_path=ROOT/migration['scope_audit'];scope=load_json(scope_path)
    assert file_hash(scope_path)==migration['scope_audit_sha256']
    assert migration['old_mesh_sha256']==scope['inputs_sha256'][f'data/cases/{cid}/input/mesh.ply']
    assert file_hash(ROOT/scope['artifact'])==scope['artifact_sha256']
    return np.asarray(mesh.vertices),np.asarray(mesh.faces),migration,meta

def audit_case(cid):
    out=ROOT/f'data/cases/{cid}/input';cert_path=out/'continuous_veto.json';cert=load_json(cert_path);cache=out/'.reconstruction_cache'
    current=read_mesh(out/'mesh.ply');assert cert['output_geometry']==geometry_hash(current.vertices,current.faces)
    rec=load_json(ROOT/f'private/annotations/{cid}/case.json');assert rec['mesh_stage_hash']==mesh_stage_key(out,config()['reconstruction'])
    assert State().valid(cid,'mesh',rec['mesh_stage_hash'])
    cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']};refs=load_json(out/'observations.json')['frames'];identity=cert['identity']
    assert cert['key']==digest(identity) and identity['cameras']==cams
    assert identity['observations']==[[f['camera_id'],f['file_sha256']] for f in refs]
    assert identity['module_sha256']==file_hash(ROOT/'src/scanbench/continuous_free_space.py')
    for package in ['numpy','numba','scipy']:assert identity[package]==importlib.metadata.version(package)
    assert cert['tolerance_mm']==identity['tolerance_mm']==load_json(out/'reconstruction.json')['filtering']['support_tolerance_mm']
    marker=load_json(cache/'continuous.json');assert marker['key']==cert['key'] and marker['identity']==identity
    assert file_hash(cache/'continuous.npz')==cert['artifact_sha256']==marker['artifact_sha256']
    bound=[out/'mesh.ply',cert_path,cache/'continuous.npz',cache/'continuous.json',out/'observations.json',out/'cameras.json',Path(__file__),ROOT/'scripts/independent_cell_minimum.py']
    migration_path=FOLDER/f'cases/{cid}.json'
    if migration_path.exists():
        migration=load_json(migration_path);bound.extend([migration_path,ROOT/migration['original_archive'],(ROOT/migration['original_archive']).with_suffix('.json'),ROOT/migration['scope_audit']])
    else:bound.extend(cache/p for p in ['supported.npz','fusion.npz'])
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in bound};signature=digest(hashes)
    report_path=ROOT/f'reports/continuous_independent/{cid}.json'
    if report_path.exists() and load_json(report_path).get('signature')==signature and load_json(report_path).get('status')=='pass':return load_json(report_path)
    started=time.time()
    if migration_path.exists():
        v,f,migration,meta=archived_original(cid)
        assert migration['new_mesh_sha256']==file_hash(out/'mesh.ply') and migration['continuous_certificate_sha256']==file_hash(cert_path)
        scope=load_json(ROOT/migration['scope_audit']);assert scope['artifact_sha256']==cert['artifact_sha256']
    else:
        # Only reconstruct the pre-veto indexing from public derived checkpoints.
        # All decisions on removed faces below use the independent convex solver.
        import open3d as o3d
        from scanbench.reconstruct import orient_from_observations
        with np.load(cache/'supported.npz') as z:before=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(z['vertices']),o3d.utility.Vector3iVector(z['faces']))
        with np.load(cache/'fusion.npz') as z:orient_from_observations(before,z['P'],z['N'])
        v=np.asarray(before.vertices);f=np.asarray(before.triangles)
    assert geometry_hash(v,f)==identity['geometry']
    with np.load(cache/'continuous.npz') as z:ids=z['face_ids'];first=z['first_frame'];pixels=z['pixels']
    assert len(ids)==cert['removed_faces'] and len(ids)==len(first)==len(pixels) and np.all(np.diff(ids)>0)
    assert np.all((ids>=0)&(ids<len(f))) and np.all((first>=0)&(first<len(refs)))
    assert cert.get('post_veto_connectivity_cleanup',{}).get('overlap_conflict_faces_removed',0)==0,'Unexpected second-pass deletion requires explicit investigation'
    keep=np.ones(len(f),bool);keep[ids]=False;kept=f[keep]
    assert len(kept)==len(current.faces)
    for start in range(0,len(kept),100000):
        assert np.array_equal(normalized_triangles(v,kept[start:start+100000]),normalized_triangles(current.vertices,current.faces[start:start+100000])),f'{cid}: output added or changed a triangle'
    witnesses=independent_witnesses(v,f,ids,first,pixels,refs,cams,cert['tolerance_mm'],out)
    result={'status':'pass','case_id':cid,'signature':signature,'bound_files_sha256':hashes,'original_faces':len(f),'current_faces':len(current.faces),'removed_faces':len(ids),'all_surviving_triangle_coordinates_exact':True,'no_added_or_moved_geometry':True,'independent_removed_face_witnesses':witnesses,'independent_solver':'2D barycentric half-plane vertices, segments and unconstrained convex quadratic minimum; production clipping not called','current_certificate_geometry_and_public_inputs_verified':True,'no_gt_used':True,'seconds':time.time()-started}
    atomic_json(report_path,result);return result

def audit_baseline_inventory():
    baseline=load_json(FOLDER/'inventory_before.json')['files'];archived={};preserved=0;superseded=0
    for path in (FOLDER/'original_meshes').glob('*.json'):
        meta=load_json(path);archived.update({name:(path,entry) for name,entry in meta['files'].items()})
    for name,entry in baseline.items():
        path=ROOT/name
        if file_hash(path)==entry['sha256'] and path.stat().st_mtime_ns==entry['mtime_ns']:preserved+=1;continue
        assert name in archived and Path(name).name in ['mesh.ply','mesh.stl','reconstruction.json'],f'Unexpected upstream change: {name}'
        meta_path,prior=archived[name];assert prior==entry
        with zipfile.ZipFile(meta_path.with_suffix('.zip')) as z:assert hashlib.sha256(z.read(name)).hexdigest()==entry['sha256']
        cid=Path(name).parts[2];assert load_json(FOLDER/f'cases/{cid}.json')['status']=='pass';superseded+=1
    result={'status':'pass','baseline_files':len(baseline),'hash_and_mtime_preserved':preserved,'explicitly_archived_downstream_mesh_files':superseded,'upstream_source_GT_scan_points_and_caches_unchanged':True,'baseline_sha256':file_hash(FOLDER/'inventory_before.json'),'script_sha256':file_hash(Path(__file__))}
    atomic_json(FOLDER/'full_inventory_audit.json',result);return result

def historical_file_verified(name,entry):
    path=ROOT/name
    if file_hash(path)==entry['sha256'] and path.stat().st_mtime_ns==entry['mtime_ns']:return True
    if name.startswith('private/annotations/'):
        old=FOLDER/'annotations_before'/Path(name).relative_to('private/annotations')
        return old.exists() and file_hash(old)==entry['sha256'] and old.stat().st_mtime_ns==entry['mtime_ns'] and (FOLDER/'cases'/f'{Path(name).parts[2]}.json').exists()
    if name.startswith('data/cases/'):cid=Path(name).parts[2]
    elif name.startswith('reports/private_previews/'):cid=Path(name).stem
    else:return False
    meta_path=FOLDER/f'original_meshes/{cid}.json'
    if not meta_path.exists() or not (FOLDER/f'cases/{cid}.json').exists():return False
    meta=load_json(meta_path);old=meta['files'].get(name,{})
    if old.get('sha256')!=entry['sha256'] or old.get('mtime_ns')!=entry['mtime_ns']:return False
    with zipfile.ZipFile(meta_path.with_suffix('.zip')) as z:return hashlib.sha256(z.read(name)).hexdigest()==entry['sha256']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case-ids',nargs='+');p.add_argument('--all',action='store_true');p.add_argument('--inventory',action='store_true');p.add_argument('--scope-available',action='store_true');args=p.parse_args()
    if args.scope_available:
        for path in sorted((ROOT/'reports/free_space_revision/current_mesh_audit').glob('*/audit.json')):
            r=audit_scope(path.parent.name);print(canonical_json({'scope_case':r['case_id'],'status':r['status'],'independent_witnesses':r['independently_verified_conflicting_faces']}),flush=True)
    ids=args.case_ids or ([json.loads(s)['case_id'] for s in (ROOT/'manifests/cases.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()] if args.all else [])
    for cid in ids:
        r=audit_case(cid);print(canonical_json({'case_id':cid,'status':r['status'],'removed_faces_independently_justified':r['removed_faces']}),flush=True)
    if args.inventory:print(canonical_json(audit_baseline_inventory()))
