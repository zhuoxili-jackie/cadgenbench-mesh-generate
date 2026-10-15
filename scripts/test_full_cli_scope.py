"""Exercise incomplete real-batch rejection and prove export behavior unchanged."""
from pathlib import Path
import os,sys,ast,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
folder=ROOT/'reports/operations/full_cli_scope';frozen=load_json(ROOT/'reports/protocol_freeze.json')
for name,h in frozen['code_sha256'].items():assert file_hash(ROOT/name)==h
def export_body(path):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.If) and ast.unparse(node.test)=="args.command == 'export-case'":return ast.dump(ast.Module(body=node.body,type_ignores=[]),include_attributes=False)
    raise AssertionError('Export branch missing')
assert export_body(folder/'scanbench.py')==export_body(ROOT/'scripts/scanbench.py')
tracked=[ROOT/f'data/cases/case_2438b1a3fd780c63/input/{name}' for name in ['mesh.ply','mesh.stl','observations.json','cameras.json','continuous_veto.json']]
before={str(p.relative_to(ROOT)).replace('\\','/'):[file_hash(p),p.stat().st_mtime_ns] for p in tracked}
rows=[]
for label,args in [('validate',['scripts/scanbench.py','validate','--all']),('supplemental',['scripts/supplemental_audit.py','--all']),('ambiguous_validate',['scripts/scanbench.py','validate'])]:
    log=ROOT/f'logs/cli_scope_{label}.log'
    with log.open('w',encoding='utf-8') as stream:result=subprocess.run([sys.executable,*args],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    message=log.read_text(encoding='utf-8');assert result.returncode!=0
    if label!='ambiguous_validate':assert 'unresolved source conclusions' in message and all(s in message for s in ['244','245','246','247','248','249','250'])
    else:assert 'validation requires explicit --all or --case-ids' in message
    rows.append({'command':args,'exit_code':result.returncode,'log':str(log.relative_to(ROOT)).replace('\\','/'),'log_sha256':file_hash(log)})
after={str(p.relative_to(ROOT)).replace('\\','/'):[file_hash(p),p.stat().st_mtime_ns] for p in tracked};assert before==after
proof={'status':'pass','category':'command_scope_and_excluded_source_dispatch','full_batch_incomplete_rejected_by_real_commands':True,'export_branch_AST_identical':True,'all_frozen_core_modules_unchanged':True,'tracked_completed_artifacts_unchanged':before,'checks':rows,'changed_scripts_sha256':{f'scripts/{name}':file_hash(ROOT/'scripts'/name) for name in ['scanbench.py','supplemental_audit.py','batch_scope.py']},'before_scripts_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [folder/'scanbench.py',folder/'supplemental_audit.py']},'script_sha256':file_hash(Path(__file__)),'correction':'--all requires all 32 source conclusions, exactly six cases per eligible source and current valid Mesh stages. Supplemental source checks use only qualified references; excluded sources are checked by the final source evidence audit. Full generation delegates to the established restartable source driver.','time':time.time()}
atomic_json(folder/'proof.json',proof);print(canonical_json(proof))
