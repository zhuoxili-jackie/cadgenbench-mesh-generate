"""Read-only correspondence of failing STEP faces across isolated OCC versions."""
from pathlib import Path
import os, sys, argparse, importlib.metadata

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
p = argparse.ArgumentParser()
p.add_argument('source')
p.add_argument('--new-kernel', action='store_true')
args = p.parse_args()
if args.new_kernel:
    sys.path.insert(0, str(ROOT / 'tools/ocp79'))
sys.path.insert(0, str(ROOT / 'src'))
from scanbench.common import atomic_json, file_hash, canonical_json, REV
from scanbench.sources import read_step
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopExp import TopExp
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepCheck import BRepCheck_Analyzer, BRepCheck_NoError
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepAdaptor import BRepAdaptor_Surface

source = ROOT / f'sources/{args.source}/input.step'
shape, units = read_step(source)
all_shapes, faces = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
TopExp.MapShapes_s(shape, all_shapes)
TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
checker = BRepCheck_Analyzer(shape, True, False, False)
valid = checker.IsValid()
results = []
for i in range(1, faces.Size() + 1):
    face = TopoDS.Face_s(faces.FindKey(i))
    statuses = [str(s) for s in checker.Result(face).Status() if s != BRepCheck_NoError]
    if not statuses and i != 966:
        continue
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(face, box, False, False)
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    c = props.CentreOfMass()
    surface = BRepAdaptor_Surface(face)
    results.append({'face_index': i, 'global_subshape_index': all_shapes.FindIndex(face),
                    'own_status': statuses, 'surface_type': str(surface.GetType()),
                    'orientation': str(face.Orientation()), 'bounds_source_mm': list(box.Get()),
                    'area_mm2': props.Mass(), 'centroid_source_mm': [c.X(), c.Y(), c.Z()],
                    'uv_bounds': [surface.FirstUParameter(), surface.LastUParameter(),
                                  surface.FirstVParameter(), surface.LastVParameter()]})
report = {'source_id': args.source, 'source_sha256': file_hash(source), 'revision': REV,
          'binding_version': importlib.metadata.version('cadquery-ocp'), 'valid': bool(valid),
          'face_count': faces.Size(), 'faces': results, 'units': units,
          'method': 'Unique face map matches vendor tessellate_shape face numbering; no meshing or repair.',
          'source_or_topology_modifications': False, 'script_sha256': file_hash(Path(__file__))}
target = ROOT / f'reports/source_investigations/{args.source}/face_identity_{"new" if args.new_kernel else "production"}.json'
if target.exists():
    raise RuntimeError('Preserve existing evidence; choose a new report for any additional experiment.')
atomic_json(target, report)
print(canonical_json(report))
