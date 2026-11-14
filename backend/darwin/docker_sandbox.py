"""Docker Compose experiment adapter for local Linux container engines."""
import json
from pathlib import PurePosixPath
import sys
import time

import httpx
import psycopg
import yaml

from darwin.docker_resources import docker_environment, docker_executable, docker_output, docker_status
from darwin.experiments import FAULT_MODES, MEASURED_MODES, write_json
from darwin.performance import metrics, WARMUP_S, WINDOW_S
from darwin.sandbox import Sandbox

TOXIPROXY_IMAGE = 'ghcr.io/shopify/toxiproxy:2.13.0'
CONTROL_DIR = '/var/lib/darwin-control'
CONTROL = PurePosixPath(CONTROL_DIR, 'pause-notification')


def verify_docker_absent(project, engine_id=None):
    if engine_id and docker_output('info', '--format', '{{.ID}}') != engine_id:
        raise RuntimeError('Select the Docker engine that owned this run before verifying cleanup')
    for command in (('ps', '-aq'), ('volume', 'ls', '-q'), ('network', 'ls', '-q')):
        if docker_output(*command, '--filter', f'label=com.docker.compose.project={project}'):
            raise RuntimeError(f'Docker resources remain for project {project}')
    if docker_output('image', 'ls', '-q', '--filter', f'reference={project}:app'):
        raise RuntimeError(f'The experiment image tag remains for project {project}')


