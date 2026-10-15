"""Adopt unchanged 192-interval payloads with explicit, verified compatibility.

This is a ledger/metadata migration, not numerical revalidation. Original numerical
results remain separately archived. The physical checks are executed again, and
the actual old inputs and outputs are hashed before any old result is adopted.
"""
from pathlib import Path
import os,sys,ast,copy,sqlite3,zipfile,hashlib,importlib.util,argparse
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
from scanbench.common import *
from snapshot_sampling_density_v2 import active_source_workers

FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'


def encoded_json(value):
    return (json.dumps(value,indent=2,ensure_ascii=False,default=json_default,allow_nan=False)+'\n').encode('utf-8')


def numerical_compatibility():
    from test_sampling_density_candidate import functions,same,Normalize
    allowed={'scan.py':{'prepare_cameras','acquire_scans'},'cases.py':{'prepare_case'},
             'validate.py':{'physical_case_check','validation_fingerprint'},
             'supplemental.py':{'source_factors'},'export.py':{'export_case'}}
    rows=[]
    for module,changed in allowed.items():
        before=functions(FOLDER/'code_before/src/scanbench'/module)
        after=functions(ROOT/'src/scanbench'/module)
        assert set(before)==set(after),module
        for function in before.keys()-changed:assert same(before[function],after[function]),(module,function)
        rows.append({'module':module,'identical_functions':sorted(before.keys()-changed),'declared_changes':sorted(changed)})
    for module,function in [('validate.py','physical_case_check'),('validate.py','validation_fingerprint'),('scan.py','acquire_scans')]:
        before=functions(FOLDER/'code_before/src/scanbench'/module)[function]
        after=Normalize().visit(copy.deepcopy(functions(ROOT/'src/scanbench'/module)[function]))
        assert same(before,after),(module,function)
    old=load_json(FOLDER/'freeze_before.json')
    for module in ['common.py','camera.py','reconstruct.py','observed_kernel.py','continuous_free_space.py','observation_grid.py','contact_support.py']:
        assert file_hash(ROOT/'src/scanbench'/module)==old['code_sha256']['src/scanbench/'+module]
    return rows


class HistoricalInputs:
    def __init__(self):
        self.baseline=load_json(FOLDER/'baseline.json')
        for name,key in [('inventory_before.json','inventory_before_sha256'),('metadata_archives.json','metadata_archives_sha256'),('state_before.sqlite','state_database_sha256'),('freeze_before.json','freeze_before_sha256')]:
            assert file_hash(FOLDER/name)==self.baseline[key],name
        self.inventory=load_json(FOLDER/'inventory_before.json')['files']
        self.archives=load_json(FOLDER/'metadata_archives.json')
        self.frozen=load_json(FOLDER/'freeze_before.json')
        self.previous=sqlite3.connect(f'file:{(FOLDER/"state_before.sqlite").as_posix()}?mode=ro',uri=True)
        self.checked={};self.archive_handles={}

    def actual_hash(self,path):
        path=Path(path);st=path.stat();signature=(st.st_size,st.st_mtime_ns)
        cached=self.checked.get(str(path))
        if cached and cached[:2]==signature:return cached[2]
        value=file_hash(path);self.checked[str(path)]=(*signature,value);return value

    def unchanged(self,name,mtime=True):
        entry=self.inventory[name];path=ROOT/name;st=path.stat()
        assert st.st_size==entry['bytes'] and self.actual_hash(path)==entry['sha256'],name
        if mtime:assert st.st_mtime_ns==entry['mtime_ns'],name
        return entry['sha256']

    def archive_bytes(self,name):
        candidates=[item for item in self.archives.values() if name in item['files']]
        assert len(candidates)==1,('historical metadata must resolve uniquely',name)
        item=candidates[0];archive=item['path']
        if archive not in self.archive_handles:
            assert file_hash(ROOT/archive)==item['sha256'],archive
            self.archive_handles[archive]=zipfile.ZipFile(ROOT/archive)
        data=self.archive_handles[archive].read(name)
        assert hashlib.sha256(data).hexdigest()==item['files'][name]['sha256'],name
        return data

    def old_json(self,name):return json.loads(self.archive_bytes(name))

    def old_row(self,subject,stage):
        result=self.previous.execute('SELECT * FROM stages WHERE subject=? AND stage=?',(subject,stage)).fetchone()
        assert result is not None and result[3]=='complete',(subject,stage)
        return result

    def verify_outputs(self,row):
        outputs=json.loads(row[4])
        for name,h in outputs.items():
            assert self.actual_hash(ROOT/name)==h,(row[0],row[1],name)
            if name in self.inventory:self.unchanged(name)
        return outputs

    def stage_hash(self,inputs,settings,modules,packages=()):
        code={name:self.frozen['code_sha256']['src/scanbench/'+name] for name in modules}
        return digest({'inputs':inputs,'settings':settings,'code':code,'environment':{p:importlib.metadata.version(p) for p in packages}})


