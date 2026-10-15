"""Reports from one SQLite snapshot and verified on-disk files, never historical sums."""
import csv,html,io,sqlite3,shutil,time
from pathlib import Path
from .common import *

REQUIRED_TESTS=['units_scale','range_projection','contact_flip_path','transform_equivalence','noise','hole_contact_mesh',
                'compiled_support_equivalence','hash_partition_unit','atomic_interrupt','shared_frames_and_seeds',
                'no_gt_portable','full_case_reproduction','real_mesh_interruption',
                'actual_payload_integrity','topology_optimization_equivalence','production_resume_and_dependencies','topology_integer_width',
                'observation_grid_equivalence','support_early_exit_equivalence',
                'all_pose_sampling_control','all_pose_sampling_migration']

def required_test_path(name):
    freeze=ROOT/'reports/protocol_freeze.json'
    active=load_json(freeze).get('active_test_reports',{}) if freeze.exists() else {}
    return ROOT/active.get(name,f'reports/tests/{name}.json')

def report():
    from .validate import validation_fingerprint
    from .cases import mesh_stage_key
    db=sqlite3.connect(ROOT/'state/state.sqlite');db.execute('BEGIN')
    records={(k,i):json.loads(b) for k,i,b in db.execute('SELECT kind,id,body FROM records')}
    stages=[dict(zip(['subject','stage','input_hash','status','outputs','metrics','updated'],r)) for r in db.execute('SELECT * FROM stages')];db.close()
    sources={i:r for (k,i),r in records.items() if k=='sources'};cases={i:r for (k,i),r in records.items() if k=='cases'}
    ledger={(r['subject'],r['stage']):r for r in stages}
    gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text())
    tiers={tier:sorted(s for s in IDS if sources.get(s,{}).get('status')==tier) for tier in ['eligible_native','eligible_official_mesh_approx','source_excluded']}
    pending_sources=sorted(set(IDS)-set(sum(tiers.values(),[])));rows=[];errors=[];verified=[]
    for cid,rec in sorted(cases.items()):
        out=ROOT/rec['input_path'];accept=ROOT/f'private/annotations/{cid}/acceptance.json'
        a=load_json(accept) if accept.exists() else {};q=a.get('quality',{});m=a.get('mesh',{})
        outputs_ok=bool(rec.get('outputs')) and all((out/f).is_file() and file_hash(out/f)==h for f,h in rec.get('outputs',{}).items())
        if not outputs_ok:errors.append(f'{cid}: missing or changed generated outputs')
        validation_row=ledger.get((cid,'validation'),{})
        expected_validation=None
        try:
            expected_validation=validation_fingerprint(out,rec,gates)
        except (OSError,ValueError):pass
        current_validation=validation_row.get('status')=='complete' and validation_row.get('input_hash')==expected_validation and a.get('validation_hash')==expected_validation
        mesh_row=ledger.get((cid,'mesh'),{})
        expected_mesh=mesh_stage_key(out,config()['reconstruction']) if outputs_ok else None
        current_mesh=mesh_row.get('status')=='complete' and mesh_row.get('input_hash')==expected_mesh and rec.get('mesh_stage_hash')==expected_mesh
        status=a.get('status','pending') if outputs_ok and current_validation and current_mesh else ('pending' if outputs_ok else 'files_invalid')
        if status=='pass':verified.append(cid)
        row={'case_id':cid,'source_id':rec['source_id'],'precision_layer':rec['precision_layer'],'difficulty':rec['level'],'seed':rec['seed'],
             'placements':rec['placement_count'],'frames_per_placement':rec['frames_per_placement'],'resolution':rec['resolution'],
             'generation_status':rec['generation_status'],'acceptance_status':status,'mesh_support':q.get('mesh_observation_supported_fraction'),
             'observed_retention':q.get('observation_mesh_retained_fraction'),'total_gt_coverage':q.get('total_gt_surface_mesh_coverage'),
             'reachable_coverage':q.get('reference_reachable_mesh_coverage'),'vertices':m.get('vertices'),'faces':m.get('faces'),
             'boundary_length_mm':m.get('boundary_length_mm'),'nonmanifold_edges':m.get('nonmanifold_edges'),'nonmanifold_vertices':m.get('nonmanifold_vertices'),
             'largest_component_area_fraction':m.get('largest_component_area_fraction'),'tiny_component_area_fraction':m.get('tiny_component_area_fraction'),
             'tolerance_mm':q.get('tolerance_mm'),'preview':f'private_previews/{cid}.png','input_path':rec['input_path']}
        rows.append(row)
    csvtext=io.StringIO()
    if rows:
        writer=csv.DictWriter(csvtext,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    atomic_bytes(ROOT/'reports/quality_table.csv',csvtext.getvalue().encode('utf-8-sig'))
    tests={}
    for name in REQUIRED_TESTS:
        path=required_test_path(name);tests[name]=load_json(path) if path.exists() else {'status':'pending'}
    tests_ok=all(t.get('status')=='pass' or t.get('pass') is True for t in tests.values())
    atomic_json(ROOT/'reports/tests_report.json',{'all_required_currently_pass':tests_ok,'tests':tests,'active_reports':{name:str(required_test_path(name).relative_to(ROOT)).replace('\\','/') for name in REQUIRED_TESTS},'scope_note':'full-batch schema/manifest/export consistency and frozen protocol audit are additional final gates'})
    complete_sources=[sid for sid in IDS if len([r for cid,r in cases.items() if r['source_id']==sid and cid in verified])==6]
    # Reports never promote unfinished work. Final complete additionally requires an explicit final-audit file.
    final_audit=ROOT/'reports/final_audit.json'
    complete=(not pending_sources and len(verified)==6*(len(tiers['eligible_native'])+len(tiers['eligible_official_mesh_approx'])) and tests_ok and not errors and config()['status']=='frozen' and final_audit.exists() and load_json(final_audit).get('status')=='pass')
    summary={'status':'complete' if complete else 'in_progress','generated_case_count':sum(r['generation_status']=='generated' for r in cases.values()),
             'verified_case_count':len(verified),'six_case_complete_sources':complete_sources,'tiers':tiers,'pending_sources':pending_sources,'errors':errors,'timestamp':time.time()}
    atomic_json(ROOT/'reports/acceptance.json',summary)
    costs={}
    for s in stages:
        if s['status']!='complete':continue
        metrics=json.loads(s['metrics']);key=s['stage'];entry=costs.setdefault(key,{'current_successful_seconds':0.,'max_peak_rss_bytes':0,'stages':0})
        entry['current_successful_seconds']+=metrics.get('seconds',0);entry['max_peak_rss_bytes']=max(entry['max_peak_rss_bytes'],metrics.get('peak_rss_bytes',0));entry['stages']+=1
    sizes={}
    for dirname in ['data','private','sources','cache','tests','.venv','reports','vendor']:
        sizes[dirname]=sum(p.stat().st_size for p in (ROOT/dirname).rglob('*') if p.is_file()) if (ROOT/dirname).exists() else 0
    atomic_json(ROOT/'reports/performance.json',{'stages':costs,'directory_bytes':sizes,'disk_free_bytes':shutil.disk_usage(ROOT).free,'note':'stage times are current successful stages, excluding superseded calibration attempts; wall-clock goal time is reported separately','resource_policy':config()['resources']})
    groups=[]
    for sid in IDS:
        sr=[r for r in rows if r['source_id']==sid]
        if not sr:continue
        gt=f'private_previews/gt_{sid}.png';items=[]
        if (ROOT/'reports'/gt).exists():items.append(f'<a href="{gt}"><img src="{gt}" loading="lazy"><span>Private GT {sid}</span></a>')
        for r in sorted(sr,key=lambda x:(x['seed'],['hard','medium','easy'].index(x['difficulty']))):
            if (ROOT/'reports'/r['preview']).exists():items.append(f'<a href="{r["preview"]}"><img src="{r["preview"]}" loading="lazy"><span>{html.escape(r["difficulty"])} · {r["seed"]} · {r["acceptance_status"]}<br>{r["case_id"]}</span></a>')
        groups.append(f'<section><h2>Source {sid}</h2><div class="grid">'+''.join(items)+'</div></section>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>CADGenBench scan full-surface previews</title><style>body{font:16px system-ui;background:#edf1f5;color:#182b40;margin:32px}h1{margin-bottom:8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(450px,1fr));gap:18px}a{background:white;padding:10px;text-decoration:none;color:inherit;border-radius:8px}img{width:100%}span{display:block;padding:8px}section{margin:34px 0}.note{max-width:1000px;line-height:1.6}</style>'
    page+=f'<h1>CADGenBench physical scan previews</h1><p class="note">Status: {summary["status"]}. {summary["generated_case_count"]} meshes generated; {len(verified)} current acceptance passes. Every image ray-renders all triangles. Orange indicates reverse sides visible through openings. All GT/source mappings on this page are PRIVATE. Click an image for full resolution.</p>'+''.join(groups)+'</html>'
    atomic_bytes(ROOT/'reports/preview_index.html',page.encode())
    text=f'# CADGenBench scan progress\n\nStatus: **{summary["status"]}**. Generated {summary["generated_case_count"]} cases; current verified {len(verified)}. This is not a completion claim.\n\n'
    text+=f'Native sources: {tiers["eligible_native"]}. Official-mesh approximation: {tiers["eligible_official_mesh_approx"]}. Excluded: {tiers["source_excluded"]}. Pending: {pending_sources}.\n\n'
    text+='| Difficulty | Cases | Mean observed retention | Mean GT coverage |\n|---|---:|---:|---:|\n'
    for level in ['hard','medium','easy']:
        rr=[r for r in rows if r['difficulty']==level and r['observed_retention'] is not None]
        if rr:text+=f'| {level} | {len(rr)} | {np.mean([r["observed_retention"] for r in rr]):.6f} | {np.mean([r["total_gt_coverage"] for r in rr]):.6f} |\n'
    text+='\nQuality is measured at the reported millimetre tolerance. Small local meshing gaps below that scale remain visible; meshes are not artificially capped or completed. All observed points remain available for independent reconstruction.\n'
    atomic_bytes(ROOT/'reports/progress_report.md',text.encode())
    print(canonical_json(summary));return summary
