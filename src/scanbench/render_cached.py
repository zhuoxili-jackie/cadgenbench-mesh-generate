"""Hash-qualified atomic preview stage, preserving completed previews on resume."""
from .common import *
from .render import atlas

def preview(identifier,state,is_source=False):
    if is_source:
        sid=identifier;gt=ROOT/f'private/gt/{sid}';mesh=gt/'mesh.ply';name=f'gt_{sid}';stage='preview_gt'
    else:
        rec=load_json(ROOT/f'private/annotations/{identifier}/case.json');sid=rec['source_id'];gt=ROOT/f'private/gt/{sid}';mesh=ROOT/rec['input_path']/'mesh.ply';name=identifier;stage='preview'
    image=ROOT/f'reports/private_previews/{name}.png';marker=image.with_suffix('.json');key=stage_hash([file_hash(mesh),file_hash(gt/'metadata.json'),file_hash(gt/'placements.json')],{'size':360,'full_surface':True},['render.py','render_cached.py'],['open3d','trimesh','pillow'])
    if state.valid(identifier,stage,key):return image
    state.begin(identifier,stage,key)
    with measured() as timing:
        # Renderer receives all facets; publish only the fully written PNG.
        bounds=load_json(gt/'metadata.json')['bounds_object_mm'];support=load_json(gt/'placements.json')['placements'][0]['support_outward_object']
        title=f'PRIVATE reference source {sid}' if is_source else f'{identifier} | source {sid} | {rec["level"]} | seed {rec["seed"]}'
        tmp=image.with_name(image.stem+'.partial.png');atlas(mesh,bounds,support,tmp,title,color=(150,157,164) if is_source else (92,166,203))
        atomic_bytes(image,tmp.read_bytes());tmp.unlink()
        atomic_json(marker,{'key':key,'mesh_sha256':file_hash(mesh),'preview_sha256':file_hash(image),'rendering':'all triangles, six fixed orthographic/oblique/contact views'})
    state.finish(identifier,stage,key,[image,marker],timing);return image