def replace_stage(state,old,new_key,outputs,receipt):
    actual={str(Path(path).relative_to(ROOT)).replace('\\','/'):file_hash(path) for path in outputs}
    metrics=json.loads(old[5]);metrics['sampling_density_compatibility']=receipt
    state.db.execute('INSERT OR REPLACE INTO stages VALUES (?,?,?,?,?,?,?)',(old[0],old[1],new_key,'complete',canonical_json(actual),canonical_json(metrics),time.time()))
    state.db.commit()


def source_migration(sid,state,historical):
    from scanbench import scan
    from scanbench.sampling_density import source_scan_settings
    gt=ROOT/f'private/gt/{sid}';sc=source_scan_settings(sid)
    assert sc==config()['scan'],'Refined sources cannot use unchanged-payload migration'
    proof_path=FOLDER/f'default_sources/{sid}.json'
    # All geometric and acquisition files, including full clean evidence, retain
    # their bytes and timestamps. Reference JSON is deliberately handled below.
    prefixes=[f'private/gt/{sid}/',f'private/scan_index/{sid}/',f'cache/clean/{sid}/',f'sources/{sid}/']
    preserved=[name for name in historical.inventory if any(name.startswith(prefix) for prefix in prefixes)]
    for name in preserved:historical.unchanged(name)
    captured={};original=scan.atomic_json
    try:
        scan.atomic_json=lambda path,value:captured.__setitem__(Path(path),encoded_json(value))
        scan.prepare_cameras(sid,state)
    finally:scan.atomic_json=original
    assert set(captured)=={gt/'cameras.json',gt/'feature_contract.json'}
    for path,data in captured.items():assert path.read_bytes()==data,('new default trajectory is not byte-identical',sid,path.name)
    inputs=[historical.actual_hash(gt/name) for name in ['mesh.npz','placements.json','features.json']]
    old=historical.old_row(sid,'trajectory');assert old[2]==historical.stage_hash(inputs,sc,['camera.py','scan.py'],['numpy','open3d'])
    historical.verify_outputs(old)
    key=stage_hash(inputs,sc,['camera.py','scan.py','sampling_density.py'],['numpy','open3d'])
    trajectory={'old_key':old[2],'current_key':key,'outputs_sha256':json.loads(old[4]),'original_metrics':json.loads(old[5])}
    replace_stage(state,old,key,[ROOT/name for name in json.loads(old[4])],{'proof':proof_path.relative_to(ROOT).as_posix(),'original_stage_digest':digest(old),'scope':'exact camera and feature-contract bytes; metadata-only adoption'})
    frames=[];mesh_hash=historical.actual_hash(gt/'mesh.npz')
    for camera in load_json(gt/'cameras.json')['cameras']:
        label=f'{sid}/{camera["id"]}';old=historical.old_row(label,'observations')
        assert old[2]==historical.stage_hash([mesh_hash,camera],sc,['scan.py','camera.py'],['numpy','open3d'])
        historical.verify_outputs(old)
        index=load_json(ROOT/f'private/scan_index/{sid}/{camera["id"]}.json')
        assert index['frame_hash']==old[2],'Original acquisition provenance must remain intact'
        key=stage_hash([mesh_hash,camera],sc,['scan.py','camera.py','sampling_density.py'],['numpy','open3d'])
        replace_stage(state,old,key,[ROOT/name for name in json.loads(old[4])],{'proof':proof_path.relative_to(ROOT).as_posix(),'original_stage_digest':digest(old),'scope':'same actual camera, integer RNG key and complete unchanged observed payloads'})
        frames.append({'camera_id':camera['id'],'old_key':old[2],'current_key':key,'old_stage_digest':digest(old),'outputs_sha256':json.loads(old[4])})
    marker=f'private/reference/{sid}/reference.json';old_report=historical.old_json(marker)
    reference_inputs=[historical.actual_hash(gt/name) for name in ['mesh.npz','cameras.json','placements.json']]
    settings={'samples':30000,'incidence_deg':sc['incidence_deg']}
    assert old_report['key']==historical.stage_hash(reference_inputs,settings,['validate.py'],['numpy','open3d','trimesh'])
    evaluation=f'private/reference/{sid}/evaluation.npz';historical.unchanged(evaluation)
    reference_key=stage_hash(reference_inputs,settings,['validate.py'],['numpy','open3d','trimesh'])
    expected={**old_report,'key':reference_key,'sampling_revision':{'proof':proof_path.relative_to(ROOT).as_posix(),'original_key':old_report['key'],'evaluation_unchanged':True}}
    assert load_json(ROOT/marker) in [old_report,expected],('unexpected reference metadata change',sid)
    atomic_json(ROOT/marker,expected)
    proof={'status':'pass_unchanged_physical_payloads_adopted','source_id':sid,'baseline_sha256':file_hash(FOLDER/'baseline.json'),'installation_sha256':file_hash(FOLDER/'installation.json'),'actual_intervals':192,'exact_regenerated_camera_bytes':True,'exact_regenerated_feature_contract_bytes':True,'preserved_file_count':len(preserved),'preserved_file_names':preserved,'trajectory':trajectory,'frames':frames,'original_reference_sha256':hashlib.sha256(historical.archive_bytes(marker)).hexdigest(),'current_reference_sha256':file_hash(ROOT/marker),'reference_original_key':old_report['key'],'reference_current_key':reference_key,'evaluation_sha256':historical.inventory[evaluation]['sha256'],'numerical_reference_function_AST_unchanged':True}
    atomic_json(proof_path,proof)
    print(canonical_json({'source_compatibility':'pass','source':sid,'frames_adopted':len(frames),'preserved_files':len(preserved)}),flush=True)
    return proof


