"""Run candidate physical/fingerprint/export checks in an isolated copied runtime."""
from pathlib import Path
import argparse,json,os,sys,shutil,subprocess,time,hashlib
MAIN_ROOT=Path(__file__).resolve().parents[1]
FOLDER=MAIN_ROOT/'reports/protocol_amendments/r5_sampling_density'


def worker(runtime):
    os.chdir(runtime);sys.path.insert(0,str(runtime/'src'))
    from scanbench.common import load_json,atomic_json,file_hash,State,config
    from scanbench.sampling_density import case_sampling_contract
    from scanbench.validate import physical_case_check,validation_fingerprint
    from scanbench.export import export_case
    import yaml
    fixtures=load_json(runtime/'fixtures.json');results=[]
    records={}
    for item in fixtures['cases']:
        record=item['record'];cid=record['case_id'];out=runtime/record['input_path']
        contract=case_sampling_contract(record['source_id'],record['level'],record['placement_count'])
        atomic_json(out/'sampling_contract.json',contract)
        record.update(protocol=contract['protocol'],sampling_contract_sha256=file_hash(out/'sampling_contract.json'))
        result=physical_case_check(record,out)
        if item.get('expected_original_physical') is not None:
            assert result==item['expected_original_physical'],(cid,result,item['expected_original_physical'])
        else:
            assert result['actual_frames_per_placement']==193 and abs(result['max_adjacent_azimuth_deg']-5.625)<1e-9
        records[cid]=record
        results.append({'case_id':cid,'scope':item['scope'],'physical_check':result,'sampling_contract_sha256':record['sampling_contract_sha256']})
    cid=fixtures['fingerprint_case'];record=records[cid];out=runtime/record['input_path']
    gates=yaml.safe_load((runtime/'configs/quality_gates.yaml').read_text(encoding='utf-8'))
    key=validation_fingerprint(out,record,gates);assert len(key)==64
    negative=[];path=out/'sampling_contract.json';original=path.read_bytes();value=load_json(path)
    atomic_json(path,{**value,'mother_intervals':384})
    try:validation_fingerprint(out,record,gates)
    except AssertionError:negative.append('tampered_contract_rejected_before_cache_lookup')
    else:raise AssertionError('tampered contract accepted')
    path.write_bytes(original)
    references=load_json(out/'observations.json')['frames'];payload=(out/references[0]['path']).resolve()
    assert payload.is_relative_to(runtime/'data')
    old=payload.read_bytes();changed=bytearray(old);changed[len(changed)//2]^=1;payload.write_bytes(changed)
    try:validation_fingerprint(out,record,gates)
    except ValueError:negative.append('corrupt_actual_observation_payload_rejected')
    else:raise AssertionError('corrupt actual payload accepted')
    payload.write_bytes(old)
    assert validation_fingerprint(out,record,gates)==key
    dense=records[fixtures['dense_case']];out_dense=runtime/dense['input_path'];path=out_dense/'cameras.json';old=path.read_bytes();camset=load_json(path)
    camset['cameras']=camset['cameras'][:-1];atomic_json(path,camset)
    try:physical_case_check(dense,out_dense)
    except AssertionError:negative.append('incomplete_dense_trajectory_rejected')
    else:raise AssertionError('incomplete dense trajectory accepted')
    path.write_bytes(old)
    # Only the actually observed hard case is exported. The dense source is a physical-control fixture.
    destination=runtime/'public_export'
    export_case(cid,destination,observations_only=False)
    exported=load_json(destination/'export.json')
    expected=f'data/cases/{cid}/input/sampling_contract.json'
    assert expected in exported['files'] and exported['files'][expected]==file_hash(runtime/expected)
    for name,h in exported['files'].items():
        p=destination/name
        assert p.resolve().is_relative_to(destination) and not p.is_symlink() and file_hash(p)==h
    assert not (destination/'private').exists() and not (destination/'sources').exists()
    public=destination/f'data/cases/{cid}/input'
    for entry in load_json(public/'observations.json')['frames']:
        p=(public/entry['path']).resolve();assert p.is_relative_to(destination/'data') and file_hash(p)==entry['file_sha256']
    output={'status':'pass','scope':'Actual candidate physical-case checks, current payload fingerprint integrity and isolated public export; no formal source/scan/Mesh changed','physical_cases':results,'negative_controls':negative,'valid_current_validation_fingerprint':key,'exported_public_files':len(exported['files']),'public_sampling_contract_included':True,'public_export_no_GT_or_STEP':True,'export_manifest_sha256':file_hash(destination/'export.json'),'time':time.time()}
    atomic_json(runtime/'runtime_result.json',output)
    print(json.dumps(output,ensure_ascii=False),flush=True)


def prepare():
    sys.path.insert(0,str(MAIN_ROOT/'src'))
    from scanbench.common import load_json,atomic_json,file_hash,config
    candidate=FOLDER/'candidate';manifest=load_json(FOLDER/'candidate_manifest.json');controls=load_json(FOLDER/'candidate_controls.json')
    assert controls['status']=='pass' and controls['candidate_manifest_sha256']==file_hash(FOLDER/'candidate_manifest.json')
    runtime=FOLDER/'controls'/f'runtime_{time.time_ns()}'
    runtime.mkdir(parents=True)
    for source in (MAIN_ROOT/'src/scanbench').glob('*.py'):
        relative=Path('src/scanbench')/source.name;selected=candidate/relative if (candidate/relative).exists() else source
        target=runtime/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(selected,target)
    shutil.copy2(candidate/'src/scanbench/sampling_density.py',runtime/'src/scanbench/sampling_density.py')
    for name in ['physical_scan_v1.yaml','quality_gates.yaml']:
        target=runtime/'configs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN_ROOT/'configs'/name,target)
    policy=load_json(candidate/'configs/sampling_density_v2.json');policy['status']='frozen';atomic_json(runtime/'configs/sampling_density_v2.json',policy)
    for sid in ['218','245']:
        for name in ['mesh.npz','metadata.json','placements.json','cameras.json','feature_contract.json','features.json','placement_audit.json']:
            target=runtime/f'private/gt/{sid}/{name}';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN_ROOT/f'private/gt/{sid}/{name}',target)
        target=runtime/f'sources/{sid}/input.step';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MAIN_ROOT/f'sources/{sid}/input.step',target)
    cases=[]
    for cid,full in [('case_2438b1a3fd780c63',True),('case_3000584756354796',False)]:
        record=load_json(MAIN_ROOT/f'private/annotations/{cid}/case.json');src=MAIN_ROOT/record['input_path'];out=runtime/record['input_path'];out.mkdir(parents=True,exist_ok=True)
        names=[p.name for p in src.iterdir() if p.is_file()] if full else ['cameras.json','README.json']
        for name in names:shutil.copy2(src/name,out/name)
        if full:
            for frame in load_json(src/'observations.json')['frames']:
                source=(src/frame['path']).resolve();target=(out/frame['path']).resolve();assert target.is_relative_to(runtime/'data')
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        expected=load_json(MAIN_ROOT/f'private/annotations/{cid}/acceptance.json')['physical_scan']
        cases.append({'record':record,'scope':'unchanged original physical trajectory','expected_original_physical':expected})
    cid='case_9a0e4b631d694e54';record=load_json(MAIN_ROOT/f'private/annotations/{cid}/case.json');out=runtime/record['input_path'];out.mkdir(parents=True,exist_ok=True)
    dense=load_json(MAIN_ROOT/'reports/density_investigations/245/cameras_768.json')
    atomic_json(runtime/'private/gt/245/cameras.json',dense)
    original=load_json(MAIN_ROOT/record['input_path']/'cameras.json');keys=['id','placement_id','mother_frame_id','resolution','K','T_object_from_camera','near_mm','far_mm']
    original['cameras']=[{k:c[k] for k in keys} for c in dense['cameras'] if c['placement_id']==0 and c['mother_frame_id']%4==0]
    atomic_json(out/'cameras.json',original)
    record['frames_per_placement']=193
    cases.append({'record':record,'scope':'768-interval dense hard physical control only; not a formal generated case'})
    atomic_json(runtime/'fixtures.json',{'cases':cases,'fingerprint_case':'case_2438b1a3fd780c63','dense_case':cid})
    shutil.copy2(MAIN_ROOT/'requirements.lock',runtime/'requirements.lock');shutil.copy2(MAIN_ROOT/'LICENSES.md',runtime/'LICENSES.md')
    receipt={'status':'prepared','runtime':str(runtime.relative_to(MAIN_ROOT)).replace('\\','/'),'candidate_manifest_sha256':file_hash(FOLDER/'candidate_manifest.json'),'candidate_controls_sha256':file_hash(FOLDER/'candidate_controls.json'),'original_inputs_sha256':{str((MAIN_ROOT/f'private/annotations/{x["record"]["case_id"]}/case.json').relative_to(MAIN_ROOT)).replace('\\','/'):file_hash(MAIN_ROOT/f'private/annotations/{x["record"]["case_id"]}/case.json') for x in cases},'runtime_files_sha256':{str(p.relative_to(runtime)).replace('\\','/'):file_hash(p) for p in runtime.rglob('*') if p.is_file()},'time':time.time()}
    atomic_json(runtime/'prepared.json',receipt)
    atomic_json(FOLDER/'runtime_prepared.json',{'runtime':receipt['runtime'],'prepared_sha256':file_hash(runtime/'prepared.json')})
    print(json.dumps({'status':'prepared','runtime':receipt['runtime'],'files':len(receipt['runtime_files_sha256'])}),flush=True)
    return runtime


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--runtime');parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
    if args.worker:return worker(Path(args.worker).resolve())
    runtime=Path(args.runtime).resolve() if args.runtime else prepare()
    assert runtime.is_relative_to(FOLDER/'controls') and runtime.name.startswith('runtime_')
    if args.prepare_only:return
    import psutil
    if psutil.virtual_memory().available<3*2**30:
        print(json.dumps({'status':'deferred_resource_guard','available_ram_gib':psutil.virtual_memory().available/2**30,'runtime':str(runtime.relative_to(MAIN_ROOT))}),flush=True)
        return
    receipt=json.loads((runtime/'prepared.json').read_text(encoding='utf-8'))
    for name,h in receipt['runtime_files_sha256'].items():assert hashlib.sha256((runtime/name).read_bytes()).hexdigest()==h,name
    log=runtime/'worker.log';start=time.time();peak=0
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',str(runtime)],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        tracked=psutil.Process(process.pid)
        while process.poll() is None:
            try:peak=max(peak,sum(p.memory_info().rss for p in [tracked,*tracked.children(recursive=True)] if p.is_running()))
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            time.sleep(.2)
    assert process.returncode==0,(process.returncode,str(log))
    result=json.loads((runtime/'runtime_result.json').read_text(encoding='utf-8'));assert result['status']=='pass'
    result.update(runtime=str(runtime.relative_to(MAIN_ROOT)).replace('\\','/'),prepared_sha256=hashlib.sha256((runtime/'prepared.json').read_bytes()).hexdigest(),worker_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),peak_process_tree_rss_bytes=peak,seconds=time.time()-start)
    output=FOLDER/'runtime_controls.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'pass','runtime':result['runtime'],'physical_cases':len(result['physical_cases']),'negative_controls':result['negative_controls'],'peak_process_tree_rss_gib':peak/2**30,'seconds':result['seconds']}),flush=True)


if __name__=='__main__':main()
