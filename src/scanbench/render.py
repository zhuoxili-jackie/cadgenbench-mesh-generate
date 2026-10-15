"""Complete-surface orthographic ray rendering; never subsamples triangles."""
from pathlib import Path
import numpy as np
import open3d as o3d
from PIL import Image,ImageDraw,ImageFont
from .common import ROOT,load_json,atomic_json
from .camera import look_at
from .validate import read_mesh,distance_scene

def render_mesh(scene,bounds,direction,size=360,color=(92,166,203)):
    bounds=np.asarray(bounds); center=bounds.mean(axis=0); diagonal=np.linalg.norm(bounds[1]-bounds[0]); d=np.asarray(direction,dtype=float); d/=np.linalg.norm(d)
    eye=center+d*diagonal*2; camera=look_at(eye,center); extent=diagonal*.59
    yy,xx=np.mgrid[:size,:size]; x=(xx-(size-1)/2)/(size/2)*extent; y=(yy-(size-1)/2)/(size/2)*extent
    origins=eye+x[:,:,None]*camera[:3,0]+y[:,:,None]*camera[:3,1]; forward=np.broadcast_to(camera[:3,2],origins.shape)
    rays=np.concatenate([origins,forward],axis=2).astype(np.float32)
    hits=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2); ranges=hits['t_hit'].numpy(); normals=hits['primitive_normals'].numpy()
    mask=np.isfinite(ranges); light=(d+np.array([.35,-.3,.8])); light/=np.linalg.norm(light)
    shade=.3+.7*np.abs(normals@light)
    rgb=np.full((size,size,3),242,np.uint8); lit=np.clip(shade[:,:,None]*np.asarray(color),0,255).astype(np.uint8)
    back=(normals@d)<0
    lit[back]=np.clip(shade[back,None]*np.array([226,152,99]),0,255).astype(np.uint8)
    rgb[mask]=lit[mask]
    # Depth contour against genuine geometric background; nothing is discarded.
    boundary=mask&(~np.roll(mask,1,axis=0)|~np.roll(mask,-1,axis=0)|~np.roll(mask,1,axis=1)|~np.roll(mask,-1,axis=1))
    rgb[boundary]=np.array(color)*.5
    return Image.fromarray(rgb)

def font(size):
    try: return ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',size)
    except OSError: return ImageFont.load_default()

def atlas(mesh_path,bounds,support_normal,output,title,size=360,color=(92,166,203)):
    mesh=read_mesh(mesh_path); scene=distance_scene(mesh)
    directions=[('Front +Y',[0,1,0]),('Right +X',[1,0,0]),('Top +Z',[0,0,1]),('Oblique',[1,-1,1]),('Back -Y',[0,-1,0]),('Initial contact side',support_normal)]
    im=Image.new('RGB',(size*3,(size+32)*2+62),'white'); draw=ImageDraw.Draw(im)
    draw.text((12,5),title,fill=(20,30,40),font=font(18)); draw.text((12,32),f'{len(mesh.vertices):,} vertices | {len(mesh.faces):,} faces | all faces | orange = reverse side visible through openings | mm',fill=(60,70,80),font=font(14))
    for i,(name,direction) in enumerate(directions):
        x=(i%3)*size;y=62+(i//3)*(size+32)
        im.paste(render_mesh(scene,bounds,direction,size,color),(x,y+28)); draw.text((x+10,y+2),name,fill=(30,40,55),font=font(16))
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); im.save(output)
    return output

def render_case(cid):
    rec=load_json(ROOT/f'private/annotations/{cid}/case.json'); sid=rec['source_id']; gt=ROOT/f'private/gt/{sid}'
    bounds=load_json(gt/'metadata.json')['bounds_object_mm']; support=load_json(gt/'placements.json')['placements'][0]['support_outward_object']
    return atlas(ROOT/rec['input_path']/'mesh.ply',bounds,support,ROOT/f'reports/private_previews/{cid}.png',f'{cid} | source {sid} | {rec["level"]} | seed {rec["seed"]}')

def render_gt(sid):
    gt=ROOT/f'private/gt/{sid}'; bounds=load_json(gt/'metadata.json')['bounds_object_mm']; support=load_json(gt/'placements.json')['placements'][0]['support_outward_object']
    return atlas(gt/'mesh.ply',bounds,support,ROOT/f'reports/private_previews/gt_{sid}.png',f'PRIVATE reference source {sid}',color=(150,157,164))
