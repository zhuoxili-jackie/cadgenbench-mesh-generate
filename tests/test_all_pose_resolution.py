"""An oblique second pose must control resolution when its image scale is worse."""
import numpy as np
from scanbench.common import atomic_json,atomic_npz,load_json,config,ROOT
from scanbench import scan

def test_sampling_resolution_covers_every_pose(tmp_path,monkeypatch):
    cfg=config();v=np.array([[x,y,z] for x in [-10,10] for y in [-10,10] for z in [0,2]],float)
    r=np.array([[2**-.5,-2**-.5,0],[2**-.5,2**-.5,0],[0,0,1.]])
    a=np.eye(4);b=np.eye(4);b[:3,:3]=r
    # Independent bbox + pinhole calculation for this specific 45-degree box.
    far0=np.linalg.norm([20,20,2])/2*(cfg['scan']['framing_margin']/np.sin(np.pi/8)+1.05)
    f768=768/(2*np.tan(np.pi/8));feature=6*far0/f768*1.1
    gt=tmp_path/'private/gt/control';gt.mkdir(parents=True)
    atomic_npz(gt/'mesh.npz',vertices=v,faces=np.empty((0,3),int))
    atomic_json(gt/'metadata.json',{'diagonal_mm':float(np.linalg.norm([20,20,2])),'area_mm2':1000.})
    atomic_json(gt/'features.json',[{'type':'cylinder','radius_mm':feature/2,'area_mm2':100.,'u_range':[0,2*np.pi]}])
    atomic_json(gt/'placements.json',{'placements':[{'placement_id':0,'T_table_from_object':a},{'placement_id':1,'T_table_from_object':b}]})
    monkeypatch.setattr(scan,'ROOT',tmp_path)
    result=scan.prepare_cameras('control',None);contract=load_json(gt/'feature_contract.json')
    assert result['resolution']==1024
    actual=max(6*c['far_mm']/c['K'][0][0] for c in result['cameras'])
    assert abs(contract['resolvable_feature_mm']-actual)<1e-12 and actual<=feature
    atomic_json(ROOT/'reports/tests/all_pose_sampling_control.json',{'status':'pass','first_pose_alone_would_select':768,'actual_selected_resolution':result['resolution'],'all_pose_worst_six_intervals_mm':actual,'focus_size_mm':feature,'nonaxis_second_pose_controls_resolution':True})
