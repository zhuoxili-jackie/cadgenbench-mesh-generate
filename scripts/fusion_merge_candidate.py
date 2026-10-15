"""Isolated exact-semantics fusion optimization candidate; not production code."""
import numpy as np
from numba import njit

@njit(cache=True)
def merge_indices(a,b,aq,bq,af,bf,au,bu):
    result=np.empty(len(a)+len(b),np.int64);i=0;j=0;n=0
    while i<len(a) and j<len(b):
        compare=0
        for k in range(4):
            if a[i,k]<b[j,k]:compare=-1;break
            if a[i,k]>b[j,k]:compare=1;break
        if compare<0:result[n]=i;i+=1
        elif compare>0:result[n]=len(a)+j;j+=1
        else:
            take_b=bq[j]>aq[i] or (bq[j]==aq[i] and (bf[j]<af[i] or (bf[j]==af[i] and bu[j]<au[i])))
            result[n]=len(a)+j if take_b else i;i+=1;j+=1
        n+=1
    while i<len(a):result[n]=i;i+=1;n+=1
    while j<len(b):result[n]=len(a)+j;j+=1;n+=1
    return result[:n]

def fuse(frames,cameras,cfg):
    from scanbench.reconstruct import frame_points_normals,reduce_representatives,voxel_keys
    from scipy.spatial import cKDTree
    spacing=float(np.median([(c['near_mm']+c['far_mm'])/2/c['K'][0][0] for c in cameras.values()]))
    voxel=spacing*cfg['voxel_pixel_factor'];P=np.empty((0,3));N=P.copy();F=np.empty(0,np.int32);U=np.empty(0,np.uint32);Q=np.empty(0);K=np.empty((0,4),np.int64)
    raw_count=0;normal_count=0;frame_counts=[]
    for i,(cid,path) in enumerate(frames):
        with np.load(path) as d:pixel=d['pixel'];ranges=d['range_mm']
        p,n,u,q=frame_points_normals(pixel,ranges,cameras[cid]);raw_count+=len(pixel);normal_count+=len(p);f=np.full(len(p),i,np.int32)
        p,n,f,u,q=reduce_representatives(p,n,f,u,q,voxel);k=voxel_keys(p,n,voxel).view(np.int64).reshape(-1,4)
        ids=merge_indices(K,k,Q,q,F,f,U,u)
        P,N,F,U,Q,K=[np.concatenate([a,b])[ids] for a,b in [(P,p),(N,n),(F,f),(U,u),(Q,q),(K,k)]]
        frame_counts.append({'camera_id':cid,'valid_returns':len(pixel),'normal_returns':len(p)})
        if i%100==0:print(f'candidate fusion {i+1}/{len(frames)} working={len(P)}',flush=True)
    if len(P)<4:raise ValueError('insufficient observed points')
    tree=cKDTree(P);sample=np.linspace(0,len(P)-1,min(20000,len(P)),dtype=int)
    nearest=tree.query(P[sample],k=2,workers=2)[0][:,1];h=float(np.median(nearest))
    if not h>0:raise ValueError('zero working point spacing')
    return P,N,F,U,{'raw_returns':raw_count,'normal_returns':normal_count,'working_points':len(P),'voxel_mm':voxel,'h_mm':h,'h_method':'median NN on 20000 deterministic query points against full working cloud','frame_counts':frame_counts,'fusion':'actual observed representative in voxel and six oriented normal cones; best incidence; no point averaging'}