def previous_validation_module(historical):
    spec=importlib.util.spec_from_file_location('scanbench._sampling_previous_validate',FOLDER/'code_before/src/scanbench/validate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.stage_hash=historical.stage_hash;module.file_hash=historical.actual_hash
    return module


def case_migration(cid,state,historical,previous):
    from scanbench.cases import prepare_case,mesh_stage_key
    from scanbench.validate import physical_case_check,validation_fingerprint
    from scanbench.sampling_density import case_sampling_contract
    started=time.time();folder=f'private/annotations/{cid}';old_record=historical.old_json(folder+'/case.json')
    old_acceptance=historical.old_json(folder+'/acceptance.json');old_extra=historical.old_json(folder+'/supplemental.json')
    sid=old_record['source_id'];out=ROOT/old_record['input_path'];proof_path=FOLDER/f'default_cases/{cid}.json'
    if proof_path.exists():
        proof=load_json(proof_path)
        assert proof['status']=='pass_unchanged_mesh_and_observations_adopted'
        assert proof['source_migration_sha256']==file_hash(FOLDER/f'default_sources/{sid}.json')
        assert proof['current_acceptance_sha256']==file_hash(ROOT/folder/'acceptance.json')
        assert proof['current_supplemental_sha256']==file_hash(ROOT/folder/'supplemental.json')
        for name in proof['preserved_public_file_names']:historical.unchanged(name)
        assert state.valid(cid,'validation',proof['current_validation_hash'])
        assert state.valid(cid,'case_inputs',proof['current_case_inputs_hash'])
        print(canonical_json({'case_compatibility':'already_verified','case':cid}),flush=True)
        return proof
    assert old_acceptance['status']==old_extra['status']=='pass'
    preserved=[name for name in historical.inventory if name.startswith(f'data/cases/{cid}/')]
    for name in preserved:historical.unchanged(name)
    old_validation=historical.old_row(cid,'validation')
    assert old_validation[2]==old_acceptance['validation_hash']==previous.validation_fingerprint(out,old_record,yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text()))
    assert json.loads(old_validation[4])=={folder+'/acceptance.json':hashlib.sha256(historical.archive_bytes(folder+'/acceptance.json')).hexdigest()}
    old_mesh=historical.old_row(cid,'mesh');historical.verify_outputs(old_mesh)
    assert old_mesh[2]==mesh_stage_key(out,config()['reconstruction'])
    old_inputs=historical.old_row(cid,'case_inputs');historical.verify_outputs(old_inputs)
    obs=load_json(out/'observations.json');public=load_json(out/'cameras.json')
    assert old_inputs[2]==historical.stage_hash([obs['frames'],public,digest(config())],config()['reconstruction'],['cases.py'],['numpy'])
    contract=case_sampling_contract(sid,old_record['level'],old_record['placement_count'])
    assert contract['mother_intervals']==192
    current_cid,_,record=prepare_case(sid,old_record['level'],old_record['seed'],state);assert current_cid==cid
    for name in preserved:historical.unchanged(name)
    actual_physical=physical_case_check(record,out)
    assert actual_physical==old_acceptance['physical_scan'],('physical result changed',cid)
    gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text())
    new_key=validation_fingerprint(out,record,gates)
    adoption={'proof':proof_path.relative_to(ROOT).as_posix(),'original_validation_hash':old_validation[2],'original_acceptance_sha256':hashlib.sha256(historical.archive_bytes(folder+'/acceptance.json')).hexdigest(),'numerical_results_adopted_with_identical_actual_inputs_and_AST':True,'physical_check_executed_again_and_exactly_equal':True}
    expected={**old_acceptance,'validation_hash':new_key,'sampling_revision':adoption}
    assert load_json(ROOT/folder/'acceptance.json') in [old_acceptance,expected],('unexpected acceptance change',cid)
    atomic_json(ROOT/folder/'acceptance.json',expected)
    record.update(validation_status='pass',validation_hash=new_key)
    atomic_json(ROOT/folder/'case.json',record);state.record('cases',cid,record)
    replace_stage(state,old_validation,new_key,[ROOT/folder/'acceptance.json'],{'proof':proof_path.relative_to(ROOT).as_posix(),'original_stage_digest':digest(old_validation),'scope':'full actual old fingerprint and unchanged numerical AST; current physical check repeated'})
    gt=ROOT/f'private/gt/{sid}'
    extra_inputs=[historical.actual_hash(path) for path in [out/'mesh.ply',out/'observations.json',out/'cameras.json',out/'reconstruction.json',gt/'features.json',gt/'feature_contract.json']]
    old_extra_key=digest([*extra_inputs,historical.frozen['code_sha256']['src/scanbench/supplemental.py'],historical.frozen['code_sha256']['src/scanbench/validate.py']])
    assert old_extra['input_hash']==old_extra_key
    extra_key=digest([*extra_inputs,file_hash(ROOT/'src/scanbench/supplemental.py'),file_hash(ROOT/'src/scanbench/validate.py')])
    extra_expected={**old_extra,'input_hash':extra_key,'sampling_revision':{'proof':proof_path.relative_to(ROOT).as_posix(),'original_input_hash':old_extra_key,'unchanged_numerical_functions_and_payloads':True}}
    assert load_json(ROOT/folder/'supplemental.json') in [old_extra,extra_expected],('unexpected supplementary change',cid)
    atomic_json(ROOT/folder/'supplemental.json',extra_expected)
    proof={'status':'pass_unchanged_mesh_and_observations_adopted','case_id':cid,'source_id':sid,'source_migration_sha256':file_hash(FOLDER/f'default_sources/{sid}.json'),'original_case_sha256':hashlib.sha256(historical.archive_bytes(folder+'/case.json')).hexdigest(),'original_acceptance_sha256':adoption['original_acceptance_sha256'],'current_acceptance_sha256':file_hash(ROOT/folder/'acceptance.json'),'current_supplemental_sha256':file_hash(ROOT/folder/'supplemental.json'),'old_validation_hash':old_validation[2],'current_validation_hash':new_key,'old_case_inputs_hash':old_inputs[2],'current_case_inputs_hash':state.db.execute("SELECT input_hash FROM stages WHERE subject=? AND stage='case_inputs'",(cid,)).fetchone()[0],'sampling_contract_sha256':file_hash(out/'sampling_contract.json'),'mesh_stage_hash_unchanged':old_mesh[2],'preserved_public_file_names':preserved,'physical_result_exactly_equal':True,'physical_result':actual_physical,'original_numerical_performance_seconds':old_acceptance['performance']['seconds'],'compatibility_migration_seconds':time.time()-started}
    atomic_json(proof_path,proof)
    print(canonical_json({'case_compatibility':'pass','case':cid,'seconds':proof['compatibility_migration_seconds']}),flush=True)
    return proof


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ids',nargs='*');args=parser.parse_args()
    assert not active_source_workers(),'Migration requires production source workers to finish'
    installed=load_json(FOLDER/'installation.json')
    for name,h in installed['active_code_sha256'].items():assert file_hash(ROOT/name)==h,name
    historical=HistoricalInputs();compatibility=numerical_compatibility();state=State()
    selected=set(args.ids or historical.baseline['eligible_sources'])-set(historical.baseline['affected_sources'])
    assert selected<=set(historical.baseline['eligible_sources'])
    previous=previous_validation_module(historical);sources=[];cases=[]
    for sid in sorted(selected):
        sources.append(source_migration(sid,state,historical))
        for cid in historical.baseline['unaffected_accepted_cases']:
            old=historical.old_json(f'private/annotations/{cid}/case.json')
            if old['source_id']==sid:cases.append(case_migration(cid,state,historical,previous))
    complete_sources=sorted(path.stem for path in (FOLDER/'default_sources').glob('*.json'))
    complete_cases=sorted(path.stem for path in (FOLDER/'default_cases').glob('*.json'))
    expected_sources=sorted(set(historical.baseline['eligible_sources'])-set(historical.baseline['affected_sources']))
    status='pass_all_unchanged_sources_migrated' if complete_sources==expected_sources and complete_cases==historical.baseline['unaffected_accepted_cases'] else 'partial_resume_required'
    result={'status':status,'baseline_sha256':file_hash(FOLDER/'baseline.json'),'installation_sha256':file_hash(FOLDER/'installation.json'),'numerical_AST_compatibility':compatibility,'source_ids':complete_sources,'case_ids':complete_cases,'sources':{sid:file_hash(FOLDER/f'default_sources/{sid}.json') for sid in complete_sources},'cases':{cid:file_hash(FOLDER/f'default_cases/{cid}.json') for cid in complete_cases},'script_sha256':file_hash(Path(__file__)),'time':time.time()}
    atomic_json(FOLDER/'default_migration.json',result)
    atomic_json(ROOT/'state/sampling_density_v2.json',{'status':status,'proof_sha256':file_hash(FOLDER/'default_migration.json'),'production_permitted':False,'next':'Prepare affected-source cache mapping; independently audit migration and freeze v2 before production','time':time.time()})
    print(canonical_json({'status':status,'sources':len(complete_sources),'cases':len(complete_cases)}),flush=True)


if __name__=='__main__':main()
