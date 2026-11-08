import json
from importlib.metadata import version
import os
import secrets
import shutil
import sys
from uuid import UUID

import psycopg

from darwin.experiments import write_json
from darwin.performance import metrics, WINDOW_S, WARMUP_S
from darwin.sandbox import Sandbox, port


class MeasuredSandbox(Sandbox):
    def __init__(self, request, candidate, folder, source):
        super().__init__(request, candidate, folder, source)
        self.job = None
        self.data = folder / 'private-pgdata'

    def launch(self, args, log, env, *, application):
        if application:
            return self.job.launch(args, cwd=self.source, env=env, stdout=log, stderr=log)
        return super().launch(args, log, env, application=False)

    def prepare_database(self, check):
        if os.name != 'nt':
            raise RuntimeError('Measured native execution requires Windows Job Objects')
        from darwin.windows_job import ApplicationJob
        self.job = ApplicationJob('darwin-' + self.folder.name, self.request.budget)
        db_port = port()
        self.socket_ports.append(db_port)
        self.ownership()
        password = secrets.token_hex(16)
        pwfile = self.folder / '.init-password'
        pwfile.write_text(password, encoding='ascii')
        try:
            self.command(['initdb', '-D', str(self.data), '-U', 'darwin', '--pwfile', str(pwfile),
                          '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'], check, 'initdb.log')
        finally:
            pwfile.unlink(missing_ok=True)
        self.command(['pg_ctl', '-D', str(self.data), '-l', str(self.folder / 'postgres.log'), '-o',
                      f'-h 127.0.0.1 -p {db_port}', '-w', 'start'], check, 'postgres-start.log', application=True)
        # Confirm pg_ctl's long-lived server inherited the limits.
        import win32api
        import win32job
        pid = int((self.data / 'postmaster.pid').read_text().splitlines()[0])
        handle = win32api.OpenProcess(0x1000, False, pid)
        try:
            if not win32job.IsProcessInJob(handle, self.job.handle):
                raise RuntimeError('PostgreSQL is outside the application resource group')
        finally:
            handle.Close()
        self.env['DARWIN_DATABASE_URL'] = psycopg.conninfo.make_conninfo(
            host='127.0.0.1', port=db_port, dbname='postgres', user='darwin', password=password)
        environment = json.loads((self.folder / 'environment.json').read_text())
        environment.update(resource_limits_enforced=True, cpu_affinity=self.job.cpus,
                           memory_limit_mib=self.request.budget.sandbox_memory_mb,
                           load_generator='locust ' + version('locust'), protocol='windows-locust-v1',
                           postgres_version=self.command(['postgres', '--version'], check, 'postgres-version.log').strip(),
                           warmup_s=WARMUP_S, measurement_s=WINDOW_S)
        write_json(self.folder / 'environment.json', environment)

    def exercise(self, base, check):
        # Fixed supply supports even the burst profile without selling out.
        with psycopg.connect(self.env['DARWIN_DATABASE_URL'], connect_timeout=2) as conn:
            conn.execute('UPDATE products SET initial_stock=1000, available=1000')
        self.command([sys.executable, '-m', 'darwin.locust_load', base.removesuffix('/shop'),
                      self.request.workload_profile, self.job.name, str(self.folder), str(self.request.seed)],
                     check, 'locust.log')
        samples = json.loads((self.folder / 'samples.json').read_text())
        resources = json.loads((self.folder / 'resources.json').read_text())
        before, after = resources['application_start'], resources['application_end']
        return {'metrics': metrics(samples, after['cpu_seconds'] - before['cpu_seconds'], after['memory_peak_mb']),
                'resource_limits_enforced': True, 'measurement_kind': 'measured', 'gate': 'not_checked'}

    def close(self):
        try:
            super().close()
        finally:
            try:
                if (self.data / 'postmaster.pid').exists():
                    # The private database can finish writing before the job is released.
                    import subprocess
                    subprocess.run(['pg_ctl', '-D', str(self.data), '-m', 'immediate', '-w', 'stop'],
                                   capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            finally:
                if self.job:
                    self.job.close()
                if self.data.exists():
                    expected = self.folder.resolve() / 'private-pgdata'
                    if str(UUID(self.folder.name)) != self.folder.name or self.data.resolve() != expected:
                        raise RuntimeError('Unexpected private database path')
                    shutil.rmtree(self.data)
