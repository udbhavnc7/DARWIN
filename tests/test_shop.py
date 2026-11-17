"""PostgreSQL integration tests. Use only an explicitly named *_test database."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import time
import json
from contextlib import contextmanager
import redis

import httpx
import psycopg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from darwin.shop import services
from darwin.shop.db import connection, initialize, invariant_report, snapshot

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def shop_services(test_database_url):
    dsn = test_database_url
    parsed = psycopg.conninfo.conninfo_to_dict(dsn)
    if not parsed.get('dbname', '').endswith('_test'):
        pytest.fail('Refusing to reset a database without the _test suffix')
    old = {name: os.environ.get(name) for name in ('DARWIN_DATABASE_URL', 'DARWIN_INVENTORY_URL', 'DARWIN_PAYMENT_URL', 'DARWIN_SHOP_API_URL')}
    os.environ.update(DARWIN_DATABASE_URL=dsn, DARWIN_INVENTORY_URL='http://127.0.0.1:18011',
                      DARWIN_PAYMENT_URL='http://127.0.0.1:18012', DARWIN_SHOP_API_URL='http://127.0.0.1:18013')
    children, logs = [], []
    try:
        initialize(reset=True)
        Path('.runtime/tests').mkdir(parents=True, exist_ok=True)
        for role, target, port in [('inventory', 'services:inventory', 18011), ('payment', 'services:payment', 18012),
                                   ('api', 'services:api', 18013), ('gateway', 'gateway:app', 18010)]:
            log = open(f'.runtime/tests/{role}.log', 'w')
            logs.append(log)
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', f'darwin.shop.{target}', '--host', '127.0.0.1', '--port', str(port)],
                                       stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            children.append(process)
            for _ in range(40):
                if process.poll() is not None:
                    pytest.fail(f'{role} exited: inspect .runtime/tests/{role}.log')
                try:
                    if httpx.get(f'http://127.0.0.1:{port}/health', trust_env=False).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                pytest.fail(f'{role} startup timed out')
        yield 'http://127.0.0.1:18010/shop'
    finally:
        for process in reversed(children):
            process.terminate()
            process.wait(timeout=10)
        for log in logs:
            log.close()
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def shop(shop_services):
    initialize(reset=True)
    yield shop_services


def purchase(base, key, quantity=1, sku='darwin-notebook'):
    return httpx.post(base + '/checkout', json={'sku': sku, 'quantity': quantity},
                      headers={'Idempotency-Key': key}, timeout=10, trust_env=False)


def test_fresh_catalog_checkout_ledgers_and_reset(shop):
    original = httpx.get(shop + '/catalog', trust_env=False).json()
    assert len(original) == 3
    response = purchase(shop, 'happy', quantity=2)
    assert response.status_code == 200, response.text
    assert response.json()['amount_cents'] == 2598
    data = snapshot()
    assert len(data['orders']) == len(data['captures']) == len(data['reservations']) == len(data['outbox']) == len(data['deliveries']) == 1
    assert data['outbox'][0]['status'] == 'completed'
    assert invariant_report()['violations'] == []
    initialize(reset=True)
    assert httpx.get(shop + '/catalog', trust_env=False).json() == original
    assert snapshot()['orders'] == []


def test_replay_is_stable_and_changed_payload_conflicts(shop):
    first = purchase(shop, 'repeat')
    before = snapshot()
    assert purchase(shop, 'repeat').json() == first.json()
    assert snapshot() == before
    assert purchase(shop, 'repeat', quantity=2).status_code == 409
    assert snapshot() == before


def test_ledger_shows_one_effect_after_repeat_and_reset_clears_it(shop):
    purchase(shop, 'ledger-proof', quantity=2)
    purchase(shop, 'ledger-proof', quantity=2)
    ledger = httpx.get(shop + '/ledger', params={'request_key': 'ledger-proof'}, trust_env=False).json()
    assert ledger['orders'] == ledger['captures'] == ledger['payment_effects'] == 1
    assert ledger['for_request'] == {'orders': 1, 'captures': 1, 'payment_effects': 1}
    assert httpx.post(shop + '/reset', trust_env=False).json() == {'status': 'reset'}
    cleared = httpx.get(shop + '/ledger', trust_env=False).json()
    assert cleared['orders'] == cleared['captures'] == cleared['payment_effects'] == 0
    catalog = httpx.get(shop + '/catalog', trust_env=False).json()
    assert next(row for row in catalog if row['sku'] == 'darwin-notebook')['available'] == 20


def test_concurrent_duplicate_requests_have_one_effect(shop):
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: purchase(shop, 'concurrent'), range(12)))
    assert all(r.status_code == 200 for r in responses), [(r.status_code, r.text) for r in responses]
    assert len({r.json()['order_id'] for r in responses}) == 1
    data = snapshot()
    assert len(data['orders']) == len(data['captures']) == len(data['deliveries']) == 1
    assert invariant_report()['violations'] == []


def test_concurrent_checkout_cannot_oversell(shop):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda i: purchase(shop, f'stock-{i}', sku='darwin-shirt'), range(16)))
    assert sum(r.status_code == 200 for r in responses) == 10, [r.text for r in responses]
    assert sum(r.status_code == 409 for r in responses) == 6
    data = snapshot()
    assert len(data['captures']) == 10
    assert next(p for p in data['products'] if p['sku'] == 'darwin-shirt')['available'] == 0
    assert invariant_report()['violations'] == []


def test_validation_and_unknown_sku_do_not_write(shop):
    assert purchase(shop, 'bad-quantity', quantity=0).status_code == 422
    assert purchase(shop, 'bad-sku', sku='absent').status_code == 404
    assert httpx.post(shop + '/checkout', json={'sku': 'darwin-mug', 'quantity': 1}, trust_env=False).status_code == 422
    assert snapshot()['orders'] == []


def test_ambiguous_capture_resumes_without_double_charge(shop, monkeypatch):
    original = services.post_safe
    def lose_payment_response(url, payload, deadline):
        response = original(url, payload, deadline)
        if url.endswith('/capture'):
            assert response.status_code == 200
            raise HTTPException(503, 'Simulated response loss after capture committed')
        return response
    monkeypatch.setattr(services, 'post_safe', lose_payment_response)
    client = TestClient(services.api)
    response = client.post('/checkout', json={'sku': 'darwin-mug', 'quantity': 1}, headers={'Idempotency-Key': 'lost-response'})
    assert response.status_code == 503
    assert snapshot()['orders'][0]['status'] == 'pending'
    assert len(snapshot()['captures']) == 1
    # Retry against the separate live API process, using the same durable key.
    assert purchase(shop, 'lost-response', sku='darwin-mug').status_code == 200
    assert len(snapshot()['captures']) == len(snapshot()['reservations']) == 1
    assert invariant_report()['violations'] == []


def test_payment_payload_conflict_preserves_capture(shop):
    assert purchase(shop, 'payment-key').status_code == 200
    before = snapshot()['captures']
    response = httpx.post('http://127.0.0.1:18012/capture', json={'request_key': 'payment-key',
                          'order_id': str(before[0]['order_id']), 'amount_cents': 1}, trust_env=False)
    assert response.status_code == 409
    assert snapshot()['captures'] == before


def test_delivery_before_ack_can_be_replayed(shop):
    assert purchase(shop, 'notify').status_code == 200
    before = snapshot()['deliveries']
    with connection() as conn:
        conn.execute("UPDATE outbox SET status='pending' WHERE job_key='notify'")
    services.deliver_notification('notify')
    assert snapshot()['deliveries'] == before
    assert snapshot()['outbox'][0]['status'] == 'completed'
    assert invariant_report()['violations'] == []


@contextmanager
def running_process(command, ready_url, env=None):
    process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        for _ in range(50):
            if process.poll() is not None:
                pytest.fail('Candidate test process exited')
            try:
                if httpx.get(ready_url, timeout=0.5, trust_env=False).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail('Candidate process startup timed out')
        yield process
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def live_redis(redis_server):
    cache = redis.Redis(host='127.0.0.1', port=redis_server, decode_responses=True, socket_timeout=0.5)
    try:
        if not cache.ping():
            pytest.fail('Test Redis did not answer on 127.0.0.1:16380')
        # A reused local server may still hold the previous run's catalog entry.
        cache.delete('darwin:catalog:integration')
        yield cache
    finally:
        cache.close()


@pytest.mark.parametrize('ttl', [10, 30])
def test_real_cache_ttl_hit_and_authoritative_stock(shop, live_redis, monkeypatch, ttl):
    monkeypatch.setenv('DARWIN_GENOME_JSON', json.dumps({'catalog_cache_ttl_s': ttl}))
    monkeypatch.setenv('DARWIN_REDIS_URL', 'redis://127.0.0.1:16380/0')
    monkeypatch.setenv('DARWIN_CACHE_NAMESPACE', 'integration')
    client = TestClient(services.api)
    first = client.get('/catalog')
    assert first.headers['x-darwin-cache'] == 'miss'
    key = 'darwin:catalog:integration'
    assert ttl - 1 <= live_redis.ttl(key) <= ttl
    assert all('available' not in product for product in json.loads(live_redis.get(key)))
    assert purchase(shop, 'cache-stock').status_code == 200
    before = live_redis.info('commandstats')['cmdstat_get']['calls']
    hit = client.get('/catalog')
    assert hit.headers['x-darwin-cache'] == 'hit'
    assert live_redis.info('commandstats')['cmdstat_get']['calls'] > before
    assert next(p for p in hit.json() if p['sku'] == 'darwin-notebook')['available'] == 19
    live_redis.pexpire(key, 1)
    time.sleep(0.02)
    assert client.get('/catalog').headers['x-darwin-cache'] == 'miss'


def test_cache_off_does_not_contact_redis(shop, live_redis, monkeypatch):
    monkeypatch.setenv('DARWIN_GENOME_JSON', '{}')
    monkeypatch.setenv('DARWIN_REDIS_URL', 'redis://127.0.0.1:16380/0')
    before = live_redis.info('commandstats').get('cmdstat_get', {}).get('calls', 0)
    response = TestClient(services.api).get('/catalog')
    assert response.headers['x-darwin-cache'] == 'off'
    assert live_redis.info('commandstats').get('cmdstat_get', {}).get('calls', 0) == before


def test_queue_waits_for_worker_and_survives_restart(shop, monkeypatch):
    monkeypatch.setenv('DARWIN_GENOME_JSON', json.dumps({'notification_mode': 'queued'}))
    client = TestClient(services.api)
    command = [sys.executable, '-m', 'uvicorn', 'darwin.shop.worker:app', '--host', '127.0.0.1', '--port', '18016']
    for key in ('queued-before-start', 'queued-after-stop'):
        response = client.post('/checkout', json={'sku': 'darwin-mug', 'quantity': 1}, headers={'Idempotency-Key': key})
        assert response.status_code == 200
        data = snapshot()
        assert next(job for job in data['outbox'] if job['job_key'] == key)['status'] == 'pending'
        assert key not in {row['job_key'] for row in data['deliveries']}
        with running_process(command, 'http://127.0.0.1:18016/ready'):
            assert next(job for job in snapshot()['outbox'] if job['job_key'] == key)['status'] == 'completed'
    assert len(snapshot()['deliveries']) == 2
    assert invariant_report()['violations'] == []


def test_three_live_replicas_receive_gateway_requests(shop):
    from contextlib import ExitStack
    with ExitStack() as stack:
        for i in range(3):
            port = 18030 + i
            env = {**os.environ, 'DARWIN_INSTANCE_ID': f'api-{i+1}'}
            stack.enter_context(running_process([sys.executable, '-m', 'uvicorn', 'darwin.shop.services:api',
                                                 '--host', '127.0.0.1', '--port', str(port)], f'http://127.0.0.1:{port}/ready', env))
        env = {**os.environ, 'DARWIN_SHOP_API_URLS': ','.join(f'http://127.0.0.1:{18030+i}' for i in range(3))}
        stack.enter_context(running_process([sys.executable, '-m', 'uvicorn', 'darwin.shop.gateway:app',
                                             '--host', '127.0.0.1', '--port', '18033'], 'http://127.0.0.1:18033/health', env))
        with httpx.Client(trust_env=False) as client:
            responses = [client.get('http://127.0.0.1:18033/shop/catalog') for _ in range(9)]
        assert all(r.status_code == 200 for r in responses)
        instances = [r.headers['x-darwin-instance'] for r in responses]
        assert {name: instances.count(name) for name in set(instances)} == {'api-1': 3, 'api-2': 3, 'api-3': 3}
