"""Verify the delivered counts, links, preview index and final documentation."""
from pathlib import Path
import os,sys,re,csv,html
from urllib.parse import unquote,urlsplit
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
from scanbench.common import *
from PIL import Image

def local_target(base,url):
    raw=html.unescape(url).strip('<>')
    if raw.startswith('#') or urlsplit(raw).scheme:return None
    target=(base/unquote(raw.split('#',1)[0])).resolve()
    assert target.is_relative_to(ROOT),f'Local delivery link escapes project: {url}'
    assert target.exists(),f'Missing delivery link: {url}'
    return target

def main():
    summary=load_json(ROOT/'reports/acceptance.json');audit=load_json(ROOT/'reports/final_audit.json')
    assert summary['status']=='complete' and audit['status']=='pass' and audit['all_32_attempted']
    sources=[json.loads(line) for line in (ROOT/'manifests/sources.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    cases=[json.loads(line) for line in (ROOT/'manifests/cases.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    assert len(sources)==32 and {x['source_id'] for x in sources}==set(IDS)
    assert len(cases)==summary['verified_case_count']==audit['actual_case_count']==6*len(summary['six_case_complete_sources'])
    with (ROOT/'reports/quality_table.csv').open(encoding='utf-8-sig',newline='') as stream:quality=list(csv.DictReader(stream))
    assert len(quality)==len(cases) and {x['case_id'] for x in quality}=={x['case_id'] for x in cases}
    assert all(x['acceptance_status']=='pass' for x in quality)
    documents={};links=[]
    for name in ['README.md','DATASET_CARD.md','LICENSES.md','reports/final_report.md']:
        path=ROOT/name;text=path.read_text(encoding='utf-8');assert '\ufffd' not in text
        documents[name]=file_hash(path)
        for url in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
            target=local_target(path.parent,url)
            if target:links.append(str(target.relative_to(ROOT)).replace('\\','/'))
    report=(ROOT/'reports/final_report.md').read_text(encoding='utf-8')
    assert f'正式案例 {len(cases)} 例' in report and f'六例完整源件 {len(summary["six_case_complete_sources"])} 件' in report
    source_table=re.findall(r'^\| (\d{3}) \| (native|官方 Mesh 近似|排除) \|',report,re.M)
    assert len(source_table)==32 and {sid for sid,tier in source_table}==set(IDS)
    labels={'eligible_native':'native','eligible_official_mesh_approx':'官方 Mesh 近似','source_excluded':'排除'}
    assert dict(source_table)=={x['source_id']:labels[x['status']] for x in sources}
    preview=ROOT/'reports/preview_index.html';markup=preview.read_text(encoding='utf-8')
    images=re.findall(r'<img\b[^>]*\bsrc="([^"]+)"',markup)
    expected={f'private_previews/{x["case_id"]}.png' for x in cases}|{f'private_previews/gt_{sid}.png' for sid in summary['six_case_complete_sources']}
    assert len(images)==len(expected) and set(images)==expected
    for url in images:
        path=local_target(preview.parent,url)
        with Image.open(path) as image:assert image.size==(1080,846);image.verify()
    for url in re.findall(r'<a\b[^>]*\bhref="([^"]+)"',markup):local_target(preview.parent,url)
    assert f'Status: complete. {len(cases)} meshes generated; {len(cases)} current acceptance passes.' in markup
    for name in ['requirements.lock','reports/environment.json','reports/performance.json','reports/tests_report.json','reports/execution_resources.json','reports/final_file_inventory.json','reports/source_validity_scope.json','reports/operations/full_acceptance_commands.json','reports/operations/delivery_export_command_r4.json']:
        assert (ROOT/name).is_file();documents[name]=file_hash(ROOT/name)
    assert audit['file_inventory_sha256']==documents['reports/final_file_inventory.json']
    documents['reports/preview_index.html']=file_hash(preview)
    documents['reports/quality_table.csv']=file_hash(ROOT/'reports/quality_table.csv')
    proof={'status':'pass','all32_source_table_consistent':True,'actual_cases':len(cases),'six_case_sources':len(summary['six_case_complete_sources']),'tiers':summary['tiers'],'current_accepted_quality_rows':len(quality),'all_triangle_preview_images':len(images),'verified_local_document_links':len(links),'documents_sha256':documents,'final_audit_sha256':file_hash(ROOT/'reports/final_audit.json'),'script_sha256':file_hash(Path(__file__)),'time':time.time(),'scope':'Document and index consistency plus actual PNG decoding; full geometry and payload acceptance are bound separately by final_audit.json.'}
    atomic_json(ROOT/'reports/delivery_verification.json',proof)
    print(canonical_json({k:v for k,v in proof.items() if k!='documents_sha256'}))

if __name__=='__main__':main()
