from pathlib import Path
import sys,os
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')];os.chdir(ROOT)
from scanbench.reporting import report
report()
