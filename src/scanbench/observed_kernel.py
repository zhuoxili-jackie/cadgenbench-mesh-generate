"""Exact compiled equivalent of the public range-support test, not a new model."""
import os
os.environ.setdefault('NUMBA_NUM_THREADS','2')
import numpy as np
from numba import njit,prange

@njit(cache=True,parallel=True,fastmath=False)
def range_support(points,img,rotation,eye,fx,fy,cx,cy,tolerance):
    count=len(points); size=img.shape[0]; supported=np.zeros(count,np.bool_); conflict=np.zeros(count,np.bool_)
    for i in prange(count):
        dx=points[i,0]-eye[0]; dy=points[i,1]-eye[1]; dz=points[i,2]-eye[2]
        px=dx*rotation[0,0]+dy*rotation[1,0]+dz*rotation[2,0]
        py=dx*rotation[0,1]+dy*rotation[1,1]+dz*rotation[2,1]
        pz=dx*rotation[0,2]+dy*rotation[1,2]+dz*rotation[2,2]
        if pz<=0: continue
        xx=int(np.rint(px/pz*fx+cx)); yy=int(np.rint(py/pz*fy+cy))
        if xx<1 or xx>=size-1 or yy<1 or yy>=size-1: continue
        rr=img[yy,xx]; ran=np.sqrt(px*px+py*py+pz*pz)
        if not np.isfinite(rr): continue
        supported[i]=abs(rr-ran)<=tolerance
        # Patch minimum cannot exceed its finite centre value.
        if ran>=rr-tolerance: continue
        lo=np.inf; hi=-np.inf; allfinite=True
        for yoff in range(-1,2):
            for xoff in range(-1,2):
                val=img[yy+yoff,xx+xoff]
                if not np.isfinite(val): allfinite=False
                else:
                    lo=min(lo,val); hi=max(hi,val)
        conflict[i]=allfinite and (hi-lo<2*tolerance) and (ran<lo-tolerance)
    return supported,conflict
