"""Independent raw-array edge audit for source investigation meshes."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
sid=sys.argv[1];folder=ROOT/f'reports/source_investigations/{sid}';trials=load_json(folder/'alternative_native_trials.json');rows=[]
for trial in trials:
    path=ROOT/trial['mesh_file'];assert file_hash(path)==trial['mesh_sha256']
    with np.load(path) as d:v=d['vertices'];f=d['triangles'].astype(np.int64)
    edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    # Int64 keys are safe here; explicitly bound the largest possible product.
    assert len(v)**2<np.iinfo(np.int64).max
    key=edges[:,0]*len(v)+edges[:,1];uniq,count=np.unique(key,return_counts=True);boundary=uniq[count==1];ids=np.stack([boundary//len(v),boundary%len(v)],axis=1)
    rows.append({'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':file_hash(path),'vertices':len(v),'faces':len(f),'open_edges':int((count==1).sum()),'nonmanifold_edges':int((count>2).sum()),'boundary_vertex_ids':ids,'boundary_edge_coordinates_mm':v[ids],'chord_mm':trial['chord_mm'],'angle_rad':trial['angle_rad']})
report={'status':'completed','source_id':sid,'method':'independent int64 raw triangle edge multiplicity; source geometry and triangles unchanged','trials':rows}
atomic_json(folder/'native_boundary_audit.json',report);print(canonical_json({'source_id':sid,'trials':[{k:r[k] for k in ['chord_mm','angle_rad','faces','open_edges','nonmanifold_edges']} for r in rows]}))
