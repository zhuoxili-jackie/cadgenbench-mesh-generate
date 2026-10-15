"""Full read-only inventory/acceptance audit. Never creates or repairs a mesh."""
from pathlib import Path
import os,sys,json,sqlite3,itertools,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.cases import case_id,mesh_stage_key
from scanbench.scan import observation_hash
from scanbench.validate import validation_fingerprint
from scanbench.reporting import REQUIRED_TESTS,report,required_test_path
from scanbench.supplemental import audit_case

def main():
    started=time.time();errors=[];cfg=config();frozen=load_json(ROOT/'reports/protocol_freeze.json');gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text());state=State()
    def check(value,message):
        if not value:errors.append(message)
    check(cfg['status']=='frozen' and digest(cfg)==frozen['protocol_config_sha256'],'protocol config differs from freeze')
    check(file_hash(ROOT/'configs/quality_gates.yaml')==frozen['quality_gates_sha256'],'quality gates differ from freeze')
    check(frozen.get('implementation_revision')=='r4_continuous_free_space','current continuous free-space correction is not frozen')
    for path,h in frozen['code_sha256'].items():check(file_hash(ROOT/path)==h,f'frozen code changed: {path}')
    check(file_hash(ROOT/frozen.get('code_snapshot_path','reports/frozen_protocol_code.zip'))==frozen['code_snapshot_sha256'],'active frozen code snapshot mismatch')
    for item in frozen.get('implementation_amendments',[]):
        p=ROOT/item['path'];check(file_hash(p)==item['sha256'],'implementation amendment changed');change=load_json(p)
        check(change['status']=='passed_implementation_correction' and not change['physical_protocol_or_quality_gates_changed'],'unverified implementation correction')
        for name,h in change['evidence_sha256'].items():check(file_hash(ROOT/name)==h,f'implementation correction evidence changed: {name}')
    for name,h in frozen.get('implementation_tests_sha256',{}).items():check(file_hash(ROOT/name)==h and load_json(ROOT/name)['status']=='pass',f'implementation compatibility test failed/stale: {name}')
    hp=load_json(ROOT/'reports/tests/hull_pose_proposals.json')
    check(hp.get('status')=='pass' and hp.get('proposal_code_sha256')==file_hash(ROOT/'scripts/hull_pose_proposals.py') and hp.get('test_script_sha256')==file_hash(ROOT/'scripts/test_hull_pose_proposals.py'),'finite hull proposal control test failed/stale')
    for item in hp.get('tests',[]):
        if 'source' in item:check(file_hash(ROOT/f'private/gt/{item["source"]}/mesh.npz')==item['mesh_sha256'],f'{item["source"]}: hull proposal regression input changed')
    manifests={}
    for name,key in [('sources','source_id'),('cases','case_id'),('failures','source_id')]:
        path=ROOT/f'manifests/{name}.jsonl';rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else [];ids=[r[key] for r in rows];check(len(ids)==len(set(ids)),f'duplicate {name} manifest IDs');manifests[name]={r[key]:r for r in rows}
        dbrows={i:json.loads(b) for i,b in state.db.execute('SELECT id,body FROM records WHERE kind=?',(name,))};check(manifests[name]==dbrows,f'{name} manifest not equal to authoritative snapshot')
    sources=manifests['sources'];cases=manifests['cases'];check(set(sources)==set(IDS),'not every one of the 32 official sources has a conclusion')
    eligible=[s for s,r in sources.items() if r['status'] in ['eligible_native','eligible_official_mesh_approx']];expected={case_id(s,l,n) for s in eligible for l in cfg['difficulty'] for n in cfg['seeds']};check(set(cases)==expected,'case set differs from eligible sources x 3 levels x 2 seeds');check({p.name for p in (ROOT/'data/cases').iterdir() if p.is_dir()}==expected,'actual public case directories differ from manifest')
    tests={}
    for name in REQUIRED_TESTS:
        p=required_test_path(name);r=load_json(p) if p.exists() else {};check(r.get('status')=='pass' or r.get('pass') is True,f'missing/failed test {name}');tests[name]=file_hash(p) if p.exists() else None
    cid=case_id('218','hard',cfg['seeds'][0]);inp=ROOT/f'data/cases/{cid}/input';mh=file_hash(inp/'mesh.ply');oh=file_hash(inp/'observations.json');ch=file_hash(ROOT/'src/scanbench/reconstruct.py')
    signature_ch=digest([ch,file_hash(ROOT/'src/scanbench/continuous_free_space.py')])
    for name,sig in [('no_gt_portable',digest([mh,signature_ch,oh])),('full_case_reproduction',digest([mh,oh,signature_ch])),('real_mesh_interruption',digest([mh,signature_ch]))]:check(load_json(required_test_path(name))['signature']==sig,f'stale current-code evidence {name}')
    obs_seen={};file_inventory={};levels={};limited=[];natural=[];feature_limits=[];nonmonotonic=[];discrete_supports=[];subpixel_limits=[];bounds_corrections=[];reference_scale_adjustments=[];mesher_adjustments=[]
    cli_path=ROOT/'reports/operations/full_cli_scope/proof.json';cli_scope=load_json(cli_path)
    check(cli_scope['status']=='pass' and cli_scope['full_batch_incomplete_rejected_by_real_commands'] and cli_scope['export_branch_AST_identical'],'CLI scope regression check failed')
    check(cli_scope['script_sha256']==file_hash(ROOT/'scripts/test_full_cli_scope.py'),'CLI scope test changed')
    for name,h in {**cli_scope['changed_scripts_sha256'],**cli_scope['before_scripts_sha256']}.items():check(file_hash(ROOT/name)==h,f'CLI scope evidence changed: {name}');file_inventory[name]=h
    for item in cli_scope['checks']:check(file_hash(ROOT/item['log'])==item['log_sha256'],'CLI scope command log changed')
    file_inventory[str(cli_path.relative_to(ROOT)).replace('\\','/')]=file_hash(cli_path)
    full_cli_path=ROOT/'reports/operations/full_acceptance_commands.json';full_cli=load_json(full_cli_path)
    check(full_cli['status']=='pass' and full_cli['source_conclusions']==32 and full_cli['case_count']==len(cases) and set(full_cli['eligible_sources'])==set(eligible),'actual full CLI acceptance scope differs')
    check([row['command'] for row in full_cli['commands']]==[['scripts/scanbench.py','validate','--all'],['scripts/supplemental_audit.py','--all']],'actual full validation commands differ')
    for row in full_cli['commands']:
        check(row['exit_code']==0 and file_hash(ROOT/row['log'])==row['log_sha256'],'actual full validation command failed or its log changed');file_inventory[row['log']]=row['log_sha256']
    for name,h in full_cli['script_sha256'].items():check(file_hash(ROOT/name)==h,f'full CLI acceptance code changed: {name}');file_inventory[name]=h
    actual_cli_inputs={str(path.relative_to(ROOT)).replace('\\','/'):{'bytes':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns} for directory in ['data','sources'] for path in (ROOT/directory).rglob('*') if path.is_file()}
    check(actual_cli_inputs==full_cli['public_and_source_files_unchanged'] and digest([actual_cli_inputs,full_cli['script_sha256']])==full_cli['signature'],'full CLI public/source input preservation proof differs')
    file_inventory[str(full_cli_path.relative_to(ROOT)).replace('\\','/')]=file_hash(full_cli_path)
    isolation_dir=ROOT/'reports/operations/case_process_isolation';isolation_path=isolation_dir/'proof.json';isolation=load_json(isolation_path)
    check(isolation.get('status')=='pass' and isolation.get('case_logic_ast_identical_except_recorded_review_dispatch') is True and isolation.get('frozen_core_unchanged') is True,'case-process isolation proof failed')
    for path,key in [(ROOT/'scripts/run_full.py','driver_sha256'),(isolation_dir/'run_full_before.py','previous_driver_sha256'),(isolation_dir/'child.log','child_log_sha256')]:
        check(file_hash(path)==isolation[key],f'case-process isolation evidence changed: {path.name}');file_inventory[str(path.relative_to(ROOT)).replace('\\','/')]=file_hash(path)
    check(len(isolation['inventory'])==isolation['qualified_files_unchanged'],'case-process isolation file count differs')
    from audit_continuous_revision import historical_file_verified,audit_case as audit_continuous_case,audit_baseline_inventory
    for name,entry in isolation['inventory'].items():
        path=ROOT/name;check(historical_file_verified(name,entry),f'case-process isolation original evidence missing or changed without explicit r4 archive: {name}');file_inventory[name]=file_hash(path)
    file_inventory[str(isolation_path.relative_to(ROOT)).replace('\\','/')]=file_hash(isolation_path)
    # Re-read the actual independent experiment outputs, not just PASS markers.
    from scanbench.validate import read_mesh
    original_proof_mesh=read_mesh(inp/'mesh.ply')
    for test,folder_field,relative_mesh in [
        ('no_gt_portable','public_export_directory','rebuilt/mesh.ply'),
        ('full_case_reproduction','fresh_directory',f'data/cases/{cid}/input/mesh.ply'),
        ('real_mesh_interruption','experiment_directory','rebuilt/mesh.ply')]:
        try:
            proof=load_json(required_test_path(test));folder=(ROOT/proof[folder_field]).resolve()
            check(folder.is_relative_to(ROOT/'tests/artifacts'),f'{test}: proof directory escaped task artifacts')
            result_mesh=folder/relative_mesh;actual=read_mesh(result_mesh)
            check(np.array_equal(original_proof_mesh.vertices,actual.vertices) and np.array_equal(original_proof_mesh.faces,actual.faces),f'{test}: actual experiment geometry changed or differs')
            file_inventory[str(result_mesh.relative_to(ROOT)).replace('\\','/')]=file_hash(result_mesh)
            if test!='full_case_reproduction':
                for module in ['common.py','camera.py','reconstruct.py','observed_kernel.py','continuous_free_space.py']:
                    copied=folder/'src/scanbench'/module
                    check(file_hash(copied)==file_hash(ROOT/'src/scanbench'/module),f'{test}: copied reconstruction code is stale: {module}')
                    file_inventory[str(copied.relative_to(ROOT)).replace('\\','/')]=file_hash(copied)
            if test=='no_gt_portable':
                access_path=ROOT/proof['audit_log'];opened=load_json(access_path)['opened']
                check(not any(Path(p).is_relative_to(ROOT/q) for p in opened for q in ['private','sources','data']),f'{test}: forbidden original input read in actual access log')
                file_inventory[str(access_path.relative_to(ROOT)).replace('\\','/')]=file_hash(access_path)
            if test=='real_mesh_interruption':
                check(bool(proof.get('actual_owned_process_tree_killed')) and proof.get('all_descendants_verified_exited'),f'{test}: actual process-tree interruption evidence missing')
                fusion=folder/'rebuilt/.reconstruction_cache/fusion.npz'
                check([file_hash(fusion),fusion.stat().st_mtime_ns]==proof['fusion_before'],f'{test}: completed fusion checkpoint changed')
        except Exception as exc:errors.append(f'{test}: unreadable actual proof artifact: {exc}')
    delivery_export_path=ROOT/frozen['delivery_export_evidence']
    try:
        export_proof=load_json(delivery_export_path);folder=(ROOT/export_proof['destination']).resolve()
        check(folder.is_relative_to(ROOT) and folder.name=='exported_case_r4','delivery export escaped its declared directory')
        check(export_proof['status']=='pass' and export_proof['no_mesh_supplied'] and export_proof['initial_output_empty'],'delivery export was not an empty observation-only reconstruction')
        check(export_proof['script_sha256']==file_hash(ROOT/export_proof['checker_script']),'delivery command checker changed')
        check(export_proof['case_id']==cid and export_proof['source_mesh_sha256']==mh and export_proof['reconstruction_code_sha256']==ch,'delivery command proof input or code differs')
        check(export_proof['continuous_module_sha256']==file_hash(ROOT/'src/scanbench/continuous_free_space.py'),'delivery continuous module changed')
        for module,h in export_proof['copied_code_sha256'].items():check(file_hash(folder/'src/scanbench'/module)==h==file_hash(ROOT/'src/scanbench'/module),f'delivery copied code differs: {module}')
        check(export_proof['commands'][0][1:]==['scripts/scanbench.py','export-case','--case-ids',cid,'--output','exported_case_r4','--observations-only'] and export_proof['commands'][1][1:]==['exported_case_r4/rebuild.py'],'verified public commands differ')
        for name,key in [('export.json','export_manifest_sha256'),('access_audit.json','access_audit_sha256'),('rebuilt/mesh.ply','rebuilt_mesh_sha256')]:
            path=folder/name;check(file_hash(path)==export_proof[key],f'delivery export artifact changed: {name}');file_inventory[str(path.relative_to(ROOT)).replace('\\','/')]=file_hash(path)
        for name,h in load_json(folder/'export.json')['files'].items():
            path=(folder/name).resolve()
            check(path.is_relative_to(folder) and not path.is_symlink() and file_hash(path)==h,f'delivery exported input differs: {name}')
            file_inventory[str(path.relative_to(ROOT)).replace('\\','/')]=h
        check(not (folder/'private').exists() and not (folder/'sources').exists(),'private source geometry present in delivery export')
        access=load_json(folder/'access_audit.json')
        check(access['initial_output_empty'] and access['forbidden_reads']==0 and not any(Path(p).is_relative_to(ROOT/q) for p in access['opened'] for q in ['private','sources','data']),'delivery rebuild read original private/source/data paths')
        rebuilt=read_mesh(folder/'rebuilt/mesh.ply')
        check(np.array_equal(original_proof_mesh.vertices,rebuilt.vertices) and np.array_equal(original_proof_mesh.faces,rebuilt.faces),'actual delivered export reconstruction differs')
        for log in export_proof['logs']:
            check(file_hash(ROOT/log['path'])==log['sha256'],'delivery command log changed');file_inventory[log['path']]=log['sha256']
        file_inventory[str(delivery_export_path.relative_to(ROOT)).replace('\\','/')]=file_hash(delivery_export_path)
    except Exception as exc:errors.append(f'delivery public command proof unreadable: {exc}')
    official={x['path'].split('/')[0]:x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path'].endswith('/input.step')}
    validity_path=ROOT/'reports/source_validity_scope.json';validity=load_json(validity_path)
    mode_path=ROOT/'reports/tests/brep_checker_modes.json';mode_controls=load_json(mode_path)
    check(mode_controls['status']=='pass' and mode_controls['script_sha256']==file_hash(ROOT/'scripts/test_brep_checker_modes.py') and not mode_controls['source_or_reference_geometry_modified'],'default/exact BREP checker controls failed or changed')
    from OCP.BRepTools import BRepTools
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shape
    from OCP.BRepCheck import BRepCheck_Analyzer
    check({item['name'] for item in mode_controls['controls']}=={'box','cylinder','sphere'},'BREP checker analytic controls incomplete')
    for item in mode_controls['controls']:
        path=ROOT/item['brep_path'];check(file_hash(path)==item['brep_sha256'],'actual BREP checker control changed')
        shape=TopoDS_Shape();BRepTools.Read_s(shape,os.path.relpath(path),BRep_Builder())
        check(not shape.IsNull() and all(BRepCheck_Analyzer(shape,True,False,exact).IsValid() for exact in [False,True]),'actual analytic BREP checker control failed after rereading')
        file_inventory[item['brep_path']]=file_hash(path)
    file_inventory[str(mode_path.relative_to(ROOT)).replace('\\','/')]=file_hash(mode_path)
    check(validity['status']=='all32_diagnostics_complete' and validity['no_source_or_geometry_modified'],'independent source-validity diagnostic is incomplete')
    check(validity['script_sha256']==file_hash(ROOT/'scripts/audit_all_source_validity.py') and validity['checker_script_sha256']==file_hash(ROOT/'scripts/investigate_brep_validity.py'),'source-validity diagnostic code changed')
    validity_rows={row['source_id']:row for row in validity['sources']}
    check(set(validity_rows)==set(IDS) and len(validity['sources'])==len(IDS),'source-validity diagnostic does not cover exactly all32')
    parameter_warnings=[]
    for sid,row in validity_rows.items():
        check(row['source_sha256']==official[sid],'independent source-validity provenance differs')
        for name,h in row['evidence_sha256'].items():check(file_hash(ROOT/name)==h,f'{sid}: source-validity evidence changed');file_inventory[name]=h
        if sid in eligible:check(row['ordinary_valid'],f'{sid}: independent default BREP validity failed')
        if row['ordinary_valid'] and not row['extra_exact_parameter_valid']:parameter_warnings.append(sid)
    file_inventory[str(validity_path.relative_to(ROOT)).replace('\\','/')]=file_hash(validity_path)
    parameter_quantification=[]
    for sid in ['244','245','246','247','248','249','250']:
        folder=ROOT/f'reports/source_investigations/{sid}';curve_path=folder/'curve_on_surface_probe_0.json';locus_path=folder/'locus_all_flagged_pairs.json'
        curve=load_json(curve_path);locus=load_json(locus_path)
        check(curve['source_sha256']==locus['source_sha256']==official[sid] and locus['prior_same_parameter_report_sha256']==file_hash(curve_path),f'{sid}: parameter diagnostic provenance changed')
        check(locus['no_geometry_or_tolerance_modified'] and locus['script_sha256']==file_hash(ROOT/'scripts/probe_parameterization_locus.py'),f'{sid}: parameter-locus diagnostic code changed')
        check(len(curve['pairs'])==len(locus['pairs']) and all(x['raw_exact_done'] and x['raw_exact_error']==0 for x in curve['pairs']),f'{sid}: parameter diagnostic is incomplete')
        row={'source_id':sid,'flagged_edge_face_pairs':len(curve['pairs']),'max_same_parameter_disagreement_mm':max(x['raw_exact_distance'] for x in curve['pairs']),'max_sampled_locus_distance_mm':locus['max_sampled_locus_distance_mm'],'locus_distance_is_sampled_not_global_hausdorff':True,'evidence':str(locus_path.relative_to(ROOT)).replace('\\','/')}
        parameter_quantification.append(row)
        for path in [curve_path,locus_path]:file_inventory[str(path.relative_to(ROOT)).replace('\\','/')]=file_hash(path)
    for sid,rec in sources.items():
        check(file_hash(ROOT/f'sources/{sid}/input.step')==official[sid]==rec['source_sha256'],f'{sid}: official STEP provenance mismatch')
        if rec['status']=='source_excluded':
            check(bool(rec.get('reason')) and len(rec.get('attempts',[]))>=2,f'{sid}: exclusion lacks evidence')
            check(bool(rec.get('evidence_sha256')),f'{sid}: exclusion lacks bound files')
            for name,h in rec.get('evidence_sha256',{}).items():
                check(file_hash(ROOT/name)==h,f'{sid}: exclusion evidence changed: {name}');file_inventory[name]=h
            check(load_json(ROOT/rec['evidence_summary'])['status']=='source_excluded',f'{sid}: missing explicit disposition')
            continue
        check(rec.get('brep_valid') is True and rec.get('source_length_units') and rec.get('internal_unit')=='millimetre',f'{sid}: reference lacks a valid unit-tagged STEP')
        check(rec.get('accuracy_check',{}).get('max_sampled_mm',float('inf'))<=max(.021,rec['chord_mm']*1.1),f'{sid}: reference exceeds its declared accuracy')
        boundary_info=rec.get('boundary_accuracy',{});qualification_path=ROOT/boundary_info['qualification'];qualification=load_json(qualification_path);boundary_path=ROOT/boundary_info['report'];boundary=load_json(boundary_path)
        check(file_hash(qualification_path)==boundary_info['qualification_sha256'] and file_hash(boundary_path)==boundary_info['report_sha256'],f'{sid}: boundary accuracy manifest binding differs')
        boundary_inputs={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [ROOT/f'sources/{sid}/input.step',ROOT/f'private/gt/{sid}/mesh.npz',ROOT/f'private/gt/{sid}/metadata.json',ROOT/f'private/gt/{sid}/placements.json']}
        boundary_code={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [ROOT/'scripts/qualify_boundary_audits.py',ROOT/'scripts/audit_reference_boundary.py',ROOT/'scripts/audit_discrete_boundary.py']}
        boundary_environment={p:__import__('importlib.metadata',fromlist=['version']).version(p) for p in ['cadquery-ocp','numpy','trimesh']};boundary_key=digest([boundary_inputs,boundary_code,boundary_environment])
        check(qualification['status']=='pass' and qualification['key']==boundary_key and state.valid(sid,'reference_boundary_audit',boundary_key),f'{sid}: missing/current boundary qualification stage')
        check(boundary['status']=='pass' and boundary['source_sha256']==rec['source_sha256'] and boundary['reference_sha256']==file_hash(ROOT/f'private/gt/{sid}/mesh.npz') and boundary['reference_tier']==rec['status'],f'{sid}: boundary reference provenance or result differs')
        check(len(boundary['boundary_distances_mm'])==128 and np.isfinite(boundary['boundary_distances_mm']).all() and max(boundary['boundary_distances_mm'])==boundary_info['sampled_max_mm']<=max(.021,rec['chord_mm']*1.1),f'{sid}: actual sampled boundary accuracy fails')
        for name,h in qualification['evidence_sha256'].items():
            check(file_hash(ROOT/name)==h,f'{sid}: independent boundary evidence changed: {name}');file_inventory[name]=h
        file_inventory[str(qualification_path.relative_to(ROOT)).replace('\\','/')]=file_hash(qualification_path)
        if rec.get('qualification_method'):
            proof=load_json(ROOT/rec['evidence_summary'])
            check(proof.get('status')=='pass' and proof.get('source_sha256')==rec['source_sha256'] and proof.get('precision_tier')==rec['status'],f'{sid}: unverified alternative reference qualification')
            if proof.get('qualification_route')=='native_boundary_retry':
                trigger_path=ROOT/proof['trigger_evidence'];trigger=load_json(trigger_path)
                check(trigger['status']=='reference_precision_requires_investigation' and trigger['source_sha256']==rec['source_sha256'] and trigger['reference_sha256']==file_hash(trigger_path.parent/'mesh.npz'),f'{sid}: missing actual rejected boundary reference')
                check(trigger['sampled_max_mm']>trigger['native_or_approx_bound_mm'] and bool(rec.get('attempts')) and all(a['status']=='failed' for a in rec['attempts']),f'{sid}: boundary retry lacks recorded failed precision')
                check(proof['accuracy_check']['max_sampled_mm']<=proof['accuracy_limit_mm'] and 'CAD boundary faces' in proof['accuracy_check']['method'],f'{sid}: retry did not use boundary accuracy')
                if rec['status']=='eligible_official_mesh_approx':
                    check(all(any((a['chord_mm'],a['angle_rad'])==pair for a in rec['attempts']) for pair in [(.02,.15),(.01,.075),(.02,.3)]),f'{sid}: boundary fallback skipped native alternatives')
            else:
                check(len(rec.get('attempts',[]))>=3 and all(a['status']=='failed' for a in rec['attempts']),f'{sid}: alternative reference lacks native attempts')
            for name,h in rec.get('evidence_sha256',{}).items():
                check(file_hash(ROOT/name)==h,f'{sid}: reference qualification evidence changed: {name}');file_inventory[name]=h
            if proof.get('mesher_overrides'):
                control_path=ROOT/'reports/tests/native_surface_control.json';controls=load_json(control_path)
                check(controls['status']=='pass' and controls['only_five_mesher_parameters_changed_ast'] and controls['unchanged_original_topology_stitching_ast'] and not controls['source_geometry_repair_performed'],f'{sid}: strict native mesher controls failed')
                check(controls['mesher_override_sha256']==proof['mesher_override_sha256']==file_hash(ROOT/'tools/native_surface_control/native_surface_control_mesh.py') and controls['original_vendor_sha256']==proof['original_vendor_sha256']==file_hash(ROOT/'vendor/cadgenbench/common/mesh.py'),f'{sid}: strict native mesher source binding changed')
                check(controls['test_script_sha256']==file_hash(ROOT/'scripts/test_native_surface_control.py'),f'{sid}: strict native mesher test code changed')
                check(proof['mesher_overrides']=={'DeflectionInterior':rec['chord_mm']/2,'AngleInterior':rec['angle_rad']/2,'MinSize':1e-7,'AdjustMinSize':True,'ForceFaceDeflection':True},f'{sid}: native mesher parameters differ from recorded policy')
                import trimesh
                for control in controls['controls']:
                    path=ROOT/control['mesh_path'];check(file_hash(path)==control['mesh_sha256'],f'{sid}: actual native control geometry changed')
                    with np.load(path) as z:mesh=trimesh.Trimesh(z['vertices'],z['faces'],process=False)
                    points,_=trimesh.sample.sample_surface(mesh,2048,seed=243)
                    if control['name']=='box':
                        distances=np.min(np.minimum(abs(points),abs(points-np.array([11.,17.,23.]))),axis=1)
                        check(np.allclose(mesh.bounds,[[0,0,0],[11,17,23]],rtol=0,atol=1e-9),f'{sid}: box control dimensions differ')
                    else:
                        radius=np.linalg.norm(points[:,:2],axis=1);height=points[:,2];inside=(radius<=10)&(height>=0)&(height<=25)
                        distances=np.where(inside,np.minimum.reduce([10-radius,height,25-height]),np.hypot(np.maximum(radius-10,0),np.maximum.reduce([-height,height-25,np.zeros(len(height))])))
                    check(mesh.is_watertight and mesh.is_winding_consistent and float(distances.max())<=control['limit_mm'] and abs(float(distances.max())-control['analytic_max_distance_mm'])<=1e-12,f'{sid}: fresh analytic native control audit failed')
                    file_inventory[control['mesh_path']]=file_hash(path)
                file_inventory[str(control_path.relative_to(ROOT)).replace('\\','/')]=file_hash(control_path)
                mesher_adjustments.append({'source_id':sid,'chord_mm':rec['chord_mm'],'angle_rad':rec['angle_rad'],'parameters':proof['mesher_overrides'],'sampled_boundary_max_mm':boundary['sampled_max_mm'],'evidence':rec['evidence_summary'],'controls':'reports/tests/native_surface_control.json'})
            if proof.get('bounds_correction_evidence'):
                bounds_path=ROOT/proof['bounds_correction_evidence'];bounds_proof=load_json(bounds_path)
                check(file_hash(bounds_path)==proof['bounds_correction_sha256'] and bounds_proof['status']=='pass' and bounds_proof['source_sha256']==rec['source_sha256'],f'{sid}: exact-bounds evidence differs')
                check(bounds_proof['script_sha256']==file_hash(ROOT/'scripts/audit_axis_plane_bounds.py') and not bounds_proof['source_or_topology_modifications'],f'{sid}: exact-bounds implementation differs')
                check(len(bounds_proof['controls'])==2 and all(x['max_error_mm']<=1e-7 for x in bounds_proof['controls']) and len(bounds_proof['queries'])==6,f'{sid}: exact-bounds geometric controls missing')
                from audit_axis_plane_bounds import measure as measure_axis_bounds
                from scanbench.sources import read_step
                actual_shape,_=read_step(ROOT/f'sources/{sid}/input.step');actual_bounds,witnesses=measure_axis_bounds(actual_shape,bounds_proof['legacy_AddOptimal_bounds_source_mm'])
                check(np.allclose(actual_bounds,bounds_proof['exact_bounds_source_mm'],rtol=0,atol=1e-7) and np.allclose(actual_bounds,rec['bounds_source_mm'],rtol=0,atol=1e-7),f'{sid}: freshly measured CAD extrema differ')
                with np.load(ROOT/proof['mesh_path']) as candidate_mesh:
                    v=candidate_mesh['vertices'];actual_mesh_bounds=np.stack([v.min(axis=0),v.max(axis=0)])
                actual_error=float(np.max(abs(actual_mesh_bounds-actual_bounds)))
                check(abs(actual_error-proof['bounds_max_difference_mm'])<=1e-7 and actual_error<=proof['bounds_limit_mm'],f'{sid}: actual reference bounds fail corrected CAD comparison')
                bounds_corrections.append({'source_id':sid,'legacy_overestimate_mm':bounds_proof['legacy_max_overestimate_mm'],'actual_reference_bounds_error_mm':actual_error,'evidence':proof['bounds_correction_evidence'],'fresh_six_plane_queries':len(witnesses)})
                if rec.get('reference_scale_rationale'):
                    rationale=rec['reference_scale_rationale']
                    if rec['status']=='eligible_native':check(rec['chord_mm']==rationale['declared_reference_chord_mm']<=rationale['sensor_sigma_mm']/2+1e-12,f'{sid}: reference-scale physical rationale differs')
                    reference_scale_adjustments.append({'source_id':sid,'tier':rec['status'],'chord_mm':rec['chord_mm'],'sampled_boundary_max_mm':boundary['sampled_max_mm'],'rationale':rationale,'evidence':rec['evidence_summary']})
            with np.load(ROOT/proof['mesh_path']) as original,np.load(ROOT/f'private/gt/{sid}/mesh.npz') as canonical:
                check(np.array_equal(original['triangles'],canonical['faces']) and np.array_equal(transform(original['vertices'],rec['T_object_from_source_mm']),canonical['vertices']),f'{sid}: qualified reference was changed beyond the declared rigid transform')
            if rec['status']=='eligible_official_mesh_approx':
                expected_sidecar=next(x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path']==f'{sid}/input.mesh.npz')
                check(file_hash(ROOT/f'sources/{sid}/input.mesh.npz')==expected_sidecar==rec['official_mesh_sha256'],f'{sid}: official approximate reference provenance mismatch')
                check(proof['original_linear_deflection_mm']==rec['original_linear_deflection_mm'] and proof['subdivision_performed'] is False,f'{sid}: approximate curvature precision misrepresented')
        elif rec['status']=='eligible_official_mesh_approx':check(False,f'{sid}: approximate reference lacks a recorded qualification')
        gt=ROOT/f'private/gt/{sid}';placement_audit=load_json(gt/'placement_audit.json');places=load_json(gt/'placements.json')
        expected_audit_key=stage_hash([file_hash(ROOT/f'sources/{sid}/input.step'),file_hash(gt/'placements.json'),file_hash(gt/'features.json')],{},['placement_audit.py','contact_support.py'],['cadquery-ocp','numpy'])
        check(placement_audit['status']=='pass' and placement_audit['key']==expected_audit_key,f'{sid}: no current physical placement audit')
        discrete=[p for p in places['placements'] if p.get('contact_kind')=='certified_discrete_CAD_contacts']
        if discrete:
            from scanbench.contact_support import audit_discrete_placement
            path=ROOT/places['discrete_contact_integration'];integration=load_json(path)
            check(integration['status']=='pass' and integration['placements_sha256']==file_hash(gt/'placements.json') and integration['source_sha256']==rec['source_sha256'],f'{sid}: stale discrete-contact integration evidence')
            integration_script=integration.get('script','scripts/integrate_discrete_poses.py')
            check(integration_script in ['scripts/integrate_discrete_poses.py','scripts/integrate_zero_area_contacts.py'],f'{sid}: unreviewed contact-integration route')
            check(integration['contact_code_sha256']==file_hash(ROOT/'src/scanbench/contact_support.py') and integration['script_sha256']==file_hash(ROOT/integration_script),f'{sid}: discrete-contact implementation binding differs')
            file_inventory[str(path.relative_to(ROOT)).replace('\\','/')]=file_hash(path)
            for name,h in integration['evidence_sha256'].items():
                check(file_hash(ROOT/name)==h,f'{sid}: discrete-contact evidence changed: {name}');file_inventory[name]=h
            for p in discrete:
                proof=audit_discrete_placement(sid,p);check(proof['status']=='pass' and p['actual_contact_area_mm2']==0,f'{sid}: independent final discrete-contact check failed')
                discrete_supports.append({'source_id':sid,'placement_id':p['placement_id'],'actual_contact_area_mm2':0,'certified_contact_points':len(p['contact_vertex_ids']),'support_polygon_area_mm2':proof['support_polygon_area_mm2'],'COM_margin_mm':proof['stability_margin_mm'],'evidence':str(path.relative_to(ROOT)).replace('\\','/')})
        audit=load_json(ROOT/f'reports/source_audits/{sid}.json');check(audit['status']=='pass',f'{sid}: factor/unit audit failed')
        mono_path=ROOT/f'reports/monotonicity/{sid}.json';mono=load_json(mono_path) if mono_path.exists() else {}
        check(mono.get('status')=='pass' and mono.get('geometric_visibility_nested'),f'{sid}: missing/failed coverage monotonicity audit')
        check(mono.get('source_sha256')==rec['source_sha256'] and mono.get('reference_sha256')==file_hash(ROOT/f'private/reference/{sid}/evaluation.npz') and mono.get('script_sha256')==file_hash(ROOT/'scripts/audit_monotonicity.py'),f'{sid}: stale monotonicity evidence')
        check(set(mono.get('cases',{}))=={case_id(sid,l,s) for l in cfg['difficulty'] for s in cfg['seeds']},f'{sid}: monotonicity audit does not cover all six cases')
        for mc,detail in mono.get('cases',{}).items():
            q=load_json(ROOT/f'private/annotations/{mc}/acceptance.json')['quality']
            check(detail['mesh_sha256']==file_hash(ROOT/f'data/cases/{mc}/input/mesh.ply') and detail['coverage']==q['total_gt_surface_mesh_coverage'] and detail['tolerance_mm']==q['tolerance_mm'],f'{mc}: stale coverage comparison')
        for pair in mono.get('nonmonotonic',[]):
            check(file_hash(ROOT/pair['distance_evidence'])==pair['distance_evidence_sha256'] and pair['physical_visibility_points_lost']==0,f'{sid}: missing coverage-decrease explanation')
            nonmonotonic.append(pair)
        if audit['not_three_poses']:
            proof_path=ROOT/f'private/gt/{sid}/limited_pose_investigation.json';proof=load_json(proof_path) if proof_path.exists() else {}
            check(proof.get('status')=='only_existing_poses_certified',f'{sid}: limited-pose candidate investigation missing or additional candidate unresolved')
            check(proof.get('source_sha256')==rec['source_sha256'] and proof.get('placements_sha256')==file_hash(ROOT/f'private/gt/{sid}/placements.json') and proof.get('script_sha256')==file_hash(ROOT/'scripts/investigate_limited_poses.py'),f'{sid}: stale limited-pose proof')
            check(proof.get('proposal_code_sha256')==file_hash(ROOT/'scripts/hull_pose_proposals.py'),f'{sid}: stale hull proposal implementation')
            limited.append({'source_id':sid,'actual_placements':audit['actual_stable_placements'],'candidate_audit':str(proof_path.relative_to(ROOT)).replace('\\','/'),'extra_candidates_checked':proof.get('nonduplicate_nonplanar_candidates_checked'),'scope':proof.get('scope')})
        review_path=ROOT/f'reports/visual_reviews/{sid}.json';review=load_json(review_path) if review_path.exists() else {};check(review.get('status')=='pass',f'{sid}: direct hard/easy image inspection missing')
        for image in review.get('cases',[]):
            check(file_hash(ROOT/image['preview'])==image['preview_sha256'] and file_hash(ROOT/f'data/cases/{image["case_id"]}/input/mesh.ply')==image['mesh_sha256'],f'{sid}: stale direct image review')
    continuous_results=[]
    for cid,rec in sorted(cases.items()):
        try:
            out=ROOT/rec['input_path'];a=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');key=validation_fingerprint(out,rec,gates);check(a['status']=='pass' and a['validation_hash']==key and state.valid(cid,'validation',key),f'{cid}: independent acceptance stale/failed');check(rec['protocol_config_sha256']==digest(cfg),f'{cid}: old protocol metadata')
            current_mesh_key=mesh_stage_key(out,cfg['reconstruction']);check(rec['mesh_stage_hash']==current_mesh_key and state.valid(cid,'mesh',current_mesh_key),f'{cid}: obsolete reconstruction stage')
            continuous=audit_continuous_case(cid);check(continuous['status']=='pass',f'{cid}: continuous geometry/witness audit failed');continuous_results.append({'case_id':cid,'removed_faces':continuous['removed_faces'],'removed_area_fraction':load_json(out/'continuous_veto.json')['removed_area_fraction']})
            cp=ROOT/f'reports/continuous_independent/{cid}.json';file_inventory[str(cp.relative_to(ROOT)).replace('\\','/')]=file_hash(cp)
            for name,h in rec['outputs'].items():check(file_hash(out/name)==h,f'{cid}: output mismatch {name}');file_inventory[str((out/name).relative_to(ROOT)).replace('\\','/')]=h
            for name in ['README.json','cameras.json','observations.json','reconstruction_config.json']:
                file_inventory[str((out/name).relative_to(ROOT)).replace('\\','/')]=file_hash(out/name)
            extra=audit_case(cid);check(extra['status']=='pass',f'{cid}: supplemental feature failure');feature_limits.extend({'case_id':cid,**f} for f in extra['all_cylindrical_passages']['features'] if f['status']=='below_declared_resolution')
            if a.get('natural_separation_evidence'):natural.append(cid)
            if (a.get('natural_separation_evidence') or {}).get('review_kind')=='quantified_subpixel_reference_region_join':
                from audit_subpixel_evidence import audit as audit_subpixel_evidence
                subpixel_limits.append(audit_subpixel_evidence(cid))
            preview=ROOT/f'reports/private_previews/{cid}.png';check(preview.exists(),f'{cid}: missing full-surface preview')
            if preview.exists():file_inventory[str(preview.relative_to(ROOT)).replace('\\','/')]=file_hash(preview)
            refs=load_json(out/'observations.json');cams={c['id']:c for c in load_json(out/'cameras.json')['cameras']};check(len(refs['frames'])==len(cams),f'{cid}: camera/frame count mismatch')
            for fr in refs['frames']:
                p=(out/fr['path']).resolve();check(p.is_relative_to(ROOT/'data/observations'),f'{cid}: non-public observation path');ph=str(p.relative_to(ROOT)).replace('\\','/')
                if ph not in obs_seen:
                    with np.load(p) as d:
                        pixel=d['pixel'];ran=d['range_mm'];check(pixel.dtype==np.uint32 and ran.dtype==np.float32,f'{ph}: dtype');check(len(pixel)==len(ran) and np.isfinite(ran).all(),f'{ph}: invalid arrays');actual=observation_hash(pixel,ran);n=len(pixel)
                    obs_seen[ph]={'array_sha256':actual,'file_sha256':file_hash(p),'count':n};file_inventory[ph]=obs_seen[ph]['file_sha256']
                v=obs_seen[ph];check(v['array_sha256']==fr['array_sha256'] and v['file_sha256']==fr['file_sha256'] and v['count']==fr['count'],f'{cid}: observation manifest mismatch')
            levels.setdefault(rec['level'],[]).append({'mesh_support':a['quality']['mesh_observation_supported_fraction'],'observed_retention':a['quality']['observation_mesh_retained_fraction'],'GT_coverage':a['quality']['total_gt_surface_mesh_coverage']})
        except Exception as exc:errors.append(f'{cid}: {type(exc).__name__}: {exc}')
    actual_obs={str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'data/observations').glob('*.npz')};check(actual_obs==set(obs_seen),'public observation inventory has missing or unreferenced payloads')
    for sid,failure in manifests['failures'].items():check(failure['status']=='resolved',f'{sid}: unresolved historical failure')
    for subject,stage,key,status,outputs in state.db.execute('SELECT subject,stage,input_hash,status,outputs FROM stages'):
        if subject not in set(IDS)|expected and subject.split('/')[0] not in IDS:continue
        check(status=='complete',f'{subject}/{stage}: unfinished stage remains')
        for path,h in json.loads(outputs).items():
            try:check((file_inventory[path] if path in file_inventory else file_hash(ROOT/path))==h,f'{subject}/{stage}: stage artifact changed {path}')
            except OSError:errors.append(f'{subject}/{stage}: missing stage artifact {path}')
    for sid in eligible:
        for seed in cfg['seeds']:
            refs=[{f['camera_id']:f for f in load_json(ROOT/f'data/cases/{case_id(sid,l,seed)}/input/observations.json')['frames']} for l in ['hard','medium','easy']]
            check(set(refs[0])<=set(refs[1])<=set(refs[2]),f'{sid}/{seed}: frames not nested')
            check(all(v==refs[i+1][k] for i in range(2) for k,v in refs[i].items()),f'{sid}/{seed}: shared frame differs')
        for level in cfg['difficulty']:
            aa,bb=[ROOT/f'data/cases/{case_id(sid,level,s)}/input' for s in cfg['seeds']];check(file_hash(aa/'cameras.json')==file_hash(bb/'cameras.json'),f'{sid}/{level}: seed changed cameras');check(file_hash(aa/'mesh.ply')!=file_hash(bb/'mesh.ply'),f'{sid}/{level}: duplicated seeded mesh')
    baseline_audit={}
    try:
        r4=ROOT/'reports/protocol_amendments/r4_continuous_free_space';baseline_ids={json.loads(line)['case_id'] for line in (r4/'cases_before.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()}
        check(len(baseline_ids)==129 and {p.stem for p in (r4/'cases').glob('*.json')}==baseline_ids,'not every original case has an explicit r4 migration proof')
        check(load_json(r4/'remaining_migration.json')['status']=='pass','remaining baseline migration incomplete')
        for original_cid in baseline_ids:
            proof=load_json(r4/f'cases/{original_cid}.json');check(proof['status']=='pass' and proof['new_mesh_sha256']==file_hash(ROOT/f'data/cases/{original_cid}/input/mesh.ply'),f'{original_cid}: stale migration proof')
        baseline_audit=audit_baseline_inventory();check(baseline_audit['status']=='pass','upstream baseline preservation failed')
        file_inventory[str((r4/'full_inventory_audit.json').relative_to(ROOT)).replace('\\','/')]=file_hash(r4/'full_inventory_audit.json')
    except Exception as exc:errors.append(f'r4 whole-baseline preservation: {type(exc).__name__}: {exc}')
    summary={l:{k:{'min':min(v[k] for v in rows),'mean':float(np.mean([v[k] for v in rows])),'max':max(v[k] for v in rows)} for k in rows[0]} for l,rows in levels.items()}
    atomic_json(ROOT/'reports/final_file_inventory.json',{'files':file_inventory,'count':len(file_inventory),'digest':digest(file_inventory)})
    result={'status':'pass' if not errors else 'failed','errors':errors,'source_count':len(sources),'eligible_source_count':len(eligible),'actual_case_count':len(cases),'actual_unique_observations':len(obs_seen),'all_32_attempted':set(sources)==set(IDS),'quality_by_difficulty':summary,'limited_placements':limited,'natural_separation_cases':natural,'below_resolution_features':feature_limits,'test_report_hashes':tests,'file_inventory_sha256':file_hash(ROOT/'reports/final_file_inventory.json'),'seconds':time.time()-started,'time':time.time(),'scope':'all sources, cases, actual payload arrays, complete PLY/STL/point provenance acceptance, shared observations, seed difference, tests and direct image-review evidence; no generation or repair'}
    result['nonmonotonic_mesh_coverage']=nonmonotonic
    result['certified_discrete_supports']=discrete_supports
    result['subpixel_region_join_limits']=subpixel_limits
    result['axis_plane_bounds_corrections']=bounds_corrections
    result['reference_scale_adjustments']=reference_scale_adjustments
    result['native_reference_mesher_adjustments']=mesher_adjustments
    result['source_validity_diagnostics']={'default_validity_method':'Frozen OCCT BRepCheck_Analyzer default geometry checks; reference topology and sampled boundary precision are qualified independently. Extra continuous same-parameter checks are a separately reported source limitation.','evidence':'reports/source_validity_scope.json','analytic_controls':'reports/tests/brep_checker_modes.json','all32_checked':True,'ordinary_valid_sources':[sid for sid,row in validity_rows.items() if row['ordinary_valid']],'extra_exact_parameter_warnings':parameter_warnings,'additional_quantification':parameter_quantification,'no_source_tolerance_or_geometry_modified':True,'extra_checks_are_not_claimed_to_pass':True}
    result['delivery_export_command_evidence']=str(delivery_export_path.relative_to(ROOT)).replace('\\','/')
    result['continuous_free_space_correction']={'cases':continuous_results,'affected_cases':sum(x['removed_faces']>0 for x in continuous_results),'removed_faces':sum(x['removed_faces'] for x in continuous_results),'max_case_removed_area_fraction':max((x['removed_area_fraction'] for x in continuous_results),default=0),'all_removed_faces_independently_justified':len(continuous_results)==len(cases),'baseline_preservation':baseline_audit}
    atomic_json(ROOT/'reports/monotonicity/summary.json',{'status':'pass' if not errors else 'failed','sources':eligible,'nonmonotonic_pairs':nonmonotonic,'formal_scores_unchanged':True})
    atomic_json(ROOT/'reports/final_audit.json',result);report();print(canonical_json({k:v for k,v in result.items() if k not in ['below_resolution_features','test_report_hashes','quality_by_difficulty','nonmonotonic_mesh_coverage']}))
    if errors:raise SystemExit(2)

if __name__=='__main__':main()
