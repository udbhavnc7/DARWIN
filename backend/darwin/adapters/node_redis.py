"""Reviewed adapter for the official Docker nginx + Node.js + Redis counter.

Detection is by source markers under web/, not by repository name. This is a
different repository from the Flask sample and it reuses HttpComposeAdapter
unchanged: only the typed manifest differs (runtime, port, counter pattern).
"""
from __future__ import annotations

from darwin.adapters.http_compose import HttpComposeAdapter
from darwin.backend_manifest import BackendManifest, CandidateDimension, HealthSpec, WorkloadSpec

NODE_REDIS_ADAPTER_ID = 'node-redis-compose-v1'
NODE_REDIS_ADAPTER_VERSION = '1.0.0'

MANIFEST = BackendManifest(
    adapter_id=NODE_REDIS_ADAPTER_ID,
    adapter_version=NODE_REDIS_ADAPTER_VERSION,
    runtime='node-express',
    app_module='server.js',
    source_subdir='web',
    source_files=('web/server.js', 'web/package.json', 'web/package-lock.json'),
    detect_markers=(
        "require('express')",
        'numVisits',
        'app.listen(5000',
    ),
    health=HealthSpec(path='/', contains='Number of visits is:', status=200),
    workload=WorkloadSpec(path='/', method='GET', warmup_s=2, window_s=6, rate=6),
    needs_redis=True,
    body_pattern='Number of visits is:',
    app_port=5000,
    counter_pattern=r'Number of visits is:\s*(\d+)',
    candidates=(
        CandidateDimension(
            'baseline-1x1', 'Original: 1 replica',
            'Single Node.js process behind nginx, shared Redis visit counter.',
            replicas=1, workers=1,
            challenges=('faster', 'spike', 'resources', 'recover'),
        ),
        CandidateDimension(
            'replicas-2x1', 'Two stateless replicas',
            'Second identical Node.js process behind nginx; Redis remains shared.',
            replicas=2, workers=1,
            challenges=('faster', 'spike', 'recover'),
        ),
    ),
    unsupported=(
        'Repository compose.yml, web/Dockerfile and nginx/ are not executed.',
        'The repository publishes Redis on a host port; DARWIN keeps Redis internal.',
        'No Express cluster mode is invented: this application is single-process.',
        'No framework conversion, cache TTL invention, or database addition.',
    ),
    correctness_rules=(
        'GET / returns HTTP 200 and the reviewed visit-counter sentence through the gateway.',
        'The visit counter strictly increases across gateway probes (shared Redis).',
        'After a web replica restart, the service becomes healthy again on loopback.',
    ),
)


class NodeRedisAdapter(HttpComposeAdapter):
    def __init__(self):
        super().__init__(MANIFEST)
