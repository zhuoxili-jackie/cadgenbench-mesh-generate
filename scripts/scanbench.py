from pathlib import Path
import os, sys
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
os.environ.setdefault('MKL_NUM_THREADS','2')
os.environ.setdefault('NUMBA_NUM_THREADS','2')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
os.chdir(ROOT)

def main():
    import argparse
    from scanbench.common import State,IDS
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['prepare-sources','scan','generate','reconstruct-case','validate','render','export-case'])
    p.add_argument('--ids',nargs='+')
    p.add_argument('--levels',nargs='+',default=['hard','medium','easy'])
    p.add_argument('--seeds',nargs='+',type=int,default=[20261014,20261015])
    p.add_argument('--input')
    p.add_argument('--output')
    p.add_argument('--case-ids',nargs='+')
    p.add_argument('--observations-only',action='store_true')
    p.add_argument('--all',action='store_true')
    p.add_argument('--pilot',action='store_true')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--force',action='store_true',help='force independent revalidation only')
    args=p.parse_args()
    if args.all and (args.ids or args.case_ids or args.pilot):p.error('--all cannot be combined with a subset or --pilot')
    if args.command=='prepare-sources':
        from scanbench.sources import prepare
        state=State()
        for sid in args.ids or IDS: prepare(sid,state)
    elif args.command=='scan':
        from scanbench.verified_placements import prepare_verified_placements
        from scanbench.scan import acquire_scans
        state=State()
        for sid in args.ids or ['218']:
            prepare_verified_placements(sid,state)
            acquire_scans(sid,state)
    elif args.command=='generate':
        from scanbench.cases import generate_case
        state=State()
        from scanbench.common import config
        if args.all and config()['status']!='frozen':p.error('full batch requires a frozen, passed pilot protocol')
        if args.all:
            import subprocess
            if set(args.levels)!=set(config()['difficulty']) or args.seeds!=config()['seeds']:p.error('--all requires all frozen levels and both seeds')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/run_full.py'),'--resume'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            raise SystemExit(result.returncode)
        selected=args.ids or (['218','231','229'] if args.pilot else IDS if args.all else ['218'])
        for sid in selected:
            for seed in args.seeds:
                for level in args.levels: generate_case(sid,level,seed,state)
    elif args.command=='reconstruct-case':
        from scanbench.reconstruct import reconstruct
        inp=Path(args.input)
        reconstruct(inp/'observations.json',inp/'cameras.json',inp/'reconstruction_config.json',args.output)
    elif args.command=='validate':
        import json
        from scanbench.validate import validate_case
        state=State()
        if args.all:
            from batch_scope import complete_batch_cases
            try:ids,_=complete_batch_cases(state)
            except (OSError,ValueError) as exc:raise SystemExit(f'Full-batch validation is incomplete: {exc}')
        elif args.case_ids:ids=args.case_ids
        else:p.error('validation requires explicit --all or --case-ids')
        if args.force:
            for cid in ids:state.db.execute("UPDATE stages SET status='pending' WHERE subject=? AND stage='validation'",(cid,))
            state.db.commit()
        results=[validate_case(cid,state) for cid in ids]
        if any(x['status']!='pass' for x in results): raise SystemExit(2)
    elif args.command=='render':
        from scanbench.render import render_case,render_gt
        state=State()
        ids=args.case_ids or [r[0] for r in state.db.execute("SELECT id FROM records WHERE kind='cases' ORDER BY id")]
        for cid in ids: print(render_case(cid))
        for sid in args.ids or []: print(render_gt(sid))
    elif args.command=='export-case':
        from scanbench.export import export_case
        if not args.case_ids or len(args.case_ids)!=1 or not args.output: p.error('one --case-ids and --output required')
        print(export_case(args.case_ids[0],args.output,args.observations_only))

if __name__=='__main__': main()
