"""Archive a failed sparse case and translate only proven reusable clean frames.

No source geometry or noisy observation payload is moved or overwritten. Dense
acquisition itself remains the normal production path after the new freeze.
"""
from pathlib import Path
import os,sys,shutil,argparse
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
from scanbench.common import *
from scanbench.sampling_density import sampling_policy,source_scan_settings,noise_frame_key
from scanbench.scan import prepare_cameras
from snapshot_sampling_density_v2 import active_source_workers
from migrate_sampling_density_defaults import HistoricalInputs,replace_stage

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'


def owned_move(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    assert source.is_relative_to(ROOT.resolve()) and destination.is_relative_to(FOLDER.resolve())
    assert source!=ROOT.resolve() and source!=FOLDER.resolve()
    if destination.exists():assert not source.exists(),('ambiguous interrupted archive',source,destination)
    elif source.exists():destination.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(source),str(destination))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source');args=parser.parse_args();sid=args.source
    assert not active_source_workers(),'Wait for all active source workers to exit'
    baseline=load_json(FOLDER/'baseline.json');installation=load_json(FOLDER/'installation.json')
    for name,h in installation['active_code_sha256'].items():assert file_hash(ROOT/name)==h,name
    assert sid in baseline['affected_sources']
    history=HistoricalInputs();state=State();sc=source_scan_settings(sid);factor=sc['intervals']//config()['scan']['intervals']
    assert factor>1 and sc['intervals']%4==0
    folder=FOLDER/f'affected_sources/{sid}';receipt=folder/'prepared.json'
    if receipt.exists():
        proof=load_json(receipt)
        assert proof['status']=='ready_for_frozen_dense_acquisition'
        assert file_hash(ROOT/f'private/gt/{sid}/cameras.json')==proof['dense_cameras_sha256']
        for name,entry in proof['old_observation_payloads'].items():history.unchanged(name)
        print(canonical_json({'status':'already_prepared','source':sid,'receipt_sha256':file_hash(receipt)}));return
    folder.mkdir(parents=True,exist_ok=True)
    archive=folder/'archive';gt=ROOT/f'private/gt/{sid}'
    previous_cameras=archive/'private/gt'/sid/'cameras.json'
    for name in ['cameras.json','feature_contract.json']:
        original=gt/name;destination=archive/f'private/gt/{sid}/{name}'
        expected=history.inventory[f'private/gt/{sid}/{name}']
        if not destination.exists():
            history.unchanged(f'private/gt/{sid}/{name}');destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,destination)
        assert file_hash(destination)==expected['sha256'] and destination.stat().st_mtime_ns==expected['mtime_ns']
    old_cameras=load_json(previous_cameras);old_cam_list=old_cameras['cameras']
    # Moving these private acquisition records avoids collisions between old and
    # new frame IDs. Complete original inventories remain independently checkable.
    archival_finished=(folder/'archive_inventory.json').exists()
    if not archival_finished:
        owned_move(ROOT/f'private/scan_index/{sid}',archive/f'private/scan_index/{sid}')
        owned_move(ROOT/f'cache/clean/{sid}',archive/f'cache/clean/{sid}')
        owned_move(ROOT/f'private/reference/{sid}',archive/f'private/reference/{sid}')
    affected=[]
    for cid in baseline['all_existing_case_ids']:
        old=history.old_json(f'private/annotations/{cid}/case.json')
        if old['source_id']!=sid:continue
        acceptance=history.old_json(f'private/annotations/{cid}/acceptance.json')
        assert acceptance['status']!='pass','Do not silently supersede an accepted affected case'
        assert acceptance['failures']==['adjacent scan overlap requires investigation'],acceptance['failures']
        if not archival_finished:
            owned_move(ROOT/f'data/cases/{cid}',archive/f'data/cases/{cid}')
            owned_move(ROOT/f'private/annotations/{cid}',archive/f'private/annotations/{cid}')
            for name in [f'reports/private_previews/{cid}.png',f'reports/private_previews/{cid}.json']:
                owned_move(ROOT/name,archive/name)
        affected.append({'case_id':cid,'original_validation_status':acceptance['status'],'failures':acceptance['failures']})
    archived_inventory={}
    for path in sorted(archive.rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(archive).as_posix();st=path.stat();entry={'sha256':file_hash(path),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
        if relative in history.inventory:assert entry==history.inventory[relative],relative
        else:
            try:assert entry['sha256']==__import__('hashlib').sha256(history.archive_bytes(relative)).hexdigest(),relative
            except (KeyError,AssertionError):
                if relative.startswith('private/annotations/'):raise
        archived_inventory[relative]=entry
    atomic_json(folder/'archive_inventory.json',archived_inventory)
    # Remove only the superseded stage rows. Their complete original values remain
    # in the immutable SQLite backup. Each future new row has its own real key.
    state.db.execute("DELETE FROM stages WHERE (subject=? AND stage='trajectory') OR (subject LIKE ? AND stage='observations')",(sid,sid+'/%'))
    for case in affected:
        state.db.execute('DELETE FROM stages WHERE subject=?',(case['case_id'],))
        state.db.execute("DELETE FROM records WHERE kind='cases' AND id=?",(case['case_id'],))
    state.db.commit()
    rows=state.db.execute("SELECT body FROM records WHERE kind='cases' ORDER BY id").fetchall()
    atomic_bytes(ROOT/'manifests/cases.jsonl',('\n'.join(row[0] for row in rows)+'\n').encode())
    captured=prepare_cameras(sid,state)
    # The independently tested trial is compared to actual production trajectory
    # generation, rather than copied in as a substitute for that implementation.
    basis=sampling_policy()['basis'][sid];trial=load_json(ROOT/basis['path'])
    expected_trial=ROOT/f'reports/density_investigations/{sid}/cameras_{sc["intervals"]}.json'
    independent=load_json(expected_trial)
    assert independent.pop('investigation_only') is True
    assert independent.pop('mother_intervals')==sc['intervals']
    assert independent==captured,'Actual dense camera payload differs from the independent trial'
    assert (gt/'feature_contract.json').read_bytes()==(archive/f'private/gt/{sid}/feature_contract.json').read_bytes()
    trajectory_key=stage_hash([file_hash(gt/name) for name in ['mesh.npz','placements.json','features.json']],sc,['camera.py','scan.py','sampling_density.py'],['numpy','open3d'])
    old_trajectory=history.old_row(sid,'trajectory')
    replace_stage(state,old_trajectory,trajectory_key,[gt/'cameras.json',gt/'feature_contract.json'],{'proof':receipt.relative_to(ROOT).as_posix(),'scope':'actual newly generated refined trajectory; old trajectory archived; original geometry unchanged'})
    new_by_position={(c['placement_id'],c['mother_frame_id']):c for c in captured['cameras']}
    payloads={};translated=[];mapping=[]
    mesh_hash=file_hash(gt/'mesh.npz')
    for old in old_cam_list:
        camera=new_by_position[(old['placement_id'],old['mother_frame_id']*factor)]
        for name in ['K','T_object_from_camera','T_table_from_camera','near_mm','far_mm','resolution']:
            np.testing.assert_array_equal(old[name],camera[name])
        assert noise_frame_key(camera,sc)==old['mother_frame_id']
        old_index=load_json(archive/f'private/scan_index/{sid}/{old["id"]}.json')
        old_row=history.old_row(f'{sid}/{old["id"]}','observations')
        assert old_index['frame_hash']==old_row[2]
        for seed in config()['seeds']:
            item=old_index['seeds'][str(seed)];name='data/'+item['observation'];history.unchanged(name)
            assert item['file_sha256']==history.inventory[name]['sha256']
            payloads[name]=history.inventory[name]
            assert stable_seed(sc['noise_algorithm'],sid,seed,camera['placement_id'],noise_frame_key(camera,sc))==stable_seed(config()['scan']['noise_algorithm'],sid,seed,old['placement_id'],old['mother_frame_id'])
        mapping.append({'old_camera_id':old['id'],'new_camera_id':camera['id'],'original_integer_noise_key':old['mother_frame_id'],'seeds':old_index['seeds']})
        if old['mother_frame_id']%4:continue
        clean_original=archive/f'cache/clean/{sid}/{old["id"]}.npz'
        clean=ROOT/f'cache/clean/{sid}/{camera["id"]}.npz';clean.parent.mkdir(parents=True,exist_ok=True)
        if clean.exists():assert file_hash(clean)==file_hash(clean_original)
        else:shutil.copy2(clean_original,clean)
        key=stage_hash([mesh_hash,camera],sc,['scan.py','camera.py','sampling_density.py'],['numpy','open3d'])
        # The new index explicitly records the unchanged original acquisition key.
        item={**old_index,'camera_id':camera['id'],'frame_hash':key,'sampling_revision':{'original_camera_id':old['id'],'original_frame_hash':old_index['frame_hash'],'proof':receipt.relative_to(ROOT).as_posix(),'exact_same_matrix_and_integer_noise_key':True}}
        index=ROOT/f'private/scan_index/{sid}/{camera["id"]}.json';atomic_json(index,item)
        outputs=[ROOT/'data'/x['observation'] for x in item['seeds'].values()]+[clean,index]
        synthetic_row=(f'{sid}/{camera["id"]}','observations',*old_row[2:])
        replace_stage(state,synthetic_row,key,outputs,{'proof':receipt.relative_to(ROOT).as_posix(),'original_subject':old_row[0],'original_stage_digest':digest(old_row),'scope':'exact actual old observations and clean evidence at identical physical position'})
        translated.append({'old_camera_id':old['id'],'new_camera_id':camera['id'],'clean_sha256':file_hash(clean),'old_frame_key':old_row[2],'new_frame_key':key})
    proof={'status':'ready_for_frozen_dense_acquisition','source_id':sid,'old_intervals':config()['scan']['intervals'],'new_intervals':sc['intervals'],'refinement_factor':factor,'original_cameras':len(old_cam_list),'dense_cameras':len(captured['cameras']),'dense_cameras_sha256':file_hash(gt/'cameras.json'),'old_observation_payloads':payloads,'old_to_new_camera_mapping':mapping,'translated_complete_clean_frames':translated,'superseded_failed_cases':affected,'original_source_geometry_unchanged':True,'public_noisy_payloads_unchanged':True,'archive_inventory_sha256':file_hash(folder/'archive_inventory.json'),'baseline_sha256':file_hash(FOLDER/'baseline.json'),'installation_sha256':file_hash(FOLDER/'installation.json'),'density_investigation_sha256':file_hash(ROOT/basis['path']),'script_sha256':file_hash(Path(__file__)),'time':time.time()}
    atomic_json(receipt,proof)
    print(canonical_json({'status':proof['status'],'source':sid,'translated_clean_frames':len(translated),'old_payloads_preserved':len(payloads),'dense_cameras':len(captured['cameras'])}),flush=True)


if __name__=='__main__':main()
