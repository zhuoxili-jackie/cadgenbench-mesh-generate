"""Analytic geometry and exact topology-code checks for the optional strict OCC mesher."""
from pathlib import Path
import os,sys,ast,copy
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor'),str(ROOT/'tools/native_surface_control')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from native_surface_control_mesh import tessellate_shape,validate_mesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
import trimesh

FIELDS={'DeflectionInterior','AngleInterior','MinSize','AdjustMinSize','ForceFaceDeflection'}
def main():
    original=ROOT/'vendor/cadgenbench/common/mesh.py';override=ROOT/'tools/native_surface_control/native_surface_control_mesh.py'
    a=ast.parse(original.read_text(encoding='utf-8'));b=ast.parse(override.read_text(encoding='utf-8'));removed=[]
    class Strip(ast.NodeTransformer):
        def visit_Assign(self,node):
            if len(node.targets)==1:
                t=node.targets[0]
                if isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name) and t.value.id=='params' and t.attr in FIELDS:
                    removed.append(t.attr);return None
            return self.generic_visit(node)
    filtered=Strip().visit(copy.deepcopy(b));assert set(removed)==FIELDS and len(removed)==5 and ast.dump(a)==ast.dump(filtered)
    folder=ROOT/'tests/artifacts/native_surface_control';folder.mkdir(exist_ok=True);rows=[]
    for name,shape in [('box',BRepPrimAPI_MakeBox(11.,17.,23.).Shape()),('cylinder',BRepPrimAPI_MakeCylinder(10.,25.).Shape())]:
        m=tessellate_shape(shape,.01,angular_deflection_rad=.075,parallel=False);validate_mesh(m);mesh=trimesh.Trimesh(m.vertices,m.triangles,process=False);assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0
        points,ids=trimesh.sample.sample_surface(mesh,2048,seed=243)
        if name=='box':
            limits=np.array([11.,17.,23.]);d=np.min(np.minimum(abs(points),abs(points-limits)),axis=1);limit=1e-8;expected_volume=11*17*23
        else:
            radius=np.linalg.norm(points[:,:2],axis=1);height=points[:,2];inside=(radius<=10)&(height>=0)&(height<=25)
            outside=np.hypot(np.maximum(radius-10,0),np.maximum.reduce([-height,height-25,np.zeros(len(height))]));inner=np.minimum.reduce([10-radius,height,25-height]);d=np.where(inside,inner,outside);limit=.01;expected_volume=np.pi*10**2*25
        assert float(d.max())<=limit and abs(mesh.volume-expected_volume)<=.02*mesh.area
        path=folder/(name+'.npz');atomic_npz(path,vertices=m.vertices,faces=m.triangles,analytic_surface_samples=points,analytic_distances=d)
        rows.append({'name':name,'mesh_path':str(path.relative_to(ROOT)).replace('\\','/'),'mesh_sha256':file_hash(path),'vertices':len(m.vertices),'faces':len(m.triangles),'sample_count':len(points),'analytic_max_distance_mm':float(d.max()),'limit_mm':limit,'volume_mm3':float(mesh.volume),'analytic_volume_mm3':expected_volume,'watertight':bool(mesh.is_watertight)})
    result={'status':'pass','controls':rows,'only_five_mesher_parameters_changed_ast':True,'unchanged_original_topology_stitching_ast':True,'parameter_fields':sorted(FIELDS),'original_vendor_sha256':file_hash(original),'mesher_override_sha256':file_hash(override),'test_script_sha256':file_hash(Path(__file__)),'source_geometry_repair_performed':False}
    atomic_json(ROOT/'reports/tests/native_surface_control.json',result);print(canonical_json(result))

if __name__=='__main__':main()
