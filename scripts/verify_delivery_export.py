"""Execute the exact public export/rebuild commands and independently compare real outputs."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.validate import read_mesh

cid='case_2438b1a3fd780c63';destination=ROOT/'exported_case';proof_path=ROOT/'reports/operations/delivery_export_command.json'
assert not destination.exists() and not proof_path.exists(),'This is a fresh command check; preserve prior evidence.'
commands=[[sys.executable,'scripts/scanbench.py','export-case','--case-ids',cid,'--output','exported_case','--observations-only'],[sys.executable,'exported_case/rebuild.py']]
started=time.time();logs=[]
for index,command in enumerate(commands):
    log=ROOT/f'logs/delivery_export_command_{index}.log'
    with log.open('w',encoding='utf-8') as f:result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,(command,result.returncode,log)
    logs.append({'path':str(log.relative_to(ROOT)).replace('\\','/'),'sha256':file_hash(log)})
    print(canonical_json({'completed_command':index,'returncode':result.returncode}),flush=True)
    if index==0:
        assert not list(destination.rglob('mesh.ply')) and not list(destination.rglob('mesh.stl'))
        assert not (destination/'rebuilt').exists()
        assert not (destination/'private').exists() and not (destination/'sources').exists()
        export=load_json(destination/'export.json')
        for name,h in export['files'].items():
            p=(destination/name).resolve();assert p.is_relative_to(destination) and not p.is_symlink() and file_hash(p)==h
source=ROOT/f'data/cases/{cid}/input/mesh.ply';rebuilt=destination/'rebuilt/mesh.ply';a=read_mesh(source);b=read_mesh(rebuilt)
assert np.array_equal(a.vertices,b.vertices) and np.array_equal(a.faces,b.faces)
access_path=destination/'access_audit.json';access=load_json(access_path)
assert access['initial_output_empty'] and access['forbidden_reads']==0
for name in access['opened']:
    p=Path(name)
    assert not any(p.is_relative_to(ROOT/part) for part in ['private','sources','data'])
assert file_hash(destination/'src/scanbench/reconstruct.py')==file_hash(ROOT/'src/scanbench/reconstruct.py')
proof={'status':'pass','case_id':cid,'commands':commands,'destination':'exported_case','no_mesh_supplied':True,'initial_output_empty':True,'actual_vertices_identical':True,'actual_connectivity_identical':True,'vertices':len(a.vertices),'faces':len(a.faces),'source_mesh_sha256':file_hash(source),'rebuilt_mesh_sha256':file_hash(rebuilt),'export_manifest_sha256':file_hash(destination/'export.json'),'access_audit_sha256':file_hash(access_path),'original_data_private_sources_reads':0,'reconstruction_code_sha256':file_hash(ROOT/'src/scanbench/reconstruct.py'),'logs':logs,'script_sha256':file_hash(Path(__file__)),'seconds':time.time()-started,'time':time.time()}
atomic_json(proof_path,proof);print(canonical_json(proof))
