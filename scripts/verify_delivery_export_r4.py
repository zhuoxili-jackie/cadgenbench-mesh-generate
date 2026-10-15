"""Execute the current public commands in a new empty export; retain r3 evidence."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.validate import read_mesh

cid='case_2438b1a3fd780c63';destination=ROOT/'exported_case_r4';proof_path=ROOT/'reports/operations/delivery_export_command_r4.json'
assert not destination.exists() and not proof_path.exists(),'Fresh check only; preserve previous artifacts.'
commands=[[sys.executable,'scripts/scanbench.py','export-case','--case-ids',cid,'--output','exported_case_r4','--observations-only'],[sys.executable,'exported_case_r4/rebuild.py']]
started=time.time();logs=[]
for index,command in enumerate(commands):
    log=ROOT/f'logs/delivery_export_command_r4_{index}.log'
    with log.open('w',encoding='utf-8') as f:result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,(command,result.returncode,log)
    logs.append({'path':str(log.relative_to(ROOT)).replace('\\','/'),'sha256':file_hash(log)})
    print(canonical_json({'completed_command':index,'returncode':result.returncode}),flush=True)
    if index==0:
        assert not list(destination.rglob('mesh.ply')) and not list(destination.rglob('mesh.stl'))
        assert not (destination/'rebuilt').exists() and not (destination/'private').exists() and not (destination/'sources').exists()
        for name,h in load_json(destination/'export.json')['files'].items():
            path=(destination/name).resolve();assert path.is_relative_to(destination) and not path.is_symlink() and file_hash(path)==h
source=ROOT/f'data/cases/{cid}/input/mesh.ply';rebuilt=destination/'rebuilt/mesh.ply';a=read_mesh(source);b=read_mesh(rebuilt)
assert np.array_equal(a.vertices,b.vertices) and np.array_equal(a.faces,b.faces)
access_path=destination/'access_audit.json';access=load_json(access_path)
assert access['initial_output_empty'] and access['forbidden_reads']==0
for name in access['opened']:assert not any(Path(name).is_relative_to(ROOT/part) for part in ['private','sources','data'])
modules=['common.py','camera.py','reconstruct.py','observed_kernel.py','continuous_free_space.py']
for name in modules:assert file_hash(destination/'src/scanbench'/name)==file_hash(ROOT/'src/scanbench'/name)
proof={'status':'pass','case_id':cid,'commands':commands,'destination':'exported_case_r4','checker_script':'scripts/verify_delivery_export_r4.py','no_mesh_supplied':True,'initial_output_empty':True,'actual_vertices_identical':True,'actual_connectivity_identical':True,'vertices':len(a.vertices),'faces':len(a.faces),'source_mesh_sha256':file_hash(source),'rebuilt_mesh_sha256':file_hash(rebuilt),'export_manifest_sha256':file_hash(destination/'export.json'),'access_audit_sha256':file_hash(access_path),'original_data_private_sources_reads':0,'reconstruction_code_sha256':file_hash(ROOT/'src/scanbench/reconstruct.py'),'continuous_module_sha256':file_hash(ROOT/'src/scanbench/continuous_free_space.py'),'copied_code_sha256':{name:file_hash(destination/'src/scanbench'/name) for name in modules},'logs':logs,'script_sha256':file_hash(Path(__file__)),'seconds':time.time()-started,'time':time.time()}
atomic_json(proof_path,proof);print(canonical_json(proof))
