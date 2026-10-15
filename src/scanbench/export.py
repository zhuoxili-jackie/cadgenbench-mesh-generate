"""Self-contained public case export with a stand-alone, audited rebuild entry."""
from pathlib import Path
import shutil
from .common import ROOT,load_json,atomic_json,atomic_bytes,file_hash

REBUILD = '''from pathlib import Path
import argparse, json, os, sys
os.environ.setdefault("OMP_NUM_THREADS","2")
os.environ.setdefault("OPENBLAS_NUM_THREADS","2")
os.environ.setdefault("NUMBA_NUM_THREADS","2")
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/"src"))
parser=argparse.ArgumentParser()
parser.add_argument("--output",default="rebuilt")
args=parser.parse_args()
out=(root/args.output).resolve()
if out.exists() and any(out.iterdir()): raise SystemExit("rebuild output must start empty")
access=[]
def audit(event,args):
    if event=="open" and isinstance(args[0],(str,bytes)):
        p=Path(os.fsdecode(args[0])).resolve()
        parts={x.lower() for x in p.parts}
        if parts & {"private","sources","cadgenbench_scan_dataset","scanmesh-toolkit-v0.2"}:
            raise PermissionError("forbidden reference-data access: "+str(p))
        access.append(str(p))
sys.addaudithook(audit)
from scanbench.reconstruct import reconstruct
inputs=list((root/"data/cases").glob("*/input"))
assert len(inputs)==1
inp=inputs[0]
reconstruct(inp/"observations.json",inp/"cameras.json",inp/"reconstruction_config.json",out)
(root/"access_audit.json").write_text(json.dumps({"initial_output_empty":True,"forbidden_reads":0,"opened":sorted(set(access))},indent=2),encoding="utf-8")
'''

def export_case(cid,destination,observations_only=False):
    destination=Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()): raise ValueError('export destination must be empty')
    source=ROOT/f'data/cases/{cid}/input'; out=destination/f'data/cases/{cid}/input'; out.mkdir(parents=True,exist_ok=True)
    names=['observations.json','cameras.json','reconstruction_config.json','README.json']
    if not observations_only: names+=['mesh.ply','mesh.stl','points_for_meshing.ply','point_provenance.npz','reconstruction.json','continuous_veto.json']
    for name in names: shutil.copy2(source/name,out/name)
    for rec in load_json(source/'observations.json')['frames']:
        src=(source/rec['path']).resolve(); dst=(out/rec['path']).resolve()
        if not src.is_relative_to(ROOT/'data') or not dst.is_relative_to(destination/'data'): raise ValueError('export path escape')
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    package=destination/'src/scanbench'; package.mkdir(parents=True,exist_ok=True)
    for name in ['__init__.py','common.py','camera.py','reconstruct.py','observed_kernel.py','continuous_free_space.py']: shutil.copy2(ROOT/f'src/scanbench/{name}',package/name)
    atomic_bytes(destination/'rebuild.py',REBUILD.encode('utf-8'))
    shutil.copy2(ROOT/'requirements.lock',destination/'requirements.lock')
    atomic_bytes(destination/'LICENSES.md',b'# Standalone export notice\n\nThe following attribution describes the parent project. Source STEP, GT, the upstream data-card copy and the vendored STEP tessellator are deliberately absent from this public-only export; their paths below refer to the parent project.\n\n'+(ROOT/'LICENSES.md').read_bytes())
    atomic_bytes(destination/'README.md',b'# Standalone observed-geometry case\n\nInstall requirements.lock in Python 3.12, then run `python rebuild.py --output rebuilt`. The output directory must start empty. This export contains public noisy observations, known camera poses and reconstruction code only; no GT or source STEP is included. Range is Euclidean distance along a unit camera ray, in millimetres. See LICENSES.md for upstream attribution and third-party notices.\n')
    atomic_json(destination/'export.json',{'case_id':cid,'public_only':True,'observations_only':observations_only,'files':{str(p.relative_to(destination)).replace('\\','/'):file_hash(p) for p in destination.rglob('*') if p.is_file()}})
    return destination
