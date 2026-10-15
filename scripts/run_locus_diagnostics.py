"""Read-only, restartable geometric interpretation of extra exact STEP diagnostics."""
from pathlib import Path
import os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='2'
from scanbench.common import *

rows=[]
script=ROOT/'scripts/probe_parameterization_locus.py'
for sid in ['244','245','246','247','248','249','250']:
    folder=ROOT/f'reports/source_investigations/{sid}';output=folder/'locus_all_flagged_pairs.json'
    if output.exists():
        result=load_json(output)
        assert result['script_sha256']==file_hash(script)
        assert result['source_sha256']==file_hash(ROOT/f'sources/{sid}/input.step')
        assert result['prior_same_parameter_report_sha256']==file_hash(folder/'curve_on_surface_probe_0.json')
    else:
        while psutil.virtual_memory().available<1.6*2**30:
            print(canonical_json({'waiting_for_ram_gib':1.6,'source':sid}),flush=True);time.sleep(15)
        print(canonical_json({'begin':sid,'time':time.time()}),flush=True)
        with (ROOT/f'logs/parameterization_locus_{sid}_all.log').open('a',encoding='utf-8') as stream:
            subprocess.run([sys.executable,str(script),sid],check=True,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=load_json(output)
    row={k:v for k,v in result.items() if k!='pairs'};row['pairs']=len(result['pairs']);row['report']=str(output.relative_to(ROOT)).replace('\\','/');row['report_sha256']=file_hash(output)
    rows.append(row);atomic_json(ROOT/'reports/remaining_sources_locus_diagnostics.json',{'status':'diagnostic_only','sources':rows,'no_source_or_mesh_modified':True,'not_a_final_source_disposition':True})
    print(canonical_json(row),flush=True)
