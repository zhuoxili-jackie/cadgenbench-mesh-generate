"""Read-only investigation of merged subpixel reference patches, not reconstruction."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='2'
import numpy as np,trimesh,open3d as o3d
from scipy.spatial import cKDTree
from scanbench.common import *
from scanbench.validate import read_mesh,distance_scene,sample_area

cid=sys.argv[1];rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path']
dest=ROOT/f'reports/fragmentation/{cid}';folder=dest/'subpixel_regions';folder.mkdir(parents=True,exist_ok=True)
acceptance=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');diagnosis=load_json(dest/'diagnosis.json')
contract=load_json(ROOT/f'private/gt/{rec["source_id"]}/feature_contract.json')
resolution=float(contract['resolvable_feature_mm']);pixel=resolution/6;tol=acceptance['quality']['tolerance_mm']
mesh=read_mesh(out/'mesh.ply');patch=read_mesh(dest/'visible_reference_patch.ply');scene=distance_scene(patch)
def components(m):
    return sorted(trimesh.graph.connected_components(m.face_adjacency,nodes=np.arange(len(m.faces)),min_len=1),key=lambda c:m.area_faces[c].sum(),reverse=True)
pc=components(patch);mc=components(mesh);labels=np.full(len(patch.faces),-1,np.int32)
for i,c in enumerate(pc):labels[c]=i
major=[i for i,c in enumerate(pc) if patch.area_faces[c].sum()>=.01*patch.area]
vertices={i:np.asarray(patch.vertices[np.unique(patch.faces[pc[i]])]) for i in major}
parent={i:i for i in major}
def root(i):
    while parent[i]!=i:i=parent[i]
    return i
pairs=[]
for at,i in enumerate(major):
    tree=cKDTree(vertices[i])
    for j in major[at+1:]:
        gap,index=tree.query(vertices[j]);k=int(np.argmin(gap));value=float(gap[k])
        pairs.append({'regions':[i,j],'nearest_vertex_gap_upper_bound_mm':value,'points_mm':[vertices[i][index[k]],vertices[j][k]],'at_most_one_declared_pixel':value<=pixel})
        if value<=pixel:parent[root(j)]=root(i)
groups={i:root(i) for i in major}
group_labels=np.array([groups.get(int(i),-1) for i in labels],np.int32)
mapping=[];original_counts=[]
for i,c in enumerate(mc):
    if mesh.area_faces[c].sum()<.01*mesh.area:continue
    sub=mesh.submesh([c],append=True,repair=False);points,_=sample_area(sub,10000,710+i)
    closest=scene.compute_closest_points(o3d.core.Tensor(points.astype(np.float32)),nthreads=2)
    primitive=closest['primitive_ids'].numpy();raw=labels[primitive];group=group_labels[primitive]
    unique,count=np.unique(group,return_counts=True);winner=int(unique[np.argmax(count)])
    mapping.append({'mesh_component':i,'reference_group':winner,'purity':float(count.max()/len(group)),'distance_p95_mm':float(np.quantile(np.linalg.norm(closest['points'].numpy()-points,axis=1),.95)),'area_mm2':float(sub.area),'reference_component_counts':{str(k):int(v) for k,v in zip(*np.unique(raw,return_counts=True))}})
closest=scene.compute_closest_points(o3d.core.Tensor(mesh.vertices.astype(np.float32)),nthreads=2)
vertex_regions=labels[closest['primitive_ids'].numpy()];vertex_groups=group_labels[closest['primitive_ids'].numpy()]
raw_faces=vertex_regions[mesh.faces];group_faces=vertex_groups[mesh.faces]
cross=(raw_faces.max(1)!=raw_faces.min(1))&(group_faces.min(1)>=0)&(group_faces.max(1)==group_faces.min(1))
ids=np.flatnonzero(cross);tri=mesh.triangles[ids]
weights=np.array([(i/5,j/5,1-(i+j)/5) for i in range(6) for j in range(6-i)]+[(1/3,1/3,1/3)])
work=np.asarray(trimesh.load(out/'points_for_meshing.ply',process=False).vertices)
samples=np.einsum('sk,nkj->nsj',weights,tri).reshape(-1,3)
dist=cKDTree(work).query(samples)[0] if len(samples) else np.array([])
edge=np.linalg.norm(tri-np.roll(tri,1,axis=1),axis=2) if len(tri) else np.zeros((0,3))
observed_closest=closest['points'].numpy()[mesh.faces[ids]]
reference_spans=np.linalg.norm(observed_closest-np.roll(observed_closest,1,axis=1),axis=2)
transition_pairs={tuple(sorted(set(map(int,x)))) for x in raw_faces[ids]}
pair_lookup={tuple(x['regions']):x for x in pairs}
bridges={'faces':len(ids),'area_mm2':float(mesh.area_faces[ids].sum()),'area_fraction':float(mesh.area_faces[ids].sum()/mesh.area),'max_triangle_edge_mm':float(edge.max()) if edge.size else 0.,'max_nearest_reference_span_mm':float(reference_spans.max()) if reference_spans.size else 0.,'lattice_samples':len(samples),'lattice_observation_supported_fraction':float(np.mean(dist<=tol)) if len(dist) else 1.,'lattice_max_working_observation_distance_mm':float(dist.max()) if len(dist) else 0.,'transition_region_sets':[list(x) for x in sorted(transition_pairs)]}
checks={'original_hard_gates_passed':not acceptance['failures'],'raw_reference_major_regions_exceed_mesh_major_regions':len(major)>len(mapping),'at_least_two_pixel_scale_reference_groups':len(set(groups.values()))>=2,'one_to_one_major_regions_at_one_pixel_scale':len(mapping)==len(set(groups.values())) and len({x['reference_group'] for x in mapping})==len(mapping),'group_area_mapping_purity':all(x['purity']>=.99 and x['distance_p95_mm']<=tol for x in mapping),'minor_area_below_unchanged_gate':acceptance['mesh']['tiny_component_area_fraction']<=.03 and sum(x['area_mm2'] for x in mapping)/mesh.area>=.97,'every_merge_pair_has_a_subpixel_gap':all(len(x)==2 and tuple(x) in pair_lookup and pair_lookup[tuple(x)]['at_most_one_declared_pixel'] for x in transition_pairs),'local_bridge_edges_below_declared_feature_size':bridges['max_triangle_edge_mm']<resolution and bridges['max_nearest_reference_span_mm']<resolution,'bridge_lattice_supported_at_unchanged_tolerance':bridges['lattice_observation_supported_fraction']>=.98,'observed_retention':acceptance['quality']['observation_mesh_retained_fraction']>=.95,'organized_same_observations_retention':diagnosis['organized_comparison_mean_retained']>=.95,'complete_trajectory':acceptance['physical_scan']['status']=='pass'}
atomic_npz(folder/'measurements.npz',bridge_face_ids=ids,vertex_reference_regions=vertex_regions,bridge_lattice_observation_distance_mm=dist,reference_span_mm=reference_spans)
if len(ids):mesh.submesh([ids],append=True,repair=False).export(folder/'bridge_faces.ply')
proof={'status':'diagnostic_checks_pass' if all(checks.values()) else 'unresolved','case_id':cid,'mesh_sha256':file_hash(out/'mesh.ply'),'source_sha256':rec['source_sha256'],'script_sha256':file_hash(Path(__file__)),'declared_feature_size_mm':resolution,'declared_pixel_step_mm':pixel,'unchanged_support_tolerance_mm':tol,'raw_reference_major_regions':len(major),'reference_groups_at_one_pixel_scale':groups,'pair_distances':pairs,'mapping':mapping,'bridges':bridges,'checks':checks,'qualification_note':'Raw reference components are not rewritten. This separately quantifies local joining across less-than-one-pixel gaps. It does not certify preservation of such subresolution grooves or alter any output mesh, observation, frozen parameter, or formal quality metric. Large observed-region separation must still map one to one after this explicitly reported scale comparison.'}
atomic_json(folder/'diagnosis.json',proof)
print(canonical_json({k:v for k,v in proof.items() if k not in ['pair_distances','mapping']}))
