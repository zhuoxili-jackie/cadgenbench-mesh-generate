"""Continue untouched source jobs while source 245 receives a versioned density revision."""
from pathlib import Path
import os, sys, subprocess
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'src'))
for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS']:
    os.environ[key] = '2'
from scanbench.common import *

frozen = load_json(ROOT / 'reports/protocol_freeze.json')
assert digest(config()) == frozen['protocol_config_sha256']
for name, value in frozen['code_sha256'].items():
    assert file_hash(ROOT / name) == value, name
command = ['scripts/run_full.py', '--resume', '--ids', '246', '247', '248', '249', '250']
status = {'status': 'running', 'stage': 'remaining_sources', 'command': command, 'pending_density_revision_source': '245', 'time': time.time()}
atomic_json(ROOT / 'state/r4_pipeline.json', status)
log = ROOT / 'logs/remaining_unaffected_246_250.log'
with log.open('a', encoding='utf-8') as stream:
    result = subprocess.run([sys.executable, *command], stdout=stream, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
status.update(status='unaffected_sources_finished_density245_pending' if result.returncode == 0 else 'needs_investigation_not_exclusion', returncode=result.returncode, log=str(log.relative_to(ROOT)).replace('\\', '/'), time=time.time())
atomic_json(ROOT / 'state/r4_pipeline.json', status)
print(canonical_json(status), flush=True)
raise SystemExit(result.returncode)
