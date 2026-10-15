"""Download, SHA256-check and safely extract the accepted release (standard library only)."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,stat,subprocess,sys,time,urllib.parse,urllib.request,zipfile

REPOSITORY='zhuoxili-jackie/cadgenbench-mesh-generate'
API='https://api.github.com'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        target=super().redirect_request(request,fp,code,msg,headers,newurl)
        if target and urllib.parse.urlsplit(request.full_url).netloc!=urllib.parse.urlsplit(newurl).netloc:
            target.remove_header('Authorization')
        return target
OPENER=urllib.request.build_opener(SafeRedirect())
def credential(username):
    token=os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:return token
    body='protocol=https\nhost=github.com\n'+('username='+username+'\n' if username else '')+'\n'
    command=['git']+(['-c','credential.username='+username] if username else [])+['credential','fill']
    env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'Never'}
    result=subprocess.run(command,input=body,text=True,capture_output=True,env=env,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    values=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if not values.get('password'):raise RuntimeError('Authenticate a GitHub account with repository access, or set GITHUB_TOKEN. Tokens are never written to disk.')
    return values['password']
def request(url,token,**headers):
    values={'User-Agent':'CADGenBench-Dataset-Downloader','X-GitHub-Api-Version':'2022-11-28',**headers}
    if urllib.parse.urlsplit(url).netloc=='api.github.com':values['Authorization']='Bearer '+token
    return OPENER.open(urllib.request.Request(url,headers=values),timeout=120)
def safe_name(name):
    parts=PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name or not parts.parts:raise ValueError('Unsafe archive member: '+name)
    return parts
def download(asset,remote,folder,token):
    if len(safe_name(asset['name']).parts)!=1:raise ValueError('Invalid asset filename.')
    target=folder/asset['name'];part=target.with_name(target.name+'.part')
    if target.is_file() and target.stat().st_size==asset['bytes'] and sha(target)==asset['sha256']:
        print('Verified cached archive: '+target.name,flush=True);return target
    for attempt in range(3):
        start=part.stat().st_size if part.exists() else 0
        if start>asset['bytes']:part.unlink();start=0
        try:
            headers={'Accept':'application/octet-stream','Cache-Control':'no-cache'}
            if start:headers['Range']='bytes='+str(start)+'-'
            url=remote['url']+'?download=1&t='+str(time.time_ns())
            with request(url,token,**headers) as response:
                if 'application/json' in response.headers.get('Content-Type',''):raise RuntimeError('GitHub returned metadata instead of asset bytes.')
                append=start and response.status==206
                if append and not response.headers.get('Content-Range','').startswith('bytes '+str(start)+'-'):raise RuntimeError('Unexpected HTTP resume offset.')
                received=start if append else 0;last=time.monotonic()
                with part.open('ab' if append else 'wb') as stream:
                    while chunk:=response.read(4*1024*1024):
                        stream.write(chunk);received+=len(chunk)
                        if time.monotonic()-last>=5:
                            print(f'{target.name}: {received/2**20:.0f}/{asset["bytes"]/2**20:.0f} MiB',flush=True);last=time.monotonic()
            if received!=asset['bytes'] or sha(part)!=asset['sha256']:
                part.unlink(missing_ok=True);raise RuntimeError('Downloaded archive size/SHA256 mismatch.')
            os.replace(part,target);print('Downloaded and verified: '+target.name,flush=True);return target
        except Exception:
            if attempt==2:raise
            time.sleep(min(2**attempt,4))
def extract(archive,destination,manifest_sha=None):
    with zipfile.ZipFile(archive) as zipped:
        names=zipped.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP entries.')
        for info in zipped.infolist():
            safe_name(info.filename)
            if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Symlink in release ZIP.')
        if 'release-manifest.json' in names:
            raw=zipped.read('release-manifest.json')
            if hashlib.sha256(raw).hexdigest()!=manifest_sha:raise ValueError('Release manifest SHA256 mismatch.')
            manifest=json.loads(raw)
        else:manifest=json.loads((destination/'release-manifest.json').read_text(encoding='utf-8'))
        for info in zipped.infolist():
            if info.is_dir():continue
            name=info.filename;target=destination.joinpath(*safe_name(name).parts)
            expected=manifest_sha if name=='release-manifest.json' else manifest['files'][name]['sha256']
            if target.is_file() and sha(target)==expected:continue
            if target.is_symlink() or not target.resolve().is_relative_to(destination.resolve()):raise ValueError('Extraction destination escapes data root.')
            target.parent.mkdir(parents=True,exist_ok=True)
            temporary=target.with_name(target.name+'.extract.partial');h=hashlib.sha256()
            with zipped.open(info) as source,temporary.open('wb') as output:
                while chunk:=source.read(4*1024*1024):output.write(chunk);h.update(chunk)
            if h.hexdigest()!=expected:temporary.unlink(missing_ok=True);raise ValueError('Extracted payload hash mismatch: '+name)
            os.replace(temporary,target)
    print('Verified extraction: '+archive.name,flush=True)
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset',choices=['meshes','rebuild','full'],default='meshes')
    parser.add_argument('--case-id')
    parser.add_argument('--destination',default='downloads/v1.0.0')
    parser.add_argument('--github-user')
    parser.add_argument('--download-only',action='store_true')
    args=parser.parse_args();repo=Path(__file__).resolve().parents[1]
    index=json.loads((repo/'data_index/releases.json').read_text(encoding='utf-8'))
    rows=[json.loads(line) for line in (repo/'data_index/accepted_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    if args.case_id and args.case_id not in {row['case_id'] for row in rows}:parser.error('Unknown case ID.')
    selected=index['presets'][args.preset]
    required=set()
    if args.case_id:
        case=next(row for row in rows if row['case_id']==args.case_id)
        for family in selected:required.update(case['release_assets'].get(family,[]))
    assets=[asset for asset in index['assets'] if asset['family'] in selected and (not args.case_id or asset['family'] in ['metadata','previews'] or asset['name'] in required)]
    assets.sort(key=lambda asset:(asset['family']!='metadata',asset['name']))
    destination=Path(args.destination).resolve()
    if any((destination/path).exists() for path in ['private','sources','state/state.sqlite']):parser.error('Use a separate download directory; source-generation workspaces are not extraction targets.')
    destination.mkdir(parents=True,exist_ok=True);archives=destination/'archives';archives.mkdir(exist_ok=True)
    token=credential(args.github_user)
    with request(API+'/repos/'+REPOSITORY+'/releases/tags/'+index['version'],token,Accept='application/vnd.github+json') as response:release=json.load(response)
    remote={asset['name']:asset for asset in release['assets']}
    print(f'{len(assets)} assets; {sum(asset["bytes"] for asset in assets)/2**30:.2f} GiB; preset={args.preset}',flush=True)
    for asset in assets:
        if asset['name'] not in remote:raise RuntimeError('Release asset missing: '+asset['name'])
        path=download(asset,remote[asset['name']],archives,token)
        if not args.download_only:extract(path,destination,index['manifest_sha256'])
    print('Complete: '+str(destination),flush=True)
if __name__=='__main__':main()
