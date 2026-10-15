"""Explicit boundary checks for the lexicographic representative selection contract."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'src'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
import numpy as np
from fusion_merge_candidate import merge_indices
from scanbench.common import *
rows=[]
for name,aq,bq,af,bf,au,bu,winner in [
 ('higher_confidence',.5,np.nextafter(.5,1),0,1,10,11,1),
 ('earlier_frame',.5,.5,1,0,1,2,1),
 ('earlier_pixel',.5,.5,0,0,8,7,1),
 ('exact_all_ties_keep_left',.5,.5,0,0,7,7,0),
 ('signed_zero_keep_left',-0.,0.,0,0,7,7,0),
 ('quality_before_frame',.7,.6,20,0,999,0,0),
]:
    k=np.array([[-20,0,40,5]],np.int64)
    ids=merge_indices(k,k,np.array([aq]),np.array([bq]),np.array([af],np.int32),np.array([bf],np.int32),np.array([au],np.uint32),np.array([bu],np.uint32));assert ids.tolist()==[winner]
    rows.append(name)
a=np.array([[-2**62,0,0,0],[2**62,0,0,0]],np.int64);b=np.array([[0,-2**62,0,0]],np.int64)
ids=merge_indices(a,b,np.ones(2),np.ones(1),np.zeros(2,np.int32),np.zeros(1,np.int32),np.zeros(2,np.uint32),np.zeros(1,np.uint32));assert ids.tolist()==[0,2,1];rows.append('large_signed_integer_keys_without_packing_overflow')
atomic_json(ROOT/'reports/tests/fusion_merge_ties.json',{'status':'pass','checks':rows,'candidate_code_sha256':file_hash(ROOT/'scripts/fusion_merge_candidate.py'),'script_sha256':file_hash(Path(__file__))});print('PASS',len(rows),'explicit merge boundary checks')
