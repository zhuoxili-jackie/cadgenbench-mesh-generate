"""Regression from the real 231 easy failure: distinct int32 edge keys aliased."""
import numpy as np
import open3d as o3d
from scanbench.reconstruct import orient_from_observations
from scanbench.common import ROOT,atomic_json

def test_large_index_distinct_edges_are_not_nonmanifold():
    count=65537;vertices=np.full((count,3),100.,np.float64)
    vertices[0]=[-2,0,0];vertices[1]=[-1,1,0];vertices[2]=[1,1,0];vertices[3]=[1,-1,0];vertices[65535]=[0,0,0];vertices[65536]=[2,0,0]
    faces=np.array([[0,65535,1],[65535,65536,2],[65536,65535,3]],np.int32);normals=np.tile([0.,0.,1.],(count,1));mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(faces))
    oldkeys=np.array([0,65535],np.int32)*count+np.array([65535,65536],np.int32);newkeys=np.array([0,65535],np.int64)*count+np.array([65535,65536],np.int64)
    assert oldkeys[0]==oldkeys[1] and newkeys[0]!=newkeys[1]
    metrics=orient_from_observations(mesh,vertices,normals)
    assert len(mesh.triangles)==3 and metrics['overlap_conflict_faces_removed']==0 and mesh.is_edge_manifold(allow_boundary_edges=True) and mesh.is_vertex_manifold()
    before=vertices[faces];after=np.asarray(mesh.vertices)[np.asarray(mesh.triangles)];np.testing.assert_array_equal(before,after)
    atomic_json(ROOT/'reports/tests/topology_integer_width.json',{'status':'pass','vertex_count_before_compaction':count,'int32_distinct_edge_alias_reproduced':True,'int64_distinct_edges_preserved':True,'all_three_original_triangles_unchanged':True,'nonmanifold_edges_after':0,'nonmanifold_vertices_after':0,'large_index_keys':newkeys.tolist(),'cause':'Open3D int32 triangle indices overflowed in canonical edge multiplication; no actual nonmanifold BPA edge in the failing real source cache'})
