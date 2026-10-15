"""Current-code, no-change production resume without overwriting prior revision proofs."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.sources import prepare
from scanbench.verified_placements import prepare_verified_placements
from scanbench.scan import acquire_scans
from scanbench.cases import generate_case,case_id
from scanbench.validate import validate_case
from scanbench.supplemental import audit_case,source_factors
state=State();sid='218';subjects={sid,*[case_id(sid,l,n) for l in config()['difficulty'] for n in config()['seeds']]};paths=set()
for subject,outputs in state.db.execute("SELECT subject,outputs FROM stages WHERE status='complete'"):
    if subject in subjects or subject.startswith(sid+'/'):paths.update(json.loads(outputs))
before={p:[file_hash(ROOT/p),(ROOT/p).stat().st_mtime_ns] for p in paths}
prepare(sid,state);prepare_verified_placements(sid,state);acquire_scans(sid,state);source_factors(sid)
for seed in config()['seeds']:
    for level in config()['difficulty']:
        cid=generate_case(sid,level,seed,state);assert validate_case(cid,state)['status']=='pass';assert audit_case(cid)['status']=='pass'
after={p:[file_hash(ROOT/p),(ROOT/p).stat().st_mtime_ns] for p in paths};assert before==after
atomic_json(ROOT/'reports/tests/discrete_contact_production_resume.json',{'status':'pass','source_id':sid,'cases':6,'qualified_files':len(before),'all_qualified_hashes_and_mtimes_unchanged':True,'files':before,'code_sha256':{p.name:file_hash(p) for p in (ROOT/'src/scanbench').glob('*.py')},'script_sha256':file_hash(Path(__file__))});print('Current discrete-contact implementation: unchanged production resume passed.')
