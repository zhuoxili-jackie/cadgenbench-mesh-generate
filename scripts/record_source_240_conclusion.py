"""Record source 240 only after its actual alternative-reader/kernel evidence."""
from pathlib import Path
import os, sys, shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *

sid='240';folder=ROOT/f'reports/source_investigations/{sid}';source=ROOT/f'sources/{sid}/input.step';sha=file_hash(source)
ordinary=load_json(folder/'brep_check_ordinary.json');exact=load_json(folder/'brep_check_exact_curve_on_surface.json');caf=load_json(folder/'alternative_reader.json');new=load_json(folder/'new_kernel_check.json');native=load_json(folder/'alternative_native_trials.json');official=load_json(folder/'official_mesh_geometry.json')
old_faces=load_json(folder/'face_identity_production.json');new_faces=load_json(folder/'face_identity_new.json')
assert all(x['source_sha256']==sha for x in [ordinary,exact,caf,new,official,old_faces,new_faces])
assert sha==next(x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path']==f'{sid}/input.step')
assert not ordinary['valid'] and not exact['valid'] and not caf['metadata']['brep_valid'] and not new['valid']
for report,field,index in [(ordinary,'own_status',1306),(exact,'own_status',1306),(caf,'status',1306),(new,'status',4697)]:
    assert any(e['subshape_index']==index and 'BRepCheck_Status.BRepCheck_UnorientableShape' in e[field] for e in report['errors'])
assert any(e['subshape_index']==1307 and any('BRepCheck_Status.BRepCheck_BadOrientationOfSubshape' in c['status'] for c in e['context']) for e in ordinary['errors'])
assert new['binding_version']=='7.9.3.1.1' and new['production_environment_unchanged']
a=next(x for x in old_faces['faces'] if x['own_status']);b=next(x for x in new_faces['faces'] if x['own_status'])
for key in ['area_mm2','bounds_source_mm','centroid_source_mm','surface_type','orientation','uv_bounds']:
    assert a[key]==b[key],f'Invalid-face geometric correspondence differs: {key}'
assert a['face_index']==115 and b['face_index']==690
assert caf['metadata']['counts']=={'solids':1,'shells':1,'compounds':0,'faces':1004}
assert len(native)==2 and [(x['chord_mm'],x['angle_rad']) for x in native]==[(.02,.15),(.01,.075)]
assert all('face #966 missing triangulation' in x['error'] and 'mesh_file' not in x for x in native)
assert official['watertight'] and official['open_edges']==0 and official['nonmanifold_edges']==0 and official['degenerate_faces']==0
assert official['official_sha256']==file_hash(ROOT/f'sources/{sid}/input.mesh.npz')==next(x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path']==f'{sid}/input.mesh.npz')
state=State();assert not any(json.loads(b).get('source_id')==sid for b, in state.db.execute("SELECT body FROM records WHERE kind='cases'"))
assert not (ROOT/f'private/gt/{sid}/mesh.npz').exists()
snap=folder/'scripts_snapshot';snap.mkdir(exist_ok=True)
for name in ['investigate_brep_validity.py','investigate_alternative_step_reader.py','investigate_ocp79_validity.py','audit_official_sidecar_geometry.py','audit_invalid_face_identity.py','record_source_240_conclusion.py']:
    target=snap/name
    if not target.exists():shutil.copy2(ROOT/'scripts'/name,target)
    assert file_hash(target)==file_hash(ROOT/'scripts'/name)
paths=[p for p in folder.glob('*.json') if p.name!='conclusion.json']+list(snap.glob('*.py'))+[source,ROOT/f'sources/{sid}/input.mesh.npz']
evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in paths}
reason='STEP 存在不可定向的 B 样条面及其线框方向错误，STEPControl、STEPCAF 和独立 OCP 7.9.3 均未通过有效性检查。两版内核的实体编号不同，但错误面的面积、包围盒、重心、曲面类型和参数域完全对应。两组原生离散另在生产内核第 966 个面缺少三角化结果。官方 0.158561543907 mm Mesh 虽闭合，不能替代任务书要求的有效 STEP；未修复、补洞或修改源件。'
attempts=[
 {'method':'OCP 7.8 STEPControl ordinary and exact geometry checks','result':'global face 1306 unorientable; wire 1307 has bad orientation in that face','evidence':'brep_check_ordinary.json'},
 {'method':'STEPCAF/XCAF alternate transfer','result':'global face 1306 remains unorientable','evidence':'alternative_reader.json'},
 {'method':'isolated OCP 7.9.3 and exact geometric face correspondence','result':'global face 4697 unorientable; geometry equals production global face 1306 despite reordered enumeration','evidence':'face_identity_new.json'},
 {'method':'two native tessellations at 0.02/0.15 and 0.01/0.075','result':'both stop at production face 966 with missing triangulation; no assembled mesh was produced','evidence':'alternative_native_trials.json'},
 {'method':'fixed-revision official sidecar provenance and full-array geometry audit','result':'closed official mesh; mandatory valid-STEP prerequisite still fails','evidence':'official_mesh_geometry.json'}]
report={'source_id':sid,'source_sha256':sha,'revision':REV,'status':'source_excluded','reason':reason,'taskbook_rule':'Native and official-mesh approximation layers both require valid STEP. This conclusion uses repeated specific geometry failures and reasonable alternatives, not one exception or timeout.','attempts':attempts,'evidence_sha256':evidence,'source_or_topology_modifications':False,'formal_case_count':0,'time':time.time()}
conclusion=folder/'conclusion.json';assert not conclusion.exists();atomic_json(conclusion,report)
key=stage_hash(sha,config()['gt'],['sources.py'],['cadquery-ocp','numpy','trimesh'])
meta={**caf['metadata'],**ordinary['units'],**report,'stage_hash':key,'evidence_summary':str(conclusion.relative_to(ROOT)).replace('\\','/')}
meta_path=ROOT/f'private/gt/{sid}/metadata.json';atomic_json(meta_path,meta);state.record('sources',sid,meta)
state.finish(sid,'gt',key,[meta_path,conclusion,*paths],{'outcome':'source_excluded_after_independent_investigation','native_reference_generated':False,'case_count':0})
prior=state.db.execute("SELECT body FROM records WHERE kind='failures' AND id=?",(sid,)).fetchone()
if prior:
    failure=json.loads(prior[0]);failure.update(status='resolved',resolution={'status':'source_excluded_after_alternative_checks','evidence_summary':meta['evidence_summary'],'reason':reason});state.record('failures',sid,failure)
atomic_json(ROOT/f'state/source_runs/{sid}.json',{'status':'source_excluded','source_id':sid,'formal_case_count':0,'reason':reason,'evidence_summary':meta['evidence_summary']})
print(canonical_json({'source_id':sid,'status':'source_excluded','attempted_alternatives':len(attempts),'formal_case_count':0}))
