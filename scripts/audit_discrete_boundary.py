"""Independent boundary-only check: solid interiors cannot certify contact points."""
from pathlib import Path
import os,sys,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
from scanbench.common import *
from scanbench.sources import read_step
from scanbench.contact_support import KIND,CONTACT_TOL_MM
from audit_reference_boundary import boundary,distance
sid=sys.argv[1];gt=ROOT/f'private/gt/{sid}';meta=load_json(gt/'metadata.json');places=load_json(gt/'placements.json')['placements'];selected=[p for p in places if p.get('contact_kind')==KIND]
code={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [Path(__file__),ROOT/'scripts/audit_reference_boundary.py',ROOT/'src/scanbench/contact_support.py']};environment={p:importlib.metadata.version(p) for p in ['cadquery-ocp','numpy','trimesh']}
inputs={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [ROOT/f'sources/{sid}/input.step',gt/'mesh.npz',gt/'metadata.json',gt/'placements.json']};key=digest([inputs,code,environment]);path=ROOT/f'reports/source_boundary_audits/{sid}_contacts.json'
if path.exists() and load_json(path).get('key')==key:
    assert load_json(path)['status']=='pass';print(sid,'boundary contact evidence reused');raise SystemExit(0)
rows=[]
if selected:
    shape,_=read_step(ROOT/f'sources/{sid}/input.step');faces=boundary(shape)
    with np.load(gt/'mesh.npz') as raw:
        for p in selected:
            points=transform(raw['vertices'][p['contact_vertex_ids']],meta['T_source_mm_from_object']);values=[]
            for point in points:
                value,inside=distance(point,faces);assert not inside;values.append(value)
            rows.append({'placement_id':p['placement_id'],'contact_vertex_ids':p['contact_vertex_ids'],'point_to_CAD_boundary_mm':values,'maximum_mm':max(values),'limit_mm':CONTACT_TOL_MM,'status':'pass' if max(values)<=CONTACT_TOL_MM else 'failed'})
result={'status':'pass' if all(r['status']=='pass' for r in rows) else 'failed','source_id':sid,'key':key,'inputs_sha256':inputs,'code_sha256':code,'environment':environment,'discrete_contacts':rows,'method':'Exact distance to all boundary faces; no SOLID interior-zero result is accepted as surface contact.'};atomic_json(path,result)
print(canonical_json({'source':sid,'status':result['status'],'discrete_pose_count':len(rows)}))
if result['status']!='pass':raise SystemExit(2)
