"""Analytic controls distinguish working default/exact checker modes."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakeSphere
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepTools import BRepTools
folder=ROOT/'tests/artifacts/brep_checker_modes';folder.mkdir(parents=True,exist_ok=True)
rows=[]
for name,dimensions,shape in [('box',{'lengths_mm':[11,17,23]},BRepPrimAPI_MakeBox(11,17,23).Shape()),('cylinder',{'radius_mm':10,'height_mm':25},BRepPrimAPI_MakeCylinder(10,25).Shape()),('sphere',{'radius_mm':10},BRepPrimAPI_MakeSphere(10).Shape())]:
    checks={label:bool(BRepCheck_Analyzer(shape,True,False,exact).IsValid()) for label,exact in [('default_geometry',False),('exact_parameter',True)]}
    assert all(checks.values()),(name,checks)
    path=folder/f'{name}.brep';BRepTools.Write_s(shape,os.path.relpath(path))
    rows.append({'name':name,'dimensions':dimensions,'checks':checks,'brep_path':str(path.relative_to(ROOT)).replace('\\','/'),'brep_sha256':file_hash(path)})
proof={'status':'pass','controls':rows,'ocp_version':__import__('importlib.metadata',fromlist=['version']).version('cadquery-ocp'),'script_sha256':file_hash(Path(__file__)),'source_or_reference_geometry_modified':False,'note':'Extra exact-parameter failures in the original STEP imports are separately diagnosed; both modes pass unambiguous analytic primitives.'}
atomic_json(ROOT/'reports/tests/brep_checker_modes.json',proof);print(canonical_json(proof))
