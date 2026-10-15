"""Additional, recorded source-reference qualification; never repairs source geometry.

The frozen production path is unchanged. A qualified reference can be promoted
with its actual parameter/sidecar provenance and hash-bound investigation files.
"""
from pathlib import Path
import os, sys, argparse, time, traceback, urllib.request, shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
if '--promote' not in sys.argv:sys.path.insert(0,str(ROOT/'tools/ocp79'))
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import read_step,shape_metadata,brep_distance_check,analytic_features
from cadgenbench.common.mesh import Mesh,tessellate_shape,validate_mesh
import trimesh
import OCP,importlib.metadata
from audit_reference_boundary import boundary

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('--trial',nargs=2,type=float);ap.add_argument('--official',action='store_true');ap.add_argument('--promote',action='store_true');args=ap.parse_args()
    sid=args.source;assert sid in IDS and args.trial and not args.official
    assert ('tools' in Path(OCP.__file__).parts) != args.promote, 'Trials use isolated 7.9; promotion uses the unchanged production runtime.'
    source=ROOT/f'sources/{sid}/input.step';sha=file_hash(source);tree=load_json(ROOT/'sources/upstream_tree.json')
    assert sha==next(x['lfs']['oid'] for x in tree if x['path']==f'{sid}/input.step')
    folder=ROOT/f'reports/source_investigations/{sid}';folder.mkdir(parents=True,exist_ok=True)
    shape,units=read_step(source);meta=shape_metadata(shape)
    assert units['source_length_units'] and meta['brep_valid'],'A valid, explicitly unit-tagged STEP is required by both reference tiers.'
    center=np.mean(meta['bounds_source_mm'],axis=0)
    prior=ROOT/f'private/gt/{sid}/native_attempts.json';attempts=load_json(prior)
    assert len(attempts)>=3 and all(t['status']=='failed' for t in attempts),'Additional qualification follows all frozen native alternatives.'
    method=f'ocp79_native_{args.trial[0]:g}_{args.trial[1]:g}'
    proof=folder/f'{method}.json';mesh_path=folder/f'{method}.npz';started=time.time()
    if proof.exists():
        result=load_json(proof)
        assert result['source_sha256']==sha and result['binding_version']=='7.9.3.1.1' and result['script_sha256']==file_hash(Path(__file__))
        if 'mesh_path' in result:assert file_hash(ROOT/result['mesh_path'])==result['mesh_sha256']
        print('Reusing hash-verified reference investigation',method,flush=True)
    else:
        assert not args.promote, 'A prior successful isolated trial is required for promotion.'
        result={'binding_version':importlib.metadata.version('cadquery-ocp'),'OCP_version':OCP.__version__,'production_environment_unchanged':True,'source_id':sid,'source_sha256':sha,'revision':REV,'method':method,'source_metadata':meta,'units':units,'source_or_topology_modifications':False,'status':'investigating'}
        try:
            if args.official:
                entry=next(x for x in tree if x['path']==f'{sid}/input.mesh.npz');mesh_path=ROOT/f'sources/{sid}/input.mesh.npz';expected=entry['lfs']['oid']
                url=f'https://huggingface.co/datasets/HuggingAI4Engineering/cadgenbench-data/resolve/{REV}/{sid}/input.mesh.npz'
                if not mesh_path.exists() or file_hash(mesh_path)!=expected:
                    with urllib.request.urlopen(url,timeout=120) as response:raw=response.read()
                    assert hashlib.sha256(raw).hexdigest()==expected;atomic_bytes(mesh_path,raw)
                with np.load(mesh_path) as z:mesh=Mesh(z['vertices'],z['triangles'],float(z['linear_deflection_mm']))
                result.update(official_url=url,official_sha256=expected,original_linear_deflection_mm=mesh.linear_deflection_mm,subdivision_performed=False,precision_tier='eligible_official_mesh_approx')
            else:
                chord,angle=args.trial
                if mesh_path.exists():
                    with np.load(mesh_path) as z:mesh=Mesh(z['vertices'],z['triangles'],chord)
                else:
                    from OCP.BRepTools import BRepTools
                    BRepTools.Clean_s(shape);mesh=tessellate_shape(shape,chord,angular_deflection_rad=angle,parallel=False)
                    atomic_npz(mesh_path,vertices=mesh.vertices,triangles=mesh.triangles)
                result.update(chord_mm=chord,angle_rad=angle,precision_tier='eligible_native')
            result.update(mesh_path=str(mesh_path.relative_to(ROOT)).replace('\\','/'),mesh_sha256=file_hash(mesh_path),vertices=len(mesh.vertices),faces=len(mesh.triangles))
            validate_mesh(mesh)
            tm=trimesh.Trimesh(mesh.vertices,mesh.triangles,process=False)
            assert np.isfinite(mesh.vertices).all() and not np.any(tm.area_faces<=1e-16)
            components=tm.split(only_watertight=False)
            assert all(c.is_watertight and c.is_winding_consistent and c.volume>0 for c in components),'Every reference component must be closed and outward.'
            accuracy=brep_distance_check(boundary(shape),mesh.vertices-center,mesh.triangles,center)
            accuracy['method']='128 fixed area-distributed mesh samples, exact OCCT distance to CAD boundary faces; no solid-interior shortcut'
            limit=max(.021,mesh.linear_deflection_mm*1.1)
            bounds_error=float(np.max(np.abs(tm.bounds-np.asarray(meta['bounds_source_mm']))))
            volume_error=abs(float(tm.volume)-meta['volume_mm3']);volume_limit=2*mesh.linear_deflection_mm*float(tm.area)
            result.update(accuracy_check=accuracy,accuracy_limit_mm=limit,bounds_max_difference_mm=bounds_error,bounds_limit_mm=max(1e-5,2*mesh.linear_deflection_mm),volume_absolute_difference_mm3=volume_error,volume_error_limit_mm3=volume_limit,volume_check_basis='2 * declared chord * mesh surface area; dimensional comparison, not an exact mathematical bound',components=[{'faces':len(c.faces),'area_mm2':float(c.area),'signed_volume_mm3':float(c.volume)} for c in components],watertight=tm.is_watertight,winding_consistent=tm.is_winding_consistent,degenerate_faces=0)
            assert accuracy['max_sampled_mm']<=limit,'Surface-to-BREP distance exceeds declared reference accuracy.'
            assert bounds_error<=result['bounds_limit_mm'],'Reference bounds disagree with the STEP.'
            assert volume_error<=volume_limit,'Reference volume disagrees with the STEP.'
            result['status']='pass'
        except Exception as exc:result.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
        result.update(seconds=time.time()-started,script_sha256=file_hash(Path(__file__)),native_attempts_sha256=file_hash(prior));atomic_json(proof,result)
        snapshot=folder/f'{method}_qualification.py'
        if not snapshot.exists():shutil.copy2(Path(__file__),snapshot)
    print(canonical_json(result),flush=True)
    if not args.promote:return
    assert result['status']=='pass','Failed investigation cannot be promoted.'
    assert not (ROOT/f'private/scan_index/{sid}/index.json').exists(), 'No reference replacement after observations.'
    mesh_path=ROOT/result['mesh_path']
    with np.load(mesh_path) as z:vertices=z['vertices']-center;faces=z['triangles']
    tm=trimesh.Trimesh(vertices,faces,process=False);gt=ROOT/f'private/gt/{sid}'
    state=State();key=stage_hash(sha,config()['gt'],['sources.py'],['cadquery-ocp','numpy','trimesh'])
    snapshot=folder/f'{method}_qualification.py'
    if not snapshot.exists():shutil.copy2(Path(__file__),snapshot)
    assert file_hash(snapshot)==result['script_sha256']
    evidence_files=[proof,mesh_path,prior,snapshot,source]+[p for p in folder.iterdir() if p.suffix in ['.json','.npz','.py']]
    evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in evidence_files}
    T=np.eye(4);T[:3,3]=-center
    meta.update(units)
    meta.update(source_id=sid,source_sha256=sha,revision=REV,status=result['precision_tier'],T_object_from_source_mm=T,T_source_mm_from_object=np.linalg.inv(T),bounds_object_mm=tm.bounds,diagonal_mm=float(np.linalg.norm(tm.extents)),center_mass_object_mm=np.asarray(meta['center_mass_source_mm'])-center,vertices=len(vertices),faces=len(faces),area_mm2=float(tm.area),mesh_volume_mm3=float(tm.volume),watertight=tm.is_watertight,winding_consistent=tm.is_winding_consistent,components=result['components'],chord_mm=result.get('chord_mm',result.get('original_linear_deflection_mm')),angle_rad=result.get('angle_rad'),accuracy_check=result['accuracy_check'],stage_hash=key,unit_scale_evidence='STEPControl FileUnits and explicit internal mm conversion, never inferred from bounding box',qualification_method=method,evidence_summary=str(proof.relative_to(ROOT)).replace('\\','/'),evidence_sha256=evidence,attempts=attempts)
    if args.official:meta.update(original_linear_deflection_mm=result['original_linear_deflection_mm'],official_mesh_sha256=result['official_sha256'],approximation_limitation='Scanning targets the unchanged official polygonal approximation; subdivision is not used to claim native curvature accuracy.')
    atomic_npz(gt/'mesh.npz',vertices=vertices,faces=faces);atomic_bytes(gt/'mesh.ply',tm.export(file_type='ply'));atomic_json(gt/'features.json',analytic_features(shape,center));atomic_json(gt/'metadata.json',meta)
    state.record('sources',sid,meta);state.finish(sid,'gt',key,[gt/'mesh.npz',gt/'mesh.ply',gt/'features.json',gt/'metadata.json',*[ROOT/p for p in evidence]],{'qualification_method':method,'reference_tier':meta['status'],'investigation_seconds':result['seconds'],'unchanged_frozen_scan_reconstruction_and_gates':True})
    print(canonical_json({'promoted':sid,'tier':meta['status'],'evidence':meta['evidence_summary']}))

if __name__=='__main__':main()
