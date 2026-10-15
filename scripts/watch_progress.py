"""Small read-only heartbeat; does not infer completion from elapsed time."""
from pathlib import Path
import os,json,time,argparse,shutil,sqlite3,collections
import psutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
def read(path):
    try:return json.loads((ROOT/path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
def snapshot():
    phase=read('state/r4_pipeline.json');migration=read('reports/protocol_amendments/r4_continuous_free_space/migration_dispatch.json')
    cid=migration.get('current_case') if phase.get('stage')=='remaining_migration' else None
    case=read(f'private/annotations/{cid}/case.json') if cid else {}
    directories=list((ROOT/'data/cases').glob('case_*'))
    pairs=sum(all((path/'input'/name).is_file() and (path/'input'/name).stat().st_size>0 for name in ['mesh.ply','mesh.stl']) for path in directories)
    result={'time':time.time(),'pipeline_status':phase.get('status'),'stage':phase.get('stage'),'baseline_cases_migrated':len(list((ROOT/'reports/protocol_amendments/r4_continuous_free_space/cases').glob('*.json'))),'initialized_case_directories':len(directories),'actual_nonempty_ply_stl_pairs':pairs,'independent_continuous_reports':len(list((ROOT/'reports/continuous_independent').glob('case_*.json'))),'extra_source_validity_checks':len(read('reports/source_validity_scope.json').get('sources',[])),'available_ram_gib':round(psutil.virtual_memory().available/2**30,3),'free_disk_gib':round(shutil.disk_usage(ROOT).free/2**30,3)}
    current=read('state/sampling_completion_pipeline.json')
    if current:
        result.update(original_pipeline_status=phase.get('status'),pipeline_status=current.get('status'),stage=current.get('phase'),sampling_protocol=read('reports/protocol_freeze.json').get('physical_protocol_revision'))
    with sqlite3.connect(f'file:{(ROOT/"state/state.sqlite").as_posix()}?mode=ro',uri=True) as database:
        cases=[json.loads(row[0]) for row in database.execute("SELECT body FROM records WHERE kind='cases'")]
        sources=[json.loads(row[0]) for row in database.execute("SELECT body FROM records WHERE kind='sources'")]
        passed=[case for case in cases if case.get('validation_status')=='pass' and read(f'private/annotations/{case["case_id"]}/supplemental.json').get('status')=='pass']
        counts=collections.Counter(case['source_id'] for case in passed)
        result.update(cases_with_current_recorded_primary_and_supplemental_pass=len(passed),six_case_sources=sum(n==6 for n in counts.values()),formal_source_dispositions=len(sources),source_tiers=dict(collections.Counter(source['status'] for source in sources)),note='Progress counters are read-only; final hash/array/independent acceptance remains separate')
    if cid:result.update(case=cid,source=case.get('source_id'),level=case.get('level'))
    if phase.get('stage')=='remaining_sources' or current:
        event=read('state/next_actions.json').get('last_event',{})
        result['last_event']={key:event[key] for key in ['event','stage','subject','source','case','level','seed','time'] if key in event}
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--interval',type=float,default=45);p.add_argument('--minutes',type=float,default=30);p.add_argument('--once',action='store_true');args=p.parse_args();end=time.monotonic()+args.minutes*60
    while True:
        value=snapshot();print(json.dumps(value,ensure_ascii=False),flush=True)
        if args.once or time.monotonic()>=end or value['pipeline_status']!='running':break
        time.sleep(args.interval)
