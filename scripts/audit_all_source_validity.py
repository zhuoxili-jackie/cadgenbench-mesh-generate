"""Bind ordinary and extra exact-parameter checks for all official source bytes.

This read-only diagnostic does not change the frozen qualification criterion,
source dispositions, imported geometry, tolerances, reference meshes or cases.
"""
from pathlib import Path
import os,sys,subprocess,collections
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *

rows=[]
names=['ordinary','exact_curve_on_surface','topology_only_diagnostic']
for sid in IDS:
    source=ROOT/f'sources/{sid}/input.step';folder=ROOT/f'reports/source_investigations/{sid}'
    paths=[folder/f'brep_check_{name}.json' for name in names]
    if not all(path.exists() and load_json(path).get('source_sha256')==file_hash(source) for path in paths):
        while psutil.virtual_memory().available<1.8*2**30:
            print(canonical_json({'source':sid,'waiting_for_ram_gib':1.8}),flush=True);time.sleep(15)
        print(canonical_json({'checking_source':sid,'time':time.time()}),flush=True)
        with (ROOT/f'logs/independent_validity_{sid}.log').open('a',encoding='utf-8') as stream:
            subprocess.run([sys.executable,'scripts/investigate_brep_validity.py',sid],check=True,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    reports={name:load_json(path) for name,path in zip(names,paths)}
    assert all(r['source_sha256']==file_hash(source) and r['source_or_topology_modifications'] is False for r in reports.values())
    statuses={name:dict(collections.Counter(s for e in rep['errors'] for s in e['own_status']+[s for c in e['context'] for s in c['status']])) for name,rep in reports.items()}
    row={'source_id':sid,'source_sha256':file_hash(source),'ordinary_valid':reports['ordinary']['valid'],'extra_exact_parameter_valid':reports['exact_curve_on_surface']['valid'],'topology_only_valid':reports['topology_only_diagnostic']['valid'],'error_status_counts':statuses,'evidence_sha256':{str(path.relative_to(ROOT)).replace('\\','/'):file_hash(path) for path in paths}}
    rows.append(row)
    atomic_json(ROOT/'reports/source_validity_scope.json',{'status':'all32_diagnostics_complete' if len(rows)==len(IDS) else 'in_progress','qualification_method':'Frozen BRepCheck_Analyzer default geometry checks plus separately qualified mesh topology and sampled CAD-boundary accuracy. Extra exact same-parameter checks are reported separately; no automatic exclusion or gate/tolerance change.','no_source_or_geometry_modified':True,'sources':rows,'script_sha256':file_hash(Path(__file__)),'checker_script_sha256':file_hash(ROOT/'scripts/investigate_brep_validity.py'),'time':time.time()})
    print(canonical_json({k:v for k,v in row.items() if k not in ['evidence_sha256','error_status_counts']}),flush=True)
