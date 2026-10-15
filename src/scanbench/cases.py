from pathlib import Path
import numpy as np
from .common import *

def case_id(sid,level,seed): return 'case_'+digest(['physical_scan_v1',sid,level,seed])[:16]

def prepare_case(sid,level,seed,state):
    cfg=config(); gt=ROOT/f'private/gt/{sid}'; meta=load_json(gt/'metadata.json'); placements=load_json(gt/'placements.json')
    allcams=load_json(gt/'cameras.json'); count=min(cfg['difficulty'][level]['placements'],len(placements['placements'])); stride=cfg['difficulty'][level]['stride']
    selected=[c for c in allcams['cameras'] if c['placement_id']<count and c['mother_frame_id']%stride==0]
    cid=case_id(sid,level,seed); out=ROOT/f'data/cases/{cid}/input'; frames=[]
    for cam in selected:
        item=load_json(ROOT/f'private/scan_index/{sid}/{cam["id"]}.json')['seeds'][str(seed)]
        frames.append({'camera_id':cam['id'],'path':'../../../'+item['observation'],'array_sha256':item['array_sha256'],'file_sha256':item['file_sha256'],'count':item['count']})
    publickeys=['id','placement_id','mother_frame_id','resolution','K','T_object_from_camera','near_mm','far_mm']
    publiccam={k:v for k,v in allcams.items() if k!='cameras'}
    publiccam['cameras']=[{k:c[k] for k in publickeys} for c in selected]
    key=stage_hash([frames,publiccam,digest(cfg)],cfg['reconstruction'],['cases.py'],['numpy'])
    inputs_changed=not state.valid(cid,'case_inputs',key)
    if inputs_changed:
        state.begin(cid,'case_inputs',key)
        atomic_json(out/'observations.json',{'schema':'observations_v1','data_root_relative':'../../..','frames':frames})
        atomic_json(out/'cameras.json',publiccam)
        atomic_json(out/'reconstruction_config.json',cfg['reconstruction'])
        atomic_json(out/'README.json',{'schema':'case_v1','case_id':cid,'units':'mm','coordinate_system':'canonical object; accurate known poses',
                   'range':'Euclidean unit-ray distance in mm','observations':'float32 noisy range_mm and uint32 row-major valid pixel; ideal foreground segmentation after tabletop occlusion',
                   'refs':'paths relative to observations.json; all resolve within the public data root','difficulty':level,'seed':seed,
                   'placement_count':count,'reorientation_count':count-1,'frames_per_placement':len(selected)//count,'config_sha256':digest(cfg)})
        state.finish(cid,'case_inputs',key,[out/'observations.json',out/'cameras.json',out/'reconstruction_config.json',out/'README.json'],{})
    annotation={'case_id':cid,'source_id':sid,'source_sha256':meta['source_sha256'],'precision_layer':meta['status'],
                'level':level,'seed':seed,'placement_count':count,'reorientation_count':count-1,'frames_per_placement':len(selected)//count,
                'resolution':allcams['resolution'],'protocol':cfg['protocol'],'protocol_config_sha256':digest(cfg),'generation_status':'inputs_ready','validation_status':'pending',
                'input_path':str(out.relative_to(ROOT)).replace('\\','/'),'limited_placements':placements['limited_placements']}
    existing=state.db.execute('SELECT body FROM records WHERE kind=? AND id=?',('cases',cid)).fetchone()
    if existing:
        previous=json.loads(existing[0]);previous.update({k:v for k,v in annotation.items() if k not in ['generation_status','validation_status']});annotation=previous
    atomic_json(ROOT/f'private/annotations/{cid}/case.json',annotation)
    state.record('cases',cid,annotation)
    return cid,out,annotation

def mesh_stage_key(out,cfg):
    return stage_hash([file_hash(out/'observations.json'),file_hash(out/'cameras.json')],cfg,['reconstruct.py','camera.py','observed_kernel.py','continuous_free_space.py'],['numpy','open3d','scipy','numba'])

def generate_case(sid,level,seed,state):
    from .reconstruct import reconstruct
    cid,out,record=prepare_case(sid,level,seed,state)
    cfg=config()['reconstruction']
    key=mesh_stage_key(out,cfg)
    if state.valid(cid,'mesh',key): return cid
    state.begin(cid,'mesh',key)
    with measured() as timing:
        metrics=reconstruct(out/'observations.json',out/'cameras.json',cfg,out)
    files=[out/f for f in ['mesh.ply','mesh.stl','points_for_meshing.ply','point_provenance.npz','reconstruction.json','continuous_veto.json']]
    record.update(generation_status='generated',validation_status='pending',mesh_stage_hash=key,outputs={f.name:file_hash(f) for f in files},metrics=metrics)
    atomic_json(ROOT/f'private/annotations/{cid}/case.json',record); state.record('cases',cid,record)
    state.finish(cid,'mesh',key,files,timing)
    return cid
