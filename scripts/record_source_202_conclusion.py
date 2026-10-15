"""Record source 202's evidenced invalid-STEP disposition without changing its geometry."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
sid='202';folder=ROOT/f'reports/source_investigations/{sid}';source=ROOT/f'sources/{sid}/input.step';sha=file_hash(source)
ordinary=load_json(folder/'brep_check_ordinary.json');exact=load_json(folder/'brep_check_exact_curve_on_surface.json');caf=load_json(folder/'alternative_reader.json');new=load_json(folder/'new_kernel_check.json');native=load_json(folder/'alternative_native_trials.json');boundary=load_json(folder/'native_boundary_audit.json');official=load_json(folder/'official_mesh_geometry.json')
assert all(x['source_sha256']==sha for x in [ordinary,exact,caf,new])
assert not ordinary['valid'] and not exact['valid'] and not caf['metadata']['brep_valid'] and not new['valid']
assert new['binding_version']=='7.9.3.1.1' and new['production_environment_unchanged']
assert [(r['chord_mm'],r['open_edges']) for r in boundary['trials']]==[(.02,9),(.01,18)]
assert len(native)==2 and all('error' in a for a in native)
expected=next(x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path']=='202/input.step');assert sha==expected
assert official['watertight'] and official['original_linear_deflection_mm']==.5
snap=folder/'scripts_snapshot';snap.mkdir(exist_ok=True)
for name in ['investigate_brep_validity.py','investigate_alternative_step_reader.py','investigate_ocp79_validity.py','audit_native_trial_boundaries.py','record_source_202_conclusion.py']:
    target=snap/name
    if not target.exists():shutil.copy2(ROOT/'scripts'/name,target)
paths=[p for p in folder.glob('*.json') if p.name!='conclusion.json']+[ROOT/t['mesh_file'] for t in native]+list(snap.glob('*.py'))+[source,ROOT/'sources/202/input.mesh.npz']
evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in paths}
reason='STEP 含自相交线框（子形状 10675）及不可定向面（10674）；STEPControl、STEPCAF 和独立 OCP 7.9.3 均确认。0.02/0.15 与 0.01/0.075 原生离散分别有 9、18 条开放边。官方 0.5 mm Mesh 虽闭合，但不满足任务书近似层必须先有有效 STEP 的前提；未修改源件或补洞。'
attempts=[{'method':'OCP 7.8 STEPControl ordinary geometry check','result':'self-intersecting wire and unorientable face','evidence':'brep_check_ordinary.json'}, {'method':'OCP 7.8 exact curve-on-surface geometry check','result':'invalid; original wire issue persists plus curve parameter errors','evidence':'brep_check_exact_curve_on_surface.json'}, {'method':'STEPCAF/XCAF alternate transfer','result':'same invalid wire and face','evidence':'alternative_reader.json'}, {'method':'independently installed OCP 7.9.3','result':'same invalid wire and face','evidence':'new_kernel_check.json'}, {'method':'two native tessellation parameter trials and independent raw-edge audit','result':'9 and 18 boundary edges respectively','evidence':'native_boundary_audit.json'}, {'method':'official sidecar hash and geometry check','result':'closed 0.5 mm reference, but invalid STEP makes approximate layer ineligible under the taskbook','evidence':'official_mesh_geometry.json'}]
report={'source_id':sid,'source_sha256':sha,'revision':REV,'status':'source_excluded','reason':reason,'taskbook_rule':'Both eligible_native and eligible_official_mesh_approx require a valid STEP; source_excluded requires concrete findings and reasonable alternatives, not a lone exception or timeout.','attempts':attempts,'evidence_sha256':evidence,'source_or_topology_modifications':False,'formal_case_count':0,'time':time.time()}
conclusion=folder/'conclusion.json';atomic_json(conclusion,report)
state=State();key=stage_hash(sha,config()['gt'],['sources.py'],['cadquery-ocp','numpy','trimesh'])
meta={**caf['metadata'],**ordinary['units'],**report,'stage_hash':key,'evidence_summary':str(conclusion.relative_to(ROOT)).replace('\\','/')}
meta_path=ROOT/f'private/gt/{sid}/metadata.json';atomic_json(meta_path,meta);state.record('sources',sid,meta)
state.finish(sid,'gt',key,[meta_path,conclusion,*paths],{'outcome':'source_excluded_after_independent_investigation','native_reference_generated':False,'case_count':0})
prior=state.db.execute("SELECT body FROM records WHERE kind='failures' AND id=?",(sid,)).fetchone()
if prior:
    failure=json.loads(prior[0]);failure.update(status='resolved',resolution={'status':'source_excluded_after_alternative_checks','evidence_summary':meta['evidence_summary'],'reason':reason});state.record('failures',sid,failure)
atomic_json(ROOT/f'state/source_runs/{sid}.json',{'status':'source_excluded','source_id':sid,'formal_case_count':0,'reason':reason,'evidence_summary':meta['evidence_summary']})
print(canonical_json({'source_id':sid,'status':'source_excluded','attempted_alternatives':len(attempts),'formal_case_count':0}))
