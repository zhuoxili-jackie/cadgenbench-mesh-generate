from pathlib import Path
import json,os,subprocess,sys,time
import pytest
from scanbench.common import ROOT,State,atomic_bytes,file_hash,digest,atomic_json

def test_hash_partition_and_missing_artifact():
    root=ROOT/'tests/artifacts/state_contract';root.mkdir(parents=True,exist_ok=True)
    state=State(root); a=root/'raw.bin';b=root/'mesh.bin';v=root/'validation.json'
    atomic_bytes(a,b'observed measurement');atomic_bytes(b,b'candidate geometry');atomic_json(v,{'status':'pass'})
    scan=digest({'raw':'source','scan':1}); mesh=digest({'observations':file_hash(a),'reconstruction':1}); valid=digest({'mesh':file_hash(b),'validator':1})
    for stage,key,path in [('scan',scan,a),('mesh',mesh,b),('validation',valid,v)]:state.begin('control',stage,key);state.finish('control',stage,key,[path],{})
    before={str(p):[file_hash(p),p.stat().st_mtime_ns] for p in [a,b,v]}
    assert state.valid('control','scan',scan)
    assert not state.valid('control','mesh',digest({'observations':file_hash(a),'reconstruction':2}))
    assert state.valid('control','mesh',mesh)
    assert not state.valid('control','validation',digest({'mesh':file_hash(b),'validator':2}))
    assert not state.valid('control','scan',digest({'raw':'source','scan':2}))
    # Same data atomic publication preserves the qualified file's mtime.
    atomic_bytes(a,b'observed measurement');assert a.stat().st_mtime_ns==before[str(a)][1]
    original=b.read_bytes();b.write_bytes(b'corrupt');assert not state.valid('control','mesh',mesh);b.write_bytes(original)
    # A missing output is rejected; the path is in this test-only directory.
    moved=root/'mesh.hidden';os.replace(b,moved);assert not state.valid('control','mesh',mesh);os.replace(moved,b)
    report={'status':'pass','changed_reconstruction_invalidates_mesh':True,'changed_validator_keeps_geometry':True,'changed_scan_invalidates_observations':True,'corruption_rejected':True,'missing_file_rejected':True,'idempotent_write_preserves_mtime':True}
    atomic_json(ROOT/'reports/tests/hash_partition_unit.json',report)

def test_real_interrupted_atomic_stage():
    root=ROOT/'tests/artifacts/atomic_interrupt';root.mkdir(parents=True,exist_ok=True)
    script=root/'worker.py'
    script.write_text('''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from scanbench.common import State,atomic_bytes
root=Path(__file__).parent;s=State(root)
first=root/'completed.dat'
if not s.valid('interrupt','first','a'):
 s.begin('interrupt','first','a');atomic_bytes(first,b'complete');s.finish('interrupt','first','a',[first],{})
s.begin('interrupt','second','b')
(root/'partial.dat.partial').write_bytes(b'incomplete')
if sys.argv[2]=='wait':
 (root/'ready').write_text('ready')
 time.sleep(300)
atomic_bytes(root/'second.dat',b'finished')
s.finish('interrupt','second','b',[root/'second.dat'],{})
''',encoding='utf-8')
    ready=root/'ready'
    if ready.exists():ready.unlink()
    proc=subprocess.Popen([sys.executable,str(script),str(ROOT/'src'),'wait'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    until=time.monotonic()+30
    while not ready.exists() and time.monotonic()<until:
        if proc.poll() is not None:raise AssertionError(proc.stderr.read().decode())
        time.sleep(.05)
    assert ready.exists();first=root/'completed.dat';before=(file_hash(first),first.stat().st_mtime_ns)
    proc.kill();proc.wait(timeout=10)
    state=State(root);assert state.valid('interrupt','first','a');assert not state.valid('interrupt','second','b')
    subprocess.run([sys.executable,str(script),str(ROOT/'src'),'resume'],check=True,stdout=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    after=(file_hash(first),first.stat().st_mtime_ns)
    assert before==after and state.valid('interrupt','second','b')
    atomic_json(ROOT/'reports/tests/atomic_interrupt.json',{'status':'pass','actual_process_killed':True,'completed_hash_and_mtime_unchanged':True,'partial_not_complete':True,'resumed_stage_complete':True,'first_before':before,'first_after':after})
