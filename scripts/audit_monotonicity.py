"""Explain actual nonmonotonic meshing coverage without changing any formal gate."""
from pathlib import Path
import os,sys,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
from scanbench.cases import case_id
from scanbench.validate import read_mesh,distance_scene,distances

def audit(sid):
    reference=ROOT/f'private/reference/{sid}/evaluation.npz';source=load_json(ROOT/f'private/gt/{sid}/metadata.json');cfg=config();cases={}
    for seed in cfg['seeds']:
        for level in ['hard','medium','easy']:
            cid=case_id(sid,level,seed);a=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');q=a['quality']
            cases[cid]={'case_id':cid,'level':level,'seed':seed,'mesh_sha256':file_hash(ROOT/f'data/cases/{cid}/input/mesh.ply'),'tolerance_mm':q['tolerance_mm'],'coverage':q['total_gt_surface_mesh_coverage']}
    key=digest({'cases':cases,'reference':file_hash(reference),'source':source['source_sha256'],'script':file_hash(Path(__file__))})
    output=ROOT/f'reports/monotonicity/{sid}.json'
    if output.exists() and load_json(output).get('key')==key:return load_json(output)
    with np.load(reference) as data:
        points=data['points'];visibility={level:data['visible_'+level] for level in ['hard','medium','easy']}
    nested=bool(np.all(~visibility['hard']|visibility['medium']) and np.all(~visibility['medium']|visibility['easy']))
    assert nested,'Physical visibility lost in nested camera/placement sets'
    comparisons=[];nonmonotonic=[]
    for seed in cfg['seeds']:
        for lower,higher in [('hard','medium'),('medium','easy')]:
            a=cases[case_id(sid,lower,seed)];b=cases[case_id(sid,higher,seed)]
            row={'source_id':sid,'seed':seed,'lower_level':lower,'higher_level':higher,'lower_case':a['case_id'],'higher_case':b['case_id'],'coverage_change':b['coverage']-a['coverage'],'physical_visibility_points_lost':int((visibility[lower]&~visibility[higher]).sum()),'lower_tolerance_mm':a['tolerance_mm'],'higher_tolerance_mm':b['tolerance_mm'],'status':'nondecreasing'}
            if row['coverage_change']<0:
                ds=[]
                for c in [a,b]:
                    mesh=read_mesh(ROOT/f'data/cases/{c["case_id"]}/input/mesh.ply');scene=distance_scene(mesh);ds.append(distances(scene,points));del scene,mesh
                da,db=ds;ca=da<=a['tolerance_mm'];cb=db<=b['tolerance_mm']
                assert float(ca.mean())==a['coverage'] and float(cb.mean())==b['coverage'],'Distance recomputation differs from formal coverage'
                lost=ca&~cb;gained=~ca&cb;counterfactual=db<=a['tolerance_mm'];tolerance_only=lost&counterfactual
                geom_loss=lost&~counterfactual
                assert int(lost.sum())==int(tolerance_only.sum()+geom_loss.sum())
                payload=ROOT/f'reports/monotonicity/{sid}_{seed}_{lower}_{higher}.npz'
                atomic_npz(payload,lower_distance_mm=da,higher_distance_mm=db,lost_indices=np.flatnonzero(lost),gained_indices=np.flatnonzero(gained),tolerance_only_lost_indices=np.flatnonzero(tolerance_only),geometry_at_previous_tolerance_lost_indices=np.flatnonzero(geom_loss))
                row.update(status='explained_nonmonotonic',n=len(points),lower_covered_samples=int(ca.sum()),higher_covered_samples=int(cb.sum()),lost_samples=int(lost.sum()),gained_samples=int(gained.sum()),lost_only_because_new_tolerance_is_stricter=int(tolerance_only.sum()),lost_also_at_previous_tolerance=int(geom_loss.sum()),higher_coverage_at_previous_tolerance=float(counterfactual.mean()),distance_evidence=str(payload.relative_to(ROOT)).replace('\\','/'),distance_evidence_sha256=file_hash(payload),interpretation='No physical view loss. More observations change selected noisy representatives, local normals and BPA connectivity; the measured pointwise distances identify any local meshing variation. A smaller h may also tighten the formal tolerance. The counterfactual old tolerance is diagnostic only and never replaces the formal score or gate.')
                nonmonotonic.append(row)
            comparisons.append(row)
    result={'status':'pass','key':key,'source_id':sid,'source_sha256':source['source_sha256'],'reference_sha256':file_hash(reference),'script_sha256':file_hash(Path(__file__)),'geometric_visibility_nested':nested,'cases':cases,'comparisons':comparisons,'nonmonotonic':nonmonotonic,'method':'Same fixed 30000 area-distributed GT points and actual final triangle meshes. Formal per-case tolerances remain unchanged. For decreases, pointwise losses are split using the previous level tolerance; exact lost/gained sample indices are retained.'}
    atomic_json(output,result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--ids',nargs='+');p.add_argument('--all',action='store_true');args=p.parse_args()
    ids=args.ids
    if args.all:ids=[r['source_id'] for r in map(json.loads,(ROOT/'manifests/sources.jsonl').read_text(encoding='utf-8').splitlines()) if r['status'].startswith('eligible_')]
    if not ids:p.error('--ids or --all is required')
    reports=[audit(sid) for sid in ids]
    summary={'status':'pass','sources':ids,'all_geometric_visibility_nested':all(r['geometric_visibility_nested'] for r in reports),'nonmonotonic_pairs':[x for r in reports for x in r['nonmonotonic']]}
    if args.all:atomic_json(ROOT/'reports/monotonicity/summary.json',summary)
    print(canonical_json(summary))

if __name__=='__main__':main()
