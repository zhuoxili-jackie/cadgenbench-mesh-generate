"""Inspect an unchanged fixed-revision sidecar; never override STEP eligibility."""
from pathlib import Path
import os,sys,urllib.request,traceback
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from cadgenbench.common.mesh import Mesh,validate_mesh
import trimesh

sid=sys.argv[1];assert sid in IDS
tree=load_json(ROOT/'sources/upstream_tree.json');source=ROOT/f'sources/{sid}/input.step'
source_sha=file_hash(source);assert source_sha==next(x['lfs']['oid'] for x in tree if x['path']==f'{sid}/input.step')
entry=next(x for x in tree if x['path']==f'{sid}/input.mesh.npz');expected=entry['lfs']['oid']
path=ROOT/f'sources/{sid}/input.mesh.npz';url=f'https://huggingface.co/datasets/HuggingAI4Engineering/cadgenbench-data/resolve/{REV}/{sid}/input.mesh.npz'
if not path.exists() or file_hash(path)!=expected:
    with urllib.request.urlopen(url,timeout=120) as response:raw=response.read()
    assert hashlib.sha256(raw).hexdigest()==expected;atomic_bytes(path,raw)
report_path=ROOT/f'reports/source_investigations/{sid}/official_mesh_geometry.json';script_sha=file_hash(Path(__file__))
if report_path.exists():
    prior=load_json(report_path)
    if prior.get('source_sha256')==source_sha and prior.get('official_sha256')==expected and prior.get('script_sha256')==script_sha:
        print(canonical_json({'source_id':sid,'reused_hash_verified_diagnostic':True}));sys.exit(0)
    raise RuntimeError('Existing sidecar evidence differs; preserve and investigate before replacing it.')
with np.load(path) as z:v=z['vertices'];f=z['triangles'].astype(np.int64);chord=float(z['linear_deflection_mm'])
assert v.ndim==2 and v.shape[1]==3 and f.ndim==2 and f.shape[1]==3 and np.isfinite(v).all() and f.min()>=0 and f.max()<len(v)
tm=trimesh.Trimesh(v,f,process=False);edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
assert len(v)**2<np.iinfo(np.int64).max
_,count=np.unique(edges[:,0]*len(v)+edges[:,1],return_counts=True)
vendor={'status':'pass'}
try:validate_mesh(Mesh(v,f,chord))
except Exception as exc:vendor={'status':'failed','error':repr(exc),'traceback':traceback.format_exc()}
components=[{'faces':len(c.faces),'area_mm2':float(c.area),'signed_volume_mm3':float(c.volume),'watertight':bool(c.is_watertight),'winding_consistent':bool(c.is_winding_consistent)} for c in tm.split(only_watertight=False)]
result={'status':'diagnostic_completed_not_an_eligibility_override','source_id':sid,'source_sha256':source_sha,'revision':REV,'official_url':url,'official_sha256':expected,'mesh_path':str(path.relative_to(ROOT)).replace('\\','/'),'original_linear_deflection_mm':chord,'vertices':len(v),'faces':len(f),'bounds_source_mm':tm.bounds,'area_mm2':float(tm.area),'signed_volume_mm3':float(tm.volume),'watertight':bool(tm.is_watertight),'winding_consistent':bool(tm.is_winding_consistent),'degenerate_faces':int((tm.area_faces<=1e-16).sum()),'open_edges':int((count==1).sum()),'nonmanifold_edges':int((count>2).sum()),'components':components,'vendor_validation':vendor,'source_or_topology_modifications':False,'subdivision_performed':False,'script_sha256':script_sha,'method':'Original official bytes verified against fixed-revision LFS SHA256; independent int64 edge multiplicity and full unchanged-array geometry checks. A negative nested-shell volume is recorded, not automatically treated as an invalid cavity. A valid STEP remains a separate mandatory eligibility prerequisite.'}
atomic_json(report_path,result);print(canonical_json({k:result[k] for k in ['source_id','status','vertices','faces','watertight','open_edges','nonmanifold_edges','components']}))
