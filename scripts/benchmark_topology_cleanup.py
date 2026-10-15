"""Numerical equivalence against real cached BPA outputs; no production writes."""
from pathlib import Path
import sys,os,inspect,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
import numpy as np,open3d as o3d
from scanbench.common import *
import scanbench.reconstruct as r
text=inspect.getsource(r.orient_from_observations)
text=text.replace("    vertex_order=np.argsort(f.reshape(-1),kind='stable'); incident_faces=vertex_order//3\n",'').replace('    offsets=np.r_[0,np.cumsum(np.bincount(f.reshape(-1),minlength=len(v)))]\n','')
text=text.replace('incident=incident_faces[offsets[vid]:offsets[vid+1]];','incident=np.flatnonzero(np.any(f==vid,axis=1));')
scope=dict(r.__dict__);exec(compile(text,'linear_incidence_reference','exec'),scope);reference=scope['orient_from_observations'];optimized=r.orient_from_observations;results=[]
for cid in sys.argv[1:]:
    out=ROOT/f'data/cases/{cid}/input';f=np.load(out/'.reconstruction_cache/fusion.npz');s=np.load(out/'.reconstruction_cache/supported.npz');mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(s['vertices']),o3d.utility.Vector3iVector(s['faces']));start=time.perf_counter();metrics=optimized(mesh,f['P'],f['N']);seconds=time.perf_counter()-start;expected=o3d.io.read_triangle_mesh(str(out/'mesh.ply'))
    baseline=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(s['vertices']),o3d.utility.Vector3iVector(s['faces']));start=time.perf_counter();slow_metrics=reference(baseline,f['P'],f['N']);slow_seconds=time.perf_counter()-start
    np.testing.assert_array_equal(np.asarray(mesh.vertices),np.asarray(baseline.vertices));np.testing.assert_array_equal(np.asarray(mesh.triangles),np.asarray(baseline.triangles));assert metrics==slow_metrics
    np.testing.assert_array_equal(np.asarray(mesh.vertices),np.asarray(expected.vertices));np.testing.assert_array_equal(np.asarray(mesh.triangles),np.asarray(expected.triangles));assert metrics==load_json(out/'reconstruction.json')['orientation'];results.append({'case_id':cid,'seconds':seconds,'linear_reference_seconds':slow_seconds,'vertices':len(mesh.vertices),'faces':len(mesh.triangles),'all_float64_vertices_and_indexed_faces_exact':True,'orientation_metrics_identical':True,'current_mesh_sha256':file_hash(out/'mesh.ply')})
    print(canonical_json(results[-1]),flush=True)
atomic_json(ROOT/'reports/tests/topology_optimization_equivalence.json',{'status':'pass','reconstruction_code_sha256':file_hash(ROOT/'src/scanbench/reconstruct.py'),'algorithm_change':'compare precomputed sorted vertex-face incidence with independent linear face-membership lookup in the current int64-safe algorithm; preserve face order and current fan links','results':results})
