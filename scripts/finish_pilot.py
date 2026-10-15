"""Run the remaining current-code pilot proofs, then freeze and continue all 32."""
from pathlib import Path
import os,sys,subprocess,json,time
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
commands=[
    ['-m','pytest','tests','-q','--junitxml=reports/tests/final_pilot_pytest.xml'],
    ['scripts/run_control_mesh.py'],
    ['scripts/supplemental_audit.py','--all'],
    ['scripts/render_physical_plan.py','218','231','229'],
    ['scripts/run_portability.py'],
    ['scripts/run_reproduction.py'],
    ['scripts/run_mesh_resume.py'],
    ['scripts/benchmark_topology_cleanup.py','case_2438b1a3fd780c63','case_2034e1b703267ec0'],
    ['scripts/test_production_resume.py'],
    ['scripts/investigate_limited_poses.py','231'],
    ['scripts/write_pilot_report.py'],
    ['scripts/freeze_protocol.py'],
    ['scripts/bootstrap.py','doctor'],
    ['scripts/run_full.py','--resume'],
]
for i,command in enumerate(commands):
    print(f'PILOT/FULL pipeline {i+1}/{len(commands)}: {command}',flush=True)
    next_file=ROOT/'state/next_actions.json';tmp=next_file.with_name('next_actions.pipeline.partial')
    tmp.write_text(json.dumps({'goal_status':'active','coordinator_pid':os.getpid(),'time':time.time(),'current_stage':i+1,'current_command':[sys.executable,*command],'current_log':f'logs/finish_pilot_{i+1:02}.log','next_commands':commands[i+1:],'completed_stages':'Current SQLite stage hashes and individual reports are authoritative; no final completion before all 32 sources and independent final audit.','known_issues':'Any nonzero stage stops this pipeline for investigation; inspect the named log.'},indent=2),encoding='utf-8');os.replace(tmp,next_file)
    with open(ROOT/f'logs/finish_pilot_{i+1:02}.log','a',encoding='utf-8') as f:
        result=subprocess.run([sys.executable,*command],env=env,stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise SystemExit(f'stage {i+1} failed with exit {result.returncode}; inspect logs/finish_pilot_{i+1:02}.log; retained all prior evidence')
print('All requested generation complete; direct full image reviews and independent final audit remain.',flush=True)
