"""Independent 2D barycentric half-plane vertex enumeration, for tests only."""
import itertools
import numpy as np

def minimum_range(tri,xlo,xhi,ylo,yhi):
    planes=np.array([[1,0,-xlo],[-1,0,xhi],[0,1,-ylo],[0,-1,yhi]],float)
    values=planes@tri.T
    A=np.vstack([values[:,1:]-values[:,0,None],np.eye(2),[-1.,-1.]])
    b=np.concatenate([values[:,0],[0.,0.,1.]])
    scales=np.maximum(np.linalg.norm(A,axis=1),1e-15);A=A/scales[:,None];b=b/scales
    def feasible(w):return np.min(A@w+b)>=-1e-9
    vertices=[]
    for i,j in itertools.combinations(range(len(A)),2):
        mat=A[[i,j]]
        if abs(np.linalg.det(mat))<1e-14:continue
        w=np.linalg.solve(mat,-b[[i,j]])
        if feasible(w):vertices.append(w)
    if not vertices:return np.inf,None
    base=tri[0];edges=(tri[1:]-base).T;best=np.inf;winner=None
    def consider(w):
        nonlocal best,winner
        p=base+edges@w;value=float(np.linalg.norm(p))
        if value<best:best=value;winner=w
    for w in vertices:consider(w)
    for a,c in itertools.combinations(vertices,2):
        origin=base+edges@a;direction=edges@(c-a);den=direction@direction
        t=np.clip(-origin@direction/den,0.,1.) if den>0 else 0.
        consider(a+t*(c-a))
    gram=edges.T@edges
    if np.linalg.det(gram)>1e-30:
        free=np.linalg.solve(gram,-edges.T@base)
        if feasible(free):consider(free)
    return best,winner
