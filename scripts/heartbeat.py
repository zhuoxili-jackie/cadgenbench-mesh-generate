"""Small read-only live snapshot; historical pass events are labeled explicitly."""
from pathlib import Path
from collections import deque,Counter
import sqlite3,json,time,psutil,shutil
root=Path(__file__).resolve().parents[1];db=sqlite3.connect(root/'state/state.sqlite');now=time.time()
running=[{'subject':s,'stage':p,'elapsed_seconds':round(now-t,1)} for s,p,t in db.execute("SELECT subject,stage,updated FROM stages WHERE status='running' ORDER BY updated")]
source_tiers=Counter(json.loads(b)['status'] for b, in db.execute("SELECT body FROM records WHERE kind='sources'"))
case_acceptance=Counter()
for cid, in db.execute("SELECT id FROM records WHERE kind='cases'"):
    path=root/f'private/annotations/{cid}/acceptance.json'
    case_acceptance[json.loads(path.read_text(encoding='utf-8'))['status'] if path.exists() else 'not_yet_validated']+=1
completed_sources=[]
for path in (root/'state/source_runs').glob('*.json'):
    entry=json.loads(path.read_text(encoding='utf-8'))
    if entry.get('status')=='six_cases_generated_and_accepted':completed_sources.append(entry['source_id'])
progress={'reference_conclusions':sum(source_tiers.values()),'reference_tiers':dict(source_tiers),'recorded_case_acceptance':dict(case_acceptance),'completed_source_runs':sorted(completed_sources),'counts_are_live_records_not_a_final_reaudit':True}
with open(root/'state/events.jsonl',encoding='utf-8') as f:events=[json.loads(s) for s in deque(f,maxlen=150) if s.strip()]
recent=[]
for e in events:
    if e['event']=='validation_result':
        q=e['quality'];recent.append({'case':e['case'],'status':e['status'],'time':e['time'],'retention':q['observation_mesh_retained_fraction'],'support':q['mesh_observation_supported_fraction']})
workers=[]
for process in psutil.process_iter(['pid','name','cmdline','create_time','cpu_times','memory_info']):
    try:
        info=process.info;cmd=info['cmdline'] or []
        if info['name']!='python.exe' or info['memory_info'].rss<20*2**20:continue
        if not any(str(root).lower() in arg.lower() for arg in cmd) and Path(process.cwd()).resolve()!=root:continue
        script=next((Path(arg).name for arg in cmd if arg.endswith('.py')),None)
        if script=='heartbeat.py':continue
        workers.append({'pid':info['pid'],'script':script,'elapsed_seconds':round(now-info['create_time'],1),'cpu_seconds':round(sum(info['cpu_times'][:2]),1),'rss_gib':round(info['memory_info'].rss/2**30,3)})
    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
print(json.dumps({'time':now,'progress':progress,'running':running,'project_workers':workers,'recent_validation_events':recent[-4:],'available_ram_gib':round(psutil.virtual_memory().available/2**30,2),'free_disk_gib':round(shutil.disk_usage(root).free/2**30,2)},indent=2))
