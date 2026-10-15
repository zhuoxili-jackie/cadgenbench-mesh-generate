from pathlib import Path
import numpy as np
import pytest
import trimesh
from scanbench.common import ROOT,atomic_json,config,transform,stable_seed
from scanbench.camera import trajectory,pixel_directions,backproject,project,look_at
from scanbench.placements import candidates
from scanbench.scan import scene_for,raycast_frame,noise_for

def evidence(name,obj): atomic_json(ROOT/f'reports/tests/{name}.json',{'status':'pass',**obj})

def control_box():
    mesh=trimesh.creation.box([20.,30.,10.])
    planes=[{'type':'plane','normal':n,'face':i} for i,n in enumerate([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]])]
    poses=candidates(mesh.vertices,mesh.faces,[0,0,0],planes)
    return mesh,poses['placements']

def test_step_units_and_serialized_scale():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_Writer,STEPControl_AsIs
    from OCP.Interface import Interface_Static
    from scanbench.sources import read_step,shape_metadata
    folder=ROOT/'tests/artifacts/units'; folder.mkdir(parents=True,exist_ok=True)
    results=[]
    for unit in ['MM','M']:
        writer=STEPControl_Writer(); Interface_Static.SetCVal_s('write.step.unit',unit)
        # The fixture writer emits these numeric coordinates in its declared unit.
        scale=1 if unit=='MM' else .001
        writer.Transfer(BRepPrimAPI_MakeBox(20*scale,30*scale,10*scale).Shape(),STEPControl_AsIs)
        path=folder/f'box_{unit}.step'; writer.Write(str(path.relative_to(ROOT)))
        shape,units=read_step(path); meta=shape_metadata(shape)
        dims=np.diff(meta['bounds_source_mm'],axis=0)[0]
        np.testing.assert_allclose(dims,[20,30,10],atol=1e-7)
        results.append({'declared_output_unit':unit,'read_units':units,'dimensions_mm':dims})
    assert results[0]['read_units']['source_length_units']!=results[1]['read_units']['source_length_units']
    box,_=control_box()
    for ext in ['ply','stl']:
        path=folder/f'box.{ext}'; box.export(path)
        back=trimesh.load(path,process=False); np.testing.assert_allclose(back.extents,[20,30,10],atol=1e-6)
    Interface_Static.SetCVal_s('write.step.unit','MM')
    evidence('units_scale',{'measurements':results,'file_roundtrip':['PLY','STL']})

