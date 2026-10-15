"""Observation-only continuous triangle veto against stable foreground pixel cells.

Clip each candidate triangle to a nearest-pixel perspective cell. The exact
minimum Euclidean range over that convex polygon determines whether any part
violates the existing 3x3 foreground free-space threshold. No GT is used.
"""
import numpy as np
from scipy.ndimage import minimum_filter,maximum_filter
from numba import njit,prange

def thresholds_from_range_image(image,tolerance):
    finite=np.isfinite(image)
    low=minimum_filter(np.where(finite,image,np.float32(np.inf)),size=3,mode='constant',cval=np.inf)
    high=maximum_filter(np.where(finite,image,np.float32(-np.inf)),size=3,mode='constant',cval=-np.inf)
    complete=minimum_filter(finite.astype(np.uint8),size=3,mode='constant',cval=0).astype(bool)
    stable=complete&((high-low)<2*tolerance)
    # The independent NumPy validator subtracts in float32; the compiled lattice
    # subtracts in float64. Enforce both existing forms without loosening either.
    threshold=np.maximum(low.astype(np.float64)-tolerance,(low-tolerance).astype(np.float64))
    threshold[~stable]=-np.inf
    return threshold

@njit(cache=True)
def clipped_min_range_squared(triangle,xlo,xhi,ylo,yhi):
    a=np.empty((12,3),np.float64);b=np.empty((12,3),np.float64)
    for i in range(3):a[i]=triangle[i]
    count=3
    planes=np.array([[1.,0.,-xlo,0.],[-1.,0.,xhi,0.],[0.,1.,-ylo,0.],[0.,-1.,yhi,0.],[0.,0.,1.,-1e-12]])
    for plane in planes:
        newcount=0
        if count==0:return np.inf
        prev=a[count-1];dp=plane[0]*prev[0]+plane[1]*prev[1]+plane[2]*prev[2]+plane[3]
        for i in range(count):
            cur=a[i];dc=plane[0]*cur[0]+plane[1]*cur[1]+plane[2]*cur[2]+plane[3]
            if (dp>=0)!=(dc>=0):
                t=dp/(dp-dc)
                for j in range(3):b[newcount,j]=prev[j]+t*(cur[j]-prev[j])
                newcount+=1
            if dc>=0:
                b[newcount]=cur;newcount+=1
            prev=cur;dp=dc
        a,b=b,a;count=newcount
    if count==0:return np.inf
    best=np.inf
    for i in range(count):
        p=a[i];q=a[(i+1)%count];edge=q-p;den=np.dot(edge,edge)
        t=max(0.,min(1.,-np.dot(p,edge)/den)) if den>0 else 0.
        v=p+t*edge;best=min(best,np.dot(v,v))
    normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]);n2=np.dot(normal,normal)
    if n2>1e-30:
        projected=normal*(np.dot(normal,triangle[0])/n2)
        # Clipping may produce duplicate vertices or a zero-area corner/edge.
        # Test the plane projection against the ORIGINAL triangle and cell
        # inequalities; a degenerate clipped polygon cannot certify an interior.
        inside=(projected[2]>=1e-12 and projected[0]>=xlo*projected[2] and projected[0]<=xhi*projected[2] and projected[1]>=ylo*projected[2] and projected[1]<=yhi*projected[2])
        if inside:
            for i in range(3):
                edge=triangle[(i+1)%3]-triangle[i]
                if np.dot(np.cross(edge,projected-triangle[i]),normal)<-1e-12*n2:
                    inside=False;break
        if inside:best=min(best,np.dot(projected,projected))
    return best

@njit(cache=True,parallel=True,fastmath=False)
def conflicting_faces(camera_vertices,faces,threshold,fx,fy,cx,cy):
    count=len(faces);height,width=threshold.shape
    bad=np.zeros(count,np.bool_);pixels=np.full((count,2),-1,np.int32)
    for i in prange(count):
        p=camera_vertices[faces[i,0]];q=camera_vertices[faces[i,1]];r=camera_vertices[faces[i,2]]
        if max(p[2],q[2],r[2])<=0:continue
        if min(p[2],q[2],r[2])<=0:
            xmin=1;xmax=width-2;ymin=1;ymax=height-2
        else:
            u0=p[0]/p[2]*fx+cx;u1=q[0]/q[2]*fx+cx;u2=r[0]/r[2]*fx+cx
            v0=p[1]/p[2]*fy+cy;v1=q[1]/q[2]*fy+cy;v2=r[1]/r[2]*fy+cy
            xmin=max(1,int(np.ceil(min(u0,u1,u2)-.5)));xmax=min(width-2,int(np.floor(max(u0,u1,u2)+.5)))
            ymin=max(1,int(np.ceil(min(v0,v1,v2)-.5)));ymax=min(height-2,int(np.floor(max(v0,v1,v2)+.5)))
        if xmin>xmax or ymin>ymax:continue
        a=(p[0]+q[0]+r[0])/3.;b=(p[1]+q[1]+r[1])/3.;c=(p[2]+q[2]+r[2])/3.
        rp=(p[0]-a)**2+(p[1]-b)**2+(p[2]-c)**2
        rq=(q[0]-a)**2+(q[1]-b)**2+(q[2]-c)**2
        rr=(r[0]-a)**2+(r[1]-b)**2+(r[2]-c)**2
        lower=max(0.,np.sqrt(a*a+b*b+c*c)-np.sqrt(max(rp,rq,rr)))
        for y in range(ymin,ymax+1):
            if bad[i]:break
            for x in range(xmin,xmax+1):
                limit=threshold[y,x]
                if limit<=0 or lower>=limit:continue
                tri=np.empty((3,3),np.float64);tri[0]=p;tri[1]=q;tri[2]=r
                distance2=clipped_min_range_squared(tri,(x-.5-cx)/fx,(x+.5-cx)/fx,(y-.5-cy)/fy,(y+.5-cy)/fy)
                if distance2<limit*limit:
                    bad[i]=True;pixels[i,0]=x;pixels[i,1]=y;break
    return bad,pixels

def conflicts_in_camera(vertices,faces,image,camera,tolerance):
    T=np.asarray(camera['T_object_from_camera'],np.float64);K=np.asarray(camera['K'],np.float64)
    cv=np.ascontiguousarray((vertices-T[:3,3])@T[:3,:3])
    return conflicting_faces(cv,np.ascontiguousarray(faces,np.int64),thresholds_from_range_image(image,tolerance),K[0,0],K[1,1],K[0,2],K[1,2])
