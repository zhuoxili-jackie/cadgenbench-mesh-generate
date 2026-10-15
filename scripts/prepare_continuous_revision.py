"""Preserve the full pre-correction state and artifact identities before any edit."""
from pathlib import Path
import os,sys,shutil,sqlite3
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *

folder=ROOT/'reports/protocol_amendments/r4_continuous_free_space';assert not folder.exists();folder.mkdir(parents=True)
frozen=load_json(ROOT/'reports/protocol_freeze.json')
for name,h in frozen['code_sha256'].items():
    assert file_hash(ROOT/name)==h,name
    target=folder/'before'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
shutil.copy2(ROOT/'reports/protocol_freeze.json',folder/'freeze_before.json')
shutil.copy2(ROOT/frozen['code_snapshot_path'],folder/'code_before.zip')
for name in ['cases','sources','failures']:
    shutil.copy2(ROOT/f'manifests/{name}.jsonl',folder/f'{name}_before.jsonl')
with sqlite3.connect(ROOT/'state/state.sqlite') as src,sqlite3.connect(folder/'state_before.sqlite') as dest:src.backup(dest)
shutil.copytree(ROOT/'private/annotations',folder/'annotations_before')
shutil.copytree(ROOT/'reports/visual_reviews',folder/'visual_reviews_before')
inventory={}
paths=[p for p in (ROOT/'data').rglob('*') if p.is_file()]
paths.extend(p for p in (ROOT/'private/gt').rglob('*') if p.is_file())
paths.extend(p for p in (ROOT/'private/scan_index').rglob('*') if p.is_file())
for i,p in enumerate(paths):
    inventory[str(p.relative_to(ROOT)).replace('\\','/')]={'sha256':file_hash(p),'mtime_ns':p.stat().st_mtime_ns,'bytes':p.stat().st_size}
    if i%5000==0:print(canonical_json({'inventoried':i,'total':len(paths)}),flush=True)
atomic_json(folder/'inventory_before.json',{'files':inventory,'count':len(inventory),'bytes':sum(x['bytes'] for x in inventory.values()),'code_revision':frozen['implementation_revision'],'no_formal_geometry_changed':True,'time':time.time()})
atomic_json(folder/'status.json',{'status':'candidate_evaluation_and_scope_audit','defect':'Source 243 easy seed 20261014: one independent area sample violates foreground free space; the 22-point per-triangle lattice missed a small conflicting interior region.','formal_data_unchanged':True,'physical_scan_and_quality_gates_unchanged':True,'next':'Finish every existing-Mesh continuous audit; preserve affected originals; install a uniformly applied observation-only continuous veto, revalidate affected downstream stages, and run fresh current-code reproduction/resume/export tests before sealing r4.'})
print(canonical_json({'status':'baseline_preserved','files':len(inventory)}))
