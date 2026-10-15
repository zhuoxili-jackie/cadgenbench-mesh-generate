"""Wait for the old pilot worker, then perform the proved camera-key migration."""
from pathlib import Path
import os,sys,time,subprocess,psutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
pid=int(sys.argv[1]);started=None
try:started=psutil.Process(pid).create_time()
except psutil.NoSuchProcess:pass
while started is not None:
    try:
        if psutil.Process(pid).create_time()!=started:break
    except psutil.NoSuchProcess:break
    time.sleep(10)
env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2')
for name,args in [('sampling_migration',['scripts/migrate_sampling_contract.py']),('pilot_remaining_v6',['scripts/run_pilot_remaining.py']),('finish_pilot',['scripts/finish_pilot.py'])]:
    print('START '+name,flush=True)
    with open(ROOT/f'logs/{name}.log','a',encoding='utf-8') as f:
        result=subprocess.run([sys.executable,*args],env=env,stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise SystemExit(f'{name} failed ({result.returncode}); inspect retained evidence and resume')
    print('COMPLETE '+name,flush=True)
