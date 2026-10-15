"""Independent STEPCAF transfer and read-only tessellation trials; never fixes source geometry."""
from pathlib import Path
import os,sys,time,traceback
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import shape_metadata,brep_distance_check
from cadgenbench.common.mesh import tessellate_shape,validate_mesh
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound
from OCP.BRepCheck import BRepCheck_Analyzer,BRepCheck_NoError
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.BRepTools import BRepTools
sid=sys.argv[1];folder=ROOT/f'reports/source_investigations/{sid}';folder.mkdir(parents=True,exist_ok=True);source=ROOT/f'sources/{sid}/input.step';started=time.time()
doc=TDocStd_Document(TCollection_ExtendedString('XCAF'));reader=STEPCAFControl_Reader();reader.SetNameMode(True);reader.SetColorMode(False);reader.SetLayerMode(False)
assert reader.ReadFile(os.path.relpath(source))==IFSelect_RetDone;assert reader.Transfer(doc)
tool=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main());labels=TDF_LabelSequence();tool.GetFreeShapes(labels);parts=[tool.GetShape_s(labels.Value(i)) for i in range(1,labels.Length()+1)]
if len(parts)==1:shape=parts[0]
else:
    shape=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(shape)
    for part in parts:builder.Add(shape,part)
report_path=folder/'alternative_reader.json';prior=load_json(report_path) if report_path.exists() else {}
if prior.get('source_sha256')==file_hash(source):meta=prior['metadata'];print('Reuse verified STEPCAF import validity evidence',flush=True)
else:
    meta=shape_metadata(shape);analysis=BRepCheck_Analyzer(shape);mapping=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape,mapping);errors=[]
    for i in range(1,mapping.Size()+1):
        sub=mapping.FindKey(i);r=analysis.Result(sub)
        if r is None:continue
        status=[str(s) for s in r.Status() if s!=BRepCheck_NoError]
        if status:errors.append({'subshape_index':i,'type':str(sub.ShapeType()),'status':status})
    report={'source_id':sid,'source_sha256':file_hash(source),'revision':REV,'reader':'STEPCAFControl_Reader with XCAF free-shape extraction','reader_reference':'https://github.com/gumyr/build123d/blob/v0.10.0/src/build123d/importers.py','free_shapes':len(parts),'metadata':meta,'errors':errors,'source_or_topology_modifications':False,'seconds':time.time()-started}
    atomic_json(report_path,report);print(canonical_json(report),flush=True)
center=np.mean(meta['bounds_source_mm'],axis=0);trials=load_json(folder/'alternative_native_trials.json') if (folder/'alternative_native_trials.json').exists() else []
for chord,angle in [(.02,.15),(.01,.075)]:
    existing=next((t for t in trials if t['chord_mm']==chord and t['angle_rad']==angle),None)
    if existing and ('mesh_file' not in existing or file_hash(ROOT/existing['mesh_file'])==existing['mesh_sha256']):print(f'Reuse recorded native trial {chord}/{angle}',flush=True);continue
    start=time.time();trial={'reader':'STEPCAFControl_Reader','chord_mm':chord,'angle_rad':angle,'source_validity_gate_pass':bool(meta['brep_valid'])}
    try:
        BRepTools.Clean_s(shape);mesh=tessellate_shape(shape,chord,angular_deflection_rad=angle,parallel=False)
        path=folder/f'caf_native_{chord}_{angle}.npz';atomic_npz(path,vertices=mesh.vertices,triangles=mesh.triangles)
        trial.update(vertices=len(mesh.vertices),faces=len(mesh.triangles),mesh_file=str(path.relative_to(ROOT)),mesh_sha256=file_hash(path));validate_mesh(mesh)
        accuracy=brep_distance_check(shape,mesh.vertices-center,mesh.triangles,center)
        trial.update(mesh_validation='pass',accuracy=accuracy,not_an_eligibility_override=True)
    except Exception as exc:trial.update(error=repr(exc),traceback=traceback.format_exc())
    trial['seconds']=time.time()-start;trials.append(trial);atomic_json(folder/'alternative_native_trials.json',trials);print(canonical_json(trial),flush=True)
