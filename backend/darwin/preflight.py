"""Read-only readiness checks for the machine that hosts DARWIN.

The checks are deliberately cheap and non-fatal: a missing optional tool is
reported with a remedy instead of raising. The API uses this to show what the
current machine can actually run before a visitor starts a demo.
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from darwin.docker_resources import docker_status

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_SECONDS = 15
_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def _command(args, timeout=3.0):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL, creationflags=_FLAGS)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = (proc.stdout or proc.stderr).strip().splitlines()
    return lines[0].strip() if lines else ''


def _tool(ident, label, commands, args, required, remedy, purpose):
    for command in commands:
        path = shutil.which(command)
        if path:
            version = _command([path, *args])
            return {'id': ident, 'label': label, 'required': required, 'status': 'ready',
                    'version': version, 'detail': purpose, 'remedy': None}
    return {'id': ident, 'label': label, 'required': required,
            'status': 'missing' if required else 'optional_missing',
            'version': None, 'detail': purpose, 'remedy': remedy}


def _tcp(host, port, timeout=0.25):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _bundled_tool(root, name):
    base = Path(root).resolve()
    for parent in (base, *base.parents):
        candidate = parent / '.runtime' / 'tools' / name
        if candidate.is_file():
            return str(candidate)
    project = Path(__file__).resolve().parents[2] / '.runtime' / 'tools' / name
    return str(project) if project.is_file() else None


def _service_check(ident, label, host, port, required, remedy, running_detail):
    running = _tcp(host, port)
    return {'id': ident, 'label': label, 'required': required,
            'status': 'ready' if running else ('missing' if required else 'optional_missing'),
            'version': None, 'detail': running_detail if running else f'Nothing is listening on {host}:{port}.',
            'remedy': None if running else remedy}


def _memory_mb():
    try:
        import psutil
        return int(psutil.virtual_memory().total / 2**20)
    except Exception:
        return None


def _execution_modes():
    modes = ['native_smoke']
    if os.name == 'nt':
        modes.extend(['native_benchmark', 'native_faults'])
    cgroups = docker_status()
    if cgroups:
        modes.append('docker_smoke')
    if cgroups == '2':
        modes.extend(['docker_benchmark', 'docker_faults'])
    return modes


def collect_preflight(root: str | Path | None = None, refresh: bool = False):
    """Return a cached readiness snapshot. Never raises for missing tools."""
    key = str(Path(root).resolve()) if root else str(Path.cwd())
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and not refresh and now - cached[0] < _CACHE_SECONDS:
            return cached[1]

    checks = [
        {'id': 'python', 'label': 'Python', 'required': True, 'status': 'ready',
         'version': platform.python_version(), 'detail': 'Runs the API, worker, simulator and shop.',
         'remedy': None},
        _tool('node', 'Node.js', ['node'], ['--version'], True,
              'Install Node.js 20.19 or newer to run the dashboard.', 'Builds the dashboard.'),
        _tool('postgres', 'PostgreSQL tools', ['initdb', 'pg_ctl'], ['--version'], True,
              'Put PostgreSQL bin/ on PATH for native measurements and the demo shop.',
              'Create isolated clusters for experiments and the demo shop.'),
        _tool('redis', 'Redis', ['redis-server'], ['--version'], False,
              'Optional: only needed by cached candidates and the cached demo shop.',
              'Serves catalog cache configurations.'),
        _service_check('demo_database', 'Demo database', '127.0.0.1', 55432, False,
                       'Start the interactive shop with scripts/run_shop.py.',
                       'The demo shop cluster is running.'),
        _service_check('demo_shop', 'Demo shop', '127.0.0.1', 8010, False,
                       'Start the interactive shop with scripts/run_shop.py.',
                       'The interactive checkout shop is running.'),
    ]

    docker = shutil.which('docker')
    cgroups = docker_status()
    checks.append({
        'id': 'docker', 'label': 'Docker engine', 'required': False,
        'status': 'ready' if cgroups else 'optional_missing',
        'version': 'Linux engine, cgroup v2' if cgroups == '2' else 'Linux engine, cgroup v1' if cgroups else None,
        'detail': 'Runs containerized measurements and faults.' if cgroups else 'Docker measurements are disabled.',
        'remedy': None if cgroups else (
            'Start Docker Desktop with a Linux engine and cgroup v2 to enable Docker runs.'),
    })
    toxiproxy = os.environ.get('DARWIN_TOXIPROXY') or shutil.which('toxiproxy-server') \
        or _bundled_tool(key, 'toxiproxy-server.exe' if os.name == 'nt' else 'toxiproxy-server')
    toxiproxy_version = _command([toxiproxy, '-version']) if toxiproxy and Path(toxiproxy).is_file() else None
    checks.append({
        'id': 'toxiproxy', 'label': 'Toxiproxy', 'required': False,
        'status': 'ready' if toxiproxy_version else 'optional_missing',
        'version': toxiproxy_version,
        'detail': 'Injects latency and disconnects for native and Docker fault tests.' if toxiproxy_version
                  else 'Native fault tests need the Toxiproxy binary.',
        'remedy': None if toxiproxy_version
                  else 'Run scripts/setup_toxiproxy.ps1 to provision the local Toxiproxy binary.',
    })

    try:
        disk = shutil.disk_usage(key)
        free_gb = round(disk.free / 1e9, 1)
        disk_status = 'ready' if disk.free >= 2 * 1e9 else 'missing'
        checks.append({'id': 'disk', 'label': 'Free disk', 'required': True, 'status': disk_status,
                       'version': f'{free_gb} GB free', 'detail': 'Artifacts, source snapshots and sandboxes.',
                       'remedy': None if disk_status == 'ready' else 'Free at least 2 GB before a measured run.'})
    except OSError:
        checks.append({'id': 'disk', 'label': 'Free disk', 'required': True, 'status': 'missing',
                       'version': None, 'detail': 'Could not read free disk space.',
                       'remedy': 'Check that the working directory is readable.'})

    memory = _memory_mb()
    checks.append({'id': 'memory', 'label': 'Memory', 'required': False,
                   'status': 'ready' if memory and memory >= 4096 else 'optional_missing',
                   'version': f'{memory} MiB' if memory else None,
                   'detail': 'Measured runs reserve about 4 GiB for a sandbox.',
                   'remedy': None if memory and memory >= 4096 else 'Use a host with at least 4 GiB of memory.'})

    modes = _execution_modes()
    required_ok = all(check['status'] == 'ready' for check in checks if check['required'])
    snapshot = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'platform': {
            'system': platform.system(), 'release': platform.release(),
            'machine': platform.machine(), 'python': platform.python_version(),
            'cpu_count': os.cpu_count(), 'memory_mb': memory,
        },
        'checks': checks,
        'execution_modes': modes,
        'capabilities': {
            'smoke': any(mode.endswith('_smoke') for mode in modes),
            'benchmark': any(mode.endswith('_benchmark') for mode in modes),
            'faults': any(mode.endswith('_faults') for mode in modes),
            'docker': any(mode.startswith('docker_') for mode in modes),
        },
        'ready': required_ok,
    }
    with _CACHE_LOCK:
        _CACHE[key] = (now, snapshot)
    return snapshot
