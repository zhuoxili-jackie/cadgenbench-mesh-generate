"""Audit a finite snapshot of completed cases while production continues.

Only missing independent reports are queued. Each case uses the frozen audit
in its own hidden process; low available memory defers work to the main driver.
"""
from pathlib import Path
import argparse, json, os, subprocess, sys, time
import psutil

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'src'))
from scanbench.common import atomic_json, canonical_json, file_hash, load_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--first')
    args = parser.parse_args()
    for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS']:
        os.environ[key] = '2'
    folder = ROOT / 'reports/protocol_amendments/r4_continuous_free_space/cases'
    ready = [p.stem for p in sorted(folder.glob('*.json'))
             if load_json(p).get('status') == 'pass'
             and not (ROOT / f'reports/continuous_independent/{p.stem}.json').exists()]
    if args.first:
        if args.first not in ready:
            raise SystemExit('Requested first case has no missing completed-case audit')
        ready.remove(args.first)
        ready.insert(0, args.first)
    selected = ready[:args.limit]
    run = str(time.time_ns())
    rows = []
    status = 'snapshot_complete'
    for cid in selected:
        available = psutil.virtual_memory().available / 2**30
        if available < 3.0:
            status = 'deferred_to_main_pipeline_for_memory'
            break
        log = ROOT / f'logs/ready_continuous_{cid}_{run}.log'
        started = time.time()
        peak = 0
        print(canonical_json({'begin': cid, 'available_ram_gib': available}), flush=True)
        with log.open('w', encoding='utf-8') as stream:
            child = subprocess.Popen(
                [sys.executable, 'scripts/audit_continuous_revision.py', '--case-ids', cid],
                stdout=stream, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            while child.poll() is None:
                try:
                    process = psutil.Process(child.pid)
                    peak = max(peak, sum(p.memory_info().rss for p in [process, *process.children(recursive=True)] if p.is_running()))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                time.sleep(0.1)
        if child.returncode:
            raise RuntimeError(f'Independent audit failed for {cid}; inspect {log}')
        proof = ROOT / f'reports/continuous_independent/{cid}.json'
        assert load_json(proof)['status'] == 'pass'
        row = {'case_id': cid, 'seconds': time.time()-started,
               'peak_process_tree_rss_bytes': peak,
               'report': str(proof.relative_to(ROOT)).replace('\\', '/'),
               'report_sha256': file_hash(proof),
               'log': str(log.relative_to(ROOT)).replace('\\', '/'),
               'log_sha256': file_hash(log)}
        rows.append(row)
        print(canonical_json(row), flush=True)
    result = {'status': status, 'selected': selected, 'completed': rows,
              'script_sha256': file_hash(Path(__file__)),
              'audit_script_sha256': file_hash(ROOT/'scripts/audit_continuous_revision.py'),
              'time': time.time(), 'production_data_or_geometry_written': False}
    atomic_json(ROOT/f'reports/operations/ready_continuous_{run}.json', result)
    print(canonical_json({'status': status, 'completed': len(rows)}), flush=True)


if __name__ == '__main__':
    main()
