"""Run all local services; Ctrl-C stops services but preserves MySQL data."""
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime'
RUNTIME.mkdir(exist_ok=True)

def main():
    with (RUNTIME / 'local.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('Local services already running')
        node = shutil.which('node')
        if not node:
            candidates = sorted((Path.home()/'.nvm/versions/node').glob('*/bin/node'))
            node = str(candidates[-1]) if candidates else None
        if not node: raise SystemExit('Install Node.js 22+ and put node on PATH')
        subprocess.run(['docker','compose','up','-d','--wait'],cwd=ROOT,check=True)
        python = str(ROOT/'backend/.venv/bin/python')
        subprocess.run([python,'-m','lottery.cli','init-db'],cwd=ROOT/'backend',check=True)
        commands = {
            'api': [python,'-m','uvicorn','lottery.api:app','--host','127.0.0.1','--port','8000'],
            'scheduler': [python,'-m','lottery.cli','scheduler'],
            'frontend': [node,str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','9998','--strictPort'],
        }
        if (RUNTIME/'cloud-deployed').exists():
            commands.pop('scheduler')
            print('Cloud scheduler owns notifications; local scheduler disabled.', flush=True)
        children=[]
        def stop(*_): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop)
        try:
            for name,command in commands.items():
                log=(RUNTIME/f'{name}.log').open('a')
                process=subprocess.Popen(command,cwd=ROOT/('frontend' if name=='frontend' else 'backend'),stdout=log,stderr=subprocess.STDOUT)
                log.close();children.append(process)
            print('Dashboard http://127.0.0.1:9998 | API http://127.0.0.1:8000 | Ctrl-C to stop',flush=True)
            while all(p.poll() is None for p in children): time.sleep(2)
            print('A service exited. Check runtime/*.log.',flush=True)
        except KeyboardInterrupt: pass
        finally:
            for p in children:
                if p.poll() is None: p.terminate()
            for p in children:
                try: p.wait(timeout=10)
                except subprocess.TimeoutExpired: p.kill();p.wait()

if __name__=='__main__': main()
