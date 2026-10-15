"""Corrupt/missing files in an isolated real export must fail acceptance hashing."""
from pathlib import Path
import os,shutil
import pytest,yaml
from scanbench.common import *
from scanbench.export import export_case
from scanbench.validate import validation_fingerprint

def test_real_export_missing_and_corrupt_payloads():
    cid='case_2438b1a3fd780c63';record=load_json(ROOT/f'private/annotations/{cid}/case.json');dest=ROOT/'tests/artifacts/payload_integrity';marker=dest/'export.json'
    if not marker.exists():export_case(cid,dest)
    out=dest/f'data/cases/{cid}/input';gates=yaml.safe_load((ROOT/'configs/quality_gates.yaml').read_text());base=validation_fingerprint(out,record,gates);targets=[out/'mesh.ply',(out/load_json(out/'observations.json')['frames'][0]['path']).resolve()];evidence=[]
    for path in targets:
        assert path.is_relative_to(dest.resolve());original_hash=file_hash(path);backup=path.with_name(path.name+'.test-hidden')
        os.replace(path,backup)
        try:
            with pytest.raises(FileNotFoundError):validation_fingerprint(out,record,gates)
        finally:os.replace(backup,path)
        if path.suffix=='.npz':
            original=path.read_bytes();bad=bytearray(original);bad[len(bad)//2]^=1;path.write_bytes(bad)
            try:
                with pytest.raises(ValueError,match='corrupt observation'):validation_fingerprint(out,record,gates)
            finally:path.write_bytes(original)
        assert file_hash(path)==original_hash and validation_fingerprint(out,record,gates)==base
        evidence.append({'relative_path':str(path.relative_to(dest)),'original_hash':original_hash,'missing_rejected':True,'corrupt_rejected':path.suffix=='.npz'})
    atomic_json(ROOT/'reports/tests/actual_payload_integrity.json',{'status':'pass','isolated_real_public_export':str(dest.relative_to(ROOT)),'fingerprint':base,'checks':evidence,'production_files_modified':False})
