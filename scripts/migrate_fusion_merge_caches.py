"""Re-key only proven identical fusion/BPA/support/mesh artifacts, retaining raw bytes."""
from pathlib import Path
import os,sys,ast,inspect,importlib.util,importlib.metadata
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
from scanbench import reconstruct as current
import open3d,numba
folder=ROOT/'reports/protocol_amendments/r2_fusion_merge';installation=load_json(folder/'installation.json');inventory=load_json(folder/'inventory_before.json');cfg=config()['reconstruction'];state=State()
assert file_hash(ROOT/'src/scanbench/reconstruct.py')==installation['new_code_sha256']
spec=importlib.util.spec_from_file_location('scanbench._pre_fusion_merge',folder/'reconstruct_before.py');before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
candidate=ast.parse((ROOT/'scripts/fusion_merge_candidate.py').read_text());actual=ast.parse((ROOT/'src/scanbench/reconstruct.py').read_text());old=ast.parse((folder/'reconstruct_before.py').read_text())
class Normalize(ast.NodeTransformer):
    def visit_ImportFrom(self,node):return None
    def visit_Constant(self,node):
        if isinstance(node.value,str):node.value=node.value.replace('candidate fusion ','fusion ')
        return node
for name in ['merge_indices','fuse']:
    aa=next(n for n in actual.body if isinstance(n,ast.FunctionDef) and n.name==name);bb=next(n for n in candidate.body if isinstance(n,ast.FunctionDef) and n.name==name)
    assert ast.dump(Normalize().visit(aa),include_attributes=False)==ast.dump(Normalize().visit(bb),include_attributes=False),f'candidate differs in {name}'
for node in old.body:
    if isinstance(node,ast.FunctionDef) and node.name not in ['fuse','reconstruct']:
        other=next(n for n in actual.body if isinstance(n,ast.FunctionDef) and n.name==node.name)
        assert ast.dump(node,include_attributes=False)==ast.dump(other,include_attributes=False),node.name
results=[]
for cid,item in inventory.items():
    out=ROOT/f'data/cases/{cid}/input';cache=out/'.reconstruction_cache';cams=load_json(out/'cameras.json');proof=load_json(ROOT/item['proof_path'])
    assert file_hash(ROOT/item['proof_path'])==item['proof_sha256']
    unchanged={path:data for path,data in item['files'].items() if Path(path).name not in ['fusion.json','bpa.json','supported.json']}
    for path,(h,mtime) in unchanged.items():assert file_hash(ROOT/path)==h and (ROOT/path).stat().st_mtime_ns==mtime,f'{cid}: original numeric/public artifact changed {path}'
    inputs=[file_hash(out/'observations.json'),file_hash(out/'cameras.json'),file_hash(ROOT/'src/scanbench/camera.py'),{'voxel_pixel_factor':cfg['voxel_pixel_factor']}]
    old_fkey=digest(inputs+[[inspect.getsource(fn) for fn in [before.fuse,before.frame_points_normals,before.reduce_representatives,before.voxel_keys]],np.__version__])
    new_fkey=digest(inputs+[[inspect.getsource(fn) for fn in [current.fuse,current.merge_indices.py_func,current.frame_points_normals,current.reduce_representatives,current.voxel_keys]],np.__version__,numba.__version__])
    fm=load_json(cache/'fusion.json');assert fm['key'] in [old_fkey,new_fkey] and fm['file_hash']==proof['original_fusion_npz_sha256']
    radii=[r*fm['metrics']['h_mm'] for r in cfg['radii_h']];old_bkey=digest([old_fkey,radii,open3d.__version__]);new_bkey=digest([new_fkey,radii,open3d.__version__])
    support_inputs=[cfg,cams['sigma_mm'],file_hash(ROOT/'src/scanbench/observed_kernel.py'),numba.__version__,[inspect.getsource(fn) for fn in [current.filter_observed_mesh,current.sample_triangles,current.support_in_camera]]]
    old_skey=digest([old_bkey]+support_inputs);new_skey=digest([new_bkey]+support_inputs)
    for filename,old_key,new_key in [('fusion.json',old_fkey,new_fkey),('bpa.json',old_bkey,new_bkey),('supported.json',old_skey,new_skey)]:
        path=cache/filename;meta=load_json(path);assert meta['key'] in [old_key,new_key],f'{cid}/{filename}: unqualified cache key'
        assert meta['file_hash']==file_hash(path.with_suffix('.npz'))
        reuse={'revision':'r2_fusion_merge','original_key':old_key,'fusion_proof_sha256':item['proof_sha256']}
        if meta['key']==new_key:assert meta.get('equivalent_implementation_reuse')==reuse
        meta.update(key=new_key,equivalent_implementation_reuse=reuse);atomic_json(path,meta)
    mesh_key=stage_hash([file_hash(out/'observations.json'),file_hash(out/'cameras.json')],cfg,['reconstruct.py','camera.py','observed_kernel.py'],['numpy','open3d','scipy','numba'])
    if not state.valid(cid,'mesh',mesh_key):state.finish(cid,'mesh',mesh_key,[ROOT/p for p in item['outputs']],{'reuse_only':True,'implementation_revision':'r2_fusion_merge','original_generation_stage_key':item['original_stage_hash'],'prior_numerical_stage_metrics':item['metrics']})
    rec=load_json(ROOT/f'private/annotations/{cid}/case.json');rec.update(mesh_stage_hash=mesh_key,qualified_implementation_reuse={'revision':'r2_fusion_merge','original_generation_stage_key':item['original_stage_hash'],'fusion_equivalence_proof_sha256':item['proof_sha256']});atomic_json(ROOT/f'private/annotations/{cid}/case.json',rec);state.record('cases',cid,rec)
    for path,(h,mtime) in unchanged.items():assert file_hash(ROOT/path)==h and (ROOT/path).stat().st_mtime_ns==mtime,f'{cid}: numeric or public artifact changed'
    results.append({'case_id':cid,'proof_sha256':item['proof_sha256'],'unchanged_public_and_numeric_cache_files':unchanged,'new_mesh_stage_hash':mesh_key,'prior_mesh_stage_hash':item['original_stage_hash']})
atomic_json(folder/'cache_reuse.json',{'status':'pass','candidate_and_installed_fusion_AST_equivalent':True,'all_other_numerical_functions_unchanged':True,'cases':results});print(canonical_json({'status':'pass','cases_reused':len(results),'numeric_files_changed':0}))
