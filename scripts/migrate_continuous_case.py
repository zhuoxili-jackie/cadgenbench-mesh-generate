"""Apply the verified continuous veto to one existing case; preserve all upstream data."""
from pathlib import Path
import os,sys,argparse,shutil,zipfile,io,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.reconstruct import continuous_identity,resolve_observations
from scanbench.cases import generate_case,mesh_stage_key
from scanbench.validate import validate_case
from scanbench.render_cached import preview
from scanbench.supplemental import audit_case
import trimesh

p=argparse.ArgumentParser();p.add_argument('case_id');args=p.parse_args();cid=args.case_id
folder=ROOT/'reports/protocol_amendments/r4_continuous_free_space';baseline=load_json(folder/'inventory_before.json')['files'];state=State()
controls=load_json(ROOT/'reports/free_space_revision/controls_candidate.json');trial=load_json(ROOT/'reports/free_space_revision/failing_case_trial.json')
assert controls['status']=='pass' and controls['module_sha256']==file_hash(ROOT/'src/scanbench/continuous_free_space.py')==file_hash(ROOT/'tools/continuous_free_space.py')
assert trial['status']=='pass' and trial['reconstruction_code_sha256']==file_hash(ROOT/'src/scanbench/reconstruct.py')
out=ROOT/f'data/cases/{cid}/input';rec=load_json(folder/f'annotations_before/{cid}/case.json')
proof_path=folder/f'cases/{cid}.json'
if proof_path.exists():
    done=load_json(proof_path)
    assert done['status']=='pass' and file_hash(out/'mesh.ply')==done['new_mesh_sha256'] and state.valid(cid,'mesh',mesh_stage_key(out,config()['reconstruction']))
    assert validate_case(cid,state)['status']=='pass';print(canonical_json({'case_id':cid,'already_migrated':True}));raise SystemExit(0)
scope_path=ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}/audit.json';scope=load_json(scope_path)
assert scope['status']=='continuous_audit_complete'
for name,h in scope['inputs_sha256'].items():
    if not name.startswith('data/cases/'):assert file_hash(ROOT/name)==h,name
artifact=ROOT/scope['artifact'];assert file_hash(artifact)==scope['artifact_sha256']
archive=folder/f'original_meshes/{cid}.zip';archive_meta=archive.with_suffix('.json');archive.parent.mkdir(parents=True,exist_ok=True)
if not archive.exists():
    names=[str((out/name).relative_to(ROOT)).replace('\\','/') for name in ['mesh.ply','mesh.stl','reconstruction.json']]
    names.extend(str(p.relative_to(ROOT)).replace('\\','/') for p in [ROOT/f'reports/private_previews/{cid}.png',ROOT/f'reports/private_previews/{cid}.json'] if p.exists())
    entries={}
    for name in names:
        path=ROOT/name;h=file_hash(path)
        if name in baseline:assert h==baseline[name]['sha256'] and path.stat().st_mtime_ns==baseline[name]['mtime_ns'],name
        entries[name]={'sha256':h,'mtime_ns':path.stat().st_mtime_ns,'bytes':path.stat().st_size}
    assert entries[f'data/cases/{cid}/input/mesh.ply']['sha256']==scope['inputs_sha256'][f'data/cases/{cid}/input/mesh.ply']
    temp=archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for name in names:z.write(ROOT/name,name)
    os.replace(temp,archive)
    atomic_json(archive_meta,{'case_id':cid,'files':entries,'archive_sha256':file_hash(archive)})
meta=load_json(archive_meta);assert file_hash(archive)==meta['archive_sha256']
with zipfile.ZipFile(archive) as z:
    name=f'data/cases/{cid}/input/mesh.ply';data=z.read(name);assert __import__('hashlib').sha256(data).hexdigest()==meta['files'][name]['sha256']
    original=trimesh.load(io.BytesIO(data),file_type='ply',force='mesh',process=False)
unchanged=[]
for name in ['README.json','cameras.json','observations.json','reconstruction_config.json','points_for_meshing.ply','point_provenance.npz']:
    unchanged.append(out/name)
unchanged.extend(out/'.reconstruction_cache'/name for name in ['fusion.npz','fusion.json','bpa.npz','bpa.json','supported.npz','supported.json'])
refs=load_json(out/'observations.json')['frames'];unchanged.extend((out/fr['path']).resolve() for fr in refs)
for path in unchanged:
    name=str(path.relative_to(ROOT)).replace('\\','/');expected=baseline[name]
    assert file_hash(path)==expected['sha256'] and path.stat().st_mtime_ns==expected['mtime_ns'],name
cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']};frames=resolve_observations(out/'observations.json')
key,identity=continuous_identity(original.vertices,original.faces,frames,cams,scope['tolerance_mm'])
cache=out/'.reconstruction_cache';target=cache/'continuous.npz'
if not target.exists() or file_hash(target)!=scope['artifact_sha256']:shutil.copy2(artifact,target)
metrics={'rule':'minimum Euclidean range over triangle clipped to every intersected stable 3x3 foreground nearest-pixel cell; no GT; unchanged tolerance','checked_faces':scope['faces'],'checked_frames':scope['frames'],'removed_faces':scope['conflicting_faces'],'removed_area_mm2':scope['conflicting_area_mm2'],'removed_area_fraction':scope['conflicting_area_fraction'],'tolerance_mm':scope['tolerance_mm'],'seconds':scope['seconds']}
marker=cache/'continuous.json'
if not marker.exists():atomic_json(marker,{'key':key,'identity':identity,'artifact_sha256':file_hash(target),'metrics':metrics,'imported_read_only_audit_sha256':file_hash(scope_path)})
else:assert load_json(marker)['key']==key and load_json(marker)['artifact_sha256']==file_hash(target)
prior_frag=ROOT/f'reports/fragmentation/{cid}';archived_frag=folder/f'fragmentation_before/{cid}'
if scope['conflicting_faces'] and prior_frag.exists() and not archived_frag.exists():
    assert prior_frag.resolve().is_relative_to(ROOT) and archived_frag.resolve().is_relative_to(folder)
    archived_frag.parent.mkdir(parents=True,exist_ok=True);os.replace(prior_frag,archived_frag)
generated=generate_case(rec['source_id'],rec['level'],rec['seed'],state);assert generated==cid
check=load_json(out/'continuous_veto.json');assert check['key']==key and check['removed_faces']==scope['conflicting_faces']
acceptance=validate_case(cid,state);preview(cid,state)
if acceptance['status']=='investigation_required':
    subprocess.run([sys.executable,str(ROOT/'scripts/review_fragmentation_dispatch.py'),cid],check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    acceptance=validate_case(cid,state)
assert acceptance['status']=='pass',(cid,acceptance['status'],acceptance['failures'])
extra=audit_case(cid);assert extra['status']=='pass'
preserved={}
for path in unchanged:
    name=str(path.relative_to(ROOT)).replace('\\','/');expected=baseline[name]
    assert file_hash(path)==expected['sha256'] and path.stat().st_mtime_ns==expected['mtime_ns'],name
    preserved[name]=expected
after=trimesh.load(out/'mesh.ply',process=False,force='mesh');old_geometry=meta['files'][f'data/cases/{cid}/input/mesh.ply']['sha256']
assert len(after.faces)==len(original.faces)-scope['conflicting_faces']-check.get('post_veto_connectivity_cleanup',{}).get('overlap_conflict_faces_removed',0)
result={'status':'pass','case_id':cid,'source_id':rec['source_id'],'old_mesh_sha256':old_geometry,'new_mesh_sha256':file_hash(out/'mesh.ply'),'mesh_bytes_unchanged':old_geometry==file_hash(out/'mesh.ply'),'original_archive':str(archive.relative_to(ROOT)).replace('\\','/'),'original_archive_sha256':file_hash(archive),'archive_inventory_sha256':file_hash(archive_meta),'scope_audit':str(scope_path.relative_to(ROOT)).replace('\\','/'),'scope_audit_sha256':file_hash(scope_path),'removed_faces':scope['conflicting_faces'],'removed_area_fraction':scope['conflicting_area_fraction'],'continuous_certificate_sha256':file_hash(out/'continuous_veto.json'),'fresh_independent_validation_hash':acceptance['validation_hash'],'unchanged_upstream_files':preserved,'reconstruction_code_sha256':file_hash(ROOT/'src/scanbench/reconstruct.py'),'module_sha256':file_hash(ROOT/'src/scanbench/continuous_free_space.py'),'script_sha256':file_hash(Path(__file__)),'time':time.time()}
atomic_json(proof_path,result);print(canonical_json({k:v for k,v in result.items() if k!='unchanged_upstream_files'}))
