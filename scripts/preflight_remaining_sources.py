"""Bounded read-only validity checks while existing Mesh migrations run."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='2'
from scanbench.common import *
rows=[]
official={x['path'].split('/')[0]:x['lfs']['oid'] for x in load_json(ROOT/'sources/upstream_tree.json') if x['path'].endswith('/input.step')}
for sid in ['244','245','246','247','248','249','250']:
    source=ROOT/f'sources/{sid}/input.step';assert file_hash(source)==official[sid]
    reserve=2.8 if source.stat().st_size>5*2**20 else 2.0
    while psutil.virtual_memory().available<reserve*2**30:
        print(canonical_json({'waiting_for_ram_gib':reserve,'source':sid,'available_gib':psutil.virtual_memory().available/2**30}),flush=True);time.sleep(20)
    log=ROOT/f'logs/remaining_preflight_{sid}.log';start=time.time();peak=0
    with log.open('a',encoding='utf-8') as stream:
        process=subprocess.Popen([sys.executable,'scripts/investigate_brep_validity.py',sid],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        while process.poll() is None:
            try:
                parent=psutil.Process(process.pid);peak=max(peak,sum(p.memory_info().rss for p in [parent,*parent.children(recursive=True)] if p.is_running()))
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            time.sleep(.2)
    assert process.returncode==0,(sid,process.returncode,str(log))
    reports=[ROOT/f'reports/source_investigations/{sid}/brep_check_{name}.json' for name in ['ordinary','exact_curve_on_surface','topology_only_diagnostic']]
    row={'source_id':sid,'source_sha256':official[sid],'seconds':time.time()-start,'peak_process_tree_rss_bytes':peak,'validity':{load_json(p)['check']:load_json(p)['valid'] for p in reports},'reports_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in reports},'no_source_or_mesh_modified':True,'not_a_final_source_disposition':True}
    rows.append(row);atomic_json(ROOT/'reports/remaining_sources_preflight.json',{'status':'diagnostic_only','sources':rows,'still_required':'Reference qualification, placements, six cases for each eligible source, and full independent acceptance. Invalidity requires further evidence, never automatic exclusion.'});print(canonical_json(row),flush=True)
