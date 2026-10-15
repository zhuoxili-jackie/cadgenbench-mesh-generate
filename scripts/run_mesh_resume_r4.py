"""Kill the real isolated reconstructor after fusion publication, then resume it."""
from pathlib import Path
import os,sys,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
os.environ.setdefault('OMP_NUM_THREADS','2');os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
from scanbench.common import *
from scanbench.export import export_case

WORKER='''from pathlib import Path
import os,sys
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'src'))
from scanbench.common import State,file_hash,digest
from scanbench.reconstruct import reconstruct
inp=next((root/'data/cases').glob('*/input'));out=root/'rebuilt';state=State(root)
key=digest([file_hash(inp/n) for n in ['observations.json','cameras.json','reconstruction_config.json']])
if not state.valid('reconstruction','inputs',key):
 state.begin('reconstruction','inputs',key);state.finish('reconstruction','inputs',key,[inp/'observations.json',inp/'cameras.json'],{})
mkey=digest([key,file_hash(root/'src/scanbench/reconstruct.py'),file_hash(root/'src/scanbench/observed_kernel.py'),file_hash(root/'src/scanbench/continuous_free_space.py')])
if not state.valid('reconstruction','mesh',mkey):
 state.begin('reconstruction','mesh',mkey)
 reconstruct(inp/'observations.json',inp/'cameras.json',inp/'reconstruction_config.json',out)
 state.finish('reconstruction','mesh',mkey,[out/'mesh.ply',out/'mesh.stl',out/'points_for_meshing.ply'],{})
'''

def run(cid):
    src=ROOT/f'data/cases/{cid}/input';signature=digest([file_hash(src/'mesh.ply'),digest([file_hash(ROOT/'src/scanbench/reconstruct.py'),file_hash(ROOT/'src/scanbench/continuous_free_space.py')])]);dest=ROOT/f'tests/artifacts/mesh_resume_{signature[:12]}'
    report=ROOT/'reports/tests/real_mesh_interruption_r4.json'
    if report.exists() and load_json(report).get('signature')==signature and load_json(report).get('status')=='pass':return
    if dest.exists():raise RuntimeError('existing incomplete interruption experiment requires inspection')
    export_case(cid,dest,observations_only=True);atomic_bytes(dest/'worker.py',WORKER.encode())
    inp=dest/f'data/cases/{cid}/input';tracked=list((dest/'data').rglob('*.npz'))+[inp/'observations.json',inp/'cameras.json']
    before={str(p.relative_to(dest)):(file_hash(p),p.stat().st_mtime_ns) for p in tracked}
    log=open(ROOT/'logs/mesh_interrupt_worker_r4.log','wb')
    process=subprocess.Popen([sys.executable,str(dest/'worker.py')],cwd=dest,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    marker=dest/'rebuilt/.reconstruction_cache/fusion.json';until=time.monotonic()+180
    while not marker.exists() and time.monotonic()<until:
        if process.poll() is not None:raise RuntimeError('reconstructor ended before interrupt point')
        time.sleep(.03)
    if not marker.exists():process.kill();process.wait();raise RuntimeError('fusion interrupt point not reached')
    fusion=marker.with_name('fusion.npz');fusion_before=(file_hash(fusion),fusion.stat().st_mtime_ns)
    descendants=psutil.Process(process.pid).children(recursive=True)
    killed_pids=[process.pid,*[p.pid for p in descendants]]
    for child in reversed(descendants):
        try:child.kill()
        except psutil.NoSuchProcess:pass
    if process.poll() is None:process.kill()
    process.wait(timeout=10)
    _,survivors=psutil.wait_procs(descendants,timeout=10)
    assert not survivors,'An owned reconstruction child survived the interruption'
    log.close()
    import sqlite3
    db=sqlite3.connect(dest/'state/state.sqlite');row=db.execute("SELECT status FROM stages WHERE stage='mesh'").fetchone();assert row[0]=='running';db.close()
    assert not (dest/'rebuilt/mesh.ply').exists()
    with open(ROOT/'logs/mesh_resume_worker_r4.log','wb') as log:
        subprocess.run([sys.executable,str(dest/'worker.py')],cwd=dest,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    after={str(p.relative_to(dest)):(file_hash(p),p.stat().st_mtime_ns) for p in tracked}
    assert before==after;assert fusion_before==(file_hash(fusion),fusion.stat().st_mtime_ns)
    from scanbench.validate import read_mesh
    a=read_mesh(src/'mesh.ply');b=read_mesh(dest/'rebuilt/mesh.ply');np.testing.assert_array_equal(a.vertices,b.vertices);np.testing.assert_array_equal(a.faces,b.faces)
    db=sqlite3.connect(dest/'state/state.sqlite');row=db.execute("SELECT status FROM stages WHERE stage='mesh'").fetchone();assert row[0]=='complete';db.close()
    atomic_json(report,{'status':'pass','signature':signature,'case_id':cid,'actual_reconstruction_process_killed':True,'actual_owned_process_tree_killed':killed_pids,'all_descendants_verified_exited':True,'completed_input_hashes_and_mtimes_unchanged':True,
                       'completed_fusion_hash_and_mtime_unchanged':True,'partial_mesh_not_marked_complete':True,'resumed_float64_vertices_and_connectivity_exact':True,
                       'tracked_input_files':len(tracked),'fusion_before':fusion_before,'experiment_directory':str(dest.relative_to(ROOT))})
    print('PASS actual reconstruction interruption, resume and geometry comparison',flush=True)

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else 'case_2438b1a3fd780c63')
