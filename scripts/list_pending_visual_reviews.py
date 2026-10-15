"""List current generated hard/easy image pairs needing an actual direct review."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
from scanbench.cases import case_id,mesh_stage_key
state=State();ready=[]
revision=ROOT/'reports/protocol_amendments/r4_continuous_free_space'
baseline={json.loads(line)['case_id'] for line in (revision/'cases_before.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()}
for sid in IDS:
    ids=[case_id(sid,level,config()['seeds'][0]) for level in ['hard','easy']]
    current=True;items=[]
    for cid in ids:
        if cid in baseline and not (revision/f'cases/{cid}.json').exists():current=False;break
        out=ROOT/f'data/cases/{cid}/input';preview=ROOT/f'reports/private_previews/{cid}.png'
        accept=ROOT/f'private/annotations/{cid}/acceptance.json'
        if not preview.exists() or not accept.exists() or not state.valid(cid,'mesh',mesh_stage_key(out,config()['reconstruction'])) or load_json(accept)['status']!='pass':
            current=False;break
        ledger=state.db.execute("SELECT input_hash,status FROM stages WHERE subject=? AND stage='validation'",(cid,)).fetchone()
        if ledger is None or ledger[1]!='complete' or ledger[0]!=load_json(accept).get('validation_hash'):current=False;break
        mesh_hash=file_hash(out/'mesh.ply');preview_hash=file_hash(preview);marker=preview.with_suffix('.json')
        if not marker.exists():current=False;break
        marker=load_json(marker)
        if marker.get('mesh_sha256')!=mesh_hash or marker.get('preview_sha256')!=preview_hash or not state.valid(cid,'preview',marker['key']):current=False;break
        items.append({'case_id':cid,'mesh_sha256':mesh_hash,'preview_sha256':preview_hash,'preview':str(preview.relative_to(ROOT)).replace('\\','/')})
    if not current:continue
    old=ROOT/f'reports/visual_reviews/{sid}.json'
    old=load_json(old) if old.exists() else {'cases':[]}
    valid=len(old['cases'])==2 and all(any(x['case_id']==item['case_id'] and x['mesh_sha256']==item['mesh_sha256'] and x['preview_sha256']==item['preview_sha256'] for x in old['cases']) for item in items)
    if not valid:ready.append({'source_id':sid,'cases':items})
print(canonical_json({'pending_direct_reviews_ready':ready,'r4_baseline_cases_migrated':len(list((ROOT/'reports/protocol_amendments/r4_continuous_free_space/cases').glob('*.json')))}))
