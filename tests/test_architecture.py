import itertools
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from darwin.architecture import canonical, genome_hash, render_compose, topology
from darwin.contracts import Genome
from darwin.main import app
from darwin.shop import services


def test_equivalent_genomes_have_same_hash():
    assert genome_hash(Genome()) == genome_hash(Genome.model_validate_json(canonical(Genome())))
    assert genome_hash(Genome()) != genome_hash(Genome(app_replicas=2))


@pytest.mark.parametrize('payload', [{'app_replicas': True}, {'app_replicas': 4}, {'catalog_cache_ttl_s': 11},
                                   {'notification_mode': 'magic'}, {'retry_policy': 'unsafe_demo'}, {'unknown': 1}])
def test_invalid_controls_rejected(payload):
    with pytest.raises(ValidationError):
        Genome(**payload)


@pytest.mark.parametrize('replicas,ttl,mode,policy', list(itertools.product([1, 2, 3], [0, 10, 30], ['sync', 'queued'], ['none', 'idempotent_only'])))
def test_all_36_supported_genomes_map_consistently(replicas, ttl, mode, policy):
    genome = Genome(app_replicas=replicas, catalog_cache_ttl_s=ttl, notification_mode=mode, retry_policy=policy)
    config = render_compose(genome)
    services = config['services']
    apis = {name for name in services if name.startswith('api-')}
    assert len(apis) == replicas
    assert ('redis' in services) == bool(ttl)
    assert ('worker' in services) == (mode == 'queued')
    assert set(services['gateway']['depends_on']) == apis
    active = [s for name, s in services.items() if name != 'seed']
    assert sum(s['cpus'] for s in active) <= 4
    assert sum(int(s['mem_limit'][:-1]) for s in active) <= 4096
    assert {node['id'] for node in topology(genome)['nodes']} == set(services) - {'seed'}
    for name in apis:
        assert json.loads(services[name]['environment']['DARWIN_GENOME_JSON']) == genome.model_dump()
    for service in services.values():
        assert set(service.get('depends_on', {})) <= set(services)


@pytest.mark.parametrize('policy,expected', [('none', 1), ('idempotent_only', 2)])
def test_retry_policy_changes_actual_outbound_attempts(monkeypatch, policy, expected):
    monkeypatch.setenv('DARWIN_GENOME_JSON', json.dumps({'retry_policy': policy}))
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(503 if len(requests) == 1 else 200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"captured"}')
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}/capture'
        if policy == 'none':
            with pytest.raises(HTTPException):
                services.post_safe(url, {'request_key': 'same-key'}, time.monotonic() + 2)
        else:
            assert services.post_safe(url, {'request_key': 'same-key'}, time.monotonic() + 2).status_code == 200
            assert requests[0] == requests[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert len(requests) == expected


def test_preview_endpoint_does_not_claim_deployment():
    response = TestClient(app).post('/api/genomes/preview', json={'app_replicas': 3, 'notification_mode': 'queued'})
    assert response.status_code == 200
    assert response.json()['topology']['deployment_verified'] is False


def test_export_compose_is_portable_and_matches_requested_topology():
    genome = {'app_replicas': 2, 'catalog_cache_ttl_s': 30, 'notification_mode': 'queued'}
    client = TestClient(app)
    preview = client.post('/api/genomes/preview', json=genome).json()
    response = client.post('/api/genomes/compose', json=genome)
    assert response.status_code == 200
    assert preview['genome_hash'][:12] in response.headers['content-disposition']
    services = yaml.safe_load(response.text)['services']
    assert set(services) == {'seed', *(node['id'] for node in preview['topology']['nodes'])}
    assert {service['build'] for service in services.values() if 'build' in service} == {'.'}
    assert client.post('/api/genomes/compose', json={'app_replicas': 4}).status_code == 422
