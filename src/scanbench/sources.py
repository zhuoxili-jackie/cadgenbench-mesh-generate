"""Private STEP provenance and BREP tessellation. Never imported by reconstruction."""
from pathlib import Path
import os, re, time, traceback, urllib.request
import numpy as np
import trimesh
from .common import *

def acquire(sid,state):
    tree=load_json(ROOT/'sources/upstream_tree.json')
    entry=next(x for x in tree if x['path']==f'{sid}/input.step')
    expected=entry['lfs']['oid']; path=ROOT/f'sources/{sid}/input.step'
    url=f'https://huggingface.co/datasets/HuggingAI4Engineering/cadgenbench-data/resolve/{REV}/{sid}/input.step'
    key=digest({'revision':REV,'sha256':expected})
    if state.valid(sid,'download',key): return path
    state.begin(sid,'download',key)
    with measured() as timing:
        if not path.exists() or file_hash(path)!=expected:
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(url,timeout=120) as response: raw=response.read()
                    if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('upstream LFS hash mismatch')
                    atomic_bytes(path,raw); break
                except Exception:
                    if attempt==3: raise
                    time.sleep(2*(attempt+1))
        meta={'source_id':sid,'revision':REV,'url':url,'sha256':expected,'bytes':path.stat().st_size,'license':'ODC-BY','role':'public editing input, used as original shape; no editing instruction executed','attribution':'HuggingAI4Engineering / CADGenBench / Mecado'}
        atomic_json(path.parent/'provenance.json',meta)
    state.finish(sid,'download',key,[path,path.parent/'provenance.json'],timing)
    return path

def read_step(path):
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.TColStd import TColStd_SequenceOfAsciiString
    from OCP.Interface import Interface_Static
    Interface_Static.SetCVal_s('xstep.cascade.unit','MM')
    reader=STEPControl_Reader()
    # Relative paths avoid legacy Windows narrow-path handling in OCC.
    status=reader.ReadFile(os.path.relpath(path))
    if status!=IFSelect_RetDone: raise ValueError(f'STEP ReadFile status={status}')
    length,angle,solidangle=(TColStd_SequenceOfAsciiString() for _ in range(3))
    reader.FileUnits(length,angle,solidangle)
    units=[length.Value(i).ToCString() for i in range(1,length.Length()+1)]
    reader.SetSystemLengthUnit(1.0)
    roots=reader.TransferRoots()
    if not roots: raise ValueError('STEP TransferRoots returned zero')
    shape=reader.OneShape()
    return shape,{'source_length_units':units,'internal_unit':'millimetre','system_length_unit_mm':reader.SystemLengthUnit(),'transfer_roots':roots}

def shape_metadata(shape):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_COMPOUND, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    box=Bnd_Box(); BRepBndLib.AddOptimal_s(shape,box,False,False)
    bounds=np.array(box.Get()).reshape(2,3)
    props=GProp_GProps(); BRepGProp.VolumeProperties_s(shape,props)
    c=props.CentreOfMass()
    counts={}
    for name,kind in [('solids',TopAbs_SOLID),('shells',TopAbs_SHELL),('compounds',TopAbs_COMPOUND),('faces',TopAbs_FACE)]:
        mapping=TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(shape,kind,mapping); counts[name]=mapping.Size()
    return {'brep_valid':BRepCheck_Analyzer(shape).IsValid(),'counts':counts,'bounds_source_mm':bounds,'volume_mm3':props.Mass(),'center_mass_source_mm':[c.X(),c.Y(),c.Z()], 'rigid_assembly_assumption':counts['solids']>1}

def analytic_features(shape,center):
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    out=[]; exp=TopExp_Explorer(shape,TopAbs_FACE); i=0
    while exp.More():
        i+=1; face=TopoDS.Face_s(exp.Current()); surf=BRepAdaptor_Surface(face)
        props=GProp_GProps(); BRepGProp.SurfaceProperties_s(face,props)
        c=props.CentreOfMass(); cm=np.array([c.X(),c.Y(),c.Z()])-center
        if surf.GetType()==GeomAbs_Plane:
            plane=surf.Plane(); d=plane.Axis().Direction(); n=np.array([d.X(),d.Y(),d.Z()])
            if face.Orientation()==TopAbs_REVERSED: n=-n
            out.append({'face':i,'type':'plane','normal':n,'centroid':cm,'area_mm2':props.Mass()})
        elif surf.GetType()==GeomAbs_Cylinder:
            cy=surf.Cylinder(); p=cy.Location(); a=cy.Axis().Direction()
            out.append({'face':i,'type':'cylinder','radius_mm':cy.Radius(),'axis_point':np.array([p.X(),p.Y(),p.Z()])-center,'axis_direction':[a.X(),a.Y(),a.Z()],'area_mm2':props.Mass(),'reversed':face.Orientation()==TopAbs_REVERSED,'u_range':[surf.FirstUParameter(),surf.LastUParameter()],'v_range':[surf.FirstVParameter(),surf.LastVParameter()]})
        exp.Next()
    return out

