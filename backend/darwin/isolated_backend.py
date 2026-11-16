"""DARWIN-owned isolated runner for reviewed backend adapters.

Repository Compose/Dockerfiles are never executed. The runner writes its own
image and Compose file from an allowlisted copy of application source, binds
the gateway to 127.0.0.1, drops privileges, and refuses host Docker sockets.
If a Linux Docker engine is not available, it refuses to start rather than
running repository code on the host.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

import httpx
import yaml

from darwin.backend_manifest import BackendManifest, CandidateDimension, validate_relative_files
from darwin.docker_resources import docker_environment, docker_executable, docker_status
from darwin.performance import metrics as summarise_samples

FORBIDDEN_COMPOSE_KEYS = {'privileged', 'devices', 'device_cgroup_rules'}
FORBIDDEN_VOLUME_FRAGMENTS = {'docker.sock', '/var/run/docker.sock', '\\pipe\\docker'}


class IsolationError(RuntimeError):
    def __init__(self, message: str, code: str = 'isolation_unavailable'):
        super().__init__(message)
        self.code = code


def runner_available() -> tuple[bool, str]:
    if not docker_executable():
        return False, 'Docker CLI was not found. Isolated backend execution is disabled.'
    cgroups = docker_status()
    if not cgroups:
        return False, (
            'A local Linux Docker engine is not running. DARWIN will not execute '
            'repository code on the host. Start a Linux engine, then re-run.'
        )
    return True, f'Linux Docker engine with cgroup v{cgroups}'


def _dockerfile(manifest: BackendManifest) -> str:
    if manifest.runtime == 'gunicorn-flask':
        return '\n'.join([
            'FROM python:3.11-alpine',
            'WORKDIR /app',
            # Alpine already ships uid/gid 65534 (nobody). Reuse it instead of
            # creating another account, so the image stays reproducible.
            'COPY requirements.txt .',
            'RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0',
            'COPY app.py .',
            'USER 65534:65534',
            'EXPOSE 8000',
            'ENTRYPOINT ["sh", "-c", "exec gunicorn -b 0.0.0.0:8000 -w ${GUNICORN_WORKERS:-1} --timeout 10 app:app"]',
            '',
        ])
    if manifest.runtime == 'uvicorn-fastapi':
        return '\n'.join([
            'FROM python:3.11-alpine',
            'WORKDIR /app',
            'COPY requirements.txt .',
            'RUN pip install --no-cache-dir -r requirements.txt uvicorn==0.34.0',
            'COPY app.py .',
            'USER 65534:65534',
            'EXPOSE 8000',
            'ENTRYPOINT ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]',
            '',
        ])
    if manifest.runtime == 'node-express':
        return '\n'.join([
            'FROM node:22-alpine',
            'WORKDIR /app',
            'COPY package.json package-lock.json ./',
            'RUN npm ci --omit=dev --ignore-scripts',
            'COPY server.js ./',
            'USER 65534:65534',
            f'EXPOSE {manifest.app_port}',
            'ENTRYPOINT ["node", "server.js"]',
            '',
        ])
    raise IsolationError(f'Unsupported reviewed runtime {manifest.runtime!r}', 'unsupported_runtime')


def _nginx_conf(replicas: int, app_port: int = 8000) -> str:
    servers = '\n'.join(f'        server web-{index}:{app_port} max_fails=1 fail_timeout=2s;'
                        for index in range(1, replicas + 1))
    return f'''
worker_processes 1;
pid /tmp/nginx.pid;
error_log /dev/stderr warn;

events {{ worker_connections 128; }}
http {{
    access_log off;
    client_body_temp_path /tmp/client_body;
    proxy_temp_path /tmp/proxy;
    fastcgi_temp_path /tmp/fastcgi;
    uwsgi_temp_path /tmp/uwsgi;
    scgi_temp_path /tmp/scgi;

    upstream darwin_app {{
{servers}
    }}
    server {{
        listen 8080;
        location / {{
            proxy_pass http://darwin_app;
            proxy_next_upstream error timeout http_502 http_503 http_504;
            proxy_connect_timeout 2s;
            proxy_read_timeout 5s;
        }}
    }}
}}
'''


def generate_compose(manifest: BackendManifest, candidate: CandidateDimension, image: str) -> dict:
    replicas = max(1, int(candidate.replicas))
    workers = max(1, int(candidate.workers))
    services: dict = {}
    if manifest.needs_redis:
        services['redis'] = {
            'image': 'redis:7-alpine',
            'entrypoint': ['redis-server'],
            'command': ['--save', '', '--appendonly', 'no'],
            'user': '999:999',
            'read_only': True,
            'security_opt': ['no-new-privileges:true'],
            'cap_drop': ['ALL'],
            'cpus': 0.25,
            'mem_limit': '64m',
            'networks': ['sandbox'],
            'restart': 'no',
        }
    for index in range(1, replicas + 1):
        name = f'web-{index}'
        environment = {'GUNICORN_WORKERS': str(workers), 'UVICORN_WORKERS': str(workers)}
        service = {
            'image': image,
            'read_only': True,
            'tmpfs': ['/tmp'],
            'security_opt': ['no-new-privileges:true'],
            'cap_drop': ['ALL'],
            'cpus': 0.5,
            'mem_limit': '128m',
            'memswap_limit': '128m',
            'environment': environment,
            'networks': ['sandbox'],
            'restart': 'no',
            'user': '65534:65534',
        }
        if manifest.needs_redis:
            service['depends_on'] = ['redis']
        services[name] = service
    services['gateway'] = {
        'image': 'nginx:1.27-alpine',
        'entrypoint': ['nginx', '-g', 'daemon off;'],
        'user': '101:101',
        'depends_on': [f'web-{index}' for index in range(1, replicas + 1)],
        'volumes': ['./nginx.conf:/etc/nginx/nginx.conf:ro'],
        'ports': [{'target': 8080, 'published': 0, 'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'security_opt': ['no-new-privileges:true'],
        'cap_drop': ['ALL'],
        'cpus': 0.25,
        'mem_limit': '64m',
        'networks': ['sandbox', 'host_access'],
        'restart': 'no',
        'read_only': True,
        'tmpfs': ['/tmp'],
    }
    return {
        'name': 'darwin-external',
        'services': services,
        'networks': {
            'sandbox': {'internal': True},
            'host_access': {},
        },
    }


def assert_safe_compose(config: dict) -> None:
    dumped = yaml.safe_dump(config).lower()
    for fragment in FORBIDDEN_VOLUME_FRAGMENTS:
        if fragment.lower() in dumped:
            raise IsolationError('Generated Compose refused: Docker socket or host engine path.', 'unsafe_compose')
    if 'privileged: true' in dumped or 'network_mode: host' in dumped or 'pid: host' in dumped:
        raise IsolationError('Generated Compose refused: host/privileged mode.', 'unsafe_compose')
    for service in (config.get('services') or {}).values():
        if not isinstance(service, dict):
            raise IsolationError('Invalid Compose service.', 'unsafe_compose')
        for key in FORBIDDEN_COMPOSE_KEYS:
            if service.get(key):
                raise IsolationError(f'Generated Compose refused key {key}.', 'unsafe_compose')
        for volume in service.get('volumes') or []:
            text = volume if isinstance(volume, str) else yaml.safe_dump(volume)
            if any(part in text.lower() for part in FORBIDDEN_VOLUME_FRAGMENTS):
                raise IsolationError('Generated Compose refused a Docker socket mount.', 'unsafe_compose')


def copy_allowlisted_source(source_root: Path, dest: Path, files: list[str] | tuple[str, ...]) -> list[str]:
    copied = []
    root = source_root.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for relative in validate_relative_files(files):
        candidate = root / relative
        if candidate.is_symlink():
            raise IsolationError(f'Refused symlink source: {relative}', 'symlink_rejected')
        src = candidate.resolve()
        if not src.is_relative_to(root):
            raise IsolationError(f'Refused path outside the checkout: {relative}', 'path_escape')
        if not src.is_file():
            raise IsolationError(f'Refused non-file source: {relative}', 'symlink_rejected')
        target = dest / Path(relative).name
        shutil.copyfile(src, target)
        copied.append(Path(relative).name)
    return copied


def topology(candidate: CandidateDimension, needs_redis: bool) -> dict:
    nodes = [{'id': 'gateway', 'label': 'Nginx gateway', 'kind': 'gateway'}]
    for index in range(1, candidate.replicas + 1):
        nodes.append({'id': f'web-{index}', 'label': f'App replica {index} × {candidate.workers} worker(s)',
                      'kind': 'service'})
    if needs_redis:
        nodes.append({'id': 'redis', 'label': 'Redis (shared counter)', 'kind': 'cache'})
    edges = [{'source': 'gateway', 'target': f'web-{index}', 'label': 'HTTP'}
             for index in range(1, candidate.replicas + 1)]
    if needs_redis:
        edges.extend({'source': f'web-{index}', 'target': 'redis', 'label': 'counter'}
                     for index in range(1, candidate.replicas + 1))
    return {
        'candidate_id': candidate.candidate_id,
        'replicas': candidate.replicas,
        'workers': candidate.workers,
        'nodes': nodes,
        'edges': edges,
        'summary': (
            f'{candidate.replicas} replica(s), {candidate.workers} worker(s) each'
            + (', shared Redis' if needs_redis else '')
        ),
    }


class IsolatedBackend:
    """One Compose project for one candidate. Caller must cleanup()."""

    def __init__(self, work_dir: Path, manifest: BackendManifest, candidate: CandidateDimension):
        self.work_dir = Path(work_dir)
        self.manifest = manifest
        self.candidate = candidate
        self.project = f'dwx{uuid4().hex[:10]}'
        self.image = f'{self.project}:app'
        self.cli = docker_executable()
        self.compose_path = self.work_dir / 'compose.yaml'
        self.url = None
        self.logs: list[str] = []

    def write_stack(self, source_root: Path) -> dict:
        build = self.work_dir / 'build'
        if build.exists():
            shutil.rmtree(build, ignore_errors=True)
        copied = copy_allowlisted_source(source_root, build, self.manifest.source_files)
        (build / 'Dockerfile').write_text(_dockerfile(self.manifest), encoding='utf-8')
        (self.work_dir / 'nginx.conf').write_text(
            _nginx_conf(self.candidate.replicas, self.manifest.app_port), encoding='utf-8')
        config = generate_compose(self.manifest, self.candidate, self.image)
        assert_safe_compose(config)
        self.compose_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
        digest = hashlib.sha256(self.compose_path.read_bytes()).hexdigest()
        return {
            'copied': copied,
            'compose_sha256': digest,
            'ignored_repo_compose': True,
            'topology': topology(self.candidate, self.manifest.needs_redis),
            'project': self.project,
        }

    def _run(self, *args: str, timeout: int = 180) -> str:
        if not self.cli:
            raise IsolationError('Docker CLI was not found.', 'docker_missing')
        completed = subprocess.run(
            [self.cli, *args], cwd=str(self.work_dir), env=docker_environment(self.cli),
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        output = (completed.stdout or '') + (completed.stderr or '')
        self.logs.append(output[-4000:])
        if completed.returncode != 0:
            raise IsolationError(output.strip()[-800:] or 'Docker command failed', 'docker_failed')
        return completed.stdout.strip()

    def compose(self, *args: str, timeout: int = 180) -> str:
        return self._run('compose', '-p', self.project, '-f', str(self.compose_path), *args, timeout=timeout)

    def start(self, check) -> None:
        ok, reason = runner_available()
        if not ok:
            raise IsolationError(reason, 'isolation_unavailable')
        check()
        self._run('build', '-t', self.image, str(self.work_dir / 'build'), timeout=300)
        check()
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '90', timeout=120)
        mapping = self.compose('port', 'gateway', '8080')
        host, _, port = mapping.rpartition(':')
        if '127.0.0.1' not in host or not port.isdigit():
            raise IsolationError(f'Gateway was not published on loopback: {mapping}', 'port_escape')
        self.url = f'http://127.0.0.1:{port}'

    def wait_ready(self, check, timeout_s: float = 40) -> float:
        started = time.perf_counter()
        deadline = started + timeout_s
        last = 'not contacted'
        while time.perf_counter() < deadline:
            check()
            try:
                response = httpx.get(self.url + self.manifest.health.path, timeout=self.manifest.health.timeout_s)
                body = response.text
                if response.status_code == self.manifest.health.status and (
                        not self.manifest.health.contains or self.manifest.health.contains in body):
                    return round(time.perf_counter() - started, 3)
                last = f'HTTP {response.status_code}'
            except httpx.HTTPError as exc:
                last = type(exc).__name__
            time.sleep(0.4)
        raise IsolationError(f'Service was not ready: {last}', 'not_ready')

    def http_samples(self, seed: int, check) -> list[dict]:
        spec = self.manifest.workload
        rng_offsets = [(index / spec.rate) for index in range(spec.window_s * spec.rate)]
        samples = []
        start = time.perf_counter()
        with httpx.Client(base_url=self.url, timeout=spec.timeout_s, trust_env=False) as client:
            for offset in rng_offsets:
                check()
                delay = start + offset - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                began = time.perf_counter()
                ok, status, error = False, 0, None
                try:
                    response = client.request(spec.method, spec.path)
                    status = response.status_code
                    ok = 200 <= status < 300
                    if ok and self.manifest.body_pattern and self.manifest.body_pattern not in response.text:
                        ok = False
                        error = 'body_mismatch'
                except httpx.HTTPError as exc:
                    error = type(exc).__name__
                ended = time.perf_counter()
                samples.append({
                    'seed': seed, 'ok': ok, 'status': status, 'error': error,
                    'latency_ms': (ended - began) * 1000,
                    'finished_s': ended - start,
                })
        return samples

    def warmup(self, check) -> None:
        spec = self.manifest.workload
        deadline = time.perf_counter() + spec.warmup_s
        with httpx.Client(base_url=self.url, timeout=spec.timeout_s, trust_env=False) as client:
            while time.perf_counter() < deadline:
                check()
                try:
                    client.request(spec.method, spec.path)
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)

    def inject_restart(self, check) -> dict:
        """Restart web-1 while probing the gateway, then wait for recovery.

        recovery_s is the time from fault injection to the first healthy probe
        after the last failed probe. A candidate that keeps serving traffic
        through another replica reports 0.0 with zero failed probes, instead of
        inheriting the duration of the Docker restart command.
        """
        import threading

        check()
        probes: list[tuple[float, bool]] = []
        stop = threading.Event()

        def probe() -> None:
            client = httpx.Client(base_url=self.url, timeout=1.0, trust_env=False)
            try:
                while not stop.is_set():
                    began = time.perf_counter()
                    try:
                        response = client.get(self.manifest.health.path)
                        ok = response.status_code == self.manifest.health.status and (
                            not self.manifest.health.contains
                            or self.manifest.health.contains in response.text)
                    except httpx.HTTPError:
                        ok = False
                    probes.append((began, ok))
                    time.sleep(0.05)
            finally:
                client.close()

        thread = threading.Thread(target=probe, daemon=True, name='darwin-restart-probe')
        thread.start()
        injected = time.perf_counter()
        try:
            self.compose('restart', '-t', '2', 'web-1', timeout=60)
            residual = self.wait_ready(check, timeout_s=30)
        finally:
            stop.set()
            thread.join(timeout=2)
        restart_s = round(time.perf_counter() - injected, 3)
        failures = [at for at, ok in probes if not ok]
        recovery_s = 0.0
        if failures:
            last_failure = failures[-1]
            after = [at for at, ok in probes if ok and at >= last_failure]
            recovery_s = round((after[0] if after else injected + residual) - injected, 3)
        return {
            'recovery_s': recovery_s,
            'restart_command_s': restart_s,
            'probes': len(probes),
            'failed_probes': len(failures),
            'observed_outage': bool(failures),
            'note': (
                'No gateway-level outage observed: another replica served traffic while web-1 restarted.'
                if not failures else
                f'{len(failures)} of {len(probes)} gateway probes failed during the restart; '
                f'the first healthy response after the last failure arrived {recovery_s:.3f}s after injection.'
            ),
        }

    def _app_containers(self) -> list[str]:
        services = [f'web-{index}' for index in range(1, max(1, self.candidate.replicas) + 1)]
        if self.manifest.needs_redis:
            services.append('redis')
        ident = []
        for service in services:
            try:
                output = self.compose('ps', '-q', service, timeout=20)
            except IsolationError:
                continue
            ident.extend(line.strip() for line in output.splitlines() if line.strip())
        return ident

    def _cgroup_file(self, container: str, relative: str) -> str | None:
        try:
            completed = subprocess.run(
                [self.cli, 'exec', container, 'cat', f'/sys/fs/cgroup/{relative}'],
                capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL,
                env=docker_environment(self.cli),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout if completed.returncode == 0 else None

    def resource_snapshot(self) -> dict:
        """Read cgroup v2 counters from DARWIN-owned containers.

        cpu_seconds is a real cumulative counter (usage_usec). memory is the
        per-container cgroup peak when the kernel exposes it; otherwise the
        current value, flagged as such. No value is invented when unreadable.
        """
        ids = self._app_containers()
        cpu_us = 0
        cpu_ok = bool(ids)
        memory = []
        peak_basis = True
        for container in ids:
            stat = self._cgroup_file(container, 'cpu.stat')
            match = None
            if stat:
                for line in stat.splitlines():
                    if line.startswith('usage_usec'):
                        match = line.split()[1]
                if match and match.isdigit():
                    cpu_us += int(match)
                else:
                    cpu_ok = False
            else:
                cpu_ok = False
            peak = self._cgroup_file(container, 'memory.peak')
            current = self._cgroup_file(container, 'memory.current')
            value = None
            if peak and peak.strip().isdigit():
                value = int(peak.strip())
            elif current and current.strip().isdigit():
                value = int(current.strip())
                peak_basis = False
            if value is not None:
                memory.append(value)
        return {
            'cpu_us': cpu_us if cpu_ok else None,
            'memory_bytes': sum(memory) if memory else None,
            'memory_basis': 'cgroup_peak_sum' if peak_basis and memory else (
                'cgroup_current_sum' if memory else None),
            'containers': len(ids),
        }

    def verify_counter_monotonic(self, check, probes: int = 5) -> dict:
        import re
        pattern = re.compile(self.manifest.counter_pattern)
        values = []
        with httpx.Client(base_url=self.url, timeout=self.manifest.workload.timeout_s, trust_env=False) as client:
            for _ in range(probes):
                check()
                response = client.get(self.manifest.health.path)
                match = pattern.search(response.text or '')
                if response.status_code != 200 or not match:
                    return {'passed': False, 'detail': 'Health body did not include a counter', 'values': values}
                values.append(int(match.group(1)))
        increasing = all(right > left for left, right in zip(values, values[1:]))
        return {
            'passed': increasing,
            'detail': 'Shared Redis counter increased through the gateway' if increasing
            else 'Counter did not strictly increase; shared state may be broken',
            'values': values,
        }

    def measure(self, seed: int, check, include_fault: bool, deadline: float | None = None) -> dict:
        def guard() -> None:
            if deadline is not None and time.perf_counter() > deadline:
                raise IsolationError(
                    'The wall-clock budget expired before this candidate finished. '
                    'No metrics are reported for it.', 'budget_exhausted',
                )
            check()

        ready_s = self.wait_ready(guard)
        self.warmup(guard)
        before = self.resource_snapshot()
        samples = self.http_samples(seed, guard)
        after = self.resource_snapshot()
        resource_measured = bool(
            before.get('cpu_us') is not None and after.get('cpu_us') is not None
            and after.get('memory_bytes') is not None
        )
        cpu_seconds = 0.0
        peak_mb = 0.0
        if resource_measured:
            cpu_seconds = round(max(0, after['cpu_us'] - before['cpu_us']) / 1_000_000, 4)
            peak_mb = round(after['memory_bytes'] / (1024 * 1024), 3)
        summary = summarise_samples(
            samples, cpu_seconds=cpu_seconds, peak_mb=peak_mb,
            window_s=self.manifest.workload.window_s,
        )
        correctness = self.verify_counter_monotonic(guard) if self.manifest.needs_redis else {
            'passed': all(row['ok'] for row in samples[:3]),
            'detail': 'HTTP smoke only; no business counter is defined',
            'values': [],
        }
        recovery_s = None
        recovery_detail = None
        if include_fault and self.manifest.allow_fault_restart:
            recovery_detail = self.inject_restart(guard)
            recovery_s = recovery_detail['recovery_s']
            if self.manifest.needs_redis:
                after_restart = self.verify_counter_monotonic(guard)
                correctness = {
                    'passed': bool(correctness.get('passed') and after_restart.get('passed')),
                    'detail': (
                        'Shared Redis counter increased before and after the web replica restart'
                        if correctness.get('passed') and after_restart.get('passed')
                        else after_restart.get('detail') or correctness.get('detail')
                    ),
                    'values': list(correctness.get('values') or []) + list(after_restart.get('values') or []),
                    'phases': ['before_restart', 'after_restart'],
                }
        return {
            'candidate_id': self.candidate.candidate_id,
            'ready_s': ready_s,
            'recovery_s': recovery_s,
            'recovery_detail': recovery_detail,
            'metrics': summary,
            'samples': samples,
            'correctness': correctness,
            'resources': {
                'measured': resource_measured,
                'cpu_seconds': cpu_seconds if resource_measured else None,
                'memory_peak_mb': peak_mb if resource_measured else None,
                'memory_basis': after.get('memory_basis'),
                'containers': after.get('containers') or 0,
                'source': 'docker-cgroup-v2' if resource_measured else 'unavailable',
            },
            'url_loopback': True,
        }

    def cleanup(self) -> str:
        status = 'completed'
        try:
            if self.compose_path.is_file() and self.cli:
                self.compose('down', '-v', '--remove-orphans', timeout=90)
        except Exception:
            status = 'requires_review'
        try:
            if self.cli:
                subprocess.run(
                    [self.cli, 'rmi', '-f', self.image], capture_output=True, timeout=60,
                    env=docker_environment(self.cli),
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )
        except Exception:
            status = 'requires_review'
        return status
