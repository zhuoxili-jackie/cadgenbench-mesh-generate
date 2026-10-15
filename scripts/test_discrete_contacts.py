"""Real CAD positive/negative contact controls and exact compatibility on prior cases."""
from pathlib import Path
import os,sys,ast,importlib.util,shutil
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench.contact_support import certify_contact
from scanbench.placement_audit import audit_placements
from scanbench.validate import physical_case_check
from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound
from OCP.BRepTools import BRepTools
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Pnt,gp_Trsf

folder=ROOT/'reports/protocol_amendments/r3_discrete_contact';art=ROOT/'tests/artifacts/discrete_contacts';art.mkdir(parents=True,exist_ok=True)
def balls(centers,radii=None):
    builder=BRep_Builder();shape=TopoDS_Compound();builder.MakeCompound(shape)
    for c,r in zip(centers,radii or [1]*len(centers)):builder.Add(shape,BRepPrimAPI_MakeSphere(gp_Pnt(*c),r).Shape())
    return shape
base=balls([[0,0,1],[10,0,1],[0,10,1]]);points=np.array([[0.,0,0],[10,0,0],[0,10,0]])
single=balls([[0,0,1]]);line=balls([[0,0,1],[10,0,1],[20,0,1]])
outside=balls([[0,0,1],[10,0,1],[0,10,1],[50,50,8]],[1,1,1,3])
angle=.37;G=np.eye(4);G[:3,:3]=[[1,0,0],[0,np.cos(angle),-np.sin(angle)],[0,np.sin(angle),np.cos(angle)]];G[:3,3]=[2,-3,4];tr=gp_Trsf();tr.SetValues(*map(float,G[:3].ravel()));moved=BRepBuilderAPI_Transform(base,tr,True).Shape()
floating=np.eye(4);floating[2,3]=.01;penetrating=np.eye(4);penetrating[2,3]=-.01
theta=np.linspace(0,2*np.pi,8,endpoint=False);radius=1e-4;near=np.column_stack([radius*np.cos(theta),radius*np.sin(theta),np.full(8,1-np.sqrt(1-radius**2))])
scenarios=[('three_separated_real_contacts',base,np.eye(4),points,True),('rigid_frame_change',moved,np.linalg.inv(G),transform(points,G),True),('floating',base,floating,points,False),('penetrating',base,penetrating,points,False),('invented_support_points',base,np.eye(4),np.array([[-5,-5,0],[15,-5,0],[-5,15,0]]),False),('single_rolling_contact',single,np.eye(4),np.array([[0.,0,0]]),False),('collinear_real_contacts',line,np.eye(4),np.array([[0.,0,0],[10,0,0],[20,0,0]]),False),('COM_outside_real_contact_polygon',outside,np.eye(4),points,False),('curvature_band_false_support',single,np.eye(4),near,False)]
controls=[]
for name,shape,T,p,expected in scenarios:
    path=art/f'{name}.brep';BRepTools.Write_s(shape,os.path.relpath(path));result=certify_contact(shape,T,p,1e-4,100.)
    assert (result['status']=='pass')==expected,(name,result)
    controls.append({'name':name,'expected_acceptance':expected,'shape_path':str(path.relative_to(ROOT)).replace('\\','/'),'shape_sha256':file_hash(path),'T_table_from_source':T,'result':result})
    print(name,result['status'],flush=True)
old_path=folder/'validate_before.py';spec=importlib.util.spec_from_file_location('scanbench._validate_before_contact',old_path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
def functions(path,skip):
    tree=ast.parse(path.read_text(encoding='utf-8'));return {node.name:ast.dump(node,include_attributes=False) for node in tree.body if isinstance(node,ast.FunctionDef) and node.name not in skip}
assert functions(old_path,{'physical_case_check','validation_fingerprint'})==functions(ROOT/'src/scanbench/validate.py',{'physical_case_check','validation_fingerprint'})
source_rows=[]
for sid in ['218','231','229','201','203']:
    before=load_json(folder/f'prior_placements/{sid}/placement_audit.json');after=audit_placements(sid)
    assert {k:v for k,v in before.items() if k!='key'}=={k:v for k,v in after.items() if k!='key'},sid
    assert file_hash(ROOT/f'private/gt/{sid}/placements.json')==file_hash(folder/f'prior_placements/{sid}/placements.json')
    source_rows.append({'source_id':sid,'planar_audit_numerics_exact':True,'placement_file_unchanged':True,'audit_sha256':file_hash(ROOT/f'private/gt/{sid}/placement_audit.json')})
case_rows=[]
for record in load_json(folder/'state_before.json')['cases']:
    cid=record['case_id'];out=ROOT/record['input_path'];a=old.physical_case_check(record,out);b=physical_case_check(record,out)
    assert canonical_json(a)==canonical_json(b),cid
    acceptance=ROOT/f'private/annotations/{cid}/acceptance.json';accepted=load_json(acceptance)
    assert accepted['status']=='pass' and canonical_json(b)==canonical_json(accepted['physical_scan'])
    saved=folder/'prior_acceptance'/f'{cid}.json';saved.parent.mkdir(exist_ok=True)
    if not saved.exists():shutil.copy2(acceptance,saved)
    case_rows.append({'case_id':cid,'physical_checks_exact':True,'physical_result_sha256':digest(b),'old_acceptance_path':str(saved.relative_to(ROOT)).replace('\\','/'),'old_acceptance_sha256':file_hash(saved)})
    print('compatible',cid,flush=True)
code={f:file_hash(ROOT/f'src/scanbench/{f}') for f in ['contact_support.py','placement_audit.py','verified_placements.py','validate.py']}
result={'status':'pass','controls':controls,'prior_sources':source_rows,'prior_cases':case_rows,'compared_cases':len(case_rows),'all_other_validator_numerical_functions_AST_unchanged':True,'code_sha256':code,'script_sha256':file_hash(Path(__file__))}
atomic_json(ROOT/'reports/tests/discrete_contact_support.json',result);print('All discrete-contact controls and prior-case compatibility checks passed')
