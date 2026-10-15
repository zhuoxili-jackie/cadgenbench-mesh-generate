"""Run one auxiliary command when production's separate memory reserve permits."""
from pathlib import Path
import os,sys,argparse,time,subprocess,json
import psutil
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--minimum-gib',type=float,default=3.0);parser.add_argument('--maximum-wait',type=float,default=1800);parser.add_argument('command',nargs=argparse.REMAINDER);args=parser.parse_args()
    command=args.command
    if command and command[0]=='--':command=command[1:]
    assert command and args.minimum_gib>=3
    os.chdir(ROOT);started=time.time();last_print=0
    while True:
        available=psutil.virtual_memory().available/2**30
        if available>=args.minimum_gib:break
        if time.time()-started>=args.maximum_wait:raise SystemExit('Auxiliary task deferred: memory reserve not reached; production remains untouched')
        if time.time()-last_print>=30:
            print(json.dumps({'auxiliary_waiting_for_memory_gib':args.minimum_gib,'available_gib':available,'wait_seconds':time.time()-started}),flush=True);last_print=time.time()
        time.sleep(5)
    print(json.dumps({'auxiliary_starting':command,'available_gib':available,'wait_seconds':time.time()-started}),flush=True)
    result=subprocess.run(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
