"""Independent reference-to-CAD boundary distances, including inward deviations."""
from pathlib import Path
import os,sys,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import read_step
import trimesh
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound
from OCP.TopExp import TopExp
from OCP.TopAbs import TopAbs_FACE
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt

def boundary(shape):
    b=BRep_Builder();out=TopoDS_Compound();b.MakeCompound(out);faces=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape,TopAbs_FACE,faces)
    for i in range(1,faces.Size()+1):b.Add(out,faces.FindKey(i))
    return out
def distance(point,shape):
    d=BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float,point))).Vertex(),shape);d.Perform();assert d.IsDone()
    return float(d.Value()),bool(d.InnerSolution())

def main():
    box=BRepPrimAPI_MakeBox(10,10,10).Shape();shell=boundary(box);controls=[]
    for p,expected in [([5,5,5],5.),([0,5,5],0.),([-.1,5,5],.1)]:
        solid,inside=distance(p,box);surface,inner=distance(p,shell);assert abs(surface-expected)<1e-8 and not inner
        controls.append({'point_mm':p,'solid_distance_mm':solid,'solid_inner_solution':inside,'boundary_distance_mm':surface,'expected_boundary_distance_mm':expected})
    folder=ROOT/'reports/source_boundary_audits';folder.mkdir(parents=True,exist_ok=True)
    atomic_json(folder/'box_control.json',{'status':'pass','controls':controls,'script_sha256':file_hash(Path(__file__))})
    for sid in sys.argv[1:] or ['201','203','204','218','229','231']:
        gt=ROOT/f'private/gt/{sid}';meta=load_json(gt/'metadata.json');key=digest([file_hash(gt/'mesh.npz'),meta['source_sha256'],file_hash(Path(__file__))]);path=folder/f'{sid}.json'
        if path.exists() and load_json(path).get('key')==key:print(sid,'verified audit reused',flush=True);continue
        started=time.time();shape,_=read_step(ROOT/f'sources/{sid}/input.step');surface=boundary(shape)
        with np.load(gt/'mesh.npz') as raw:mesh=trimesh.Trimesh(raw['vertices'],raw['faces'],process=False)
        points,faces=trimesh.sample.sample_surface(mesh,128,seed=1234);source_points=transform(points,meta['T_source_mm_from_object']);values=[];legacy=[];inside=[]
        for p in source_points:
            d,inner=distance(p,surface);assert not inner;values.append(d);old,is_inside=distance(p,shape);legacy.append(old);inside.append(is_inside)
        limit=max(.021,meta['chord_mm']*1.1);result={'status':'pass' if max(values)<=limit else 'reference_precision_requires_investigation','source_id':sid,'source_sha256':meta['source_sha256'],'reference_sha256':file_hash(gt/'mesh.npz'),'reference_tier':meta['status'],'key':key,'method':'128 identical fixed area-distributed mesh samples; exact OCCT distance to a compound of all CAD boundary faces, with no SOLID interior-zero shortcut','unit':'mm','not_exact_hausdorff':True,'n':128,'sampled_max_mm':max(values),'p95_mm':float(np.quantile(values,.95)),'native_or_approx_bound_mm':limit,'legacy_solid_distance_max_mm':max(legacy),'legacy_inside_zero_samples':sum(inside),'boundary_distances_mm':values,'legacy_solid_distances_mm':legacy,'sample_points_source_mm':source_points,'script_sha256':file_hash(Path(__file__)),'seconds':time.time()-started}
        atomic_json(path,result);print(canonical_json({k:v for k,v in result.items() if k not in ['boundary_distances_mm','legacy_solid_distances_mm','sample_points_source_mm']}),flush=True)
if __name__=='__main__':main()
