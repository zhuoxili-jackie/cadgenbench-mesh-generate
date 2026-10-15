from pathlib import Path
import json, sqlite3, shutil, time
ROOT=Path(__file__).resolve().parents[1]
db=sqlite3.connect(ROOT/'state/state.sqlite')
rows=db.execute('SELECT stage,status,COUNT(*) FROM stages GROUP BY stage,status').fetchall()
cases=db.execute("SELECT body FROM records WHERE kind='cases'").fetchall()
files=list((ROOT/'data/observations').glob('*.npz'))
print(json.dumps({'time':time.time(),'stages':rows,'cases':[{k:json.loads(r[0]).get(k) for k in ['case_id','source_id','level','seed','generation_status','validation_status']} for r in cases],
                  'observations_files':len(files),'observations_gib':sum(p.stat().st_size for p in files)/2**30,'disk_free_gib':shutil.disk_usage(ROOT).free/2**30},indent=2))
