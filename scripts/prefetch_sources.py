"""Cache all fixed-revision STEP bytes, without touching production stage state."""
from pathlib import Path
import sys,os,urllib.request,time,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import IDS,REV,load_json,file_hash,atomic_bytes,atomic_json,canonical_json

tree=load_json(ROOT/'sources/upstream_tree.json')
entries={x['path'].split('/')[0]:x for x in tree if x['path'].endswith('/input.step')}
assert set(entries)==set(IDS)
rows=[]
for sid in IDS:
    expected=entries[sid]['lfs']['oid'];path=ROOT/f'sources/{sid}/input.step'
    cached=path.exists() and file_hash(path)==expected
    attempts=[]
    if not cached:
        url=f'https://huggingface.co/datasets/HuggingAI4Engineering/cadgenbench-data/resolve/{REV}/{sid}/input.step'
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url,timeout=90) as response:raw=response.read()
                assert hashlib.sha256(raw).hexdigest()==expected,'official LFS SHA256 mismatch'
                atomic_bytes(path,raw);break
            except Exception as exc:
                attempts.append({'attempt':attempt+1,'error':repr(exc)})
                atomic_json(ROOT/f'reports/source_cache_errors/{sid}.json',attempts)
                if attempt==3:raise
                time.sleep(2*(attempt+1))
    row={'source_id':sid,'sha256':file_hash(path),'expected_sha256':expected,'bytes':path.stat().st_size,'reused':cached,'failed_attempts':attempts}
    assert row['sha256']==expected
    rows.append(row)
    atomic_json(ROOT/'reports/source_cache.json',{'revision':REV,'verified_source_count':len(rows),'expected_source_count':32,'all_verified':len(rows)==32,'scope':'download integrity only; geometric eligibility is determined by production source preparation','sources':rows})
    print(canonical_json(row),flush=True)
