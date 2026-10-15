from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor'),str(ROOT/'tests')]
os.chdir(ROOT)
os.environ['OMP_NUM_THREADS']='2'
os.environ['OPENBLAS_NUM_THREADS']='2'
os.environ['MKL_NUM_THREADS']='2'
from control_mesh_experiment import run
run()