class DockerSandbox(Sandbox):
    def __init__(self, request, candidate, folder, source):
        super().__init__(request, candidate, folder, source)
        self.cli = docker_executable()
        self.env = docker_environment(self.cli, self.env)
        self.image = f'{self.project}:app'
        self.config['networks'].setdefault('host_access', {})
        self.services = self.config['services']
        self.app_services = [name for name in self.services if name != 'seed']
        self.api_services = [name for name in self.app_services if name.startswith('api-')]
        self.paused = []
        for service in self.services.values():
            if 'build' in service:
                service['image'] = self.image
            service['memswap_limit'] = service['mem_limit']
        self.publish('gateway', 8000)
        self.services['db']['healthcheck']['test'] = [
            'CMD', 'pg_isready', '-h', '127.0.0.1', '-U', 'darwin', '-d', 'darwin_shop',
        ]
        if request.mode in MEASURED_MODES:
            self.publish('db', 5432)
        if request.mode in FAULT_MODES:
            self.configure_faults()
        self.compose.write_text(yaml.safe_dump(self.config, sort_keys=False), encoding='utf-8')

    def publish(self, name, target):
        service = self.services[name]
        service['networks'] = list(dict.fromkeys([*service['networks'], 'host_access']))
        service['ports'] = [{'target': target, 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]

    def configure_faults(self):
        self.services['toxiproxy'] = {
            'image': TOXIPROXY_IMAGE, 'networks': ['sandbox'],
            'command': ['-host=0.0.0.0', f'-seed={self.request.seed}'],
            'cpus': 0.25, 'mem_limit': '128m', 'memswap_limit': '128m',
        }
        self.publish('toxiproxy', 8474)
        self.config['volumes']['fault-control'] = {}
        for name in ('inventory', 'payment', *self.api_services, 'worker'):
            if name not in self.services:
                continue
            environment = self.services[name]['environment']
            environment['DARWIN_DATABASE_URL'] = psycopg.conninfo.make_conninfo(
                environment['DARWIN_DATABASE_URL'], host='toxiproxy', port=15432)
            environment['DARWIN_PAYMENT_URL'] = 'http://toxiproxy:18000'
            environment['DARWIN_INSTANCE_ID'] = name
            environment['DARWIN_ISOLATED_FAULT_TEST'] = '1'
            if name in (*self.api_services, 'worker'):
                environment['DARWIN_FAULT_CONTROL_FILE'] = str(CONTROL)
                self.services[name]['volumes'] = [f'fault-control:{CONTROL_DIR}']
        self.services['gateway']['volumes'] = [f'fault-control:{CONTROL_DIR}']
        if self.request.fault_fixture == 'unsafe_retry':
            command = self.services['payment']['command']
            command[command.index('darwin.shop.services:payment')] = 'darwin.unsafe_payment:app'

    def compose_command(self, check, log, *args):
        return self.command(
            [self.cli, 'compose', '-p', self.project, '-f', str(self.compose), *args], check, log,
        ).strip()

    def published_port(self, name, target, check):
        address = self.compose_command(check, 'ports.log', 'port', name, str(target))
        host, _, port = address.rpartition(':')
        if host != '127.0.0.1' or not port.isdigit():
            raise RuntimeError(f'Invalid loopback port mapping for {name}')
        self.socket_ports.append(int(port))
        self.ownership()
        return int(port)

    def ownership(self):
        super().ownership()
        path = self.folder / 'ownership.json'
        write_json(path, {**json.loads(path.read_bytes()), 'docker_engine_id': self.engine_id})

    def run(self, check):
        check()
        cgroups = docker_status()
        if not self.cli or not cgroups:
            raise RuntimeError('A local Linux Docker engine and Docker Compose are required')
        if self.request.mode in MEASURED_MODES and cgroups != '2':
            raise RuntimeError('Docker measurements require cgroup v2')
        self.compose_command(check, 'deployment.log', 'config', '--quiet')
        self.engine_id = docker_output('info', '--format', '{{.ID}}')
        self.docker = True
        self.ownership()
        self.compose_command(check, 'deployment.log', 'build', 'gateway')
        if self.request.mode in FAULT_MODES:
            self.compose_command(check, 'deployment.log', 'up', '-d', '--no-build', '--wait',
                                 '--wait-timeout', '60', 'db', 'toxiproxy')
            self.tox_url = f"http://127.0.0.1:{self.published_port('toxiproxy', 8474, check)}"
            self.ready(self.tox_url + '/version', check)
            for name, listen, upstream in [('database', '15432', 'db:5432'), ('payment', '18000', 'payment:8000')]:
                self.proxy_call('POST', '/proxies', {
                    'name': name, 'listen': f'0.0.0.0:{listen}', 'upstream': upstream, 'enabled': True,
                })
            write_json(self.folder / 'fault-tool.json', {
                'image': TOXIPROXY_IMAGE, 'image_id': docker_output('image', 'inspect', '--format', '{{.Id}}', TOXIPROXY_IMAGE),
                'version': self.proxy_call('GET', '/version'), 'application_resource_group': False,
            })
        self.compose_command(check, 'deployment.log', 'up', '-d', '--no-build', '--wait', '--wait-timeout', '90')
        self.gateway_port = self.published_port('gateway', 8000, check)
        base = f'http://127.0.0.1:{self.gateway_port}/shop'
        self.ready(base + '/ready', check)
        if self.request.mode == 'docker_smoke':
            result = super().exercise(base, check)
            return {**result, 'resource_limits_enforced': False}
        db_port = self.published_port('db', 5432, check)
        self.direct_dsn = psycopg.conninfo.make_conninfo(
            self.services['seed']['environment']['DARWIN_DATABASE_URL'], host='127.0.0.1', port=db_port)
        if self.request.mode in FAULT_MODES:
            self.compose_command(check, 'fault-control.log', 'exec', '-T', '-u', '0', 'gateway',
                                 'chown', 'darwin:darwin', CONTROL_DIR)
        result = self.measure(base, check)
        if self.request.mode in FAULT_MODES:
            from darwin.fault_suite import FaultSuite
            return FaultSuite(self, base, check).run(result)
        return result

    def measure(self, base, check):
        with psycopg.connect(self.direct_dsn, connect_timeout=2, options='-c statement_timeout=5000') as conn:
            conn.execute('UPDATE products SET initial_stock=1000, available=1000')
        containers = {}
        self.container_ids = {}
        for name in self.app_services:
            ident = self.compose_command(check, 'container-ids.log', 'ps', '-q', name)
            if not ident or '\n' in ident or ident in containers:
                raise RuntimeError(f'Expected one running container for {name}')
            config = self.services[name]
            self.container_ids[name] = ident
            containers[ident] = {'service': name, 'cpus': config['cpus'],
                                 'memory_bytes': int(config['mem_limit'][:-1]) * 2**20}
        manifest = self.folder / 'docker-cgroups.json'
        write_json(manifest, containers)
        self.command([sys.executable, '-m', 'darwin.locust_load', base.removesuffix('/shop'),
                      self.request.workload_profile, str(manifest), str(self.folder), str(self.request.seed),
                      '--docker'], check, 'locust.log')
        samples = json.loads((self.folder / 'samples.json').read_bytes())
        resources = json.loads((self.folder / 'resources.json').read_bytes())
        before, after = resources['application_start'], resources['application_end']
        environment = json.loads((self.folder / 'environment.json').read_bytes())
        environment.update(resource_limits_enforced=True, protocol='docker-cgroup-v2-locust-v1',
                           memory_scope='sum of container lifetime peaks', warmup_s=WARMUP_S,
                           measurement_s=WINDOW_S, engine_version=docker_output('version', '--format', '{{.Server.Version}}'),
                           compose_version=docker_output('compose', 'version', '--short'))
        write_json(self.folder / 'environment.json', environment)
        return {'metrics': metrics(samples, after['cpu_seconds'] - before['cpu_seconds'], after['memory_peak_mb']),
                'resource_limits_enforced': True, 'measurement_kind': 'measured', 'gate': 'not_checked'}

    def proxy_call(self, method, path, body=None):
        with httpx.Client(base_url=self.tox_url, timeout=3, trust_env=False) as client:
            response = client.request(method, path, json=body)
            response.raise_for_status()
            return response.json() if response.content else None

    def pause_apis(self):
        # Keep the complete target list available for cleanup if the command partially succeeds.
        self.paused = [self.container_ids[name] for name in self.api_services]
        docker_output('pause', *self.paused)
        return list(self.paused)

    def resume_apis(self, paused):
        if paused:
            states = docker_output('inspect', '--format', '{{.Id}} {{.State.Paused}}', *paused)
            active = [ident for ident, state in (line.split() for line in states.splitlines()) if state == 'true']
            if active:
                docker_output('unpause', *active)
        self.paused = []

    def stop_service(self, name):
        if name not in (*self.api_services, 'worker') or name not in self.services:
            raise RuntimeError('Unexpected notification process identity')
        docker_output('compose', '-p', self.project, '-f', str(self.compose), 'kill', '-s', 'SIGKILL', name)

    def restart_service(self, name, check):
        self.compose_command(check, 'restart.log', 'up', '-d', '--no-build', '--no-deps', '--wait',
                             '--wait-timeout', '20', name)

    def arm_notification(self, key, check):
        self.compose_command(check, 'fault-control.log', 'exec', '-T', 'gateway', 'python', '-c',
                             'from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2])',
                             str(CONTROL), key)

    def notification_marker(self, check):
        output = self.compose_command(check, 'fault-control.log', 'exec', '-T', 'gateway', 'python', '-c',
                                      'from pathlib import Path; import sys; p=Path(sys.argv[1]); '
                                      'print(p.read_text() if p.exists() else "null")',
                                      str(CONTROL.with_suffix('.reached.json')))
        return json.loads(output)

    def disarm_notification(self):
        docker_output('compose', '-p', self.project, '-f', str(self.compose), 'exec', '-T', 'gateway',
                      'python', '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).unlink(missing_ok=True)',
                      str(CONTROL))

    def close(self):
        if not self.docker:
            return
        if docker_output('info', '--format', '{{.ID}}') != self.engine_id:
            raise RuntimeError('Docker engine changed before cleanup')
        if self.paused:
            try:
                self.resume_apis(self.paused)
            except Exception:
                pass  # Down and the absence check below determine cleanup success.
        deadline = time.monotonic() + 45

        def check():
            if time.monotonic() >= deadline:
                raise TimeoutError('Docker cleanup timed out')

        try:
            self.compose_command(check, 'containers.log', 'logs', '--no-color')
        except Exception:
            pass
        self.compose_command(check, 'cleanup.log', 'down', '--volumes', '--remove-orphans', '--timeout', '5')
        if docker_output('image', 'ls', '-q', '--filter', f'reference={self.image}'):
            self.command([self.cli, 'image', 'rm', self.image], check, 'cleanup.log')
        verify_docker_absent(self.project, self.engine_id)
