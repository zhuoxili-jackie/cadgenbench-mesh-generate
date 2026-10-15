"""Install a behavior-preserving candidate only after every existing fusion is compared."""
from pathlib import Path
import os,sys,ast,shutil,zipfile
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *

for p in psutil.process_iter(['name','cmdline']):
    cmd=p.info['cmdline'] or []
    if p.info['name']=='python.exe' and '--worker' in cmd and any(a.endswith('run_full.py') for a in cmd):raise RuntimeError('finish the active source worker before changing reconstruction code')
module=ROOT/'src/scanbench/reconstruct.py';old_hash=file_hash(module)
assert old_hash=='21b273481cefdb685fad03ffc8b1c93e750ff903ffacacf936238e1fa064feb0'
candidate=ROOT/'scripts/fusion_merge_candidate.py';candidate_hash=file_hash(candidate)
folder=ROOT/'reports/protocol_amendments/r2_fusion_merge';folder.mkdir(parents=True,exist_ok=True)
freeze=load_json(ROOT/'reports/protocol_freeze.json');assert freeze['code_sha256']['src/scanbench/reconstruct.py']==old_hash
with zipfile.ZipFile(ROOT/freeze.get('code_snapshot_path','reports/frozen_protocol_code.zip')) as z:prior_packages=set(z.read('requirements.lock').decode().splitlines())
packages=set((ROOT/'requirements.lock').read_text().splitlines());assert not (prior_packages-packages) and packages-prior_packages<= {'py-spy==0.4.1'},'computational package versions changed'
state=State();inventory={}
for fp in sorted((ROOT/'data/cases').glob('*/input/.reconstruction_cache/fusion.npz')):
    cid=fp.parent.parent.parent.name;out=fp.parent.parent;proof_path=ROOT/f'reports/tests/fusion_merge_candidate/{cid}.json';proof=load_json(proof_path)
    assert proof['status']=='pass' and proof['candidate_code_sha256']==candidate_hash and proof['original_code_sha256']==old_hash,cid
    for field,path in [('original_fusion_npz_sha256',fp),('observations_sha256',out/'observations.json'),('cameras_sha256',out/'cameras.json')]:assert proof[field]==file_hash(path),cid
    stage=state.db.execute("SELECT input_hash,status,outputs,metrics FROM stages WHERE subject=? AND stage='mesh'",(cid,)).fetchone()
    assert stage and stage[1]=='complete' and state.valid(cid,'mesh',stage[0]),f'{cid}: complete qualified mesh required'
    paths=[p for p in out.rglob('*') if p.is_file()]
    sealed=folder/f'equivalence/{cid}.json';sealed.parent.mkdir(exist_ok=True)
    if sealed.exists():assert file_hash(sealed)==file_hash(proof_path)
    else:shutil.copy2(proof_path,sealed)
    inventory[cid]={'original_stage_hash':stage[0],'outputs':json.loads(stage[2]),'metrics':json.loads(stage[3]),'proof_path':str(sealed.relative_to(ROOT)).replace('\\','/'),'proof_sha256':file_hash(sealed),'files':{str(p.relative_to(ROOT)).replace('\\','/'):[file_hash(p),p.stat().st_mtime_ns] for p in paths}}
assert inventory,'no production fusion proofs'
generated={cid for cid,body in state.db.execute("SELECT id,body FROM records WHERE kind='cases'") if json.loads(body).get('generation_status')=='generated'}
assert set(inventory)==generated,'every generated case must have exact fusion evidence'
for source,name in [(module,'reconstruct_before.py'),(ROOT/'reports/protocol_freeze.json','freeze_before.json'),(ROOT/freeze.get('code_snapshot_path','reports/frozen_protocol_code.zip'),'code_before.zip')]:
    target=folder/name
    if target.exists():assert file_hash(target)==file_hash(source),'archive already differs'
    else:shutil.copy2(source,target)
for name in ['no_gt_portable','full_case_reproduction','real_mesh_interruption','production_resume_and_dependencies']:
    source=ROOT/f'reports/tests/{name}.json'
    if source.exists():shutil.copy2(source,folder/f'{name}_before.json')
atomic_json(folder/'inventory_before.json',inventory)
old=module.read_text(encoding='utf-8');trial=candidate.read_text(encoding='utf-8');old_tree=ast.parse(old);trial_tree=ast.parse(trial)
def block(text,node):
    start=min([node.lineno]+[n.lineno for n in node.decorator_list]);return ''.join(text.splitlines(keepends=True)[start-1:node.end_lineno])
old_fuse=next(n for n in old_tree.body if isinstance(n,ast.FunctionDef) and n.name=='fuse')
merge=block(trial,next(n for n in trial_tree.body if isinstance(n,ast.FunctionDef) and n.name=='merge_indices'))
fuse=block(trial,next(n for n in trial_tree.body if isinstance(n,ast.FunctionDef) and n.name=='fuse'))
fuse=''.join(line for line in fuse.splitlines(keepends=True) if not line.strip().startswith(('from scanbench.reconstruct import','from scipy.spatial import'))).replace('candidate fusion ','fusion ')
new=old.replace('from scipy.spatial import cKDTree\n','from scipy.spatial import cKDTree\nfrom numba import njit\n')
new=new.replace(block(old,old_fuse),merge+'\n'+fuse)
new=new.replace('[fuse,frame_points_normals,reduce_representatives,voxel_keys]],np.__version__]','[fuse,merge_indices.py_func,frame_points_normals,reduce_representatives,voxel_keys]],np.__version__,__import__(\'numba\').__version__]')
assert new!=old and 'merge_indices.py_func' in new
compile(new,str(module),'exec');atomic_bytes(module,new.encode('utf-8'))
atomic_json(folder/'installation.json',{'old_code_sha256':old_hash,'new_code_sha256':file_hash(module),'candidate_code_sha256':candidate_hash,'compared_existing_cases':list(inventory),'protocol_unchanged':True,'next':'migrate qualified cache keys, run current-code independent reconstruction/resume tests, then register amendment before resuming full queue'})
print(canonical_json({'installed_candidate':file_hash(module),'qualified_existing_cases':len(inventory)}))
