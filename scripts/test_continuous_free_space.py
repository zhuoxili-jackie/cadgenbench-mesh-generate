"""Independent convex-optimization and actual-witness tests for the candidate veto."""
from pathlib import Path
import os,sys,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from continuous_free_space import clipped_min_range_squared,conflicts_in_camera,thresholds_from_range_image
from scipy.optimize import linprog,minimize
from scanbench.validate import read_mesh
from independent_cell_minimum import minimum_range

started=time.time();folder=ROOT/'reports/free_space_revision';folder.mkdir(exist_ok=True)
cam={'resolution':33,'K':[[100.,0.,16.],[0.,100.,16.],[0.,0.,1.]],'T_object_from_camera':np.eye(4).tolist()}
image=np.full((33,33),10.,np.float32);face=np.array([[0,1,2]],np.int64)
controls=[]
for name,tri,expected in [
    ('foreground_conflict',[[-.2,-.2,8],[.2,-.2,8],[0,.2,8]],True),
    ('on_observed_surface',[[-.2,-.2,10],[.2,-.2,10],[0,.2,10]],False),
    ('behind_surface',[[-.2,-.2,11],[.2,-.2,11],[0,.2,11]],False),
    ('outside_image',[[10,10,8],[11,10,8],[10,11,8]],False),
    ('camera_behind',[[-.2,-.2,-8],[.2,-.2,-8],[0,.2,-8]],False),
]:
    actual=bool(conflicts_in_camera(np.asarray(tri,float),face,image,cam,1.)[0][0]);assert actual==expected,(name,actual)
    controls.append({'name':name,'expected':expected,'actual':actual})
for name,img in [('all_missing',np.full_like(image,np.nan)),('only_center_valid',np.full_like(image,np.nan)),('unstable_patch',image.copy())]:
    if name=='only_center_valid':img[16,16]=10.
    if name=='unstable_patch':img[::2,::2]=15.
    actual=bool(conflicts_in_camera(np.array([[-.01,-.01,8],[.01,-.01,8],[0,.01,8]]),face,img,cam,1.)[0][0]);assert not actual,name
    controls.append({'name':name,'expected':False,'actual':actual})
box=clipped_min_range_squared(np.array([[-1.,-1.,8.],[1.,-1.,8.],[0.,1.,8.]]),-.005,.005,-.005,.005)
assert abs(box-64)<1e-12
corner_triangle=np.array([[0.,0.,10.],[1.,0.,11.],[0.,1.,11.]])
for name,cell in [('corner_only',[-.005,0.,-.005,0.]),('edge_only',[-.005,0.,0.,.05]),('near_zero_area',[-.005,1e-15,-.005,1e-15])]:
    value=float(clipped_min_range_squared(corner_triangle,*cell));assert abs(value-100)<1e-10,(name,value)
    controls.append({'name':name,'expected_min_range_squared_mm2':100.,'actual':value})
rng=np.random.default_rng(610243);comparisons=[]
for i in range(300):
    tri=np.column_stack((rng.uniform(-.35,.35,(3,2)),rng.uniform(7.,13.,3)))
    center=rng.uniform(-.03,.03,2);half=rng.uniform(.002,.02,2);xlo,xhi=center[0]+np.array([-1,1])*half[0];ylo,yhi=center[1]+np.array([-1,1])*half[1]
    planes=np.array([[1,0,-xlo],[-1,0,xhi],[0,1,-ylo],[0,-1,yhi]],float)
    constraints=planes@tri.T
    feasible=linprog(np.zeros(3),A_ub=-constraints,b_ub=np.zeros(4),A_eq=np.ones((1,3)),b_eq=[1.],bounds=[(0,None)]*3,method='highs')
    actual=float(clipped_min_range_squared(tri,xlo,xhi,ylo,yhi))
    if not feasible.success:
        assert np.isinf(actual),(i,actual);comparisons.append({'id':i,'feasible':False});continue
    matrix=tri@tri.T
    reference=minimize(lambda w:float(w@matrix@w),feasible.x,jac=lambda w:2*matrix@w,bounds=[(0,1)]*3,constraints=[{'type':'eq','fun':lambda w:np.sum(w)-1,'jac':lambda w:np.ones(3)},{'type':'ineq','fun':lambda w:constraints@w,'jac':lambda w:constraints}],method='SLSQP',options={'ftol':1e-12,'maxiter':300})
    w=reference.x
    assert abs(w.sum()-1)<1e-8 and np.min(constraints@w)>-1e-8 and np.min(w)>-1e-8,(i,reference.message)
    error=abs(actual-float(w@matrix@w));assert error<2e-6,(i,actual,reference.fun,reference.message)
    comparisons.append({'id':i,'feasible':True,'error_squared_mm':error,'solver_success':bool(reference.success)})
