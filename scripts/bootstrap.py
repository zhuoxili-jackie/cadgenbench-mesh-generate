"""Read-only environment inventory and fixed upstream provenance acquisition."""
from pathlib import Path
import hashlib, json, os, platform, shutil, sys, time, urllib.request

ROOT = Path(__file__).resolve().parents[1]
REV = 'f76f965585817c621d6ea0d150d745adf670e66e'
CODE_REV = '33304cf771fc5639144b1df9611e347251052cf8'
IDS = '201 202 203 204 205 206 207 208 209 211 212 214 215 217 218 224 225 229 230 231 238 240 241 242 243 244 245 246 247 248 249 250'.split()

def save_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)

def fetch(url, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'cadgenbench-physical-scan/1.0'})
            with urllib.request.urlopen(req, timeout=90) as response:
                data = response.read()
            tmp = path.with_name(path.name + '.tmp'); tmp.write_bytes(data); os.replace(tmp,path)
            return data
        except Exception:
            if attempt == 3: raise
            time.sleep(2 * (attempt + 1))

def doctor():
    import psutil
    import importlib.metadata as md
    disk = shutil.disk_usage(ROOT)
    info = dict(time=time.time(), python=sys.version, executable=sys.executable, platform=platform.platform(),
                cpu=platform.processor(), logical_cpus=os.cpu_count(), physical_cpus=psutil.cpu_count(logical=False),
                memory_total=psutil.virtual_memory().total, memory_available=psutil.virtual_memory().available,
                disk_total=disk.total, disk_free=disk.free, root=str(ROOT),
                packages={d.metadata['Name']:d.version for d in md.distributions()},
                resource_policy={'geometry_threads':2,'source_workers':1,'project_target_gib':35,'system_reserve_gib':15})
    save_json(ROOT/'reports/environment.json', info)
    print(json.dumps({k:v for k,v in info.items() if k!='packages'}, indent=2))

def inventory():
    base = 'https://huggingface.co/datasets/HuggingAI4Engineering/cadgenbench-data'
    api = f'https://huggingface.co/api/datasets/HuggingAI4Engineering/cadgenbench-data/tree/{REV}?recursive=true&expand=false&limit=1000'
    raw = fetch(api, ROOT/'sources/upstream_tree.json')
    tree = json.loads(raw)
    steps = [x for x in tree if x['path'].endswith('input.step')]
    fetch(f'{base}/resolve/{REV}/README.md', ROOT/'sources/DATA_CARD_UPSTREAM.md')
    for fname in ['mesh.py','profiling.py']:
        fetch(f'https://raw.githubusercontent.com/huggingface/cadgenbench/{CODE_REV}/src/cadgenbench/common/{fname}', ROOT/f'vendor/cadgenbench/common/{fname}')
    fetch(f'https://raw.githubusercontent.com/huggingface/cadgenbench/{CODE_REV}/LICENSE', ROOT/'vendor/cadgenbench/LICENSE')
    for folder in [ROOT/'vendor/cadgenbench', ROOT/'vendor/cadgenbench/common']:
        (folder/'__init__.py').touch(exist_ok=True)
    print(json.dumps({'step_count':len(steps),'steps':steps}, indent=2))
    save_json(ROOT/'state/next_actions.json', {'milestone':'M0','goal_status':'active','next':['download verified sources','geometry control tests','218 resource pilot','18-case pilot and freeze','remaining 29 sources','independent full acceptance'], 'known_issues':[]})

if __name__=='__main__':
    {'doctor':doctor, 'inventory':inventory}[sys.argv[1]]()
