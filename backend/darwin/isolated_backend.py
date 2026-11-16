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
            'RUN adduser -D -u 65534 appuser',
            'COPY requirements.txt .',
            'RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0',
            'COPY app.py .',
            'USER 65534',
            'EXPOSE 8000',
            'CMD gunicorn -b 0.0.0.0:8000 -w ${GUNICORN_WORKERS:-1} --timeout 10 app:app',
            '',
        ])
    if manifest.runtime == 'uvicorn-fastapi':
        return '\n'.join([
            'FROM python:3.11-alpine',
            'WORKDIR /app',
            'RUN adduser -D -u 65534 appuser',
            'COPY requirements.txt .',
            'RUN pip install --no-cache-dir -r requirements.txt uvicorn==0.34.0',
            'COPY app.py .',
            'USER 65534',
            'EXPOSE 8000',
            'CMD uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}',
            '',
        ])
    raise IsolationError(f'Unsupported reviewed runtime {manifest.runtime!r}', 'unsupported_runtime')


def _nginx_conf(replicas: int) -> str:
    servers = '\n'.join(f'        server web-{index}:8000 max_fails=1 fail_timeout=2s;'
                        for index in range(1, replicas + 1))
    return f'''
events {{ worker_connections 128; }}
http {{
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
            'command': ['redis-server', '--save', '', '--appendonly', 'no'],
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
        'tmpfs': ['/var/run', '/var/cache/nginx', '/tmp'],
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
        src = (root / relative).resolve()
        if not src.is_relative_to(root):
            raise IsolationError(f'Refused path outside the checkout: {relative}', 'path_escape')
        if src.is_symlink() or not src.is_file():
            raise IsolationError(f'Refused non-file or symlink source: {relative}', 'symlink_rejected')
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
        (self.work_dir / 'nginx.conf').write_text(_nginx_conf(self.candidate.replicas), encoding='utf-8')
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

    def inject_restart(self, check) -> float:
        check()
        self.compose('restart', '-t', '2', 'web-1', timeout=60)
        return self.wait_ready(check, timeout_s=30)

    def verify_counter_monotonic(self, check, probes: int = 5) -> dict:
        import re
        pattern = re.compile(r'(\d+)')
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

    def measure(self, seed: int, check, include_fault: bool) -> dict:
        ready_s = self.wait_ready(check)
        self.warmup(check)
        samples = self.http_samples(seed, check)
        summary = summarise_samples(samples, cpu_seconds=0.0, peak_mb=0.0)
        correctness = self.verify_counter_monotonic(check) if self.manifest.needs_redis else {
            'passed': all(row['ok'] for row in samples[:3]),
            'detail': 'HTTP smoke only; no business counter is defined',
            'values': [],
        }
        recovery_s = None
        if include_fault and self.manifest.allow_fault_restart:
            recovery_s = self.inject_restart(check)
        return {
            'candidate_id': self.candidate.candidate_id,
            'ready_s': ready_s,
            'recovery_s': recovery_s,
            'metrics': summary,
            'samples': samples,
            'correctness': correctness,
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
