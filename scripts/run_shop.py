"""Run the real PostgreSQL shop locally without Docker. Ctrl+C stops owned processes."""
import os
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

import httpx
import psycopg
from psycopg import sql
import redis

from darwin.contracts import Genome
from darwin.architecture import runtime_environment

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime' / 'shop'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def run(args, **kwargs):
    return subprocess.run(args, check=True, creationflags=FLAGS, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--genome', type=Path)
    args = parser.parse_args()
    genome = Genome.model_validate_json(args.genome.read_text()) if args.genome else Genome()
    if genome.catalog_cache_ttl_s and not shutil.which('redis-server'):
        raise SystemExit('redis-server is required for a cached local candidate')
    for name in ('initdb', 'pg_ctl'):
        if not shutil.which(name):
            raise SystemExit(f'{name} is required on PATH. Alternatively use Docker Compose.')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    data = RUNTIME / 'pgdata'
    if not (data / 'PG_VERSION').exists():
        password_file = RUNTIME / 'demo-password.txt'
        password_file.write_text('darwin_demo', encoding='utf-8')
        try:
            run(['initdb', '-D', str(data), '-U', 'darwin', '--pwfile', str(password_file),
                 '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'])
        finally:
            password_file.unlink(missing_ok=True)
    status = subprocess.run(['pg_ctl', '-D', str(data), 'status'], capture_output=True, creationflags=FLAGS)
    if status.returncode == 0:
        raise SystemExit('This local shop cluster is already running. Stop its existing runner first.')
    run(['pg_ctl', '-D', str(data), '-l', str(RUNTIME / 'postgres.log'),
         '-o', '-h 127.0.0.1 -p 55432', '-w', 'start'])
    children, logs = [], []
    try:
        with psycopg.connect('postgresql://darwin:darwin_demo@127.0.0.1:55432/postgres', autocommit=True) as conn:
            for name in ('darwin_shop', 'darwin_shop_test'):
                if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
                    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        env = os.environ.copy()
        env['DARWIN_DATABASE_URL'] = 'postgresql://darwin:darwin_demo@127.0.0.1:55432/darwin_shop'
        env.update(runtime_environment(genome))
        env['DARWIN_REDIS_URL'] = 'redis://127.0.0.1:6380/0'
        env['DARWIN_SHOP_API_URLS'] = ','.join(f'http://127.0.0.1:{8013+i}' for i in range(genome.app_replicas))
        env['DARWIN_INVENTORY_URL'] = 'http://127.0.0.1:8011'
        env['DARWIN_PAYMENT_URL'] = 'http://127.0.0.1:8012'
        if genome.catalog_cache_ttl_s:
            log = (RUNTIME / 'redis.log').open('a', encoding='utf-8')
            logs.append(log)
            child = subprocess.Popen([shutil.which('redis-server'), '--bind', '127.0.0.1', '--port', '6380',
                                      '--save', '', '--appendonly', 'no'], stdout=log, stderr=log, creationflags=FLAGS, cwd=RUNTIME)
            children.append(child)
            cache = redis.Redis.from_url(env['DARWIN_REDIS_URL'], socket_timeout=0.3)
            for _ in range(40):
                if child.poll() is not None:
                    raise RuntimeError('Redis exited; inspect .runtime/shop/redis.log')
                try:
                    if cache.ping():
                        break
                except redis.RedisError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError('Redis startup timed out')
        run([sys.executable, '-m', 'darwin.shop.cli', 'init'], env=env, cwd=ROOT)
        service_list = [('inventory', 'darwin.shop.services:inventory', 8011),
                        ('payment', 'darwin.shop.services:payment', 8012)]
        service_list.extend((f'api-{i+1}', 'darwin.shop.services:api', 8013+i) for i in range(genome.app_replicas))
        if genome.notification_mode == 'queued':
            service_list.append(('worker', 'darwin.shop.worker:app', 8016))
        service_list.append(('gateway', 'darwin.shop.gateway:app', 8010))
        for name, target, port in service_list:
            log = (RUNTIME / f'{name}.log').open('a', encoding='utf-8')
            logs.append(log)
            child = subprocess.Popen([sys.executable, '-m', 'uvicorn', target, '--host', '127.0.0.1', '--port', str(port)],
                                     env={**env, 'DARWIN_INSTANCE_ID': name}, cwd=ROOT, stdout=log, stderr=log, creationflags=FLAGS)
            children.append(child)
            for _ in range(40):
                if child.poll() is not None:
                    raise RuntimeError(f'{name} failed; inspect {log.name}')
                try:
                    if httpx.get(f'http://127.0.0.1:{port}/' + ('health' if name == 'gateway' else 'ready'), timeout=1, trust_env=False).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError(f'{name} did not become ready')
        print('DARWIN shop ready: http://127.0.0.1:8010/shop/catalog', flush=True)
        print('Ctrl+C stops this shop. Create .runtime/shop/STOP to stop a background runner.', flush=True)
        stop = RUNTIME / 'STOP'
        stop.unlink(missing_ok=True)
        while not stop.exists():
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A shop service exited; see .runtime/shop logs')
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for log in logs:
            log.close()
        run(['pg_ctl', '-D', str(data), '-m', 'fast', '-w', 'stop'])


if __name__ == '__main__':
    main()
