"""Rebuild the failing case in a fresh output, reusing only verified public caches."""
from pathlib import Path
import os,sys,shutil,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.reconstruct import reconstruct,continuous_identity,resolve_observations
from scanbench.validate import read_mesh,mesh_statistics,sample_area,observed_evaluation,distance_scene,distances,sorted_facets

cid='case_b104fc2cd648b353';source=ROOT/f'data/cases/{cid}/input';out=ROOT/'tests/artifacts/continuous_revision_243_easy';assert not out.exists();out.mkdir(parents=True)
proof=load_json(ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}/audit.json')
for name,h in proof['inputs_sha256'].items():assert file_hash(ROOT/name)==h,name
assert file_hash(ROOT/'tools/continuous_free_space.py')==file_hash(ROOT/'src/scanbench/continuous_free_space.py')
before_mesh=file_hash(source/'mesh.ply');mesh=read_mesh(source/'mesh.ply');frames=resolve_observations(source/'observations.json');cams={c['id']:c for c in load_json(source/'cameras.json')['cameras']};tol=proof['tolerance_mm']
key,identity=continuous_identity(mesh.vertices,mesh.faces,frames,cams,tol);cache=out/'.reconstruction_cache';cache.mkdir()
upstream_cache={}
for name in ['fusion.npz','fusion.json','bpa.npz','bpa.json','supported.npz','supported.json']:
    original=source/'.reconstruction_cache'/name;shutil.copy2(original,cache/name);upstream_cache[name]=[file_hash(cache/name),(cache/name).stat().st_mtime_ns]
artifact=ROOT/proof['artifact'];assert file_hash(artifact)==proof['artifact_sha256'];shutil.copy2(artifact,cache/'continuous.npz')
metrics={'rule':'minimum Euclidean range over triangle clipped to every intersected stable 3x3 foreground nearest-pixel cell; no GT; unchanged tolerance','checked_faces':proof['faces'],'checked_frames':proof['frames'],'removed_faces':proof['conflicting_faces'],'removed_area_mm2':proof['conflicting_area_mm2'],'removed_area_fraction':proof['conflicting_area_fraction'],'tolerance_mm':tol,'seconds':proof['seconds']}
atomic_json(cache/'continuous.json',{'key':key,'identity':identity,'artifact_sha256':file_hash(cache/'continuous.npz'),'metrics':metrics,'imported_read_only_audit_sha256':file_hash(ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}/audit.json')})
started=time.time();result=reconstruct(source/'observations.json',source/'cameras.json',source/'reconstruction_config.json',out)
assert result['continuous_free_space']['key']==key
for name,item in upstream_cache.items():assert [file_hash(cache/name),(cache/name).stat().st_mtime_ns]==item,name
assert file_hash(source/'mesh.ply')==before_mesh
actual=read_mesh(out/'mesh.ply');stats=mesh_statistics(actual);stl=read_mesh(out/'mesh.stl')
np.testing.assert_allclose(sorted_facets(actual),sorted_facets(stl),atol=1e-5,rtol=1e-7)
assert file_hash(out/'points_for_meshing.ply')==file_hash(source/'points_for_meshing.ply')
with np.load(out/'point_provenance.npz') as a,np.load(source/'point_provenance.npz') as b:
    for name in ['frame_index','pixel']:np.testing.assert_array_equal(a[name],b[name])
samples,_=sample_area(actual,30000,2901);observed,supported,denominator=observed_evaluation(source/'observations.json',source/'cameras.json',samples,tol,30000)
retention=float((distances(distance_scene(actual),observed)<=tol).mean())
assert float(supported.mean())>=.98 and retention>=.95 and denominator['sampled_mesh_free_space_conflicts']==0
assert stats['nonmanifold_edges']==0 and stats['nonmanifold_vertices']==0
proof_result={'status':'pass','case_id':cid,'fresh_output':str(out.relative_to(ROOT)).replace('\\','/'),'old_mesh_sha256':before_mesh,'new_mesh_sha256':file_hash(out/'mesh.ply'),'new_stl_sha256':file_hash(out/'mesh.stl'),'mesh_supported_fraction':float(supported.mean()),'observation_retention':retention,'sampled_free_space_conflicts':denominator['sampled_mesh_free_space_conflicts'],'independent_samples':30000,'nonmanifold_edges':stats['nonmanifold_edges'],'nonmanifold_vertices':stats['nonmanifold_vertices'],'vertices':len(actual.vertices),'faces':len(actual.faces),'continuous_veto':result['continuous_free_space'],'all_six_upstream_public_cache_hashes_and_mtimes_preserved':True,'formal_source_mesh_unchanged':True,'working_points_and_provenance_exact':True,'reconstruction_code_sha256':file_hash(ROOT/'src/scanbench/reconstruct.py'),'module_sha256':file_hash(ROOT/'src/scanbench/continuous_free_space.py'),'script_sha256':file_hash(Path(__file__)),'seconds':time.time()-started}
atomic_json(ROOT/'reports/free_space_revision/failing_case_trial.json',proof_result);print(canonical_json(proof_result))
