"""Retain native parameter/accuracy trials without publishing eligibility."""
from pathlib import Path
import os,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import read_step,shape_metadata,brep_distance_check
from cadgenbench.common.mesh import tessellate_shape,validate_mesh
from OCP.BRepTools import BRepTools

sid=sys.argv[1];folder=ROOT/f'reports/source_investigations/{sid}';folder.mkdir(parents=True,exist_ok=True)
shape,units=read_step(ROOT/f'sources/{sid}/input.step');meta=shape_metadata(shape);center=np.mean(meta['bounds_source_mm'],axis=0);rows=[]
atomic_json(folder/'step_check.json',{'source_sha256':file_hash(ROOT/f'sources/{sid}/input.step'),'units':units,'shape':meta})
for chord,angle in [(0.02,0.15),(0.01,0.075),(0.02,0.3)]:
    row={'chord_mm':chord,'angle_rad':angle}
    try:
        with measured() as perf:
            BRepTools.Clean_s(shape);mesh=tessellate_shape(shape,chord,angular_deflection_rad=angle,parallel=False);validate_mesh(mesh)
            vertices=mesh.vertices-center;faces=mesh.triangles;path=folder/f'native_{chord}_{angle}.npz';atomic_npz(path,vertices=vertices,faces=faces)
            accuracy=brep_distance_check(shape,vertices,faces,center);limit=max(.021,chord*1.1)
        row.update(status='pass' if accuracy['max_sampled_mm']<=limit else 'accuracy_failed',vertices=len(vertices),faces=len(faces),accuracy=accuracy,acceptance_limit_mm=limit,mesh_path=str(path.relative_to(ROOT)).replace('\\','/'),mesh_sha256=file_hash(path),performance=perf)
    except Exception as e:row.update(status='error',exception=repr(e),traceback=traceback.format_exc())
    rows.append(row);atomic_json(folder/'native_accuracy_trials.json',{'source_id':sid,'source_sha256':file_hash(ROOT/f'sources/{sid}/input.step'),'trials':rows});print(canonical_json(row),flush=True)
    if row['status']=='pass':break
