"""Independent newer-kernel source validity check, isolated from the frozen runtime."""
from pathlib import Path
import os,sys,time,collections,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'tools/ocp79'),str(ROOT/'src')]
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
from scanbench.common import *
from scanbench.sources import read_step
import OCP
assert 'tools' in Path(OCP.__file__).parts,'new-kernel test imported the production binding'
from OCP.BRepCheck import BRepCheck_Analyzer,BRepCheck_NoError
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
sid=sys.argv[1];source=ROOT/f'sources/{sid}/input.step';start=time.time();shape,units=read_step(source);mapping=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape,mapping)
checker=BRepCheck_Analyzer(shape,True,False,False);valid=checker.IsValid();errors=[]
for i in range(1,mapping.Size()+1):
    sub=mapping.FindKey(i);result=checker.Result(sub)
    if result is None:continue
    status=[str(s) for s in result.Status() if s!=BRepCheck_NoError]
    if status:errors.append({'subshape_index':i,'type':str(sub.ShapeType()),'status':status})
report={'source_id':sid,'source_sha256':file_hash(source),'revision':REV,'binding_version':importlib.metadata.version('cadquery-ocp'),'OCP_module':str(Path(OCP.__file__).relative_to(ROOT)),'OCP_version':OCP.__version__,'source_or_topology_modifications':False,'units':units,'valid':bool(valid),'unique_subshape_counts':dict(collections.Counter(str(mapping.FindKey(i).ShapeType()) for i in range(1,mapping.Size()+1))),'errors':errors,'seconds':time.time()-start,'production_environment_unchanged':True}
atomic_json(ROOT/f'reports/source_investigations/{sid}/new_kernel_check.json',report);print(canonical_json(report))
