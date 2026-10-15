"""Finish the current source, qualify exact acceleration, then continue the full source queue."""
from pathlib import Path
import os,sys,time,subprocess,json,psutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
waiting=[]
for pid in [6616,7472]:
    try:
        process=psutil.Process(pid);cmd=process.cmdline()
        assert any(a.endswith(('test_fusion_merge_candidate.py','run_full.py')) for a in cmd)
        waiting.append(process)
    except psutil.NoSuchProcess:pass
while any(p.is_running() for p in waiting):
    time.sleep(5)
result=json.loads((ROOT/'state/source_runs/201.json').read_text());assert result['status']=='six_cases_generated_and_accepted','201 source needs investigation before optimization install'
commands=[
 ['scripts/test_fusion_merge_candidate.py','--all-existing'],
 ['scripts/install_fusion_merge_optimization.py'],
 ['scripts/migrate_fusion_merge_caches.py'],
 ['scripts/run_portability.py'],
 ['scripts/run_reproduction.py'],
 ['scripts/run_mesh_resume.py'],
 ['scripts/test_production_resume.py'],
 ['scripts/record_fusion_merge_amendment.py'],
 ['scripts/bootstrap.py','doctor'],
 ['scripts/run_full.py','--resume','--ids',*'202 203 204 205 206 207 208 209 211 212 214 215 217 224 225 230 238 240 241 242 243 244 245 246 247 248 249 250'.split()],
]
for i,command in enumerate(commands,1):
    status={'goal_status':'active','coordinator_pid':os.getpid(),'time':time.time(),'current_stage':i,'current_command':command,'current_log':f'logs/fusion_revision_{i:02}.log','next_commands':commands[i:],'scope':'exact implementation optimization and full remaining source generation; final independent audit and direct image reviews still required'}
    path=ROOT/'state/next_actions.json';tmp=path.with_name('next_actions.coordinator.partial');tmp.write_text(json.dumps(status,indent=2),encoding='utf-8');os.replace(tmp,path)
    print(json.dumps(status),flush=True)
    with open(ROOT/f'logs/fusion_revision_{i:02}.log','a',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,*command],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise SystemExit(f'Stage {i} failed, investigate logs/fusion_revision_{i:02}.log; all previous evidence retained')
print('Generation queue finished; complete independent audit and delivery before goal completion.',flush=True)
