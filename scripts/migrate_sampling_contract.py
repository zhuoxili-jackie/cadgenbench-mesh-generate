"""Re-key already verified observations only when all camera bytes are unchanged.

The archived/current scanner must differ solely in prepare_cameras. No cast,
noise or observation-storage function may differ. Every prior output is checked.
"""
from pathlib import Path
import ast,os,sys,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *
from scanbench.scan import prepare_cameras

old=ROOT/'reports/pilot_comparison/scan_before_all_pose_resolution.py';new=ROOT/'src/scanbench/scan.py'
def without_camera_builder(path):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    tree.body=[n for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name!='prepare_cameras']
    return ast.dump(tree,include_attributes=False)
assert without_camera_builder(old)==without_camera_builder(new),'Acquisition logic differs; no reuse is allowed'
assert file_hash(old)!=file_hash(new),'Apply the all-placement sampling fix before migration'
state=State();cfg=config();camera_hash=file_hash(ROOT/'src/scanbench/camera.py');old_hash=file_hash(old);results=[]
def legacy_key(inputs):
    return digest({'inputs':inputs,'settings':cfg['scan'],'code':{'camera.py':camera_hash,'scan.py':old_hash},'environment':{p:importlib.metadata.version(p) for p in ['numpy','open3d']}})

for sid in ['218','231','229']:
    gt=ROOT/f'private/gt/{sid}';paths=[gt/'cameras.json',gt/'feature_contract.json'];before={str(p):[file_hash(p),p.stat().st_mtime_ns] for p in paths}
    prepare_cameras(sid,state)
    after={str(p):[file_hash(p),p.stat().st_mtime_ns] for p in paths}
    assert before==after,f'{sid}: camera/contract changed; do not reuse observations'
    mesh_hash=file_hash(gt/'mesh.npz');inputs=[mesh_hash,file_hash(gt/'placements.json'),file_hash(gt/'features.json')]
    trajectory_key=stage_hash(inputs,cfg['scan'],['camera.py','scan.py'],['numpy','open3d'])
    if not state.valid(sid,'trajectory',trajectory_key):
        assert state.valid(sid,'trajectory',legacy_key(inputs)),f'{sid}: no qualified old trajectory'
        row=state.db.execute('SELECT metrics FROM stages WHERE subject=? AND stage=?',(sid,'trajectory')).fetchone()
        metrics={'equivalent_camera_builder_migration':True,'prior_numerical_stage_metrics':json.loads(row[0]),'reuse_only':True}
        state.finish(sid,'trajectory',trajectory_key,paths,metrics)
    count=0;payloads={}
    for camera in load_json(gt/'cameras.json')['cameras']:
        subject=f'{sid}/{camera["id"]}';inputs=[mesh_hash,camera];key=stage_hash(inputs,cfg['scan'],['scan.py','camera.py'],['numpy','open3d'])
        if state.valid(subject,'observations',key):continue
        assert state.valid(subject,'observations',legacy_key(inputs)),f'{subject}: old output hash mismatch'
        row=state.db.execute('SELECT outputs,metrics FROM stages WHERE subject=? AND stage=?',(subject,'observations')).fetchone()
        outputs=json.loads(row[0]);metrics={'prior_numerical_stage_metrics':json.loads(row[1]),'reuse_only':True};index=ROOT/f'private/scan_index/{sid}/{camera["id"]}.json';item=load_json(index)
        for path,h in outputs.items():
            p=ROOT/path
            if p!=index:payloads[path]=[h,p.stat().st_mtime_ns]
        item['frame_hash']=key;atomic_json(index,item)
        metrics['equivalent_camera_builder_migration']=True
        state.finish(subject,'observations',key,[ROOT/p for p in outputs],metrics);count+=1
    for path,(h,mtime) in payloads.items():assert file_hash(ROOT/path)==h and (ROOT/path).stat().st_mtime_ns==mtime
    frames=[load_json(ROOT/f'private/scan_index/{sid}/{c["id"]}.json') for c in load_json(gt/'cameras.json')['cameras']]
    atomic_json(ROOT/f'private/scan_index/{sid}/index.json',{'frames':frames,'camera_hash':file_hash(gt/'cameras.json')})
    results.append({'source_id':sid,'rekeyed_frames':count,'unchanged_camera_and_contract_hash_mtime':True,'unchanged_observation_payloads':len(payloads),'payload_hash_mtime_digest':digest(payloads)})
report={'status':'pass','old_scan_sha256':old_hash,'new_scan_sha256':file_hash(new),'only_prepare_cameras_AST_changed':True,'reason':'Resolution is selected against the coarsest projected interval over every actual placement. Pilot p0 already has the largest interval, so all camera bytes and numeric contracts remain identical. Existing raycasts and noise arrays are reused after full hash/mtime verification.','sources':results}
atomic_json(ROOT/'reports/tests/all_pose_sampling_migration.json',report);print(canonical_json(report))
