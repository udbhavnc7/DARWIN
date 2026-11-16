"""Second reviewed HTTP adapter used to prove the Compose adapter is not Flask-only.

The fixture lives under tests/fixtures/fastapi_counter and is not a GitHub execution
target. Production execution still requires catalog pin + isolation.
"""
from __future__ import annotations

from darwin.adapters.http_compose import HttpComposeAdapter
from darwin.backend_manifest import BackendManifest, CandidateDimension, HealthSpec, WorkloadSpec

FASTAPI_FIXTURE_ID = 'fastapi-counter-fixture-v1'
FASTAPI_FIXTURE_VERSION = '1.0.0'

MANIFEST = BackendManifest(
    adapter_id=FASTAPI_FIXTURE_ID,
    adapter_version=FASTAPI_FIXTURE_VERSION,
    runtime='uvicorn-fastapi',
    app_module='app:app',
    source_subdir='',
    source_files=('app.py', 'requirements.txt'),
    detect_markers=('from fastapi import FastAPI', '/health', '/work'),
    health=HealthSpec(path='/health', contains='"ok": true', status=200),
    workload=WorkloadSpec(path='/work', method='GET', warmup_s=1, window_s=4, rate=5),
    needs_redis=False,
    body_pattern='"n":',
    candidates=(
        CandidateDimension('baseline-1x1', '1 replica', 'Single FastAPI process.', 1, 1,
                           challenges=('faster', 'spike', 'resources', 'recover')),
        CandidateDimension('replicas-2x1', '2 replicas', 'Two identical processes behind nginx.', 2, 1,
                           challenges=('faster', 'spike', 'recover')),
    ),
    unsupported=('This fixture is not a public GitHub product backend.',),
    correctness_rules=('GET /health returns ok.', 'GET /work returns a deterministic n.'),
    allow_fault_restart=True,
)


class FastApiFixtureAdapter(HttpComposeAdapter):
    def __init__(self):
        super().__init__(MANIFEST)
