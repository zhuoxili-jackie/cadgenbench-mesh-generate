"""Independently resolve an oversized OCC bounding box using exterior-plane distances."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import read_step,shape_metadata
from audit_reference_boundary import boundary,distance
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace,BRepBuilderAPI_Transform
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pln,gp_Pnt,gp_Dir,gp_Trsf

def measure(shape,coarse):
    coarse=np.asarray(coarse);center=coarse.mean(axis=0);span=float(np.linalg.norm(np.ptp(coarse,axis=0)));surface=boundary(shape);rows=[];bounds=np.zeros((2,3))
    assert span>0 and np.isfinite(coarse).all()
    for axis in range(3):
        for end,sign in enumerate([-1,1]):
            point=center.copy();point[axis]=coarse[end,axis]+sign*span;normal=np.zeros(3);normal[axis]=1
            plane=BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(*point),gp_Dir(*normal)),-2*span,2*span,-2*span,2*span).Face()
            query=BRepExtrema_DistShapeShape(surface,plane);query.Perform()
            assert query.IsDone() and not query.InnerSolution() and query.Value()>0
            value=float(point[axis]-sign*query.Value());bounds[end,axis]=value
            points=np.array([[query.PointOnShape1(i).X(),query.PointOnShape1(i).Y(),query.PointOnShape1(i).Z()] for i in range(1,query.NbSolution()+1)])
            witness_error=max(distance(p,surface)[0] for p in points)
            assert witness_error<=1e-6 and np.max(abs(points[:,axis]-value))<=1e-6
            rows.append({'axis':axis,'end':end,'plane_point_source_mm':point,'plane_half_extent_mm':2*span,'distance_mm':query.Value(),'extremum_mm':value,'witness_points_source_mm':points,'max_witness_boundary_distance_mm':witness_error})
    return bounds,rows

def main():
    sid=sys.argv[1];folder=ROOT/f'reports/source_investigations/{sid}';out=folder/'exact_axis_plane_bounds.json';assert not out.exists(),'Preserve the existing audit.'
    controls=[];shape=BRepPrimAPI_MakeBox(11.,17.,23.).Shape();corners=np.array([[x,y,z] for x in [0,11] for y in [0,17] for z in [0,23]],dtype=float)
    for angle in [0.,.37]:
        c,s=np.cos(angle),np.sin(angle);T=np.eye(4);T[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]];T[:3,3]=[4,-7,13]
        tr=gp_Trsf();tr.SetValues(*map(float,T[:3].ravel()));moved=BRepBuilderAPI_Transform(shape,tr,True).Shape();v=transform(corners,T);expected=np.stack([v.min(axis=0),v.max(axis=0)])
        actual,rows=measure(moved,expected+np.array([[-10]*3,[10]*3]));error=float(np.max(abs(actual-expected)));assert error<=1e-7
        controls.append({'rotation_z_radians':angle,'expected_bounds_mm':expected,'actual_bounds_mm':actual,'max_error_mm':error,'queries':rows})
    source=ROOT/f'sources/{sid}/input.step';shape,units=read_step(source);meta=shape_metadata(shape);assert meta['brep_valid']
    actual,rows=measure(shape,meta['bounds_source_mm'])
    report={'status':'pass','source_id':sid,'source_sha256':file_hash(source),'revision':REV,'units':units,'legacy_AddOptimal_bounds_source_mm':meta['bounds_source_mm'],'exact_bounds_source_mm':actual,'legacy_max_overestimate_mm':float(np.max(abs(actual-np.asarray(meta['bounds_source_mm'])))),'queries':rows,'controls':controls,'source_or_topology_modifications':False,'script_sha256':file_hash(Path(__file__)),'method':'Minimum distances from the compound of actual trimmed CAD boundary faces to six exterior planes. Plane rectangles enclose every projected coordinate of the conservative box; returned surface witness points are independently checked. No solid-interior shortcut.','documentation':'https://occt3d.com/dev/doc/refman/html/class_b_rep_extrema___dist_shape_shape.html'}
    atomic_json(out,report);print(canonical_json({k:v for k,v in report.items() if k not in ['queries','controls']}))

if __name__=='__main__':main()
