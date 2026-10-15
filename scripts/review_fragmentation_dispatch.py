"""Run the unchanged strict review, then a separately evidenced subpixel inquiry."""
from pathlib import Path
import os,sys,subprocess,json
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
cid=sys.argv[1]
def run(script):
    return subprocess.run([sys.executable,str(ROOT/'scripts'/script),cid],stdout=sys.stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).returncode
code=run('review_fragmentation.py')
if code==0:raise SystemExit(0)
if code!=2:raise SystemExit(code)
r=json.loads((ROOT/f'private/annotations/{cid}/fragmentation_review.json').read_text(encoding='utf-8'))
prerequisites=['all_hard_gates_passed','at_least_two_reference_regions','minor_unexplained_area_below_gate','observed_retention','organized_same_observations_retention','complete_trajectory']
if not all(r['checks'][k] for k in prerequisites) or r['reference_major_regions']<=len(r['component_correspondence']):raise SystemExit(2)
for script in ['diagnose_subpixel_regions.py','check_subpixel_raw_support.py','review_subpixel_regions.py','audit_subpixel_evidence.py']:
    code=run(script)
    if code:raise SystemExit(code)
