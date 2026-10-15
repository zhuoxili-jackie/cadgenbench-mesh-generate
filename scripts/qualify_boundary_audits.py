"""Read-only geometric qualification layered over source preparation, with atomic state."""
from pathlib import Path
import os,sys,subprocess,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
sid=sys.argv[1];assert sid in IDS;gt=ROOT/f'private/gt/{sid}';meta=load_json(gt/'metadata.json');assert meta['status'] in ['eligible_native','eligible_official_mesh_approx']
environment={p:importlib.metadata.version(p) for p in ['cadquery-ocp','numpy','trimesh']}
assert environment=={'cadquery-ocp':'7.8.1.1.post1','numpy':'2.2.6','trimesh':'4.9.0'},'Boundary evidence requires the declared locked production environment.'
inputs={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [ROOT/f'sources/{sid}/input.step',gt/'mesh.npz',gt/'metadata.json',gt/'placements.json']}
code={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [Path(__file__),ROOT/'scripts/audit_reference_boundary.py',ROOT/'scripts/audit_discrete_boundary.py']};key=digest([inputs,code,environment]);state=State();marker=ROOT/f'reports/source_boundary_audits/{sid}_qualification.json'
if state.valid(sid,'reference_boundary_audit',key):print(sid,'qualified boundary stage reused');raise SystemExit(0)
state.begin(sid,'reference_boundary_audit',key)
with measured() as timing:
    for script in ['audit_reference_boundary.py','audit_discrete_boundary.py']:
        subprocess.run([sys.executable,str(ROOT/'scripts'/script),sid],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    reference_path=ROOT/f'reports/source_boundary_audits/{sid}.json';reference=load_json(reference_path);contacts_path=ROOT/f'reports/source_boundary_audits/{sid}_contacts.json';contacts=load_json(contacts_path)
    assert reference['source_sha256']==meta['source_sha256'] and reference['reference_sha256']==file_hash(gt/'mesh.npz')
    assert reference['script_sha256']==file_hash(ROOT/'scripts/audit_reference_boundary.py') and reference['native_or_approx_bound_mm']==max(.021,meta['chord_mm']*1.1)
    assert reference['status']=='pass' and max(reference['boundary_distances_mm'])==reference['sampled_max_mm']<=reference['native_or_approx_bound_mm'],f'{sid}: exact boundary precision requires investigation; no exclusion or relaxed gate'
    assert contacts['status']=='pass' and contacts['inputs_sha256']==inputs
    evidence={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in [reference_path,contacts_path,ROOT/'reports/source_boundary_audits/box_control.json']}
    qualification={'status':'pass','source_id':sid,'key':key,'inputs_sha256':inputs,'code_sha256':code,'environment':environment,'evidence_sha256':evidence,'boundary_sampled_max_mm':reference['sampled_max_mm'],'bound_mm':reference['native_or_approx_bound_mm'],'reference_geometry_changed':False,'historical_quick_metric':'Existing metadata accuracy_check is an OCCT point-to-shape diagnostic; solid-interior samples can have distance zero. This independent all-boundary-face audit is the complete sampled reference accuracy check.'};atomic_json(marker,qualification)
    record=json.loads(state.db.execute("SELECT body FROM records WHERE kind='sources' AND id=?",(sid,)).fetchone()[0]);record['boundary_accuracy']={'report':str(reference_path.relative_to(ROOT)).replace('\\','/'),'report_sha256':file_hash(reference_path),'sampled_max_mm':reference['sampled_max_mm'],'p95_mm':reference['p95_mm'],'n':128,'unit':'mm','not_exact_hausdorff':True,'qualification':str(marker.relative_to(ROOT)).replace('\\','/'),'qualification_sha256':file_hash(marker)};state.record('sources',sid,record)
state.finish(sid,'reference_boundary_audit',key,[marker,*[ROOT/p for p in evidence]],timing)
print(canonical_json({'source':sid,'boundary_accuracy_status':'pass','sampled_max_mm':reference['sampled_max_mm']}))
