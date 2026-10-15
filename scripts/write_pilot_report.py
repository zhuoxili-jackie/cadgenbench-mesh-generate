from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *
from scanbench.cases import case_id

table='| Source | Level | Seed | Poses | Resolution | Faces | Mesh support | Observed retained | GT coverage | Status |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---|\n';accepted=[];costs=[]
for sid in ['218','231','229']:
    for seed in config()['seeds']:
        for level in ['hard','medium','easy']:
            cid=case_id(sid,level,seed);r=load_json(ROOT/f'private/annotations/{cid}/case.json');a=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');q=a['quality'];m=a['mesh'];assert a['status']=='pass',cid
            table+=f'| {sid} | {level} | {seed} | {r["placement_count"]} | {r["resolution"]} | {m["faces"]} | {q["mesh_observation_supported_fraction"]:.6f} | {q["observation_mesh_retained_fraction"]:.6f} | {q["total_gt_surface_mesh_coverage"]:.6f} | {a["status"]} |\n';accepted.append(cid);costs.append(r['metrics']['performance'])
factor='| Source | Comparison | Placements | Frames/placement | Visible surface | Initial contact revealed | Overlap P10 |\n|---|---|---:|---:|---:|---:|---:|\n'
for sid in ['218','231','229']:
    for r in load_json(ROOT/f'reports/source_audits/{sid}.json')['factor_checks']:
        factor+=f'| {sid} | {r["factor"]} | {r["placements"]} | {r["frames_per_placement"]} | {r["surface_fraction"]:.6f} | {r["initial_contact_visible_fraction"]} | {r["adjacent_overlap_p10"]:.6f} |\n'
