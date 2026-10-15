"""Check orchestration-only extraction and real qualified-case reuse in a child."""
from pathlib import Path
import ast,json,os,subprocess,sys,time,copy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import atomic_json,file_hash,load_json

folder=ROOT/'reports/operations/case_process_isolation'
old=ast.parse((folder/'run_full_before.py').read_text(encoding='utf-8'))
new=ast.parse((ROOT/'scripts/run_full.py').read_text(encoding='utf-8'))
old_worker=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
old_loop=next(n for n in ast.walk(old_worker) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='level')
new_worker=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='case_worker')
comparable=copy.deepcopy(new_worker.body[6:]);review_dispatch_changes=0
for statement in comparable:
    for node in ast.walk(statement):
        if isinstance(node,ast.Constant) and node.value=='scripts/review_fragmentation_dispatch.py':
            node.value='scripts/review_fragmentation.py';review_dispatch_changes+=1
assert review_dispatch_changes<=1
assert [ast.dump(n) for n in old_loop.body]==[ast.dump(n) for n in comparable],'case execution logic changed beyond the explicitly recorded review dispatcher'
frozen=load_json(ROOT/'reports/protocol_freeze.json')
assert all(file_hash(ROOT/p)==h for p,h in frozen['code_sha256'].items())
cid='case_2438b1a3fd780c63'
out=ROOT/f'data/cases/{cid}/input'
paths=list(out.rglob('*'))+list((ROOT/f'private/annotations/{cid}').rglob('*'))+[ROOT/f'reports/private_previews/{cid}.png']
paths += [(out/f['path']).resolve() for f in load_json(out/'observations.json')['frames']]
def inventory():
    return {str(p.relative_to(ROOT)).replace('\\','/'): {'sha256':file_hash(p),'mtime_ns':p.stat().st_mtime_ns} for p in sorted(set(paths)) if p.is_file()}
before=inventory();started=time.time()
command=[sys.executable,str(ROOT/'scripts/run_full.py'),'--case-worker','218','hard','20261014']
with open(folder/'child.log','w',encoding='utf-8') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
after=inventory()
assert result.returncode==0,f'child failed: {result.returncode}'
assert before==after,'qualified files or mtimes changed'
assert all(file_hash(ROOT/p)==h for p,h in frozen['code_sha256'].items())
proof={'status':'pass','time':time.time(),'seconds':time.time()-started,'case_id':cid,'command':command,'case_logic_ast_identical_except_recorded_review_dispatch':True,'review_dispatch_path_changes':review_dispatch_changes,'frozen_core_unchanged':True,'qualified_files_unchanged':len(before),'inventory':before,'driver_sha256':file_hash(ROOT/'scripts/run_full.py'),'previous_driver_sha256':file_hash(folder/'run_full_before.py'),'child_log_sha256':file_hash(folder/'child.log'),'scope':'orchestration and cached reuse only; additional subpixel-review evidence is separately exercised on real affected cases; fresh case resource measurements remain in production stage events'}
atomic_json(folder/'proof.json',proof)
print(json.dumps({k:v for k,v in proof.items() if k!='inventory'}))
