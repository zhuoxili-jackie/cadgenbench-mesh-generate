"""Public geometry conventions, also usable by an isolated reconstructor."""
import numpy as np

def look_at(eye,target):
    z=np.asarray(target)-np.asarray(eye); z=z/np.linalg.norm(z)
    up=np.array([0.,0,1.])
    if abs(np.dot(up,z))>.999: up=np.array([0.,1.,0.])
    x=np.cross(z,up); x/=np.linalg.norm(x)
    y=np.cross(z,x)
    T=np.eye(4); T[:3,:3]=np.stack([x,y,z],axis=1); T[:3,3]=eye
    return T

def pixel_directions(pixel,resolution,K):
    pixel=np.asarray(pixel,dtype=np.int64); u=pixel%resolution; v=pixel//resolution
    rays=np.stack([(u-K[0][2])/K[0][0],(v-K[1][2])/K[1][1],np.ones(len(pixel))],axis=1)
    return rays/np.linalg.norm(rays,axis=1,keepdims=True)

def backproject(pixel,ranges,camera):
    rays=pixel_directions(pixel,camera['resolution'],camera['K'])
    T=np.asarray(camera['T_object_from_camera'])
    return (rays*np.asarray(ranges)[:,None])@T[:3,:3].T+T[:3,3]

def project(points,camera):
    T=np.asarray(camera['T_object_from_camera']); p=(np.asarray(points)-T[:3,3])@T[:3,:3]
    K=np.asarray(camera['K']); uv=p[:,:2]/p[:,2,None]*[K[0,0],K[1,1]]+[K[0,2],K[1,2]]
    return uv,np.linalg.norm(p,axis=1),p[:,2]

def trajectory(vertices,T_table_from_object,scan,resolution,placement_id=0):
    T=np.asarray(T_table_from_object); v=np.asarray(vertices)@T[:3,:3].T+T[:3,3]
    lo=v.min(axis=0); hi=v.max(axis=0); c=(hi+lo)/2
    sphere=np.linalg.norm(hi-lo)/2
    fov=np.deg2rad(scan['fov_deg']); R=sphere/np.sin(fov/2)*scan['framing_margin']
    f=resolution/(2*np.tan(fov/2)); K=[[f,0,(resolution-1)/2],[0,f,(resolution-1)/2],[0,0,1]]
    inv=np.linalg.inv(T); cameras=[]
    corners=np.array([[x,y,z] for x in [lo[0],hi[0]] for y in [lo[1],hi[1]] for z in [lo[2],hi[2]]])
    for j in range(scan['intervals']+1):
        t=j/scan['intervals']; theta=2*np.pi*scan['turns']*t
        beta=np.deg2rad(scan['beta_top_deg']+(scan['beta_bottom_deg']-scan['beta_top_deg'])*t)
        eye=c+R*np.array([np.cos(beta)*np.cos(theta),np.cos(beta)*np.sin(theta),np.sin(beta)])
        TC=look_at(eye,c); OC=inv@TC
        pc=(corners-eye)@TC[:3,:3]; u=pc[:,:2]/pc[:,2,None]*f+(resolution-1)/2
        if u.min()<0 or u.max()>resolution-1: raise ValueError('bbox outside image')
        if eye[2]<=0 or R<=sphere: raise ValueError('camera inside object sphere or under table')
        cameras.append({'id':f'p{placement_id:02d}_f{j:04d}','placement_id':placement_id,'mother_frame_id':j,
                        'resolution':resolution,'K':K,'T_object_from_camera':OC.tolist(),'T_table_from_camera':TC.tolist(),
                        'theta_unwrapped_deg':float(np.rad2deg(theta)),'elevation_deg':float(np.rad2deg(beta)),
                        'near_mm':max(.001,R-sphere*1.05),'far_mm':R+sphere*1.05,
                        'camera_table_height_mm':float(eye[2]),'sphere_clearance_mm':float(R-sphere),
                        'bbox_pixel_min':u.min(axis=0).tolist(),'bbox_pixel_max':u.max(axis=0).tolist(),'target_table_mm':c.tolist()})
    return cameras
