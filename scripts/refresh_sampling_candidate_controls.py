"""Run fresh isolated controls after a candidate-code change, preserving old runs."""
from pathlib import Path
import os,sys,time,subprocess,json,argparse
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[name]='2'
from scanbench.common import *
FOLDER=ROOT/'reports/protocol_amendments/r5_sampling_density'


def wait_memory(label):
    last=0
    while psutil.virtual_memory().available<3*2**30:
        if time.time()-last>=30:
            print(canonical_json({'control_waiting':label,'available_gib':psutil.virtual_memory().available/2**30}),flush=True);last=time.time()
        time.sleep(5)


def command(arguments,log):
    result=subprocess.run([sys.executable,*arguments],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic_bytes(log,result.stdout.encode('utf-8'))
    assert result.returncode==0,('isolated control command failed',arguments,str(log),result.stdout[-2000:])
    return result.stdout


def main():
    manifest=file_hash(FOLDER/'candidate_manifest.json');run=str(time.time_ns());folder=FOLDER/'controls'/('refresh_'+run);folder.mkdir()
    controls=[]
    for name,script in [('runtime_controls','test_sampling_density_runtime.py'),('migration_controls','test_sampling_density_migration.py'),('refined_preparation_controls','test_refined_sampling_preparation.py')]:
        assert file_hash(FOLDER/'candidate_manifest.json')==manifest,'Candidate changed during control refresh'
        stdout=command(['scripts/'+script,'--prepare-only'],folder/(name+'_prepare.log'))
        rows=[]
        for line in stdout.splitlines():
            try:rows.append(json.loads(line))
            except ValueError:pass
        prepared=next(row for row in rows if row.get('status')=='prepared')
        runtime=Path(prepared['runtime']);assert (ROOT/runtime).resolve().is_relative_to((FOLDER/'controls').resolve())
        atomic_json(ROOT/'state/sampling_candidate_controls.json',{'status':'prepared_waiting_for_memory','control':name,'runtime':runtime.as_posix(),'candidate_manifest_sha256':manifest,'time':time.time()})
        attempt=0
        while True:
            wait_memory(name);attempt+=1
            print(canonical_json({'control_begin':name,'runtime':runtime.as_posix(),'attempt':attempt}),flush=True)
            command(['scripts/'+script,'--runtime',runtime.as_posix()],folder/f'{name}_run_{attempt}.log')
            report_path=FOLDER/(name+'.json');proof=load_json(report_path) if report_path.exists() else {}
            if proof.get('status')=='pass' and Path(proof.get('runtime','')).as_posix()==runtime.as_posix():break
            print(canonical_json({'control_deferred_after_preparation':name}),flush=True)
            time.sleep(5)
        controls.append({'name':name,'runtime':runtime.as_posix(),'report_sha256':file_hash(report_path),'attempts':attempt})
        print(canonical_json({'control_pass':name,'seconds':proof['seconds'],'peak_process_tree_rss_bytes':proof['peak_process_tree_rss_bytes']}),flush=True)
    frozen=load_json(ROOT/'reports/protocol_freeze.json')
    assert all(file_hash(ROOT/name)==value for name,value in frozen['code_sha256'].items())
    receipt={'status':'pass','reason':'Candidate now rejects legal-but-unfrozen policy mutations before acquisition','candidate_manifest_sha256':manifest,'controls':controls,'production_core_unchanged':True,'script_sha256':file_hash(Path(__file__)),'time':time.time()}
    atomic_json(folder/'result.json',receipt);atomic_json(FOLDER/'freeze_guard_control_refresh.json',receipt)
    atomic_json(ROOT/'state/sampling_candidate_controls.json',receipt)
    print(canonical_json(receipt),flush=True)


if __name__=='__main__':main()
