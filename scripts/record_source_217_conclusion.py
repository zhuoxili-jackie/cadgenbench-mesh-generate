"""Record the specifically verified source-217 invalid-STEP disposition."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *

sid='217';folder=ROOT/f'reports/source_investigations/{sid}';source=ROOT/f'sources/{sid}/input.step';sha=file_hash(source)
ordinary=load_json(folder/'brep_check_ordinary.json');exact=load_json(folder/'brep_check_exact_curve_on_surface.json');caf=load_json(folder/'alternative_reader.json');new=load_json(folder/'new_kernel_check.json');native=load_json(folder/'alternative_native_trials.json');boundary=load_json(folder/'native_boundary_audit.json');official=load_json(folder/'official_mesh_geometry.json')
assert all(x['source_sha256']==sha for x in [ordinary,exact,caf,new,official])
assert sha==next(x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path']==f'{sid}/input.step')
assert not ordinary['valid'] and not exact['valid'] and not caf['metadata']['brep_valid'] and not new['valid']
for report,field in [(ordinary,'own_status'),(exact,'own_status'),(caf,'status'),(new,'status')]:
    assert any(e['subshape_index']==184 and 'BRepCheck_Status.BRepCheck_UnorientableShape' in e[field] for e in report['errors'])
    assert any(e['subshape_index']==185 and 'BRepCheck_Status.BRepCheck_SelfIntersectingWire' in e[field] for e in report['errors'])
assert new['binding_version']=='7.9.3.1.1' and new['production_environment_unchanged']
assert caf['metadata']['counts']['solids']==1 and caf['metadata']['counts']['shells']==2
assert [(r['chord_mm'],r['open_edges']) for r in boundary['trials']]==[(.02,10),(.01,11)]
assert len(native)==2 and all('error' in a and 'mesh_file' in a for a in native)
assert official['watertight'] and official['open_edges']==0 and official['nonmanifold_edges']==0 and official['degenerate_faces']==0
assert official['original_linear_deflection_mm']==0.1933864930194207
assert official['official_sha256']==file_hash(ROOT/f'sources/{sid}/input.mesh.npz')==next(x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path']==f'{sid}/input.mesh.npz')
state=State();assert not any(json.loads(b).get('source_id')==sid for b, in state.db.execute("SELECT body FROM records WHERE kind='cases'"))
assert not (ROOT/f'private/gt/{sid}/mesh.npz').exists()
snap=folder/'scripts_snapshot';snap.mkdir(exist_ok=True)
for name in ['investigate_brep_validity.py','investigate_alternative_step_reader.py','investigate_ocp79_validity.py','audit_native_trial_boundaries.py','audit_official_sidecar_geometry.py','record_source_217_conclusion.py']:
    target=snap/name
    if not target.exists():shutil.copy2(ROOT/'scripts'/name,target)
    assert file_hash(target)==file_hash(ROOT/'scripts'/name)
paths=[p for p in folder.glob('*.json') if p.name!='conclusion.json']+[ROOT/t['mesh_file'] for t in native]+list(snap.glob('*.py'))+[source,ROOT/f'sources/{sid}/input.mesh.npz']
evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in paths}
reason='STEP 的线框 185 自相交，导致面 184 不可定向；STEPControl、STEPCAF 和独立 OCP 7.9.3 均复现同一问题。两组原生离散分别有 10、11 条开放边，经独立 int64 原始三角形边计数确认。官方 0.193386493019 mm Mesh 虽闭合，但任务书的 native 与近似层都要求有效 STEP。1 solid、2 shells 已分别记录；未修复、补洞或修改源件。'
attempts=[
    {'method':'OCP 7.8 STEPControl ordinary geometry check','result':'wire 185 self-intersects; face 184 unorientable','evidence':'brep_check_ordinary.json'},
    {'method':'OCP 7.8 exact curve-on-surface check','result':'same wire/face failure, with additional curve parameter diagnostics','evidence':'brep_check_exact_curve_on_surface.json'},
    {'method':'STEPCAF/XCAF alternate transfer','result':'same wire 185 and face 184 errors','evidence':'alternative_reader.json'},
    {'method':'isolated OCP 7.9.3','result':'same wire 185 and face 184 errors; production runtime unchanged','evidence':'new_kernel_check.json'},
    {'method':'two native tessellations and independent int64 edge audit','result':'10 and 11 open edges respectively; raw meshes retained','evidence':'native_boundary_audit.json'},
    {'method':'fixed-revision official sidecar provenance and full-array geometry check','result':'closed reference with two shells; valid-STEP prerequisite still fails. Negative inner-shell volume is recorded without treating a cavity as an extra solid or automatic defect.','evidence':'official_mesh_geometry.json'}]
report={'source_id':sid,'source_sha256':sha,'revision':REV,'status':'source_excluded','reason':reason,'taskbook_rule':'Both native and official-mesh approximation layers require a valid STEP. Exclusion follows specific repeated geometric failures and reasonable alternatives, not a lone exception or timeout.','attempts':attempts,'evidence_sha256':evidence,'source_or_topology_modifications':False,'formal_case_count':0,'time':time.time()}
conclusion=folder/'conclusion.json';atomic_json(conclusion,report)
key=stage_hash(sha,config()['gt'],['sources.py'],['cadquery-ocp','numpy','trimesh'])
meta={**caf['metadata'],**ordinary['units'],**report,'stage_hash':key,'evidence_summary':str(conclusion.relative_to(ROOT)).replace('\\','/')}
meta_path=ROOT/f'private/gt/{sid}/metadata.json';atomic_json(meta_path,meta);state.record('sources',sid,meta)
state.finish(sid,'gt',key,[meta_path,conclusion,*paths],{'outcome':'source_excluded_after_independent_investigation','native_reference_generated':False,'case_count':0})
prior=state.db.execute("SELECT body FROM records WHERE kind='failures' AND id=?",(sid,)).fetchone()
if prior:
    failure=json.loads(prior[0]);failure.update(status='resolved',resolution={'status':'source_excluded_after_alternative_checks','evidence_summary':meta['evidence_summary'],'reason':reason});state.record('failures',sid,failure)
atomic_json(ROOT/f'state/source_runs/{sid}.json',{'status':'source_excluded','source_id':sid,'formal_case_count':0,'reason':reason,'evidence_summary':meta['evidence_summary']})
print(canonical_json({'source_id':sid,'status':'source_excluded','attempted_alternatives':len(attempts),'formal_case_count':0}))
