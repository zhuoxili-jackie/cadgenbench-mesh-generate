"""First real return in each fixed voxel, exactly matching repeated stable union."""
import numpy as np

class FirstReturnGrid:
    def __init__(self,voxel):
        self.voxel=voxel;self.seen=set();self.blocks=[]
    def add(self,points):
        if not len(points):return
        keys=np.floor(points/self.voxel).astype(np.int32)
        unique,index=np.unique(keys,axis=0,return_index=True)
        raw=np.ascontiguousarray(unique,dtype='<i4').tobytes();selected=[]
        for j in range(len(unique)):
            token=raw[j*12:j*12+12]
            if token not in self.seen:self.seen.add(token);selected.append(j)
        if selected:self.blocks.append(np.array(points[index[selected]],copy=True))
    def result(self):
        if not self.blocks:return np.empty((0,3),np.float64)
        points=np.concatenate(self.blocks);keys=np.floor(points/self.voxel).astype(np.int32)
        order=np.lexsort((keys[:,2],keys[:,1],keys[:,0]));return points[order]
