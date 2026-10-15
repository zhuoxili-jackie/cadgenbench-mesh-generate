"""Separate same-parameter disagreement from sampled physical curve-locus distance."""
from pathlib import Path
import os,sys,argparse
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
from scanbench.sources import read_step
from scipy.optimize import minimize_scalar
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve

def coordinates(curve,parameters):return np.array([list(curve.Value(float(t)).Coord()) for t in parameters])
def distances_to_curve(points,curve,a,b):
    grid=np.linspace(a,b,257);sample=coordinates(curve,grid);distances=[]
    for point in points:
        d=((sample-point)**2).sum(axis=1);i=int(d.argmin());lo=grid[max(i-2,0)];hi=grid[min(i+2,len(grid)-1)]
        def objective(t):return float(((np.asarray(curve.Value(float(t)).Coord())-point)**2).sum())
        result=minimize_scalar(objective,bounds=(lo,hi),method='bounded',options={'xatol':max(1e-14,abs(b-a)*1e-13),'maxiter':120})
        assert result.success
        distances.append(float(np.sqrt(min(result.fun,float(d[i]),objective(lo),objective(hi)))))
    return np.asarray(distances)

p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--worst-only',action='store_true');args=p.parse_args();sid=args.source
folder=ROOT/f'reports/source_investigations/{sid}';source=ROOT/f'sources/{sid}/input.step';prior_path=folder/'curve_on_surface_probe_0.json';prior=load_json(prior_path);shape,_=read_step(source);mapping=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape,mapping)
selected=sorted(prior['pairs'],key=lambda x:x['raw_exact_distance'],reverse=True);selected=selected[:1] if args.worst_only else selected
rows=[]
for record in selected:
    edge=TopoDS.Edge_s(mapping.FindKey(record['edge_global_index']));face=TopoDS.Face_s(mapping.FindKey(record['face_global_index']));c3=BRepAdaptor_Curve(edge);cs=BRepAdaptor_Curve(edge,face)
    a,b=c3.FirstParameter(),c3.LastParameter();times=np.unique(np.r_[np.linspace(a,b,17),record['raw_exact_parameter']]);points3=coordinates(c3,times);points2=coordinates(cs,times)
    forward=distances_to_curve(points3,cs,cs.FirstParameter(),cs.LastParameter());backward=distances_to_curve(points2,c3,a,b)
    rows.append({'edge_global_index':record['edge_global_index'],'face_global_index':record['face_global_index'],'same_parameter_max_mm':record['raw_exact_distance'],'independent_tested_parameters':times.tolist(),'3D_to_pcurve_locus_mm':forward.tolist(),'pcurve_to_3D_locus_mm':backward.tolist(),'max_sampled_symmetric_locus_distance_mm':float(max(forward.max(),backward.max()))})
result={'status':'diagnostic_only','source_id':sid,'source_sha256':file_hash(source),'prior_same_parameter_report_sha256':file_hash(prior_path),'script_sha256':file_hash(Path(__file__)),'no_geometry_or_tolerance_modified':True,'method':'World-coordinate distance to curve: 257 independent coarse samples and bounded SciPy minimization around nearest sample; both directions, 17 uniform parameters plus the exact checker maximum. This is a sampled distance upper bound, not a global Hausdorff certificate.','pairs':rows,'max_same_parameter_disagreement_mm':max(r['same_parameter_max_mm'] for r in rows),'max_sampled_locus_distance_mm':max(r['max_sampled_symmetric_locus_distance_mm'] for r in rows)}
atomic_json(folder/('locus_worst_probe.json' if args.worst_only else 'locus_all_flagged_pairs.json'),result);print(canonical_json({k:v for k,v in result.items() if k!='pairs'}))
