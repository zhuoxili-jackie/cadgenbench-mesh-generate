import numpy as np
from scanbench.common import ROOT,load_json,atomic_json,digest,file_hash

def test_seed_changes_ranges_not_cameras_and_frames_are_shared():
    source='218';index=load_json(ROOT/f'private/scan_index/{source}/index.json')['frames'];count=0;different=0
    for frame in index[::23]:
        a=frame['seeds']['20261014'];b=frame['seeds']['20261015'];assert a['array_sha256']!=b['array_sha256']
        with np.load(ROOT/'data'/a['observation']) as aa,np.load(ROOT/'data'/b['observation']) as bb:
            np.testing.assert_array_equal(aa['pixel'],bb['pixel']);count+=len(aa['pixel']);different+=int(np.count_nonzero(aa['range_mm']!=bb['range_mm']))
    assert different>count*.99
    caseids=['case_2438b1a3fd780c63','case_464615fa87a6774b','case_3000584756354796']
    frames=[{f['camera_id']:f for f in load_json(ROOT/f'data/cases/{cid}/input/observations.json')['frames']} for cid in caseids]
    assert set(frames[0])<=set(frames[1])<=set(frames[2])
    for i in range(2):
        for key,value in frames[i].items():assert value==frames[i+1][key]
    cameras=[{c['id']:c for c in load_json(ROOT/f'data/cases/{cid}/input/cameras.json')['cameras']} for cid in caseids]
    for key,value in cameras[0].items():assert value==cameras[1][key]==cameras[2][key]
    second='case_'+digest(['physical_scan_v1','218','hard',20261015])[:16]
    first=ROOT/f'data/cases/{caseids[0]}/input';other=ROOT/f'data/cases/{second}/input'
    assert file_hash(first/'cameras.json')==file_hash(other/'cameras.json')
    assert file_hash(first/'mesh.ply')!=file_hash(other/'mesh.ply')
    atomic_json(ROOT/'reports/tests/shared_frames_and_seeds.json',{'status':'pass','paired_pixels':count,'different_ranges':different,'difference_fraction':different/count,'same_seed_common_frames_identical':True,'cameras_identical_across_difficulties':True,'cameras_identical_across_seeds':True,'second_seed_mesh_not_a_copy':True,'geometric_case_frame_sets_nested':True})
