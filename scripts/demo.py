"""Start, inspect, or stop the local DARWIN demo stack.

The launcher reuses anything already listening, checks machine readiness first,
and only stops processes it started itself. Local use is bound to 127.0.0.1.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import httpx
import psutil

from darwin.preflight import collect_preflight

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime' / 'demo'
STATE = RUNTIME / 'processes.json'
LOGS = RUNTIME / 'logs'
API = 'http://127.0.0.1:8000/api/health'
SHOP = 'http://127.0.0.1:8010/shop/ready'
UI = 'http://127.0.0.1:5173/'
FLAGS = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0


def ready(url):
    try:
        return httpx.get(url, timeout=0.6, trust_env=False).status_code == 200
    except httpx.HTTPError:
        return False


def wait(url, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if ready(url):
            return True
        time.sleep(0.5)
    return False


def load_state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(state):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    temporary.replace(STATE)


def spawn(name, args, env=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    log = (LOGS / f'{name}.log').open('a', encoding='utf-8')
    process = subprocess.Popen(args, cwd=ROOT, env={**os.environ, **(env or {})},
                               stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                               creationflags=FLAGS, start_new_session=os.name != 'nt')
    state = load_state()
    state[name] = {'pid': process.pid, 'started_at': time.time()}
    save_state(state)
    print(f'started {name} (pid {process.pid})', flush=True)
    return process


def owned(pid):
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def stop_pid(pid):
    if not owned(pid):
        return False
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(pid, signal.SIGTERM)
        process = psutil.Process(pid)
        process.wait(timeout=10)
    except (psutil.Error, ProcessLookupError, subprocess.SubprocessError):
        return False
    return True


def start():
    snapshot = collect_preflight(ROOT, refresh=True)
    blockers = [check for check in snapshot['checks'] if check['required'] and check['status'] != 'ready']
    if blockers:
        print('This machine is not ready to run DARWIN:')
        for check in blockers:
            print(f"  - {check['label']}: {check['remedy'] or check['detail']}")
        return 1
    print(f"Readiness: {snapshot['platform']['system']} | "
          f"{snapshot['platform']['cpu_count']} CPUs | {snapshot['platform']['memory_mb']} MiB")
    if snapshot['capabilities']['faults']:
        print('Fault verification is available on this machine.')

    if not ready(SHOP):
        if not shutil.which('pg_ctl'):
            print('PostgreSQL tools are missing; start the shop with Docker Compose instead.')
            return 1
        spawn('shop', [sys.executable, str(ROOT / 'scripts' / 'run_shop.py')])
        if not wait(SHOP, 90):
            print('The demo shop did not become ready; inspect .runtime/demo/logs/shop.log')
            return 1
    else:
        print('reusing the demo shop already listening on 8010', flush=True)

    if not ready(API):
        spawn('api', [sys.executable, '-m', 'uvicorn', 'darwin.main:app', '--host', '127.0.0.1', '--port', '8000'])
        if not wait(API, 45):
            print('The API did not become ready; inspect .runtime/demo/logs/api.log')
            return 1
    else:
        print('reusing the API already listening on 8000', flush=True)

    npm = shutil.which('npm')
    if not ready(UI):
        if not npm:
            print('Node.js and npm are required for the dashboard.')
            return 1
        command = [npm, '--prefix', 'frontend', 'run', 'dev']
        if os.name == 'nt':
            command = [os.environ.get('COMSPEC', 'cmd.exe'), '/c', *command]
        spawn('ui', command)
        if not wait(UI, 60):
            print('The dashboard did not become ready; inspect .runtime/demo/logs/ui.log')
            return 1
    else:
        print('reusing the dashboard already listening on 5173', flush=True)

    token = ' (API token required)' if os.environ.get('DARWIN_API_TOKEN') else ''
    print(f'\nDARWIN is ready: {UI}{token}')
    print('Stop it with: python scripts/demo.py stop')
    return 0


def stop():
    state = load_state()
    stopped = []
    for name in ('ui', 'api'):
        entry = state.pop(name, None)
        if entry and stop_pid(entry['pid']):
            stopped.append(name)
    shop = state.pop('shop', None)
    if shop:
        stop_file = ROOT / '.runtime' / 'shop' / 'STOP'
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.write_text('stop\n', encoding='utf-8')
        deadline = time.monotonic() + 25
        while owned(shop['pid']) and time.monotonic() < deadline:
            time.sleep(0.5)
        stop_file.unlink(missing_ok=True)
        if stop_pid(shop['pid']) or not owned(shop['pid']):
            stopped.append('shop')
    save_state(state)
    print('stopped ' + ', '.join(stopped) if stopped else 'no launcher-owned processes were running')
    return 0


def status():
    snapshot = collect_preflight(ROOT)
    blockers = [check for check in snapshot['checks'] if check['required'] and check['status'] != 'ready']
    print(f"ready={str(snapshot['ready']).lower()} modes={', '.join(snapshot['execution_modes'])}")
    for check in snapshot['checks']:
        print(f"  {check['label']:<20} {check['status']:<16} {check.get('version') or check['detail']}")
    for name, url in [('shop', SHOP), ('api', API), ('ui', UI)]:
        print(f"  {name:<20} {'listening' if ready(url) else 'not running':<16} {url}")
    print('state=' + (', '.join(f'{name}:{entry["pid"]}' for name, entry in load_state().items()) or 'none'))
    return 1 if blockers and not ready(API) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'stop', 'status'])
    args = parser.parse_args()
    return {'start': start, 'stop': stop, 'status': status}[args.command]()


if __name__ == '__main__':
    raise SystemExit(main())
