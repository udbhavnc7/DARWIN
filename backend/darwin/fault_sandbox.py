import hashlib
import json
import os
from pathlib import Path
import shutil

import httpx
import psycopg
import psutil

from darwin.architecture import ROOT
from darwin.experiments import write_json
from darwin.measured_sandbox import MeasuredSandbox
from darwin.sandbox import port, stop_process


class FaultSandbox(MeasuredSandbox):
    def __init__(self, request, candidate, folder, source):
        super().__init__(request, candidate, folder, source)
        self.services = {}
        self.control = folder / 'pause-notification'
        self.env.update(DARWIN_ISOLATED_FAULT_TEST='1', DARWIN_FAULT_CONTROL_FILE=str(self.control))

    def proxy_call(self, method, path, body=None):
        with httpx.Client(base_url=self.tox_url, timeout=3, trust_env=False) as client:
            response = client.request(method, path, json=body)
            response.raise_for_status()
            return response.json() if response.content else None

    def create_proxy(self, name, upstream):
        spec = self.proxy_call('POST', '/proxies', {
            'name': name, 'listen': '127.0.0.1:0', 'upstream': upstream, 'enabled': True})
        proxy_port = int(spec['listen'].rsplit(':', 1)[1])
        self.socket_ports.append(proxy_port)
        self.ownership()
        return proxy_port

    def prepare_database(self, check):
        super().prepare_database(check)
        self.direct_dsn = self.env['DARWIN_DATABASE_URL']
        executable = os.environ.get('DARWIN_TOXIPROXY') or shutil.which('toxiproxy-server') or str(ROOT / '.runtime/tools/toxiproxy-server.exe')
        if not Path(executable).is_file():
            raise RuntimeError('Install Toxiproxy with scripts/setup_toxiproxy.ps1')
        api_port = port()
        self.socket_ports.append(api_port)
        self.tox_url = f'http://127.0.0.1:{api_port}'
        log = (self.folder / 'toxiproxy.log').open('ab')
        self.logs.append(log)
        # Fault tooling runs outside the capped application group.
        process = super().launch([executable, '-host', '127.0.0.1', '-port', str(api_port)],
                                 log, self.env, application=False)
        self.processes.append(process)
        self.ownership()
        self.ready(self.tox_url + '/version', check)
        dsn = psycopg.conninfo.conninfo_to_dict(self.direct_dsn)
        proxy_port = self.create_proxy('database', f"127.0.0.1:{dsn['port']}")
        self.env['DARWIN_DATABASE_URL'] = psycopg.conninfo.make_conninfo(self.direct_dsn, port=proxy_port)
        write_json(self.folder / 'fault-tool.json', {
            'sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
            'version': self.proxy_call('GET', '/version'), 'application_resource_group': False})

    def spawn(self, args, env, name):
        args = list(args)
        if name == 'payment' and self.request.fault_fixture == 'unsafe_retry':
            args = ['darwin.unsafe_payment:app' if arg == 'darwin.shop.services:payment' else arg for arg in args]
        process = super().spawn(args, env, name)
        self.services[name] = (process, args, env)
        if name == 'payment':
            upstream = self.env['DARWIN_PAYMENT_URL'].removeprefix('http://')
            proxy_port = self.create_proxy('payment', upstream)
            self.env['DARWIN_PAYMENT_URL'] = f'http://127.0.0.1:{proxy_port}'
        return process

    def stop_service(self, name):
        process, args, env = self.services[name]
        stop_process(process)
        self.processes.remove(process)
        self.ownership()

    def restart_service(self, name, check):
        _, args, env = self.services[name]
        self.spawn(args, env, name)
        service_port = args[args.index('--port') + 1]
        self.ready(f'http://127.0.0.1:{service_port}/ready', check)

    def pause_apis(self):
        paused = []
        try:
            for name, (process, _, _) in self.services.items():
                if name.startswith('api-'):
                    parent = psutil.Process(process.pid)
                    for child in [parent, *parent.children(recursive=True)]:
                        child.suspend()
                        paused.append(child)
        except BaseException:
            self.resume_apis(paused)
            raise
        return paused

    @staticmethod
    def resume_apis(paused):
        for process in reversed(paused):
            try:
                process.resume()
            except psutil.NoSuchProcess:
                pass

    def exercise(self, base, check):
        from darwin.fault_suite import FaultSuite
        result = super().exercise(base, check)
        return FaultSuite(self, base, check).run(result)

    def close(self):
        self.control.unlink(missing_ok=True)
        super().close()
