"""Read-only STEP validity diagnosis with ordinary and exact curve-on-surface checks."""
from pathlib import Path
import os,sys,time,collections
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import read_step,shape_metadata
from OCP.BRepCheck import BRepCheck_Analyzer,BRepCheck_NoError
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
sid=sys.argv[1];folder=ROOT/f'reports/source_investigations/{sid}';folder.mkdir(parents=True,exist_ok=True)
source=ROOT/f'sources/{sid}/input.step';shape,units=read_step(source)
mapping=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape,mapping)
counts=collections.Counter(str(mapping.FindKey(i).ShapeType()) for i in range(1,mapping.Size()+1))
base={'source_id':sid,'source_sha256':file_hash(source),'source_revision':REV,'units':units,'unique_subshape_counts':dict(counts),'source_or_topology_modifications':False,'reference_documentation':'https://occt3d.com/dev/doc/refman/html/class_b_rep_check___analyzer.html'}
for label,geom,exact in [('ordinary',True,False),('exact_curve_on_surface',True,True),('topology_only_diagnostic',False,False)]:
    path=folder/f'brep_check_{label}.json'
    if path.exists() and load_json(path).get('source_sha256')==base['source_sha256']:print(canonical_json({'reused':label,'valid':load_json(path)['valid']}),flush=True);continue
    started=time.time();analyzer=BRepCheck_Analyzer(shape,geom,False,exact);valid=analyzer.IsValid();errors=[]
    for i in range(1,mapping.Size()+1):
        sub=mapping.FindKey(i);result=analyzer.Result(sub)
        if result is None:continue
        own=[str(s) for s in result.Status() if s!=BRepCheck_NoError];context=[];result.InitContextIterator()
        while result.MoreShapeInContext():
            statuses=[str(s) for s in result.StatusOnShape() if s!=BRepCheck_NoError]
            if statuses:context.append({'context_subshape_index':mapping.FindIndex(result.ContextualShape()),'status':statuses})
            result.NextShapeInContext()
        if own or context:errors.append({'subshape_index':i,'shape_type':str(sub.ShapeType()),'own_status':own,'context':context})
    report={**base,'check':label,'geometry_checks':geom,'exact_method':exact,'valid':bool(valid),'errors':errors,'seconds':time.time()-started}
    atomic_json(path,report);print(canonical_json({k:v for k,v in report.items() if k!='errors'}|{'error_subshapes':len(errors),'error_status_counts':dict(collections.Counter(s for e in errors for s in e['own_status']+[s for c in e['context'] for s in c['status']]))}),flush=True)
