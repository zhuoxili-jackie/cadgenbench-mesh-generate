"""Wait for real pilot completion, seal checked evidence, then continue the full scope."""
from pathlib import Path
import os,sys,time,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
marker=ROOT/'reports/protocol_amendments/r4_continuous_free_space/pilot_migration.json'
while not marker.exists():
    live=False
    for p in psutil.process_iter(['name','cmdline']):
        try:
            argv=p.info['cmdline'] or []
            if p.info['name']=='python.exe' and any(Path(x).name=='run_continuous_migration.py' for x in argv) and '--pilot' in argv and Path(p.cwd()).resolve()==ROOT:live=True
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    assert live,'Pilot is incomplete and its worker exited; inspect logs before proceeding'
    time.sleep(2)
assert load_json(marker)['status']=='pass'
for script in ['record_continuous_amendment.py','run_r4_completion_pipeline.py']:
    print(canonical_json({'running':script,'time':time.time()}),flush=True)
    result=subprocess.run([sys.executable,'scripts/'+script],stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,(script,result.returncode)
