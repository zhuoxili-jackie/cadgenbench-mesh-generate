"""Re-run a complete hard case from original STEP bytes in a fresh directory."""
from pathlib import Path
import os,sys,shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
os.environ.setdefault('OMP_NUM_THREADS','2');os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
from scanbench.common import *
from scanbench.sampling_density import source_scan_settings,noise_frame_key,case_sampling_contract,sampling_policy
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
assert sampling_policy()['protocol']=='physical_scan_v2_overlap_density'


def run(cid):
    from scanbench.sources import read_step,shape_metadata,analytic_features
    from scanbench.placements import candidates
    from scanbench.camera import trajectory
    from scanbench.scan import scene_for,raycast_frame,noise_for,observation_hash
    from scanbench.reconstruct import reconstruct
    from scanbench.validate import read_mesh,sorted_facets
    from cadgenbench.common.mesh import tessellate_shape,validate_mesh
    rec=load_json(ROOT/f'private/annotations/{cid}/case.json');sid=rec['source_id'];original=ROOT/rec['input_path'];cfg=config();scan_settings=source_scan_settings(sid)
    signature=digest([file_hash(original/'mesh.ply'),file_hash(original/'observations.json'),digest([file_hash(ROOT/'src/scanbench/reconstruct.py'),file_hash(ROOT/'src/scanbench/continuous_free_space.py')])]);code_hashes={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in (ROOT/'src/scanbench').glob('*.py')};policy_sha=file_hash(ROOT/'configs/sampling_density_v2.json');run_signature=digest([signature,code_hashes,policy_sha]);dest=ROOT/f'tests/artifacts/full_reproduction_sampling_v2_{run_signature[:12]}'
    report=ROOT/'reports/tests/full_case_reproduction_sampling_v2.json'
    if report.exists() and load_json(report).get('run_signature')==run_signature and load_json(report).get('status')=='pass':return
    if dest.exists():raise RuntimeError('existing incomplete reproduction must be inspected')
    dest.mkdir(parents=True);sim=dest/'simulator_reference';sim.mkdir();shutil.copy2(ROOT/f'sources/{sid}/input.step',sim/'input.step')
    assert file_hash(sim/'input.step')==rec['source_sha256']
    with measured() as perf:
        shape,units=read_step(sim/'input.step');meta=shape_metadata(shape);center=np.mean(meta['bounds_source_mm'],axis=0)
        mesh=tessellate_shape(shape,cfg['gt']['chord_mm'],angular_deflection_rad=cfg['gt']['angle_rad'],parallel=False);validate_mesh(mesh)
        vertices=mesh.vertices-center;features=analytic_features(shape,center)
        poses=candidates(vertices,mesh.triangles,np.asarray(meta['center_mass_source_mm'])-center,features)['placements']
        priorcam=load_json(original/'cameras.json')
        nplace=cfg['difficulty'][rec['level']]['placements'];stride=cfg['difficulty'][rec['level']]['stride']
        # Derive resolution, cameras and sigma from the newly imported STEP too.
        # No existing source tessellation, GT or placement file is copied.
        import trimesh
        from scanbench import scan as current_scan
        gt=dest/f'private/gt/{sid}';gt.mkdir(parents=True)
        native=trimesh.Trimesh(vertices,mesh.triangles,process=False)
        atomic_npz(gt/'mesh.npz',vertices=vertices,faces=mesh.triangles)
        atomic_json(gt/'metadata.json',{'diagonal_mm':float(np.linalg.norm(native.extents)),'area_mm2':float(native.area)})
        atomic_json(gt/'placements.json',{'placements':poses})
        atomic_json(gt/'features.json',features)
        previous_root=current_scan.ROOT
        try:
            current_scan.ROOT=dest
            fresh_camset=current_scan.prepare_cameras(sid,None)
        finally:current_scan.ROOT=previous_root
        assert fresh_camset['resolution']==priorcam['resolution'] and fresh_camset['sigma_mm']==priorcam['sigma_mm']
        newcams=[c for c in fresh_camset['cameras'] if c['placement_id']<nplace and c['mother_frame_id']%stride==0]
        assert len(newcams)==len(priorcam['cameras'])
        scene=scene_for(vertices,mesh.triangles);frames=[];originalobs=load_json(original/'observations.json')['frames'];out=dest/f'data/cases/{cid}/input';out.mkdir(parents=True)
        total=0;max_camera_error=0.
        for cam,prior,obs in zip(newcams,priorcam['cameras'],originalobs):
            np.testing.assert_allclose(cam['T_object_from_camera'],prior['T_object_from_camera'],atol=1e-10,rtol=0)
            max_camera_error=max(max_camera_error,float(np.max(abs(np.asarray(cam['T_object_from_camera'])-np.asarray(prior['T_object_from_camera'])))))
            pixel,clean,_=raycast_frame(scene,cam,poses[cam['placement_id']]['T_table_from_object'],cfg['scan']['incidence_deg'],poses[cam['placement_id']]['epsilon_contact_mm'])
            key=stable_seed(scan_settings['noise_algorithm'],sid,rec['seed'],cam['placement_id'],noise_frame_key(cam,scan_settings))
            noisy=(clean.astype(np.float64)+noise_for(pixel,key,priorcam['sigma_mm'])).astype(np.float32)
            with np.load((original/obs['path']).resolve()) as before:
                np.testing.assert_array_equal(pixel,before['pixel']);np.testing.assert_array_equal(noisy,before['range_mm'])
            total+=len(pixel);h=observation_hash(pixel,noisy);p=dest/f'data/observations/{h}.npz';atomic_npz(p,pixel=pixel,range_mm=noisy)
            frames.append({'camera_id':cam['id'],'path':f'../../../observations/{h}.npz','array_sha256':h,'file_sha256':file_hash(p),'count':len(pixel)})
        pubkeys=list(priorcam['cameras'][0]);cameraobj={**priorcam,'cameras':[{k:c[k] for k in pubkeys} for c in newcams]}
        atomic_json(out/'cameras.json',cameraobj);atomic_json(out/'observations.json',{'schema':'observations_v1','data_root_relative':'../../..','frames':frames})
        atomic_json(out/'reconstruction_config.json',cfg['reconstruction'])
        contract=case_sampling_contract(sid,rec['level'],min(nplace,len(poses)))
        assert contract==load_json(original/'sampling_contract.json')
        atomic_json(out/'sampling_contract.json',contract)
        shutil.copy2(original/'README.json',out/'README.json')
        assert not list(dest.rglob('mesh.ply')) and not list(dest.rglob('mesh.stl'))
        reconstruct(out/'observations.json',out/'cameras.json',cfg['reconstruction'],out)
        am=read_mesh(original/'mesh.ply');bm=read_mesh(out/'mesh.ply')
        a=sorted_facets(am);b=sorted_facets(bm);np.testing.assert_array_equal(a,b)
        tolerance=max(1e-6,1e-8*np.linalg.norm(np.ptp(vertices,axis=0)))
        np.testing.assert_allclose(am.vertices,bm.vertices,rtol=0,atol=tolerance);np.testing.assert_array_equal(am.faces,bm.faces)
        vertex_error=float(np.max(abs(am.vertices-bm.vertices)))
    atomic_json(report,{'status':'pass','signature':signature,'case_id':cid,'fresh_directory':str(dest.relative_to(ROOT)),
                'source_sha256':rec['source_sha256'],'step_import_tessellation_placement_scan_noise_reconstruction_reexecuted':True,
                'observed_pixels_compared':total,'float32_observations_array_equal':True,'camera_max_abs_error':max_camera_error,
                'geometry_triangle_coordinates_and_connectivity_exact':True,'indexed_connectivity_identical':True,'float64_vertex_max_error_mm':vertex_error,'declared_tolerance_mm':tolerance,'performance':perf,'run_signature':run_signature,'physical_protocol':sampling_policy()['protocol'],'sampling_policy_sha256':policy_sha,'current_code_sha256':code_hashes,'checker_script_sha256':file_hash(Path(__file__)),'resolution_and_sigma_independently_rederived':True,'only_original_STEP_copied_as_source_geometry':True,'sampling_contract_sha256':file_hash(out/'sampling_contract.json'),'fresh_source_step':str((sim/'input.step').relative_to(ROOT))})
    print('PASS current sampling-v2 complete same-seed STEP-to-mesh reproduction',flush=True)

if __name__=='__main__':
    import psutil,time
    while psutil.virtual_memory().available<2.5*2**30:
        print(canonical_json({'status':'waiting_for_profiled_memory_reserve','minimum_gib':2.5}),flush=True);time.sleep(5)
    # Earlier full same-case reproduction measured 0.677 GiB peak; 2.5 GiB
    # available leaves over 1.8 GiB for the active production worker and system.
    run(sys.argv[1] if len(sys.argv)>1 else 'case_2438b1a3fd780c63')