def brep_distance_check(shape,vertices,faces,center,n=128):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt
    mesh=trimesh.Trimesh(vertices,faces,process=False)
    points,ids=trimesh.sample.sample_surface(mesh,n,seed=1234)
    values=[]
    for p in points+center:
        vertex=BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex()
        dist=BRepExtrema_DistShapeShape(vertex,shape); dist.Perform()
        if not dist.IsDone(): raise RuntimeError('BREP distance query failed')
        values.append(dist.Value())
    return {'direction':'mesh surface -> BREP','unit':'mm','method':'128 fixed area-distributed samples, OCC exact point-shape distance','n':n,'max_sampled_mm':max(values),'p95_mm':float(np.quantile(values,.95)),'not_exact_hausdorff':True}

def prepare(sid,state):
    path=acquire(sid,state); cfg=config()['gt']
    key=stage_hash(file_hash(path),cfg,['sources.py'],['cadquery-ocp','numpy','trimesh'])
    folder=ROOT/f'private/gt/{sid}'; meta_path=folder/'metadata.json'
    if state.valid(sid,'gt',key): return load_json(meta_path)
    state.begin(sid,'gt',key)
    from cadgenbench.common.mesh import tessellate_shape,validate_mesh
    with measured() as timing:
        shape,units=read_step(path); meta=shape_metadata(shape)
        if not units['source_length_units']: raise ValueError('no explicit source units')
        if not meta['brep_valid']: raise ValueError('BREP invalid; requires further source investigation')
        center=np.mean(meta['bounds_source_mm'],axis=0); attempts=[]; chosen=None; chosen_accuracy=None
        for chord,ang in [(cfg['chord_mm'],cfg['angle_rad']),(cfg['chord_mm']/2,cfg['angle_rad']/2),(cfg['chord_mm'],0.3)]:
            attempt={'chord_mm':chord,'angle_rad':ang};t=time.perf_counter()
            try:
                from OCP.BRepTools import BRepTools
                BRepTools.Clean_s(shape)
                mesh=tessellate_shape(shape,chord,angular_deflection_rad=ang,parallel=False)
                validate_mesh(mesh)
                trial_vertices=mesh.vertices-center;trial_faces=mesh.triangles
                trial_tm=trimesh.Trimesh(trial_vertices,trial_faces,process=False)
                if np.any(trial_tm.area_faces<=1e-16):raise ValueError('geometrically degenerate GT face')
                accuracy=brep_distance_check(shape,trial_vertices,trial_faces,center)
                limit=max(.021,mesh.linear_deflection_mm*1.1)
                attempt.update(accuracy_check=accuracy,accuracy_limit_mm=limit,vertices=len(trial_vertices),faces=len(trial_faces))
                if accuracy['max_sampled_mm']>limit:raise ValueError(f'sampled BREP deviation {accuracy["max_sampled_mm"]:.12g} mm exceeds unchanged bound {limit:.12g} mm')
                attempt.update(status='pass',seconds=time.perf_counter()-t);attempts.append(attempt)
                chosen=mesh;chosen_accuracy=accuracy;break
            except Exception as e:
                attempt.update(status='failed',seconds=time.perf_counter()-t,error=repr(e),traceback=traceback.format_exc());attempts.append(attempt)
                atomic_json(folder/'native_attempts.json',attempts)
        atomic_json(folder/'native_attempts.json',attempts)
        if chosen is None: raise RuntimeError(f'native tessellation failed for {sid}; investigate official sidecar: {attempts[-1]["error"]}')
        vertices=chosen.vertices-center; faces=chosen.triangles
        tm=trimesh.Trimesh(vertices,faces,process=False)
        if np.any(tm.area_faces<=1e-16): raise ValueError('geometrically degenerate GT face')
        T=np.eye(4); T[:3,3]=-center
        meta.update(units)
        meta.update(source_id=sid,source_sha256=file_hash(path),revision=REV,status='eligible_native',
                    T_object_from_source_mm=T,T_source_mm_from_object=np.linalg.inv(T),
                    bounds_object_mm=tm.bounds,diagonal_mm=float(np.linalg.norm(tm.extents)),
                    center_mass_object_mm=np.array(meta['center_mass_source_mm'])-center,
                    vertices=len(vertices),faces=len(faces),area_mm2=float(tm.area),
                    mesh_volume_mm3=float(tm.volume),watertight=tm.is_watertight,winding_consistent=tm.is_winding_consistent,
                    components=[{'faces':len(c.faces),'area_mm2':float(c.area),'signed_volume_mm3':float(c.volume)} for c in tm.split(only_watertight=False)],
                    chord_mm=chosen.linear_deflection_mm,angle_rad=attempts[-1]['angle_rad'],
                    accuracy_check=chosen_accuracy,stage_hash=key,
                    unit_scale_evidence='STEPControl FileUnits and explicit internal mm conversion, never inferred from bounding box')
        if meta['accuracy_check']['max_sampled_mm']>max(.021,chosen.linear_deflection_mm*1.1): raise ValueError('sampled BREP deviation exceeds chord bound')
        atomic_npz(folder/'mesh.npz',vertices=vertices,faces=faces)
        atomic_bytes(folder/'mesh.ply',tm.export(file_type='ply'))
        atomic_json(folder/'features.json',analytic_features(shape,center))
        atomic_json(meta_path,meta)
    state.record('sources',sid,meta)
    state.finish(sid,'gt',key,[folder/'mesh.npz',folder/'mesh.ply',folder/'features.json',meta_path,folder/'native_attempts.json'],timing)
    return meta
