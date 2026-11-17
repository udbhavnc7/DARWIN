"""Shared integration fixtures for a plain local checkout.

The PostgreSQL/Redis suites used to skip unless ``DARWIN_TEST_DATABASE_URL``
was exported by hand. A bare checkout should exercise them when the demo
cluster is running (``scripts/run_shop.py``) or when Docker is available, so
these fixtures discover, prepare, and clean up disposable resources instead.

Nothing here touches a database whose name does not end in ``_test``.
"""
import os
import shutil
import socket
import subprocess
import time
import uuid

import psycopg
import pytest
import redis

DEMO_DSN = 'postgresql://darwin:darwin_demo@127.0.0.1:55432/darwin_shop'
REDIS_PORT = 16380
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
POSTGRES_IMAGE = 'postgres:18'
REDIS_IMAGE = 'redis:7-alpine'


def _info(dsn):
    return psycopg.conninfo.conninfo_to_dict(dsn)


def _test_dsn(dsn):
    """Return the same connection settings pointed at the ``*_test`` database."""
    info = _info(dsn)
    name = info.get('dbname') or 'darwin_shop'
    if not name.endswith('_test'):
        info['dbname'] = f'{name}_test'
    return psycopg.conninfo.make_conninfo(**info)


def _connect(dsn, timeout=1):
    return psycopg.connect(dsn, connect_timeout=timeout, autocommit=True)


def _postgres_reachable(dsn):
    try:
        with _connect(dsn):
            return True
    except psycopg.Error:
        return False


def _create_database(dsn):
    """Create the target ``*_test`` database if missing; report whether we made it."""
    info = _info(dsn)
    name = info.pop('dbname')
    admin = psycopg.conninfo.make_conninfo(**info, dbname='postgres')
    with _connect(admin) as conn:
        found = conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone()
        if found:
            return False
        conn.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
        return True


def _drop_database(dsn):
    info = _info(dsn)
    name = info.pop('dbname')
    if not name.endswith('_test'):
        return
    admin = psycopg.conninfo.make_conninfo(**info, dbname='postgres')
    try:
        with _connect(admin) as conn:
            conn.execute(psycopg.sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)')
                         .format(psycopg.sql.Identifier(name)))
    except psycopg.Error:
        # A teardown failure must not hide the test result; the database is disposable.
        pass


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _docker_ready():
    executable = shutil.which('docker')
    if not executable:
        return False
    try:
        return subprocess.run([executable, 'info'], capture_output=True, timeout=20,
                              creationflags=FLAGS).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _wait_until(dsn, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _postgres_reachable(dsn):
            return True
        time.sleep(0.5)
    return False


def _docker_run(arguments):
    subprocess.run([shutil.which('docker'), 'run', '-d', '--rm', *arguments],
                   check=True, capture_output=True, text=True, timeout=180, creationflags=FLAGS)


def _docker_remove(name):
    subprocess.run([shutil.which('docker'), 'rm', '-f', name], capture_output=True,
                   timeout=60, creationflags=FLAGS)


def _local_test_database():
    """Use the running demo cluster and prepare its ``*_test`` database."""
    candidates = [os.environ.get('DARWIN_DATABASE_URL'), DEMO_DSN]
    for candidate in candidates:
        if not candidate or not _postgres_reachable(candidate):
            continue
        dsn = _test_dsn(candidate)
        if not _postgres_reachable(dsn):
            try:
                _create_database(dsn)
            except psycopg.Error as exc:
                pytest.skip(f'The local PostgreSQL server cannot create a test database: {exc}')
        return dsn
    return None


@pytest.fixture(scope='session')
def test_database_url():
    """A dedicated, disposable PostgreSQL database whose name ends in ``_test``."""
    configured = os.environ.get('DARWIN_TEST_DATABASE_URL')
    if configured:
        if not (_info(configured).get('dbname') or '').endswith('_test'):
            pytest.fail('DARWIN_TEST_DATABASE_URL must name a database ending in _test')
        yield configured
        return

    local = _local_test_database()
    if local:
        # The demo runner owns this cluster and already expects darwin_shop_test to exist.
        yield local
        return

    if _docker_ready():
        name = f'darwin-test-postgres-{uuid.uuid4().hex[:8]}'
        port = _free_port()
        dsn = f'postgresql://darwin:darwin_demo@127.0.0.1:{port}/darwin_shop_test'
        _docker_run(['--name', name, '-e', 'POSTGRES_USER=darwin', '-e', 'POSTGRES_PASSWORD=darwin_demo',
                     '-e', 'POSTGRES_DB=darwin_shop_test', '-p', f'127.0.0.1:{port}:5432', POSTGRES_IMAGE])
        try:
            if not _wait_until(dsn):
                pytest.fail('The disposable PostgreSQL container did not become ready')
            yield dsn
        finally:
            _docker_remove(name)
        return

    pytest.skip('No local PostgreSQL demo cluster is running and Docker is unavailable; '
                'start scripts/run_shop.py, run docker compose, or set DARWIN_TEST_DATABASE_URL')


def _redis_answers(port):
    client = redis.Redis(host='127.0.0.1', port=port, socket_timeout=0.5)
    try:
        return client.ping()
    except redis.RedisError:
        return False
    finally:
        client.close()


def _wait_for_redis(seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _redis_answers(REDIS_PORT):
            return True
        time.sleep(0.2)
    return False


@pytest.fixture(scope='session')
def redis_server():
    """A Redis listener on 127.0.0.1:16380, reused, started natively, or containerized."""
    if _redis_answers(REDIS_PORT):
        yield REDIS_PORT
        return

    executable = shutil.which('redis-server')
    if executable:
        process = subprocess.Popen([executable, '--bind', '127.0.0.1', '--port', str(REDIS_PORT),
                                    '--save', '', '--appendonly', 'no'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=FLAGS)
        try:
            if not _wait_for_redis():
                pytest.fail('The native Redis server did not start on 127.0.0.1:16380')
            yield REDIS_PORT
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        return

    if _docker_ready():
        name = f'darwin-test-redis-{uuid.uuid4().hex[:8]}'
        _docker_run(['--name', name, '-p', f'127.0.0.1:{REDIS_PORT}:6379', REDIS_IMAGE])
        try:
            if not _wait_for_redis():
                pytest.fail('The disposable Redis container did not become ready')
            yield REDIS_PORT
        finally:
            _docker_remove(name)
        return

    pytest.skip('redis-server is not on PATH and Docker is unavailable; '
                'install Redis or start Docker')
