from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import hashlib, importlib.metadata, json, os, sqlite3, threading, time
import numpy as np
import psutil
import yaml

ROOT = Path(__file__).resolve().parents[2]
IDS = '201 202 203 204 205 206 207 208 209 211 212 214 215 217 218 224 225 229 230 231 238 240 241 242 243 244 245 246 247 248 249 250'.split()
REV = 'f76f965585817c621d6ea0d150d745adf670e66e'

def json_default(v):
    if isinstance(v, np.ndarray): return v.tolist()
    if isinstance(v, np.generic): return v.item()
    if isinstance(v, Path): return str(v)
    raise TypeError(type(v).__name__)

def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=False, default=json_default, allow_nan=False)

def digest(obj): return hashlib.sha256(canonical_json(obj).encode()).hexdigest()

def file_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

RUN_CODE_HASHES={p.name:file_hash(p) for p in Path(__file__).parent.glob('*.py')}
STAGE_CODE_HASHES={}

def load_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def atomic_bytes(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and path.stat().st_size==len(data) and path.read_bytes()==data: return
    tmp=path.with_name(path.name+'.partial')
    with open(tmp,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def atomic_json(path,obj): atomic_bytes(path,(json.dumps(obj,indent=2,ensure_ascii=False,default=json_default,allow_nan=False)+'\n').encode('utf-8'))

def atomic_npz(path,**arrays):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.partial')
    with open(tmp,'wb') as f: np.savez_compressed(f,**arrays); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def config(): return yaml.safe_load((ROOT/'configs/physical_scan_v1.yaml').read_text(encoding='utf-8'))

def stage_hash(inputs, settings, modules, packages=()):
    code={m:file_hash(Path(__file__).parent/m) for m in modules}
    if any(RUN_CODE_HASHES.get(m)!=h for m,h in code.items()):raise RuntimeError('stage code changed during this process; restart before using a new hash')
    key=digest({'inputs':inputs,'settings':settings,'code':code,'environment':{p:importlib.metadata.version(p) for p in packages}})
    STAGE_CODE_HASHES[key]=code
    return key

def event(kind,**fields):
    item={'time':time.time(),'pid':os.getpid(),'event':kind,**fields}
    path=ROOT/'state/events.jsonl'; path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a',encoding='utf-8') as f: f.write(canonical_json(item)+'\n'); f.flush()
    if kind.startswith('stage_'):
        atomic_json(ROOT/'state/next_actions.json',{'goal_status':'active','last_event':item,
                    'next_commands':['scripts/scanbench.py validate','scripts/scanbench.py generate --ids 218 231 229','freeze only after all controls and 18 pilot cases pass','prepare and generate remaining 29 sources','full independent validation and report'],
                    'completed_stages':'state/state.sqlite is authoritative; verify all hashes before resume',
                    'known_issues':'see current validation reports and logs; no result is final before full acceptance'})
    print(canonical_json(item),flush=True)

class State:
    """One CLI process owns writes; all successful outputs are hash verified on resume."""
    def __init__(self,root=ROOT):
        self.root=Path(root); (self.root/'state').mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'state/state.sqlite')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS stages (subject TEXT,stage TEXT,input_hash TEXT,status TEXT,outputs TEXT,metrics TEXT,updated REAL,PRIMARY KEY(subject,stage))')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
        self.db.commit()
    def valid(self,subject,stage,key):
        row=self.db.execute('SELECT input_hash,status,outputs FROM stages WHERE subject=? AND stage=?',(subject,stage)).fetchone()
        if not row or row[0]!=key or row[1]!='complete': return False
        return all((self.root/p).is_file() and file_hash(self.root/p)==h for p,h in json.loads(row[2]).items())
    def begin(self,subject,stage,key):
        self.db.execute('INSERT OR REPLACE INTO stages VALUES (?,?,?,?,?,?,?)',(subject,stage,key,'running','{}','{}',time.time())); self.db.commit()
        event('stage_begin',subject=subject,stage=stage,key=key)
    def finish(self,subject,stage,key,outputs,metrics):
        if any(file_hash(Path(__file__).parent/m)!=h for m,h in STAGE_CODE_HASHES.get(key,{}).items()):
            raise RuntimeError('code changed during stage; results must be rechecked in a fresh process before publication')
        hashes={str(Path(p).relative_to(self.root)).replace('\\','/'):file_hash(p) for p in outputs}
        self.db.execute('INSERT OR REPLACE INTO stages VALUES (?,?,?,?,?,?,?)',(subject,stage,key,'complete',canonical_json(hashes),canonical_json(metrics),time.time())); self.db.commit()
        event('stage_complete',subject=subject,stage=stage,metrics=metrics)
    def record(self,kind,id,obj):
        self.db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)',(kind,str(id),canonical_json(obj))); self.db.commit()
        dest=self.root/f'manifests/{kind}.jsonl'
        rows=self.db.execute('SELECT body FROM records WHERE kind=? ORDER BY id',(kind,)).fetchall()
        atomic_bytes(dest,('\n'.join(x[0] for x in rows)+'\n').encode('utf-8'))

@contextmanager
def measured():
    stats={}; stop=threading.Event(); proc=psutil.Process(); start=time.perf_counter()
    def monitor():
        peak=0
        while not stop.is_set():
            try: peak=max(peak,proc.memory_info().rss)
            except psutil.Error: pass
            stats['peak_rss_bytes']=peak; stop.wait(0.2)
    thread=threading.Thread(target=monitor,daemon=True); thread.start()
    try: yield stats
    finally: stop.set(); thread.join(); stats['seconds']=time.perf_counter()-start

def transform(points,T): return np.asarray(points) @ np.asarray(T)[:3,:3].T + np.asarray(T)[:3,3]

def stable_seed(*parts): return int.from_bytes(hashlib.sha256(canonical_json(parts).encode()).digest()[:8],'little')
