from pathlib import Path
import os,sys,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *
from scanbench.supplemental import source_factors,audit_case
p=argparse.ArgumentParser();p.add_argument('--ids',nargs='*');p.add_argument('--case-ids',nargs='*');p.add_argument('--all',action='store_true');args=p.parse_args();state=State()
if args.all:
    if args.ids or args.case_ids:p.error('--all cannot be combined with a subset')
    from batch_scope import complete_batch_cases
    try:cids,ids=complete_batch_cases(state)
    except (OSError,ValueError) as exc:raise SystemExit(f'Full-batch supplemental audit is incomplete: {exc}')
else:ids=args.ids or [];cids=args.case_ids or []
if not ids and not cids:p.error('choose --all, --ids, or --case-ids')
for sid in ids:source_factors(sid);print('source audit',sid,flush=True)
failed=[]
for cid in cids:
    r=audit_case(cid);print(cid,r['status'],flush=True)
    if r['status']!='pass':failed.append(cid)
if failed:raise SystemExit(f'failed: {failed}')
