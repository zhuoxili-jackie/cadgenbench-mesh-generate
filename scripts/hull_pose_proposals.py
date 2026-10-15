"""Finite convex-hull support proposals; no probability sampling or COM rejection loop."""
import numpy as np
from scipy.spatial import ConvexHull

def propose(vertices,center_mass):
    vertices=np.asarray(vertices,dtype=np.float64);com=np.asarray(center_mass,dtype=np.float64)
    hull=ConvexHull(vertices);tri=vertices[hull.simplices];normals=hull.equations[:,:3]
    halfspace=normals@com+hull.equations[:,3]
    if np.max(halfspace)>=0:raise ValueError('exact COM is not strictly within the independent SciPy convex hull')
    projected=com-halfspace[:,None]*normals
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);den=np.einsum('ij,ij->i',cross,cross)
    with np.errstate(divide='ignore',invalid='ignore'):
        bary=np.stack([np.einsum('ij,ij->i',np.cross(tri[:,(i+1)%3]-projected,tri[:,(i+2)%3]-projected),cross)/den for i in range(3)],axis=1)
    ids=np.flatnonzero(np.isfinite(bary).all(axis=1)&(bary.min(axis=1)>=-1e-8)&(bary.max(axis=1)<=1+1e-8))
    seen=[];transforms=[]
    for i in ids:
        n=normals[i]
        if any(np.dot(n,previous)>.999999 for previous in seen):continue
        seen.append(n.copy());z=-n;helper=np.array([1.,0,0]) if abs(z[0])<.8 else np.array([0.,1,0])
        x=np.cross(helper,z);x/=np.linalg.norm(x);y=np.cross(z,x)
        T=np.eye(4);T[:3,:3]=np.stack([x,y,z]);T[2,3]=-float((vertices@z).min());transforms.append(T)
    return np.array(transforms),{'method':'SciPy convex-hull facets with COM projection inside a facet; exact outward halfspaces; all distinct qualifying normals; no stochastic rejection or landing-probability cutoff','hull_facets':len(hull.simplices),'max_COM_halfspace_mm':float(halfspace.max()),'qualifying_facets':len(ids),'distinct_proposals':len(transforms),'nonfinite_barycentric_facets':int((~np.isfinite(bary).all(axis=1)).sum()),'proposal_barycentric_epsilon':1e-8}
