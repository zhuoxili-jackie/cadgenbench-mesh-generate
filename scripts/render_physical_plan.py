"""Physical plan diagrams; full-surface mesh previews are separate artifacts."""
from pathlib import Path
import os,sys,io
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
os.environ['MPLCONFIGDIR']=str(ROOT/'cache/matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from scanbench.common import *

def render(sid):
    gt=ROOT/f'private/gt/{sid}';dest=ROOT/f'reports/physical_plans/{sid}.png';marker=dest.with_suffix('.json');key=digest([*[file_hash(gt/n) for n in ['mesh.npz','metadata.json','placements.json','cameras.json']],file_hash(Path(__file__)),matplotlib.__version__])
    if marker.exists() and dest.exists() and load_json(marker).get('key')==key and load_json(marker).get('png_sha256')==file_hash(dest):return dest
    raw=np.load(gt/'mesh.npz');meta=load_json(gt/'metadata.json');places=load_json(gt/'placements.json')['placements'];cams=load_json(gt/'cameras.json')['cameras'];count=len(places)
    fig=plt.figure(figsize=(6*count,10));fig.suptitle(f'Source {sid}: {count} actual stable placements, full 3-turn downward spirals',fontsize=15)
    for i,p in enumerate(places):
        T=np.asarray(p['T_table_from_object']);vv=transform(raw['vertices'],T);com=transform(np.array([meta['center_mass_object_mm']]),T)[0];lo=vv.min(0);hi=vv.max(0);poly=np.asarray(p['support_polygon_table_xy']);ax=fig.add_subplot(2,count,i+1)
        contact=np.max(abs(vv[raw['faces'],2]),axis=1)<=p['epsilon_contact_mm'];pc=PolyCollection(vv[raw['faces'][contact],:2],facecolor='#76aeba',edgecolor='none');ax.add_collection(pc);ax.plot(*np.vstack([poly,poly[0]]).T,color='#152f43',lw=1,label='support hull (not contact area)');ax.scatter(com[0],com[1],marker='x',color='#b43235',s=70,label='centre of mass projection')
        if p.get('contact_vertex_ids') is not None:
            points=vv[np.asarray(p['contact_vertex_ids']),:2];ax.scatter(points[:,0],points[:,1],s=24,color='#267f93',label='exact CAD contact points')
        ax.autoscale_view();ax.set_aspect('equal');ax.set_xlabel('table X / mm');ax.set_ylabel('table Y / mm');ax.set_title(f'Pose {i}: contact {p["actual_contact_area_mm2"]:.2f} mm2\nCOM margin {p["stability_margin_mm"]:.3f} mm');ax.legend(fontsize=7,loc='upper right')
        ax=fig.add_subplot(2,count,count+i+1,projection='3d');eyes=np.array([(T@np.array(c['T_object_from_camera']))[:3,3] for c in cams if c['placement_id']==i]);ax.plot(*eyes.T,color='#326c91',lw=1.3);ax.scatter(*eyes[0],color='green',label='start 75 deg');ax.scatter(*eyes[-1],color='red',label='end 5 deg')
        corners=np.array([[x,y,z] for x in [lo[0],hi[0]] for y in [lo[1],hi[1]] for z in [0,hi[2]]]);
        for a in range(8):
            for b in range(a+1,8):
                if np.count_nonzero(corners[a]!=corners[b])==1:ax.plot(*corners[[a,b]].T,color='#758995',lw=.8)
        center=(lo+hi)/2
        for eye in eyes[::32]:ax.plot(*np.array([eye,center]).T,color='#86a5b0',lw=.5,alpha=.5)
        ax.set_box_aspect([1,1,.6]);ax.set_xlabel('X / mm');ax.set_ylabel('Y / mm');ax.set_zlabel('Z / mm');ax.set_title(f'All {len(eyes)} mother positions; sampled sight lines to centre\nwire box = object bounds, support plane z = 0');ax.legend(fontsize=8)
    fig.tight_layout(rect=[0,0,1,.95]);buffer=io.BytesIO();fig.savefig(buffer,format='png',dpi=130);plt.close(fig);atomic_bytes(dest,buffer.getvalue());atomic_json(marker,{'key':key,'png_sha256':file_hash(dest)});return dest

if __name__=='__main__':
    for sid in sys.argv[1:]:print(render(sid),flush=True)
