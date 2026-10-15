"""Independent constrained minimization on actual flagged faces and camera pixels."""
from pathlib import Path
import os,sys,argparse
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.validate import read_mesh
from continuous_free_space import clipped_min_range_squared
from scipy.optimize import linprog,minimize

p=argparse.ArgumentParser();p.add_argument('case_id');args=p.parse_args();cid=args.case_id;out=ROOT/f'data/cases/{cid}/input'
folder=ROOT/f'reports/free_space_revision/current_mesh_audit/{cid}'
with np.load(folder/'conflicting_faces.npz') as z:ids=z['face_ids'];first=z['first_frame'];pixels=z['pixels']
rng=np.random.default_rng(610218);chosen=np.sort(rng.choice(len(ids),min(150,len(ids)),replace=False))
mesh=read_mesh(out/'mesh.ply');cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']};refs=load_json(out/'observations.json')['frames'];tol=load_json(out/'reconstruction.json')['filtering']['support_tolerance_mm'];rows=[]
for ordinal in np.unique(first[chosen]):
    fr=refs[int(ordinal)];cam=cams[fr['camera_id']];K=np.asarray(cam['K']);T=np.asarray(cam['T_object_from_camera']);res=cam['resolution']
    with np.load((out/fr['path']).resolve()) as z:
        img=np.full(res*res,np.nan,np.float32);img[z['pixel']]=z['range_mm'];img=img.reshape(res,res)
    for j in chosen[first[chosen]==ordinal]:
        tri=(mesh.triangles[ids[j]]-T[:3,3])@T[:3,:3];x,y=map(int,pixels[j]);xlo,xhi=(x+np.array([-.5,.5])-K[0,2])/K[0,0];ylo,yhi=(y+np.array([-.5,.5])-K[1,2])/K[1,1]
        planes=np.array([[1,0,-xlo],[-1,0,xhi],[0,1,-ylo],[0,-1,yhi]],float);constraint=planes@tri.T
        feasible=linprog(np.zeros(3),A_ub=-constraint,b_ub=np.zeros(4),A_eq=np.ones((1,3)),b_eq=[1.],bounds=[(0,None)]*3,method='highs')
        candidate=float(clipped_min_range_squared(tri,xlo,xhi,ylo,yhi));patch=img[y-1:y+2,x-1:x+2];limit=max(float(patch.min())-tol,float(patch.min()-tol))
        row={'face_id':int(ids[j]),'frame':int(ordinal),'pixel':[x,y],'candidate_range_mm':float(np.sqrt(candidate)),'limit_mm':limit,'feasible':bool(feasible.success)}
        if feasible.success:
            # Recenter the quadratic to avoid cancellation from large camera ranges.
            base=tri[0];edge=(tri[1:]-base).T;scale=max(float(np.linalg.norm(base)),1.)
            A=np.column_stack((constraint[:,1]-constraint[:,0],constraint[:,2]-constraint[:,0]));b=constraint[:,0]
            cons=[{'type':'ineq','fun':lambda w:A@w+b,'jac':lambda w:A},{'type':'ineq','fun':lambda w:1-w.sum(),'jac':lambda w:-np.ones(2)}]
            opt=minimize(lambda w:float(np.sum((base+edge@w)**2)/scale**2),feasible.x[1:],jac=lambda w:2*(edge.T@(base+edge@w))/scale**2,bounds=[(0,1)]*2,constraints=cons,method='SLSQP',options={'ftol':1e-15,'maxiter':500})
            point=base+edge@opt.x;actual=float(np.linalg.norm(point));feasible_point=bool(np.min(A@opt.x+b)>-1e-8 and opt.x.sum()<=1+1e-8 and opt.x.min()>=-1e-8)
            uv=point[:2]/point[2]*[K[0,0],K[1,1]]+[K[0,2],K[1,2]]
            row.update(reference_range_mm=actual,difference_mm=float(np.sqrt(candidate))-actual,independent_conflict=actual<limit,solver_success=bool(opt.success),feasible_point=feasible_point,actual_uv=uv.tolist(),barycentric=[float(1-opt.x.sum()),*opt.x.tolist()])
        rows.append(row)
result={'case_id':cid,'checked':len(rows),'infeasible':sum(not x['feasible'] for x in rows),'reference_nonconflicts':sum(x.get('independent_conflict') is False for x in rows),'max_absolute_difference_mm':max(abs(x.get('difference_mm',0)) for x in rows),'rows':rows}
atomic_json(folder/'independent_candidate_probe.json',result);print(canonical_json({k:v for k,v in result.items() if k!='rows'}));print(canonical_json(rows[:3]))
