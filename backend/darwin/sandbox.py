import json
import os
import platform
import random
import shutil
import socket
import subprocess
import sys
import time
from importlib.metadata import version

import httpx
import psycopg
import psutil
from psycopg import sql
import yaml

from darwin.architecture import render_compose, runtime_environment
from darwin.contracts import Genome
from darwin.experiments import write_json
from darwin.shop.db import DEFAULT_DSN


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stop_process(process):
    if process.poll() is not None:
        return
    parent = psutil.Process(process.pid)
    children = parent.children(recursive=True)
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    process.terminate()
    _, alive = psutil.wait_procs(children, timeout=3)
    for child in alive:
        child.kill()
    process.wait(timeout=5)


class Sandbox:
    def __init__(self, request, candidate, folder, source):
        self.request, self.folder, self.source = request, folder, source
        self.genome = Genome.model_validate(candidate['genome'])
        self.processes, self.logs = [], []
        self.socket_ports = []
        self.database = None
        self.docker = False
        self.project = 'darwin-run-' + folder.name.replace('-', '')
        self.env = {**os.environ, **runtime_environment(self.genome), 'PYTHONPATH': str(source / 'backend')}
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'
        self.env['DARWIN_CACHE_NAMESPACE'] = folder.name
        self.admin = os.environ.get('DARWIN_NATIVE_DATABASE_URL', DEFAULT_DSN)
        self.config = render_compose(self.genome)
        self.config['name'] = self.project
        for service in self.config['services'].values():
            if 'build' in service:
                service['build'] = str(source)
        self.gateway_port = port()
        self.config['services']['gateway']['ports'] = [f'127.0.0.1:{self.gateway_port}:8000']
        self.compose = folder / 'compose.yaml'
        self.compose.write_text(yaml.safe_dump(self.config, sort_keys=False))
        write_json(folder / 'environment.json', {'python': sys.version, 'platform': platform.platform(),
                   'packages': {name: version(name) for name in ('fastapi', 'httpx', 'psycopg', 'redis')},
                   'mode': request.mode, 'resource_limits_enforced': False})

    def launch(self, args, log, env, *, application):
        return subprocess.Popen(args, env=env, cwd=self.source, stdout=log, stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def command(self, args, check, name, env=None, *, application=False):
        log = (self.folder / name).open('ab')
        offset = log.tell()
        try:
            process = self.launch(args, log, env or self.env, application=application)
            try:
                while process.poll() is None:
                    check()
                    time.sleep(.1)
                if process.returncode:
                    raise RuntimeError(f'Command failed; inspect {name}')
            finally:
                stop_process(process)
        finally:
            log.close()
        return (self.folder / name).read_bytes()[offset:].decode('utf-8', errors='replace')

    def spawn(self, args, env, name):
        log = (self.folder / f'{name}.log').open('ab')
        self.logs.append(log)
        process = self.launch(args, log, env, application=True)
        self.processes.append(process)
        self.ownership()
        return process

    def ownership(self):
        identities = []
        for process in self.processes:
            if process.poll() is None:
                try:
                    parent = psutil.Process(process.pid)
                    identities.extend({'pid': p.pid, 'created_at': p.create_time()} for p in [parent, *parent.children(recursive=True)])
                except psutil.NoSuchProcess:
                    pass
        write_json(self.folder / 'ownership.json', {'database': self.database, 'project': self.project,
                   'mode': self.request.mode, 'process_ids': [p.pid for p in self.processes],
                   'process_identities': identities, 'socket_ports': self.socket_ports,
                   'note': 'IDs are historical evidence; verify process identity before manual cleanup.'})

    def ready(self, url, check):
        until = time.monotonic() + 30
        while time.monotonic() < until:
            check()
            if any(p.poll() is not None for p in self.processes):
                raise RuntimeError('Sandbox process exited; inspect service logs')
            try:
                if httpx.get(url, timeout=.5, trust_env=False).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(.1)
        raise TimeoutError('Sandbox readiness timed out')

    def prepare_database(self, check):
        database_name = 'darwin_run_' + self.folder.name.replace('-', '')
        with psycopg.connect(self.admin, autocommit=True, connect_timeout=2) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))
        self.database = database_name
        self.ownership()
        self.env['DARWIN_DATABASE_URL'] = psycopg.conninfo.make_conninfo(self.admin, dbname=self.database)

    def run(self, check):
        check()
        if self.request.mode == 'docker_smoke':
            if not shutil.which('docker'):
                raise RuntimeError('Docker is not installed; no sandbox was deployed')
            self.docker = True
            self.ownership()
            self.command(['docker', 'compose', '-f', str(self.compose), 'up', '--build', '-d', '--wait', '--wait-timeout', '60'], check, 'deployment.log')
        else:
            self.prepare_database(check)
            inventory_port, payment_port = port(), port()
            self.env['DARWIN_INVENTORY_URL'] = f'http://127.0.0.1:{inventory_port}'
            self.env['DARWIN_PAYMENT_URL'] = f'http://127.0.0.1:{payment_port}'
            if self.genome.catalog_cache_ttl_s:
                redis_exe = shutil.which('redis-server')
                if not redis_exe:
                    raise RuntimeError('redis-server is required for this native candidate')
                redis_port = port()
                self.socket_ports.append(redis_port)
                self.ownership()
                self.env['DARWIN_REDIS_URL'] = f'redis://127.0.0.1:{redis_port}/0'
                self.spawn([redis_exe, '--bind', '127.0.0.1', '--port', str(redis_port), '--save', '', '--appendonly', 'no'], self.env, 'redis')
            self.command([sys.executable, '-m', 'darwin.shop.cli', 'init'], check, 'seed.log')
            specs = [('inventory', 'services:inventory', inventory_port), ('payment', 'services:payment', payment_port)]
            urls = []
            for i in range(self.genome.app_replicas):
                api_port = port()
                urls.append(f'http://127.0.0.1:{api_port}')
                specs.append((f'api-{i+1}', 'services:api', api_port))
            self.env['DARWIN_SHOP_API_URLS'] = ','.join(urls)
            if self.genome.notification_mode == 'queued':
                specs.append(('worker', 'worker:app', port()))
            specs.append(('gateway', 'gateway:app', self.gateway_port))
            self.socket_ports.extend(spec[2] for spec in specs)
            self.ownership()
            for name, target, service_port in specs:
                check()
                self.spawn([sys.executable, '-m', 'uvicorn', f'darwin.shop.{target}', '--host', '127.0.0.1', '--port', str(service_port)],
                           {**self.env, 'DARWIN_INSTANCE_ID': name}, name)
                self.ready(f'http://127.0.0.1:{service_port}/' + ('health' if name == 'gateway' else 'ready'), check)
                self.ownership()
        base = f'http://127.0.0.1:{self.gateway_port}/shop'
        self.ready(base + '/ready', check)
        return self.exercise(base, check)

    def exercise(self, base, check):
        with httpx.Client(timeout=3, trust_env=False) as client:
            for _ in range(2):
                check()
                client.get(base + '/catalog').raise_for_status()
            rng = random.Random(self.request.seed)
            samples = []
            for i in range(2):
                check()
                payload = {'sku': rng.choice(['darwin-notebook', 'darwin-mug', 'darwin-shirt']), 'quantity': 1}
                headers = {'Idempotency-Key': f'smoke-{self.request.seed}-{i}'}
                first = client.post(base + '/checkout', json=payload, headers=headers)
                first.raise_for_status()
                check()
                replay = client.post(base + '/checkout', json=payload, headers=headers)
                replay.raise_for_status()
                if first.json() != replay.json():
                    raise RuntimeError('Replay changed the order response')
                samples.append({'request': payload, 'response': first.json(), 'replay_equal': True})
            write_json(self.folder / 'requests.json', samples)
        command = [sys.executable, '-m', 'darwin.shop.cli', 'verify']
        if self.docker:
            from darwin.docker_resources import docker_executable
            command = [docker_executable() or 'docker', 'compose', '-p', self.project, '-f', str(self.compose),
                       'exec', '-T', 'api-1', 'python', '-m', 'darwin.shop.cli', 'verify']
        # Quiescent queue drain; this is smoke evidence, not an adversarial gate.
        for _ in range(50):
            check()
            report = json.loads(self.command(command, check, 'ledger-check.log'))
            if not report['pending_notifications']:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Notification drain timed out')
        return {'requests': len(samples), 'replays_equal': True, 'seed': self.request.seed,
                'measurement_kind': 'smoke_only', 'gate': 'not_checked', 'resource_limits_enforced': self.docker}

    def close(self):
        errors = []
        if self.docker:
            until = time.monotonic() + 30
            def cleanup_check():
                if time.monotonic() > until:
                    raise TimeoutError('Docker cleanup timed out')
            try:
                self.command(['docker', 'compose', '-f', str(self.compose), 'logs', '--no-color'], cleanup_check, 'containers.log')
            except Exception:
                pass
            try:
                self.command(['docker', 'compose', '-f', str(self.compose), 'down', '--volumes', '--remove-orphans', '--timeout', '5'], cleanup_check, 'cleanup.log')
            except Exception as exc:
                errors.append(str(exc))
        for process in reversed(self.processes):
            try:
                stop_process(process)
            except Exception as exc:
                errors.append(str(exc))
        for log in self.logs:
            log.close()
        ownership_file = self.folder / 'ownership.json'
        if ownership_file.exists() and not self.docker:
            for identity in json.loads(ownership_file.read_text()).get('process_identities', []):
                try:
                    process = psutil.Process(identity['pid'])
                    if abs(process.create_time() - identity['created_at']) < .01:
                        errors.append(f'Owned process {process.pid} remains after cleanup')
                except psutil.NoSuchProcess:
                    pass
        if self.database:
            try:
                with psycopg.connect(self.admin, autocommit=True, connect_timeout=2, options='-c statement_timeout=3000') as conn:
                    conn.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(self.database)))
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError('; '.join(errors))
