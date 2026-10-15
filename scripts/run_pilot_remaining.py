from pathlib import Path
import sys,os,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2';os.environ['MKL_NUM_THREADS']='2'
from scanbench.common import *
from scanbench.sources import prepare
from scanbench.verified_placements import prepare_verified_placements
from scanbench.scan import acquire_scans
from scanbench.cases import generate_case
from scanbench.validate import validate_case
from scanbench.render_cached import preview

def main():
    state=State()
    for sid in ['229','231']:
        event('pilot_source_begin',source=sid)
        prepare(sid,state);prepare_verified_placements(sid,state);acquire_scans(sid,state)
        preview(sid,state,True)
        for seed in config()['seeds']:
            for level in ['hard','medium','easy']:
                cid=generate_case(sid,level,seed,state);result=validate_case(cid,state);preview(cid,state)
                if result['status']=='investigation_required':
                    subprocess.run([sys.executable,str(ROOT/'scripts/review_fragmentation.py'),cid],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    result=validate_case(cid,state)
                if result['status']!='pass':raise RuntimeError(f'{cid}: {result["status"]}; investigate before continuing pilot')
        event('pilot_source_complete',source=sid)
    # Refresh the first source against the final pilot validator without regenerating its geometry.
    prepare_verified_placements('218',state)
    for seed in config()['seeds']:
        for level in ['hard','medium','easy']:
            cid=generate_case('218',level,seed,state);result=validate_case(cid,state);preview(cid,state)
            if result['status']!='pass':raise RuntimeError(f'{cid}: {result["status"]}')
    event('pilot_18_generated_and_validated')

if __name__=='__main__':main()
