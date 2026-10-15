"""Real hole/contact control data, reconstructed through the same public interface."""
from pathlib import Path
import sys
import numpy as np
import trimesh
from scanbench.common import *
from scanbench.camera import trajectory
from scanbench.placements import candidates
from scanbench.scan import scene_for,raycast_frame,noise_for,observation_hash
from scanbench.reconstruct import reconstruct
from scanbench.validate import read_mesh,distance_scene

def run():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir
    from cadgenbench.common.mesh import tessellate_shape,validate_mesh
    import open3d as o3d
    folder=ROOT/'tests/artifacts/hole_contact_r4'; folder.mkdir(parents=True,exist_ok=True)
    box=BRepPrimAPI_MakeBox(gp_Pnt(-20,-20,-4),40,40,8).Shape()
    hole=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0,0,-6),gp_Dir(0,0,1)),5,12).Shape()
    cut=BRepAlgoAPI_Cut(box,hole).Shape(); ref=tessellate_shape(cut,.01,angular_deflection_rad=.12,parallel=False); validate_mesh(ref)
    planes=[{'type':'plane','normal':n,'face':i} for i,n in enumerate([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]])]
    p=candidates(ref.vertices,ref.triangles,[0,0,0],planes)['placements'][0]
    sc=config()['scan']; cams=trajectory(ref.vertices,p['T_table_from_object'],sc,512,0)[::4]
    sigma=float(np.clip(np.linalg.norm(np.ptp(ref.vertices,axis=0))*.0002,.01,.1)); scene=scene_for(ref.vertices,ref.triangles)
    frames=[]
    for c in cams:
        pixel,clean,stats=raycast_frame(scene,c,p['T_table_from_object'],75,p['epsilon_contact_mm'])
        noise=noise_for(pixel,stable_seed(sc['noise_algorithm'],'hole_control',20261014,0,c['mother_frame_id']),sigma)
        noisy=(clean+noise).astype(np.float32); h=observation_hash(pixel,noisy); path=folder/f'observations/{h}.npz'
        if not path.exists(): atomic_npz(path,pixel=pixel,range_mm=noisy)
        frames.append({'camera_id':c['id'],'path':f'observations/{h}.npz','file_sha256':file_hash(path)})
    atomic_json(folder/'observations.json',{'data_root_relative':'.','frames':frames})
    public={k:c[k] for k in []} if False else {'schema':'camera_v1','cameras':cams,'sigma_mm':sigma}
    atomic_json(folder/'cameras.json',public); atomic_json(folder/'reconstruction_config.json',config()['reconstruction'])
    out=folder/'result'; metrics=reconstruct(folder/'observations.json',folder/'cameras.json',config()['reconstruction'],out)
    mesh=read_mesh(out/'mesh.ply'); mscene=distance_scene(mesh)
    xy=np.array([[x,y] for x in np.linspace(-3,3,21) for y in np.linspace(-3,3,21) if x*x+y*y<9])
    rays=np.column_stack([xy,np.full(len(xy),-20.),np.zeros((len(xy),2)),np.ones(len(xy))]).astype(np.float32)
    hit=mscene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy(); hole_free=float(np.isinf(hit).mean())
    ring=np.array([[x,y] for x in np.linspace(-16,16,31) for y in np.linspace(-16,16,31) if x*x+y*y>9**2])
    rays2=np.column_stack([ring,np.full(len(ring),-20.),np.zeros((len(ring),2)),np.ones(len(ring))]).astype(np.float32)
    hit2=mscene.cast_rays(o3d.core.Tensor(rays2))['t_hit'].numpy(); ring_retained=float(np.isfinite(hit2).mean())
    # First pose may be upside down; test contact in table coordinates using transformed rays.
    T=np.asarray(p['T_table_from_object']); inv=np.linalg.inv(T)
    # The box is 8 mm thick in the selected broad-area support orientation.
    origins_table=np.column_stack([ring,np.full(len(ring),-20.)]); origins_object=transform(origins_table,inv)
    dirs=np.broadcast_to(inv[:3,:3]@np.array([0.,0,1.]),origins_object.shape)
    hit3=mscene.cast_rays(o3d.core.Tensor(np.column_stack([origins_object,dirs]).astype(np.float32)))['t_hit'].numpy()
    false_bottom=float((np.isfinite(hit3)&(hit3<22.)).mean())
    h=metrics['fusion']['h_mm']
    result={'hole_diameter_mm':10,'h_mm':h,'diameter_over_h':10/h,'axial_hole_free_fraction':hole_free,'solid_annulus_retained_fraction':ring_retained,
            'false_contact_closure_fraction':false_bottom,'support_transform':T,'method':'independent analytic cylinder-axis rays and annulus rays; all actual reconstructed faces',
            'pass':hole_free>=.99 and ring_retained>=.95 and false_bottom==0 and 10/h>=6,'metrics':metrics}
    atomic_json(ROOT/'reports/tests/hole_contact_mesh_r4.json',result)
    print(canonical_json({k:v for k,v in result.items() if k!='metrics'}))
    if not result['pass']: raise SystemExit(2)

if __name__=='__main__': run()
