"""Re-run a complete hard case from original STEP bytes in a fresh directory."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
os.environ.setdefault('OMP_NUM_THREADS','2');os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
from scanbench.common import *

def run(cid):
    from scanbench.sources import read_step,shape_metadata,analytic_features
    from scanbench.placements import candidates
    from scanbench.camera import trajectory
    from scanbench.scan import scene_for,raycast_frame,noise_for,observation_hash
    from scanbench.reconstruct import reconstruct
    from scanbench.validate import read_mesh,sorted_facets
    from cadgenbench.common.mesh import tessellate_shape,validate_mesh
    rec=load_json(ROOT/f'private/annotations/{cid}/case.json');sid=rec['source_id'];original=ROOT/rec['input_path'];cfg=config()
    signature=digest([file_hash(original/'mesh.ply'),file_hash(original/'observations.json'),digest([file_hash(ROOT/'src/scanbench/reconstruct.py'),file_hash(ROOT/'src/scanbench/continuous_free_space.py')])]);dest=ROOT/f'tests/artifacts/full_reproduction_{signature[:12]}'
    report=ROOT/'reports/tests/full_case_reproduction_r4.json'
    if report.exists() and load_json(report).get('signature')==signature and load_json(report).get('status')=='pass':return
    if dest.exists():raise RuntimeError('existing incomplete reproduction must be inspected')
    dest.mkdir(parents=True);sim=dest/'simulator_reference';sim.mkdir();shutil.copy2(ROOT/f'sources/{sid}/input.step',sim/'input.step')
    assert file_hash(sim/'input.step')==rec['source_sha256']
    with measured() as perf:
        shape,units=read_step(sim/'input.step');meta=shape_metadata(shape);center=np.mean(meta['bounds_source_mm'],axis=0)
        mesh=tessellate_shape(shape,cfg['gt']['chord_mm'],angular_deflection_rad=cfg['gt']['angle_rad'],parallel=False);validate_mesh(mesh)
        vertices=mesh.vertices-center;features=analytic_features(shape,center)
        poses=candidates(vertices,mesh.triangles,np.asarray(meta['center_mass_source_mm'])-center,features)['placements']
        priorcam=load_json(original/'cameras.json');newcams=[]
        nplace=cfg['difficulty'][rec['level']]['placements'];stride=cfg['difficulty'][rec['level']]['stride']
        for pid,pose in enumerate(poses[:nplace]):newcams.extend(trajectory(vertices,pose['T_table_from_object'],cfg['scan'],priorcam['resolution'],pid)[::stride])
        assert len(newcams)==len(priorcam['cameras'])
        scene=scene_for(vertices,mesh.triangles);frames=[];originalobs=load_json(original/'observations.json')['frames'];out=dest/f'data/cases/{cid}/input';out.mkdir(parents=True)
        total=0;max_camera_error=0.
        for cam,prior,obs in zip(newcams,priorcam['cameras'],originalobs):
            np.testing.assert_allclose(cam['T_object_from_camera'],prior['T_object_from_camera'],atol=1e-10,rtol=0)
            max_camera_error=max(max_camera_error,float(np.max(abs(np.asarray(cam['T_object_from_camera'])-np.asarray(prior['T_object_from_camera'])))))
            pixel,clean,_=raycast_frame(scene,cam,poses[cam['placement_id']]['T_table_from_object'],cfg['scan']['incidence_deg'],poses[cam['placement_id']]['epsilon_contact_mm'])
            key=stable_seed(cfg['scan']['noise_algorithm'],sid,rec['seed'],cam['placement_id'],cam['mother_frame_id'])
            noisy=(clean.astype(np.float64)+noise_for(pixel,key,priorcam['sigma_mm'])).astype(np.float32)
            with np.load((original/obs['path']).resolve()) as before:
                np.testing.assert_array_equal(pixel,before['pixel']);np.testing.assert_array_equal(noisy,before['range_mm'])
            total+=len(pixel);h=observation_hash(pixel,noisy);p=dest/f'data/observations/{h}.npz';atomic_npz(p,pixel=pixel,range_mm=noisy)
            frames.append({'camera_id':cam['id'],'path':f'../../../observations/{h}.npz','array_sha256':h,'file_sha256':file_hash(p),'count':len(pixel)})
        pubkeys=list(priorcam['cameras'][0]);cameraobj={**priorcam,'cameras':[{k:c[k] for k in pubkeys} for c in newcams]}
        atomic_json(out/'cameras.json',cameraobj);atomic_json(out/'observations.json',{'schema':'observations_v1','data_root_relative':'../../..','frames':frames})
        atomic_json(out/'reconstruction_config.json',cfg['reconstruction'])
        reconstruct(out/'observations.json',out/'cameras.json',cfg['reconstruction'],out)
        am=read_mesh(original/'mesh.ply');bm=read_mesh(out/'mesh.ply')
        a=sorted_facets(am);b=sorted_facets(bm);np.testing.assert_array_equal(a,b)
        tolerance=max(1e-6,1e-8*np.linalg.norm(np.ptp(vertices,axis=0)))
        np.testing.assert_allclose(am.vertices,bm.vertices,rtol=0,atol=tolerance);np.testing.assert_array_equal(am.faces,bm.faces)
        vertex_error=float(np.max(abs(am.vertices-bm.vertices)))
    atomic_json(report,{'status':'pass','signature':signature,'case_id':cid,'fresh_directory':str(dest.relative_to(ROOT)),
                'source_sha256':rec['source_sha256'],'step_import_tessellation_placement_scan_noise_reconstruction_reexecuted':True,
                'observed_pixels_compared':total,'float32_observations_array_equal':True,'camera_max_abs_error':max_camera_error,
                'geometry_triangle_coordinates_and_connectivity_exact':True,'indexed_connectivity_identical':True,'float64_vertex_max_error_mm':vertex_error,'declared_tolerance_mm':tolerance,'performance':perf})
    print('PASS complete same-seed STEP-to-mesh reproduction',flush=True)

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else 'case_2438b1a3fd780c63')
