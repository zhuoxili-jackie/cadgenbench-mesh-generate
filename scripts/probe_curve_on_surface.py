"""Read-only direct-coordinate diagnosis of exact curve-on-surface check failures."""
from pathlib import Path
import os,sys,argparse
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
from scanbench.sources import read_step
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRep import BRep_Tool
from OCP.BRepLib import BRepLib_ValidateEdge
from OCP.GeomLib import GeomLib_CheckCurveOnSurface
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--limit',type=int,default=3);args=p.parse_args();sid=args.source
folder=ROOT/f'reports/source_investigations/{sid}';prior=load_json(folder/'brep_check_exact_curve_on_surface.json');shape,units=read_step(ROOT/f'sources/{sid}/input.step')
mapping=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape,mapping);rows=[]
pairs=[(e['subshape_index'],c['context_subshape_index']) for e in prior['errors'] if e['shape_type'].endswith('TopAbs_EDGE') for c in e['context'] if any('InvalidCurveOnSurface' in s or 'InvalidCurveOnClosedSurface' in s for s in c['status'])]
for ei,fi in pairs[:args.limit] if args.limit else pairs:
    edge=TopoDS.Edge_s(mapping.FindKey(ei));face=TopoDS.Face_s(mapping.FindKey(fi));c3=BRepAdaptor_Curve(edge);cs=BRepAdaptor_Curve(edge,face);surface=cs.CurveOnSurface();ref=c3.Curve()
    first,last=c3.FirstParameter(),c3.LastParameter();parameters=np.linspace(first,last,4097)
    distance=np.array([c3.Value(float(t)).Distance(cs.Value(float(t))) for t in parameters]);tol=BRep_Tool.Tolerance_s(edge)
    representation=np.array([max(c3.Value(float(t)).Distance(ref.Value(float(t))),cs.Value(float(t)).Distance(surface.Value(float(t)))) for t in parameters[::256]])
    results={}
    for exact in [False,True]:
        check=BRepLib_ValidateEdge(ref,surface,BRep_Tool.SameParameter_s(edge));check.SetExactMethod(exact);check.SetParallel(False);check.Process()
        results['exact' if exact else 'ordinary']={'done':check.IsDone(),'tolerance_pass':check.CheckTolerance(tol),'reported_max_distance_mm':check.GetMaxDistance()}
    raw=GeomLib_CheckCurveOnSurface(ref);raw.SetParallel(False);raw.Perform(surface)
    row={'edge_global_index':ei,'face_global_index':fi,'edge_tolerance_mm':tol,'edge_degenerate':BRep_Tool.Degenerated_s(edge),'range':[first,last],'curve_type':str(c3.GetType()),'pcurve_type':str(surface.GetCurve().GetType()),'same_parameter':BRep_Tool.SameParameter_s(edge),'dense_sample_count':len(parameters),'dense_max_distance_mm':float(distance.max()),'dense_max_parameter':float(parameters[distance.argmax()]),'adaptor_to_world_coordinate_max_difference_mm':float(representation.max()),'validator':results,'raw_exact_done':raw.IsDone(),'raw_exact_error':raw.ErrorStatus(),'raw_exact_distance':raw.MaxDistance(),'raw_exact_parameter':raw.MaxParameter()}
    rows.append(row);print(canonical_json(row),flush=True)
atomic_json(folder/f'curve_on_surface_probe_{args.limit}.json',{'status':'diagnostic_only','source_id':sid,'source_sha256':file_hash(ROOT/f'sources/{sid}/input.step'),'pairs':rows,'all_reported_edge_face_pairs':len(pairs),'source_modified':False,'script_sha256':file_hash(Path(__file__))})
