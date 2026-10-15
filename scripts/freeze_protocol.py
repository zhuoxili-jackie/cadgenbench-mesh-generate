"""Freeze only a passed 18-case pilot with current independent evidence."""
from pathlib import Path
import sys,os,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *
from scanbench.cases import case_id
from scanbench.validate import validation_fingerprint
from scanbench.reporting import REQUIRED_TESTS

state=State();cfg=config();gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text());cases=[]
for sid in ['218','231','229']:
    source=load_json(ROOT/f'private/gt/{sid}/metadata.json');assert source['status']=='eligible_native'
    visual=load_json(ROOT/f'reports/visual_reviews/{sid}.json');assert visual['status']=='pass'
    for item in visual['cases']:
        assert file_hash(ROOT/item['preview'])==item['preview_sha256']
        assert file_hash(ROOT/f'data/cases/{item["case_id"]}/input/mesh.ply')==item['mesh_sha256']
    for seed in cfg['seeds']:
        for level in ['hard','medium','easy']:
            cid=case_id(sid,level,seed);rec=load_json(ROOT/f'private/annotations/{cid}/case.json');out=ROOT/rec['input_path'];a=load_json(ROOT/f'private/annotations/{cid}/acceptance.json');extra=load_json(ROOT/f'private/annotations/{cid}/supplemental.json')
            assert a['status']=='pass' and a['validation_hash']==validation_fingerprint(out,rec,gates),cid
            assert extra['status']=='pass' and extra['mesh_sha256']==file_hash(out/'mesh.ply'),cid
            cases.append({'case_id':cid,'source_id':sid,'level':level,'seed':seed,'mesh_sha256':file_hash(out/'mesh.ply'),'pilot_acceptance_sha256':file_hash(ROOT/f'private/annotations/{cid}/acceptance.json'),'observed_retention':a['quality']['observation_mesh_retained_fraction'],'mesh_support':a['quality']['mesh_observation_supported_fraction'],'coverage':a['quality']['total_gt_surface_mesh_coverage']})
tests={}
for name in REQUIRED_TESTS+['actual_payload_integrity','topology_optimization_equivalence']:
    path=ROOT/f'reports/tests/{name}.json';r=load_json(path);assert r.get('status')=='pass' or r.get('pass') is True,name;tests[name]=file_hash(path)
cid=case_id('218','hard',cfg['seeds'][0]);out=ROOT/f'data/cases/{cid}/input';mh=file_hash(out/'mesh.ply');oh=file_hash(out/'observations.json');ch=file_hash(ROOT/'src/scanbench/reconstruct.py')
for name,sig in [('no_gt_portable',digest([mh,ch,oh])),('full_case_reproduction',digest([mh,oh,ch])),('real_mesh_interruption',digest([mh,ch]))]:
    assert load_json(ROOT/f'reports/tests/{name}.json')['signature']==sig,f'{name}: stale evidence from old reconstruction code'
assert len(cases)==18
prior=digest(cfg);cfg['status']='frozen';atomic_bytes(ROOT/'configs/physical_scan_v1.yaml',yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False).encode());gates['version']='quality_v1';atomic_bytes(ROOT/'configs/quality_gates.yaml',yaml.safe_dump(gates,sort_keys=False).encode())
code={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in sorted((ROOT/'src/scanbench').glob('*.py'))}
snapshot=ROOT/'reports/frozen_protocol_code.zip'
with zipfile.ZipFile(snapshot.with_suffix('.zip.partial'),'w',zipfile.ZIP_DEFLATED) as z:
    for name in [*code,'configs/physical_scan_v1.yaml','configs/quality_gates.yaml','requirements.lock']:
        z.write(ROOT/name,name)
    for item in cases:
        cid=item['case_id'];z.write(ROOT/f'private/annotations/{cid}/acceptance.json',f'pilot_acceptance/{cid}.json')
        z.write(ROOT/f'data/cases/{cid}/input/README.json',f'pilot_case_metadata/{cid}.json')
    z.write(ROOT/'reports/pilot_report.md','pilot_report.md')
os.replace(snapshot.with_suffix('.zip.partial'),snapshot)
report={'status':'frozen_after_passed_pilot','time':time.time(),'source_revision':REV,'pilot_sources':['218','231','229'],'pilot_cases':cases,'prior_draft_config_sha256':prior,'protocol_config_sha256':digest(cfg),'quality_gates_sha256':file_hash(ROOT/'configs/quality_gates.yaml'),'code_sha256':code,'tests_sha256_at_freeze':tests,'code_snapshot_sha256':file_hash(snapshot),'settings_change':'status/version labels only; all scan/reconstruction/gate numbers unchanged from accepted pilot','normal_policy':'actual implementation uses six oriented dominant-axis normal cones; normal_cluster_degrees is an unused draft metadata field and does not control reconstruction','next_actions':'refresh public full-configuration hashes without resampling/regenerating valid geometry; independently revalidate; then all remaining 29 sources'}
atomic_json(ROOT/'reports/protocol_freeze.json',report);print(canonical_json({'status':report['status'],'cases':len(cases),'config':digest(cfg)}))
