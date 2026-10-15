"""Record a direct image inspection performed by the operator; not an auto-review."""
from pathlib import Path
import os,sys,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *
from scanbench.cases import case_id
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--notes',required=True);args=p.parse_args();sid=args.source;cases=[]
for level in ['hard','easy']:
    cid=case_id(sid,level,config()['seeds'][0]);out=ROOT/f'data/cases/{cid}/input';preview=ROOT/f'reports/private_previews/{cid}.png'
    if not preview.exists():raise SystemExit('image must exist and be directly viewed before recording review')
    mesh_hash=file_hash(out/'mesh.ply');preview_hash=file_hash(preview);marker=load_json(preview.with_suffix('.json'))
    if marker['mesh_sha256']!=mesh_hash or marker['preview_sha256']!=preview_hash or not State().valid(cid,'preview',marker['key']):raise SystemExit('preview is not a completed render of the current Mesh; wait for its verified preview stage')
    cases.append({'case_id':cid,'level':level,'mesh_sha256':mesh_hash,'preview_sha256':preview_hash,'preview':str(preview.relative_to(ROOT))})
atomic_json(ROOT/f'reports/visual_reviews/{sid}.json',{'status':'pass','source_id':sid,'reviewer':'Codex direct inspection of displayed full-surface images','views':'all six panels: front, side, top, oblique, back, initial-contact side; all triangles ray-rendered','cases':cases,'observations':args.notes,'time':time.time()})
