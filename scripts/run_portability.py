"""Fresh public export + independent no-GT process; compare actual facet geometry."""
from pathlib import Path
import os,sys,subprocess,time,json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
os.environ.setdefault('OMP_NUM_THREADS','2');os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
from scanbench.common import *
from scanbench.export import export_case

def run(cid):
    src=ROOT/f'data/cases/{cid}/input';signature=digest([file_hash(src/'mesh.ply'),file_hash(ROOT/'src/scanbench/reconstruct.py'),file_hash(src/'observations.json')])
    dest=ROOT/f'tests/artifacts/public_export_{signature[:12]}'
    report_path=ROOT/'reports/tests/no_gt_portable.json'
    if report_path.exists() and load_json(report_path).get('signature')==signature and (dest/'rebuilt/mesh.ply').exists():
        print('verified portability evidence already exists');return
    if not dest.exists():export_case(cid,dest,observations_only=True)
    assert not list((dest/'data/cases').rglob('mesh.ply'))
    output=dest/'rebuilt'
    if output.exists() and any(output.iterdir()):raise RuntimeError('prior unfinished rebuild requires inspection, not silent overwrite')
    log=ROOT/'logs/no_gt_reconstruction.log'
    with open(log,'wb') as f:
        subprocess.run([sys.executable,str(dest/'rebuild.py')],cwd=dest,stdout=f,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    from scanbench.validate import read_mesh,sorted_facets
    import numpy as np
    a=read_mesh(src/'mesh.ply');b=read_mesh(output/'mesh.ply')
    aa,bb=sorted_facets(a),sorted_facets(b);np.testing.assert_array_equal(aa,bb)
    np.testing.assert_array_equal(a.vertices,b.vertices);np.testing.assert_array_equal(a.faces,b.faces)
    accesses=load_json(dest/'access_audit.json')
    forbidden=[p for p in accesses['opened'] if Path(p).is_relative_to(ROOT/'private') or Path(p).is_relative_to(ROOT/'sources') or Path(p).is_relative_to(ROOT/'data')]
    assert not forbidden
    atomic_json(report_path,{'status':'pass','signature':signature,'case_id':cid,'public_export_directory':str(dest.relative_to(ROOT)),
                'output_initially_empty':True,'existing_mesh_not_copied':True,'separate_process':True,'forbidden_gt_or_original_data_reads':forbidden,
                'all_float64_vertices_and_indexed_connectivity_exact':True,'all_triangle_connectivity_and_coordinates_equal':True,'facet_count':len(aa),'audit_log':str((dest/'access_audit.json').relative_to(ROOT)),
                'public_rebuild_command':f'& .\\.venv\\Scripts\\python.exe "{dest.relative_to(ROOT)}\\rebuild.py"'})
    print('PASS: portable no-GT rebuild and full geometry comparison',flush=True)

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else 'case_2438b1a3fd780c63')
