"""Fresh GT builds prove the retry fix preserves every already accepted pilot GT."""
from pathlib import Path
import os,sys,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *
signature=digest([file_hash(ROOT/'src/scanbench/sources.py'),{sid:file_hash(ROOT/f'private/gt/{sid}/mesh.npz') for sid in ['218','231','229']}])
dest=ROOT/f'tests/artifacts/gt_retry_{signature[:12]}';report=ROOT/'reports/tests/gt_retry_compatibility.json'
if report.exists() and load_json(report).get('signature')==signature and load_json(report).get('status')=='pass':print('Existing exact compatibility evidence');raise SystemExit(0)
dest.mkdir(parents=True,exist_ok=True)
for folder in ['src/scanbench','vendor/cadgenbench','vendor/cadgenbench/common','configs']:
    target=dest/folder;target.mkdir(parents=True,exist_ok=True)
    for source in (ROOT/folder).iterdir():
        if source.is_file() and source.suffix in ['.py','.yaml']:shutil.copy2(source,target/source.name)
(dest/'sources').mkdir(exist_ok=True);shutil.copy2(ROOT/'sources/upstream_tree.json',dest/'sources/upstream_tree.json')
for sid in ['218','231','229']:
    (dest/f'sources/{sid}').mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/f'sources/{sid}/input.step',dest/f'sources/{sid}/input.step')
worker="""from pathlib import Path
import os,sys,json,numpy as np
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
from scanbench.common import State,atomic_json,load_json
from scanbench.sources import prepare
original=Path(sys.argv[1]);state=State();rows=[]
for sid in ['218','231','229']:
 prepare(sid,state);m=load_json(ROOT/f'private/gt/{sid}/metadata.json');new=np.load(ROOT/f'private/gt/{sid}/mesh.npz');old=np.load(original/f'private/gt/{sid}/mesh.npz')
 np.testing.assert_array_equal(new['vertices'],old['vertices']);np.testing.assert_array_equal(new['faces'],old['faces'])
 prior=load_json(original/f'private/gt/{sid}/metadata.json');assert {k:v for k,v in m.items() if k!='stage_hash'}=={k:v for k,v in prior.items() if k!='stage_hash'}
 rows.append({'source_id':sid,'all_float64_GT_vertices_and_triangles_identical':True,'all_physical_metadata_identical_except_stage_hash':True,'first_native_attempt_accepted':len(load_json(ROOT/f'private/gt/{sid}/native_attempts.json'))==1})
atomic_json(ROOT/'result.json',{'status':'pass','sources':rows})
"""
atomic_bytes(dest/'run.py',worker.encode())
env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONUTF8='1')
with open(ROOT/'logs/gt_retry_compatibility_worker.log','wb') as log:subprocess.run([sys.executable,str(dest/'run.py'),str(ROOT)],cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
result=load_json(dest/'result.json');result.update(signature=signature,new_sources_py_sha256=file_hash(ROOT/'src/scanbench/sources.py'),experiment_directory=str(dest.relative_to(ROOT)).replace('\\','/'))
atomic_json(report,result);print(canonical_json(result))
