"""Read-only checks defining full official batch scope for validation CLIs."""
import json
from scanbench.common import ROOT,IDS,config
from scanbench.cases import case_id,mesh_stage_key

def complete_batch_cases(state):
    sources={sid:json.loads(body) for sid,body in state.db.execute("SELECT id,body FROM records WHERE kind='sources'")}
    valid={'eligible_native','eligible_official_mesh_approx','source_excluded'}
    pending=[sid for sid in IDS if sources.get(sid,{}).get('status') not in valid]
    if pending or set(sources)!=set(IDS):raise ValueError(f'full batch has unresolved source conclusions: {pending}')
    eligible=[sid for sid in IDS if sources[sid]['status'].startswith('eligible_')]
    cfg=config();expected={case_id(sid,level,seed) for sid in eligible for level in cfg['difficulty'] for seed in cfg['seeds']}
    records={cid:json.loads(body) for cid,body in state.db.execute("SELECT id,body FROM records WHERE kind='cases'")}
    if set(records)!=expected:raise ValueError(f'full batch case set differs: missing={sorted(expected-set(records))}, unexpected={sorted(set(records)-expected)}')
    for cid,record in records.items():
        out=ROOT/record['input_path'];key=mesh_stage_key(out,cfg['reconstruction'])
        if record.get('generation_status')!='generated' or record.get('mesh_stage_hash')!=key or not state.valid(cid,'mesh',key):raise ValueError(f'{cid}: current complete Mesh stage is missing or invalid')
    return sorted(expected),eligible