def test_analytic_range_and_projection():
    import open3d as o3d
    v=np.array([[-100,-100,7],[100,-100,7],[100,100,7],[-100,100,7]])
    scene=scene_for(v,[[0,1,2],[0,2,3]])
    rays=np.array([[0,0,0,.3,.4,np.sqrt(.75)],[0,0,1,.6,0,.8]],np.float32)
    measured=scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy()
    analytical=(7-rays[:,2])/rays[:,5]
    np.testing.assert_allclose(measured,analytical,rtol=2e-7)
    assert np.max(np.abs(measured-(7-rays[:,2])))>1
    box,poses=control_box(); cam=trajectory(box.vertices,poses[0]['T_table_from_object'],config()['scan'],128)[43]
    pix=np.array([0,91,128*55+72,128**2-1]); ran=np.array([20.,30.,40.,25.])
    p=backproject(pix,ran,cam); uv,r,z=project(p,cam)
    np.testing.assert_allclose(uv,np.stack([pix%128,pix//128],axis=1),atol=1e-10)
    np.testing.assert_allclose(r,ran,atol=1e-10)
    evidence('range_projection',{'ray_ranges_mm':measured,'analytic_mm':analytical,'roundtrip_pixel_error':float(np.max(abs(uv-np.stack([pix%128,pix//128],1))))})

def test_contact_flip_full_path():
    box,poses=control_box(); scene=scene_for(box.vertices,box.faces); sc=config()['scan']
    observed=[]; bottom=np.asarray(poses[0]['support_outward_object']); support=float(np.max(box.vertices@bottom))
    sidecounts=np.zeros(6,int); total=0
    for pid,pose in enumerate(poses[:2]):
        points=[]; cameras=trajectory(box.vertices,pose['T_table_from_object'],sc,128,pid)[::4]
        angles=np.array([c['theta_unwrapped_deg'] for c in cameras])
        np.testing.assert_allclose(np.diff(angles),22.5,atol=1e-10)
        assert abs(angles[-1]-angles[0]-1080)<1e-10
        for turn in range(3):
            aa=angles[(angles>=turn*360)&(angles<(turn+1)*360)]%360
            assert len(np.unique((aa//45).astype(int)))==8
        for cam in cameras:
            pix,ran,_=raycast_frame(scene,cam,pose['T_table_from_object'],75,pose['epsilon_contact_mm'])
            p=backproject(pix,ran,cam); table=transform(p,pose['T_table_from_object'])
            assert table[:,2].min()>-1e-5
            # A box's analytic boundary distinguishes object returns from tabletop points.
            on_box=np.min(np.abs(np.abs(p)-[10,15,5]),axis=1)
            assert np.max(on_box)<1e-4
            points.append(p)
        points=np.concatenate(points); observed.append(points)
    oldbottom0=np.count_nonzero(abs(observed[0]@bottom-support)<1e-4)
    oldbottom1=np.count_nonzero(abs(observed[1]@bottom-support)<1e-4)
    assert oldbottom0==0 and oldbottom1>100
    # Four vertical faces and top face are observed with complete azimuths.
    normal_axes=np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]])
    for i,n in enumerate(normal_axes): sidecounts[i]=np.count_nonzero(abs(observed[0]@n-np.max(box.vertices@n))<1e-4)
    assert (sidecounts>100).sum()==5
    evidence('contact_flip_path',{'bottom_before':oldbottom0,'bottom_after':oldbottom1,'surface_counts':sidecounts,'hard_camera_count':49,'turns':3})

def test_transform_ray_equivalence():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.gp import gp_Pnt
    from cadgenbench.common.mesh import tessellate_shape
    body=BRepPrimAPI_MakeBox(gp_Pnt(-6.5,-13.5,-4.5),13,27,9).Shape()
    notch=BRepPrimAPI_MakeBox(gp_Pnt(0,0,0),8,16,6).Shape()
    asymmetric=BRepAlgoAPI_Cut(body,notch).Shape();m=tessellate_shape(asymmetric,.02,angular_deflection_rad=.15,parallel=False)
    mesh=trimesh.Trimesh(m.vertices,m.triangles,process=False); mesh.apply_translation([3,-4,2])
    R=trimesh.transformations.rotation_matrix(.73,[1,2,-.5]); R[:3,3]=[1,2,20]
    mesh2=mesh.copy(); mesh2.apply_transform(R)
    sc=config()['scan']; cam=trajectory(mesh.vertices,R,sc,96)[77]
    scene1=scene_for(mesh.vertices,mesh.faces); scene2=scene_for(mesh2.vertices,mesh2.faces)
    a,b,_=raycast_frame(scene1,cam,R)
    cam2={**cam,'T_object_from_camera':cam['T_table_from_camera']}
    c,d,_=raycast_frame(scene2,cam2,np.eye(4))
    np.testing.assert_array_equal(a,c); np.testing.assert_allclose(b,d,atol=2e-5,rtol=1e-6)
    p=backproject(a,b,cam); world=transform(p,R)
    np.testing.assert_allclose(transform(world,np.linalg.inv(R)),p,atol=1e-12)
    evidence('transform_equivalence',{'paired_rays':len(a),'range_max_error_mm':float(np.max(abs(b-d)))})

def test_keyed_noise_statistics():
    pixels=np.arange(200000,dtype=np.uint32); key=stable_seed('splitmix64_box_muller_v1','control',20261014,1,72); sigma=.037
    clean=np.linspace(50,150,len(pixels)).astype(np.float32)
    noisy=(clean.astype(float)+noise_for(pixels,key,sigma)).astype(np.float32); delta=noisy-clean
    assert abs(np.mean(delta))<.05*sigma
    assert .9<np.std(delta)/sigma<1.1
    assert np.max(abs(delta))<=3*sigma+1e-5
    np.testing.assert_array_equal(noise_for(pixels[::5],key,sigma),noise_for(pixels,key,sigma)[::5])
    second=noise_for(pixels,stable_seed('splitmix64_box_muller_v1','control',20261015,1,72),sigma)
    assert not np.array_equal(second,delta)
    evidence('noise',{'n':len(delta),'sigma_mm':sigma,'mean_mm':float(np.mean(delta)),'std_mm':float(np.std(delta)),'max_abs_mm':float(np.max(abs(delta))),'schedule_independent':True})
