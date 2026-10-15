"""Hidden subprocess with bounded numeric threads and a persistent append-only log."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
os.environ['PYTHONUTF8']='1';os.environ['PYTHONIOENCODING']='utf-8'
log=(ROOT/sys.argv[1]).resolve();assert log.is_relative_to(ROOT/'logs')
command=[sys.executable,*sys.argv[2:]]
with log.open('a',encoding='utf-8') as stream:
    result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
print({'returncode':result.returncode,'log':str(log)},flush=True);raise SystemExit(result.returncode)
