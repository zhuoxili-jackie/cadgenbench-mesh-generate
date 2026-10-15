from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
from scanbench.placement_audit import audit_placements
from scanbench.common import canonical_json
for sid in sys.argv[1:]:print(canonical_json(audit_placements(sid)),flush=True)
