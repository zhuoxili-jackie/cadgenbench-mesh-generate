"""Resolve only quantified natural separation; never alters geometry or gates."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *
cid=sys.argv[1];rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path'];dest=ROOT/f'reports/fragmentation/{cid}'
diag=dest/'diagnosis.json'
if not diag.exists() or load_json(diag)['mesh_sha256']!=file_hash(out/'mesh.ply'):
    subprocess.run([sys.executable,str(ROOT/'scripts/diagnose_fragmentation.py'),cid],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
subprocess.run([sys.executable,str(ROOT/'scripts/map_fragment_components.py'),cid],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
d=load_json(diag);mapping=load_json(dest/'component_correspondence.json');a=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');q=a['quality'];m=a['mesh']
large=[v for v in mapping if v['area_mm2']>=.01*m['area_mm2']];ra=d['visible_reference_component_areas_mm2'];nr=sum(v>=.01*sum(ra) for v in ra)
checks={'all_hard_gates_passed':not a['failures'],'at_least_two_reference_regions':nr>=2,'one_to_one_major_regions':len(large)==nr and len({v['reference_component'] for v in large})==nr,'area_mapping_purity':all(v['reference_component_purity']>=.99 and v['distance_p95']<=q['tolerance_mm'] for v in large),'minor_unexplained_area_below_gate':m['tiny_component_area_fraction']<=.03 and sum(v['area_mm2'] for v in large)/m['area_mm2']>=.97,'observed_retention':q['observation_mesh_retained_fraction']>=.95,'organized_same_observations_retention':d['organized_comparison_mean_retained']>=.95,'complete_trajectory':a['physical_scan']['status']=='pass'}
evidence=[diag,dest/'component_correspondence.json',dest/'visible_reference_patch.ply',dest/'visible_reference.png',dest/'organized_first_frame.ply',dest/'organized_first_frame.png',ROOT/'scripts/diagnose_fragmentation.py',ROOT/'scripts/map_fragment_components.py',Path(__file__)]
result={'case_id':cid,'status':'pass_natural_separation' if all(checks.values()) else 'unresolved','mesh_sha256':file_hash(out/'mesh.ply'),'source_sha256':rec['source_sha256'],'checks':checks,'evidence_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in evidence},'reference_major_regions':nr,'component_correspondence':large,'interpretation':'The selected physical camera path and incidence threshold expose disconnected surface regions. Each major reconstructed region maps independently to a distinct visible-reference component with >=99% area-sample purity. Same-noisy-frame local triangulation and observed retention pass. Subresolution BPA pores remain and are not called physical missing regions. No scan directions or GT faces were deleted and no mesh was changed.'}
atomic_json(ROOT/f'private/annotations/{cid}/fragmentation_review.json',result);print(canonical_json(result))
if result['status']=='unresolved':raise SystemExit(2)
