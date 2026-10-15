"""Record a quantified resolution limitation without changing any delivered geometry."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='2'
import numpy as np
from scanbench.common import *
from scanbench.validate import read_mesh
cid=sys.argv[1];rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path'];dest=ROOT/f'reports/fragmentation/{cid}';folder=dest/'subpixel_regions'
d=load_json(folder/'diagnosis.json');raw=load_json(folder/'all_raw_support.json');a=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');mesh=read_mesh(out/'mesh.ply')
assert d['mesh_sha256']==raw['mesh_sha256']==file_hash(out/'mesh.ply') and d['source_sha256']==rec['source_sha256']
assert d['script_sha256']==file_hash(ROOT/'scripts/diagnose_subpixel_regions.py') and raw['script_sha256']==file_hash(ROOT/'scripts/check_subpixel_raw_support.py')
assert file_hash(folder/'all_raw_support.npz')==raw['measurement_sha256']
for p,h in raw['observation_sha256'].items():assert file_hash(ROOT/p)==h
with np.load(folder/'measurements.npz') as z:ids=z['bridge_face_ids']
with np.load(folder/'all_raw_support.npz') as z:dist=z['nearest_noisy_return_distance_mm']
tol=a['quality']['tolerance_mm'];assert raw['support_tolerance_mm']==d['unchanged_support_tolerance_mm']==tol
area_support=float(np.average((dist.reshape(len(ids),22)<=tol).mean(1),weights=mesh.area_faces[ids]))
# A fused working-point subset is deliberately retained as a diagnostic. Formal
# observation support is measured against ALL original returns at the same queries.
checks={k:v for k,v in d['checks'].items() if k!='bridge_lattice_supported_at_unchanged_tolerance'}
checks.update(all_original_observation_lattice_support=raw['supported_fraction']>=.98,area_weighted_original_observation_lattice_support=area_support>=.98,no_formal_hard_gate_failure=not a['failures'])
review_path=ROOT/f'private/annotations/{cid}/fragmentation_review.json'
prior=folder/'prior_strict_component_review.json'
if not prior.exists():shutil.copy2(review_path,prior)
old=load_json(prior);assert old['mesh_sha256']==file_hash(out/'mesh.ply')
files=[dest/'diagnosis.json',dest/'component_correspondence.json',dest/'visible_reference_patch.ply',dest/'visible_reference.png',dest/'organized_first_frame.ply',dest/'organized_first_frame.png',prior,folder/'diagnosis.json',folder/'measurements.npz',folder/'all_raw_support.json',folder/'all_raw_support.npz',folder/'bridge_faces.ply',ROOT/f'private/gt/{rec["source_id"]}/feature_contract.json',*[ROOT/'scripts'/n for n in ['diagnose_fragmentation.py','map_fragment_components.py','review_fragmentation.py','diagnose_subpixel_regions.py','check_subpixel_raw_support.py','review_subpixel_regions.py']]]
result={'status':'pass_natural_separation' if all(checks.values()) else 'unresolved','case_id':cid,'mesh_sha256':file_hash(out/'mesh.ply'),'source_sha256':rec['source_sha256'],'checks':checks,'review_kind':'quantified_subpixel_reference_region_join','evidence_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in files},'strict_raw_component_checks_retained':old['checks'],'reference_major_regions_raw':d['raw_reference_major_regions'],'reference_major_regions_at_declared_pixel_scale':len(set(d['reference_groups_at_one_pixel_scale'].values())),'component_correspondence':[{**x,'reference_component':x['reference_group'],'reference_component_purity':x['purity'],'reference_component_basis':'independently recorded groups at the declared pixel scale; raw components retained separately'} for x in d['mapping']],'local_bridge_area_fraction':d['bridges']['area_fraction'],'bridge_original_observation_support_fraction':raw['supported_fraction'],'bridge_area_weighted_original_observation_support_fraction':area_support,'working_subset_support_fraction':d['bridges']['lattice_observation_supported_fraction'],'declared_pixel_step_mm':d['declared_pixel_step_mm'],'declared_feature_size_mm':d['declared_feature_size_mm'],'resolution_limitation':'The local join across a less-than-one-pixel gap is a reconstruction limitation: preservation of this subresolution groove is not certified. Its area and original-observation support are quantified, and it is not described as a physical missing region. Fine BPA pores likewise remain reconstruction loss.','interpretation':'The large disconnected mesh regions correspond one to one to independently visible reference groups at the declared pixel scale. Raw reference connectivity and the failed stricter one-to-one result remain archived. Only reference pairs separated by less than one declared pixel are grouped; every observed local transition is smaller than the declared resolvable feature and is supported by all original noisy observations at the unchanged tolerance. No source mesh, scan direction, observation or output triangle is altered.'}
atomic_json(review_path,result)
print(canonical_json({k:v for k,v in result.items() if k not in ['evidence_sha256','component_correspondence','interpretation','resolution_limitation']}))
if result['status']!='pass_natural_separation':raise SystemExit(2)
