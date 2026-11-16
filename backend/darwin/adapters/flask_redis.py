"""Reviewed adapter for the docker/awesome-compose Flask + Redis sample.

Detection is by source markers under flask-redis/, not by repository name.
"""
from __future__ import annotations

from darwin.adapters.http_compose import HttpComposeAdapter
from darwin.backend_manifest import BackendManifest, CandidateDimension, HealthSpec, WorkloadSpec

FLASK_REDIS_ADAPTER_ID = 'flask-redis-compose-v1'
FLASK_REDIS_ADAPTER_VERSION = '1.0.0'

MANIFEST = BackendManifest(
    adapter_id=FLASK_REDIS_ADAPTER_ID,
    adapter_version=FLASK_REDIS_ADAPTER_VERSION,
    runtime='gunicorn-flask',
    app_module='app:app',
    source_subdir='flask-redis',
    source_files=('flask-redis/app.py', 'flask-redis/requirements.txt'),
    detect_markers=(
        'from flask import Flask',
        "Redis(host='redis'",
        'This webpage has been viewed',
    ),
    health=HealthSpec(path='/', contains='This webpage has been viewed', status=200),
    workload=WorkloadSpec(path='/', method='GET', warmup_s=2, window_s=6, rate=6),
    needs_redis=True,
    body_pattern='This webpage has been viewed',
    candidates=(
        CandidateDimension(
            'baseline-1x1', 'Original: 1 replica × 1 worker',
            'Single Flask process behind nginx, shared Redis counter.',
            replicas=1, workers=1,
            challenges=('faster', 'spike', 'resources', 'recover'),
        ),
        CandidateDimension(
            'replicas-2x1', 'Two stateless replicas × 1 worker',
            'Second identical app replica behind nginx; Redis remains shared.',
            replicas=2, workers=1,
            challenges=('faster', 'spike', 'recover'),
        ),
        CandidateDimension(
            'workers-1x2', 'One replica × 2 gunicorn workers',
            'More in-process workers on a single replica; Redis unchanged.',
            replicas=1, workers=2,
            challenges=('faster', 'spike', 'resources'),
        ),
    ),
    unsupported=(
        'Repository docker-compose.yaml / Dockerfile are not executed.',
        'Flask debug server is never used; gunicorn is DARWIN-owned.',
        'No framework conversion, cache TTL invention, or queue migration.',
        'Database delay faults are unsupported because this sample has no SQL database.',
    ),
    correctness_rules=(
        'GET / returns HTTP 200 and the reviewed Flask counter sentence.',
        'The viewed-count integer strictly increases across gateway requests (shared Redis).',
        'After a web replica restart, the service becomes healthy again on loopback.',
    ),
)


class FlaskRedisAdapter(HttpComposeAdapter):
    def __init__(self):
        super().__init__(MANIFEST)