regression_folder=folder/'rejected_degenerate_polygon_audit/case_2438b1a3fd780c63'
regression=load_json(regression_folder/'independent_candidate_probe.json')
regression_out=ROOT/'data/cases/case_2438b1a3fd780c63/input';regression_mesh=read_mesh(regression_out/'mesh.ply')
regression_cams={c['id']:c for c in load_json(regression_out/'cameras.json')['cameras']};regression_refs=load_json(regression_out/'observations.json')['frames']
regression_errors=[]
for row in regression['rows']:
    assert row['feasible_point'] and not row['independent_conflict']
    cam=regression_cams[regression_refs[row['frame']]['camera_id']];T=np.asarray(cam['T_object_from_camera']);K=np.asarray(cam['K']);tri=(regression_mesh.triangles[row['face_id']]-T[:3,3])@T[:3,:3];x,y=row['pixel']
    actual=float(np.sqrt(clipped_min_range_squared(tri,(x-.5-K[0,2])/K[0,0],(x+.5-K[0,2])/K[0,0],(y-.5-K[1,2])/K[1,1],(y+.5-K[1,2])/K[1,1])))
    reference,_=minimum_range(tri,(x-.5-K[0,2])/K[0,0],(x+.5-K[0,2])/K[0,0],(y-.5-K[1,2])/K[1,1],(y+.5-K[1,2])/K[1,1])
    error=abs(actual-reference);assert error<1e-6,(row['face_id'],error,actual,reference)
    assert actual>=row['limit_mm'];regression_errors.append(error)
cid='case_b104fc2cd648b353';out=ROOT/f'data/cases/{cid}/input';witness=load_json(ROOT/f'reports/free_space_investigations/{cid}/witnesses.json')['witnesses'][0]
cam=next(c for c in load_json(out/'cameras.json')['cameras'] if c['id']==witness['camera_id'])
with np.load(ROOT/witness['observation_file']) as z:
    img=np.full(cam['resolution']**2,np.nan,np.float32);img[z['pixel']]=z['range_mm'];img=img.reshape(cam['resolution'],cam['resolution'])
tol=load_json(out/'reconstruction.json')['filtering']['support_tolerance_mm']
actual=conflicts_in_camera(np.asarray(witness['triangle_vertices_mm']),face,img,cam,tol)
assert actual[0][0]
mesh=read_mesh(out/'mesh.ply');begin=time.time();bad,pixels=conflicts_in_camera(mesh.vertices,mesh.faces,img,cam,tol);seconds=time.time()-begin
assert bad[witness['face_id']]
actual_positive_checks=[]
T=np.asarray(cam['T_object_from_camera']);K=np.asarray(cam['K'])
for fid in np.flatnonzero(bad):
    x,y=map(int,pixels[fid]);tri=(mesh.triangles[fid]-T[:3,3])@T[:3,:3]
    reference,weights=minimum_range(tri,(x-.5-K[0,2])/K[0,0],(x+.5-K[0,2])/K[0,0],(y-.5-K[1,2])/K[1,1],(y+.5-K[1,2])/K[1,1])
    patch=img[y-1:y+2,x-1:x+2];limit=max(float(patch.min())-tol,float(patch.min()-tol))
    assert reference<limit,(fid,reference,limit)
    actual_positive_checks.append({'face_id':int(fid),'pixel':[x,y],'independent_minimum_range_mm':reference,'limit_mm':limit,'margin_mm':limit-reference})
atomic_npz(folder/'actual_frame_benchmark.npz',face_ids=np.flatnonzero(bad),pixels=pixels[bad])
result={'status':'pass','analytic_controls':controls,'known_clipped_plane_range_squared_mm2':box,'independent_solver':'SciPy linprog feasibility and SLSQP convex quadratic minimization in barycentric weights; does not call the clipping implementation','random_convex_problems':len(comparisons),'max_error_squared_mm':max(x.get('error_squared_mm',0) for x in comparisons),'feasible_random_problems':sum(x['feasible'] for x in comparisons),'actual_regression':{'case_id':cid,'mesh_sha256':file_hash(out/'mesh.ply'),'camera_id':witness['camera_id'],'previous_lattice_missed_witness':True,'continuous_veto_detected_witness':True,'faces':len(mesh.faces),'conflicting_faces_in_actual_frame':int(bad.sum()),'seconds_one_full_frame':seconds,'artifact':'reports/free_space_revision/actual_frame_benchmark.npz','artifact_sha256':file_hash(folder/'actual_frame_benchmark.npz')},'module_sha256':file_hash(ROOT/'tools/continuous_free_space.py'),'test_script_sha256':file_hash(Path(__file__)),'no_gt_used':True,'formal_geometry_unchanged':True,'seconds':time.time()-started}
result['actual_degenerate_pixel_cell_regressions']={'cases':len(regression_errors),'max_distance_error_mm':max(regression_errors),'all_prior_false_conflicts_rejected':True,'independent_method':'fresh enumeration of every feasible 2D barycentric half-plane vertex, all connecting segments, and unconstrained quadratic minimum; no 3D clipping','independent_code_sha256':file_hash(ROOT/'scripts/independent_cell_minimum.py'),'initial_diagnostic':str((regression_folder/'independent_candidate_probe.json').relative_to(ROOT)).replace('\\','/'),'initial_diagnostic_sha256':file_hash(regression_folder/'independent_candidate_probe.json')}
result['actual_positive_independent_checks']=actual_positive_checks
atomic_json(folder/'controls_candidate.json',result);print(canonical_json(result))