old=load_json(ROOT/'reports/pilot_comparison/218_hard_initial_acceptance.json');current=load_json(ROOT/f'private/annotations/{case_id("218","hard",20261014)}/acceptance.json');diag=load_json(ROOT/f'reports/fragmentation/{case_id("231","hard",20261014)}/diagnosis.json');mapping=load_json(ROOT/f'reports/fragmentation/{case_id("231","hard",20261014)}/component_correspondence.json')
body=f'''# Pilot report: physical_scan_v1

All three required source parts (218, 231, 229), both seeds and three levels are present: {len(accepted)} actual independently accepted cases. Source and case manifests, exact data hashes and complete images are retained. This report is the basis for the protocol freeze; it is not a claim that the remaining 29 sources have already been completed.

## Actual outcomes

{table}
All official source STEP SHA256 values match revision `{REV}`. Native BREP tessellation is used for these pilot sources. Every chosen placement passes an independent exact-CAD contact/minimum-height/support audit. Source 231 has two certified stable support directions; easy uses those two, without a duplicate third pose. A further 142 nonduplicate stable-hull proposals were checked against exact CAD contact and a conservative COM support-margin test, without certifying a third reliable pose. The evidence in `private/gt/231/limited_pose_investigation.json` is a finite candidate audit, not a mathematical enumeration of all continuous rolling equilibria. All paths retain all three full turns and the same incidence threshold, optics and noise law.

## Calibration and method decision

The initial 218 hard attempt is retained as `pilot_comparison/218_hard_initial_acceptance.json` and its full-surface preview. It had locally inconsistent winding and unnecessary perforation caused by a nearest-working-point veto inside triangles. The corrected method checks continuous measured range-image support at 22 triangle samples and foreground free space; it does not require every sample to coincide with a sparse working vertex. Four bounded BPA radii 1/1.5/2/2.5h are used uniformly. Folded shared-edge conflicts are discarded using observed normals, and disconnected vertex fans receive distinct coincident vertex identities. No faces are added to fill missing regions, no GT normals are used, and no points are projected to GT.

Initial 218 hard area: {old['mesh']['area_mm2']:.6f} mm²; corrected area: {current['mesh']['area_mm2']:.6f} mm². Corrected observed retention: {current['quality']['observation_mesh_retained_fraction']:.6f}; mesh observation support: {current['quality']['mesh_observation_supported_fraction']:.6f}; nonmanifold edges/vertices: {current['mesh']['nonmanifold_edges']}/{current['mesh']['nonmanifold_vertices']}. Fine local BPA pores remain below the explicit sampling/support scale and are not relabeled as physical occlusion.

231 hard triggered the 85% largest-component investigation. Independent first-hit/table/incidence visibility on seven barycentric points of every GT face yields two large visible reference regions, with areas {diag['visible_reference_component_areas_mm2'][:2]} mm². The two major measured Mesh components independently map to distinct reference regions with purities {[r['reference_component_purity'] for r in mapping[:2]]}. Same noisy distance-image local triangulation was constructed for every hard frame as a diagnostic, never overlaid into the delivered Mesh. Its area-sampled centroid retention against BPA is {diag['organized_comparison_mean_retained']:.6f}. Complete comparison images, frame-level data and hashed correspondence evidence are in `reports/fragmentation/`. This satisfies the task's natural-separation exception with evidence; no gate was lowered.

The compiled range-support kernel produced exactly equal support/free-space masks on 1,338,304 sample-camera comparisons. Precomputed vertex-to-face incidence is checked against a linear face-membership reference, preserving float64 vertices, triangle indices and cleanup metrics. During 231 easy seed 20261015, an int32 canonical edge-key multiplication incorrectly reported a nonmanifold BPA edge. Independent row-wise edge counting on the saved supported mesh found zero actual nonmanifold edges. The implementation now uses int64 keys, and a 65,537-vertex regression demonstrates the exact aliasing mechanism and preserves all three original test triangles. Existing observations, fusion and supported geometry were reused; affected topology and acceptance stages were rerun. This is a corrected implementation defect, not a source exclusion or a relaxed gate. The sample lattice documentation was also corrected to fifth-edge division (22 samples); numerical weights and support results never changed.

## Placement versus density factors

{factor}
These comparisons reuse finite dense mother-camera visibility on the same 30,000 fixed area samples. They are not extra formal Mesh cases and not omniscient cavity views. Flip count exposes former support surfaces; greater density chiefly improves adjacent overlap in these pilot parts. The low overlap for extra placements at 49 frames in the factor experiment explains why the formal medium/easy levels use 97/193 frames. Hard always retains the complete first-pose spiral.

## Independent tests and limits

The analytic millimetre/metre STEP controls, oblique-plane Euclidean range, backprojection, box tabletop occlusion and flip exposure, asymmetric inverse-pose equivalence, actual paired noise/clipping, through-hole and material-ring preservation are passed. Every pilot case has independent physical/path, real-pixel provenance, observation-to-mesh, mesh-to-observation/free-space, PLY/STL facet correspondence, topology, finite-reference visibility and cylindrical-passage checks. Missing/corrupt real export files are rejected. A fresh public-only process rebuild, a complete same-seed original-STEP rebuild, and a real killed/resumed reconstruction are separately evidenced. The final current-code evidence is in `tests_report.json` and individual `reports/tests/` records; a stale code signature is not sufficient for freezing.

Measured working-process peak RSS in current pilot case reconstructions is {max(c['peak_rss_bytes'] for c in costs)/2**30:.3f} GiB. Individual persisted timings may include valid cache reuse; historical completed attempt times are retained in `state/events.jsonl`. The full batch remains serial with two numeric-library threads and a disk reserve. No completed valid raycast or observation stage is rerun for meshing/validation-only changes.

Additional equivalent optimizations were checked before freezing: the incremental first-return voxel inventory matches every float64 representative and its lexicographic order on all 36,147,676 real observations of 231 easy (722,701 spatial cells). A centre-depth bound avoids unnecessary 3x3 patch reads in the compiled support kernel; old compiled, new compiled and independent NumPy masks match on 1,338,304 comparisons. Exact old code hashes are recognized only for the proven support-kernel/label equivalences, preserving valid cached support results. Neither optimization changes physical sampling, tolerance, selected validation points or Mesh geometry.

Resolution selection was corrected to use the coarsest projected interval over every actual placement. An independent rotated-box counterexample demonstrated the original first-pose-only defect (768 incorrectly selected), and now selects the required 1024. The three pilot sources already have their worst interval at pose zero. The migration checks that all code outside the camera builder has identical AST, and that pilot camera/contract files and every observation payload retain identical hashes and mtimes. Only dependency keys and private scan-index bookkeeping are refreshed; no valid raycasts or noisy data are regenerated. Evidence: `reports/tests/all_pose_sampling_control.json` and `all_pose_sampling_migration.json`.

The frozen gate values remain support >=98%, observation retention >=95%, zero nonmanifold edges/vertices and zero illegal/duplicate faces, no resolved-scale through-hole closure, and adjacent-overlap P10 >=50%. Largest component <85% or tiny components >3% triggers investigation rather than forced completion of unseen surfaces. Per-source resolution contracts and actual pose counts remain explicit. This is an ideal segmented, exact-pose, geometric tabletop simulator with controlled ray noise; reflectance, pose drift and scanner-specific photometry are not modeled.
'''
atomic_bytes(ROOT/'reports/pilot_report.md',body.encode('utf-8'));print('wrote factual 18-case pilot report')
