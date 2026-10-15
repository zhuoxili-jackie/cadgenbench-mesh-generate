"""Derive private per-case resource records from real stage ledgers and files.

Recorded numerical timings are retained; metadata-only stages and measurements
not taken in the historical run remain explicitly uninstrumented. File bytes
refer to current verified outputs, not an invented historical disk peak.
"""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *


def build():
    audit=load_json(ROOT/'reports/final_audit.json');assert audit['status']=='pass'
    state=State();cases={cid:json.loads(body) for cid,body in state.db.execute("SELECT id,body FROM records WHERE kind='cases'")}
    sources={sid:json.loads(body) for sid,body in state.db.execute("SELECT id,body FROM records WHERE kind='sources'")}
    assert len(sources)==32 and len(cases)==audit['actual_case_count']
    known_hashes=load_json(ROOT/'reports/final_file_inventory.json')['files']
    audited_inputs=load_json(ROOT/'reports/operations/full_acceptance_commands.json')['public_and_source_files_unchanged']
    historical={}
    for line in (ROOT/'state/events.jsonl').read_text(encoding='utf-8').splitlines():
        event_item=json.loads(line)
        if event_item.get('event')=='stage_complete' and ('seconds' in event_item.get('metrics',{}) or 'peak_rss_bytes' in event_item.get('metrics',{})):
            historical[(event_item['subject'],event_item['stage'])]={'time':event_item['time'],'metrics':event_item['metrics']}
    entries={};output_stats={}
    for subject,stage,key,status,outputs,body,updated in state.db.execute('SELECT * FROM stages ORDER BY subject,stage'):
        if subject not in set(IDS)|set(cases) and subject.split('/')[0] not in IDS:continue
        assert status=='complete',(subject,stage)
        metrics=json.loads(body);files={}
        for name,expected in json.loads(outputs).items():
            if name not in output_stats:
                path=ROOT/name;st=path.stat()
                if name in known_hashes and name in audited_inputs:
                    assert {'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}==audited_inputs[name],('file changed after full acceptance',name)
                    actual=known_hashes[name]
                else:actual=file_hash(path)
                assert actual==expected,(subject,stage,name)
                output_stats[name]={'sha256':actual,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
            assert output_stats[name]['sha256']==expected
            files[name]=output_stats[name]
        numeric=metrics.get('prior_numerical_stage_metrics',metrics)
        timing={'seconds':numeric.get('seconds',metrics.get('investigation_seconds')),'peak_rss_bytes':numeric.get('peak_rss_bytes'),'basis':'recorded current stage or explicitly retained numerical generation metrics'}
        if timing['seconds'] is None and timing['peak_rss_bytes'] is None:timing['basis']='metadata adoption/assembly stage not separately instrumented; no zero cost fabricated'
        record={'subject':subject,'stage':stage,'input_hash':key,'status':status,'recorded_metrics':metrics,'recorded_timing':timing,'current_unique_output_bytes':sum(item['bytes'] for item in files.values()),'outputs':files,'updated':updated}
        if (subject,stage) in historical:record['historical_last_timed_event']=historical[(subject,stage)]
        entries[subject+'::'+stage]=record
    source_profiles={sid:{stage:subject+'::'+stage for subject,stage in state.db.execute('SELECT subject,stage FROM stages WHERE subject=?',(sid,))} for sid in sources}
    case_profiles={}
    for cid,case in sorted(cases.items()):
        out=ROOT/case['input_path'];refs=load_json(out/'observations.json')['frames'];names={str((out/frame['path']).resolve().relative_to(ROOT)).replace('\\','/') for frame in refs}
        own={stage:cid+'::'+stage for subject,stage in state.db.execute('SELECT subject,stage FROM stages WHERE subject=?',(cid,))}
        for stage in ['mesh','validation','preview']:
            timing=entries[own[stage]]['recorded_timing']
            assert timing['seconds'] is not None and timing['peak_rss_bytes'] is not None,(cid,stage)
        profile={'schema':'case_resource_links_v1','case_id':cid,'source_id':case['source_id'],'case_input_path':case['input_path'],'case_stages':own,'shared_source_stages':source_profiles[case['source_id']],'shared_acquisition_stages':[case['source_id']+'/'+frame['camera_id']+'::observations' for frame in refs],'shared_observation_unique_files':len(names),'shared_observation_referenced_bytes':sum(output_stats[name]['bytes'] for name in names),'sampling_contract_sha256':file_hash(out/'sampling_contract.json'),'resource_table':'../../../reports/stage_resources.json','notes':['Acquisition stages generate both fixed seeds together and are shared across difficulty levels. Do not add per-case referenced bytes to estimate physical storage.','Each case numerical reconstruction, independent validation and render has recorded elapsed time and process RSS.','Source/placement metadata adoption and case-input assembly not separately measured are identified explicitly. Original historical timed events are kept separate from current stage costs.','Disk numbers are actual current output byte sizes, not historical temporary-disk peaks.']}
        assert all(name in entries for name in profile['shared_acquisition_stages'])
        path=ROOT/f'private/annotations/{cid}/resources.json';atomic_json(path,profile)
        case_profiles[cid]={'path':path.relative_to(ROOT).as_posix(),'sha256':file_hash(path)}
    result={'status':'pass','schema':'current_stage_resource_inventory_v1','case_count':len(cases),'source_count':len(sources),'stages':entries,'cases':case_profiles,'sources':source_profiles,'unique_stage_output_bytes':sum(item['bytes'] for item in output_stats.values()),'unique_stage_output_files':len(output_stats),'final_audit_sha256':file_hash(ROOT/'reports/final_audit.json'),'case_manifest_sha256':file_hash(ROOT/'manifests/cases.jsonl'),'source_manifest_sha256':file_hash(ROOT/'manifests/sources.jsonl'),'script_sha256':file_hash(Path(__file__)),'time':time.time(),'scope':'Actual private resource links for every current case. Numeric stages retain measured timings/RSS; shared-source/historical telemetry remains clearly labelled; output bytes are verified current files.'}
    atomic_json(ROOT/'reports/stage_resources.json',result)
    return result


if __name__=='__main__':
    result=build();print(canonical_json({key:value for key,value in result.items() if key not in ['stages','cases','sources']}))
