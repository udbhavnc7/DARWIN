"""End-to-end lifecycle for Real Project Mode with a bounded fake adapter."""
import io
import json
from pathlib import Path
import time
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient

from darwin.adapters.base import AdapterCancelled, Candidate, EvaluationBudget, PreparedEvaluation, SupportAssessment
from darwin.main import app
from darwin.verdict_policy import decide


class FakeAdapter:
    id = 'fake-reporting-v1'
    version = '1.0.0'
    evaluation_type = 'client_data_processing'

    def __init__(self, block=False):
        self.block = block

    def detect(self, source_root, commit_sha, pinned):
        return SupportAssessment(self.id, self.version, True, self.evaluation_type,
                                 'Fake source is ready.', ['src/reporting.ts'])

    def prepare(self, source_root, work_dir, budget):
        work_dir = Path(work_dir)
        harness = work_dir / 'harness'
        harness.mkdir(parents=True, exist_ok=True)
        diff = work_dir / 'candidate.diff'
        diff.write_text('--- a/src/reporting.ts\n+++ b/src/reporting.ts\n+export const candidate = true;\n',
                        encoding='utf-8')
        return PreparedEvaluation(
            work_dir=work_dir, source_root=Path(source_root), harness_dir=harness,
            fixtures=[{'id': 'fake-1000', 'seed': 7, 'size': 1000, 'currency': 'INR',
                       'timed': True, 'file': 'fake.json'}],
            config_path=harness / 'config.json', candidate_diff=diff,
            candidate_files=['src/reporting.ts'],
            checks=[{'name': 'candidate is wired into the real call site', 'passed': True, 'detail': ''}],
        )

    def candidates(self, prepared):
        return [Candidate('fake-single-pass', 'Single pass', 'A fake candidate for lifecycle tests.',
                          prepared.candidate_diff, prepared.candidate_files,
                          {'call_site': 'src/reporting.ts', 'checks': prepared.checks})]

    def measure(self, prepared, candidate, budget, check):
        if self.block:
            while not check():
                time.sleep(0.02)
            raise AdapterCancelled('Cancelled by test')
        baseline = [5_000_000, 5_100_000, 5_200_000, 5_300_000]
        cand = [2_000_000, 2_050_000, 2_100_000, 2_150_000]
        benchmark = {
            'ok': True,
            'measurement_scope': 'pure report aggregation functions',
            'environment': {'node_version': 'v26.13.1', 'platform': 'test', 'arch': 'x64',
                            'cpu_model': 'Test CPU', 'total_memory_bytes': 8 * 1024 ** 3},
            'parity': {'passed': True, 'checks': [
                {'name': 'baseline and candidate match', 'passed': True, 'detail': ''},
            ]},
            'summaries': [{'fixture_id': 'fake-1000', 'seed': 7, 'size': 1000,
                           'baseline_median_ns': 5_150_000, 'candidate_median_ns': 2_075_000,
                           'change_pct': 59.7, 'paired_candidate_wins': 4, 'samples': 4}],
            'runs': [{'fixture_id': 'fake-1000', 'seed': 7, 'size': 1000,
                      'baseline_ns': baseline, 'candidate_ns': cand}],
        }
        return {'benchmark': benchmark, 'source_tests': None, 'duration_s': 0.1,
                'command': ['node', 'runner.mjs'], 'stdout_tail': '', 'stderr_tail': ''}

    def verify(self, prepared, candidate, measurements):
        benchmark = measurements['benchmark']
        run = benchmark['runs'][0]
        summaries = [{**benchmark['summaries'][0],
                      'baseline_samples_ns': run['baseline_ns'],
                      'candidate_samples_ns': run['candidate_ns']}]
        checks = prepared.checks + benchmark['parity']['checks']
        verdict = decide(parity_passed=benchmark['parity']['passed'], checks=checks, summaries=summaries)
        verdict['source_tests'] = {'status': 'not_run', 'reason': 'Fake mode'}
        return {
            'parity': {'passed': True, 'checks_passed': len(checks), 'checks_total': len(checks), 'failures': []},
            'checks': checks,
            'summaries': summaries,
            'verdict': verdict,
            'source_tests': verdict['source_tests'],
            'environment': benchmark['environment'],
            'measurement_scope': benchmark['measurement_scope'],
            'harness': {'command': measurements['command'], 'duration_s': 0.1},
        }


class FakeImporter:
    def __init__(self, record):
        self.record = record
        self.calls = []

    def inspect(self, url, ref, consent):
        self.calls.append((url, ref, consent))
        return json.loads(json.dumps(self.record))


def inspection_record(source_root: Path, *, allowed=True, screening=None, backend=None):
    return {
        'schema_version': 1,
        'inspection_id': str(uuid4()),
        'created_at': '2026-11-15T10:00:00+00:00',
        'status': 'inspected',
        'source': {
            'url': 'https://github.com/example/fake', 'owner': 'example', 'repo': 'fake',
            'requested_ref': 'main', 'commit_sha': 'a' * 40, 'short_sha': 'a' * 12,
            'trusted': True, 'cache_key': 'example__fake__a', 'file_count': 3, 'size_bytes': 100,
            'metadata': {},
        },
        'project': {
            'type': 'client_web_app', 'display_type': 'Client-side web application',
            'summary': 'A test application with a real report call site.',
            'application_host': 'Browser', 'persistence': 'Browser storage',
            'is_server_backend': False, 'languages': ['TypeScript/React'],
            'adapter_checks': {'reporting_exports': True},
            'backend': backend or {},
        },
        'architecture': {'nodes': [], 'edges': [], 'flow': [], 'summary': 'Test graph'},
        'hotspots': [],
        'facts': [{'label': 'Visible application', 'value': 'React + TypeScript',
                   'evidence': ['web/package.json']}],
        'not_supported': [{'capability': 'API replica scaling', 'reason': 'No server exists.'}],
        'supported_evaluations': ([{
            'adapter_id': FakeAdapter.id, 'adapter_version': FakeAdapter.version,
            'display_name': 'Fake reporting comparison', 'evaluation_type': FakeAdapter.evaluation_type,
            'summary': 'Compare reports.', 'change_summary': 'One pass.', 'mechanism': 'One traversal.',
            'correctness_rules': ['Outputs must match.'], 'scope_note': 'Not server architecture.',
            'modes': [], 'execution_allowed': True, 'execution_note': 'Test adapter.',
            'evidence': ['src/reporting.ts'],
        }] if allowed else []),
        'screening': screening or {'available': False, 'controls': [],
                                   'reason': 'No backend service was detected.'},
        'guesses': [],
        'readiness': {'node_available': True, 'node_version': 'v26.13.1',
                      'source_paths_present': True, 'adapter_approved': allowed,
                      'source_tests_available': False},
        'warnings': [],
        'execution_allowed': allowed,
        'evaluation_status': 'NOT_MEASURED' if allowed else 'UNSUPPORTED_PROJECT',
        '_source_root': str(source_root),
        'policy': {'download': 'consent'},
    }


def screening_backend():
    return {
        'detected': True,
        'services': [{'name': 'fake-api', 'path': '', 'language': 'JavaScript/TypeScript',
                      'framework': 'Express', 'kind': 'http_api',
                      'entry_points': ['server.js'], 'evidence': ['package.json']}],
        'routes': [
            {'method': 'GET', 'path': '/api/health', 'file': 'server.js', 'line': 1,
             'service_path': '', 'snippet': 'app.get'},
            {'method': 'GET', 'path': '/api/items', 'file': 'server.js', 'line': 2,
             'service_path': '', 'snippet': 'app.get'},
            {'method': 'POST', 'path': '/api/items', 'file': 'server.js', 'line': 3,
             'service_path': '', 'snippet': 'app.post'},
        ],
        'route_count': 3, 'datastores': [], 'queues': [], 'auth': [],
        'external_services': [{'name': 'Stripe', 'evidence': ['server.js']}],
        'deployment': [], 'tests': {'frameworks': [], 'file_count': 0, 'evidence': []},
        'models': [], 'model_count': 0, 'migrations': [], 'background_jobs': [],
        'gateway': '', 'confidence': 'high', 'evidence': ['package.json'],
    }


def screening_support():
    return {
        'available': True,
        'adapter_id': 'architecture-screening-v1',
        'adapter_version': '1.0.0',
        'display_name': 'Backend architecture evolution (simulated)',
        'evaluation_type': 'architecture_screening',
        'summary': 'Model deployment variants from inspected source.',
        'change_summary': 'Only deployment-level controls change.',
        'mechanism': 'Deterministic queueing model. Repository code is never executed.',
        'scope_note': 'Simulated screening, not a measured winner.',
        'correctness_rules': ['Every model input is file-backed or an explicit assumption.'],
        'controls': ['replicas', 'cache_ttl_s', 'offload_jobs', 'retry_policy', 'rate_limit'],
        'modes': [{'id': 'quick', 'label': 'Quick screening', 'estimated_seconds': 8,
                   'description': 'One seed.'}],
        'execution_note': 'Simulation only. No repository code is executed.',
        'evidence': ['package.json'],
    }


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('DARWIN_EXPERIMENT_DIR', str(tmp_path / 'experiments'))
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'src').mkdir()
    (source / 'src/reporting.ts').write_text('export const x = 1;', encoding='utf-8')
    with TestClient(app) as client:
        engine = app.state.repositories
        engine.adapters = {FakeAdapter.id: FakeAdapter()}
        engine.importer = FakeImporter(inspection_record(source))
        yield client, engine, source


def wait(client, ident, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = client.get(f'/api/project-evaluations/{ident}').json()
        if record['status'] in {'completed', 'failed', 'cancelled'}:
            return record
        time.sleep(0.05)
    raise AssertionError('evaluation did not finish')


def test_full_api_lifecycle_with_digest_verified_evidence(api):
    client, engine, _ = api
    inspected = client.post('/api/repositories/inspect', json={
        'url': 'https://github.com/example/fake', 'ref': 'main', 'consent': True,
    })
    assert inspected.status_code == 200
    inspection = inspected.json()
    assert '_source_root' not in inspection
    assert inspection['execution_allowed'] is True

    response = client.post('/api/project-evaluations', json={
        'inspection_id': inspection['inspection_id'], 'mode': 'quick',
    })
    assert response.status_code == 202
    detail = wait(client, response.json()['evaluation_id'])
    assert detail['status'] == 'completed'
    assert detail['verdict']['status'] == 'VERIFIED_IMPROVEMENT'
    assert detail['correctness']['checks_passed'] == detail['correctness']['checks_total'] == 2
    assert detail['measurements'][0]['size'] == 1000
    assert detail['evidence_kind'] == 'live'
    assert '_source_root' not in detail

    events = client.get(f'/api/project-evaluations/{detail["evaluation_id"]}/events').json()
    assert [event['status'] for event in events][:2] == ['queued', 'running']
    assert events[-1]['status'] == 'completed'

    diff = client.get(f'/api/project-evaluations/{detail["evaluation_id"]}/diff')
    assert diff.status_code == 200
    assert 'candidate = true' in diff.text

    artifact = client.get(f'/api/project-evaluations/{detail["evaluation_id"]}/artifacts/verdict.json')
    assert artifact.status_code == 200
    assert artifact.json()['status'] == 'VERIFIED_IMPROVEMENT'
    assert client.get(f'/api/project-evaluations/{detail["evaluation_id"]}/artifacts/unknown').status_code == 404

    bundle = client.get(f'/api/project-evaluations/{detail["evaluation_id"]}/bundle')
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert 'manifest.json' in archive.namelist()
        assert 'candidate.diff' in archive.namelist()
        manifest = json.loads(archive.read('manifest.json'))
        assert 'candidate.diff' in manifest['files']


def test_cancelled_evaluation_has_no_winner(api, monkeypatch):
    client, engine, _ = api
    engine.adapters[FakeAdapter.id] = FakeAdapter(block=True)
    inspection = client.post('/api/repositories/inspect', json={
        'url': 'https://github.com/example/fake', 'consent': True,
    }).json()
    started = client.post('/api/project-evaluations', json={
        'inspection_id': inspection['inspection_id'], 'mode': 'quick',
    }).json()
    time.sleep(0.15)
    cancelled = client.post(f'/api/project-evaluations/{started["evaluation_id"]}/cancel')
    assert cancelled.status_code == 200
    detail = wait(client, started['evaluation_id'])
    assert detail['status'] == 'cancelled'
    assert detail['verdict']['status'] == 'INTERRUPTED'
    assert detail['measurements'] == []
    assert not any(file['name'] == 'benchmark.json' for file in detail['evidence'].get('files', []))


def test_unsupported_repository_cannot_start(api):
    client, engine, source = api
    engine.store.save_inspection(inspection_record(source, allowed=False))
    record = engine.store.all_inspections()[0]
    response = client.post('/api/project-evaluations', json={
        'inspection_id': record['inspection_id'], 'mode': 'quick',
    })
    assert response.status_code == 409
    assert 'No approved executable adapter' in response.json()['detail']


def test_missing_evaluation_and_inspection_are_404(api):
    client, _, _ = api
    assert client.get('/api/project-evaluations/nope').status_code == 404
    assert client.get('/api/repositories/inspections/nope').status_code == 404
    assert client.post('/api/project-evaluations', json={
        'inspection_id': 'nope', 'mode': 'quick',
    }).status_code == 404


def test_generic_repository_runs_simulated_screening_without_an_adapter(api):
    client, engine, source = api
    record = inspection_record(source, allowed=False, screening=screening_support(),
                               backend=screening_backend())
    record['project'].update({'type': 'node_service', 'display_type': 'Express service',
                              'is_server_backend': True})
    engine.store.save_inspection(record)
    engine.adapters = {}

    response = client.post('/api/project-evaluations', json={
        'inspection_id': record['inspection_id'], 'mode': 'quick',
    })
    assert response.status_code == 202
    started = response.json()
    assert started['adapter_id'] == 'architecture-screening-v1'
    assert started['evaluation_type'] == 'architecture_screening'
    assert started['evidence_kind'] == 'simulated'

    detail = wait(client, started['evaluation_id'])
    assert detail['status'] == 'completed'
    assert detail['adapter_id'] == 'architecture-screening-v1'
    assert detail['evidence_kind'] == 'simulated'
    assert detail['measurements'] == []
    assert detail['candidate'] is None
    assert detail['screening']['label'] == 'SIMULATED'
    assert detail['screening']['not_measured'] is True
    assert detail['verdict']['status'] == 'NOT_MEASURED'
    assert detail['recommendation']['measured'] is False
    assert detail['recommendation']['evidence_kind'] == 'simulated'
    assert detail['correctness']['checks_total'] == 0
    assert '_source_root' not in detail

    architecture = client.get(
        f'/api/project-evaluations/{detail["evaluation_id"]}/artifacts/architecture.json'
    )
    assert architecture.status_code == 200
    assert architecture.json()['project']['backend']['route_count'] == 3
    screening = client.get(
        f'/api/project-evaluations/{detail["evaluation_id"]}/artifacts/screening.json'
    )
    assert screening.status_code == 200
    assert screening.json()['evidence_kind'] == 'simulated'
    note = client.get(
        f'/api/project-evaluations/{detail["evaluation_id"]}/artifacts/project-note.md'
    )
    assert note.status_code == 200
    assert 'No repository code was executed' in note.text

    bundle = client.get(f'/api/project-evaluations/{detail["evaluation_id"]}/bundle')
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = archive.namelist()
        assert {'screening.json', 'verdict.json', 'project-note.md'} <= set(names)
        assert 'benchmark.json' not in names
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['evidence_kind'] == 'simulated'
        assert 'screening.json' in manifest['files']


def test_cancelled_screening_has_no_recommendation(api, monkeypatch):
    client, engine, source = api
    record = inspection_record(source, allowed=False, screening=screening_support(),
                               backend=screening_backend())
    engine.store.save_inspection(record)

    def slow_model(analysis, mode):
        time.sleep(0.3)
        from darwin.project_simulation import screen_repository as real_model
        return real_model(analysis, mode)

    monkeypatch.setattr('darwin.repository_evaluations.screen_repository', slow_model)
    started = client.post('/api/project-evaluations', json={
        'inspection_id': record['inspection_id'], 'mode': 'quick',
    }).json()
    time.sleep(0.1)
    cancelled = client.post(f'/api/project-evaluations/{started["evaluation_id"]}/cancel')
    assert cancelled.status_code == 200

    detail = wait(client, started['evaluation_id'])
    assert detail['status'] == 'cancelled'
    assert detail['verdict']['status'] == 'NOT_MEASURED'
    assert detail['recommendation']['status'] == 'INCONCLUSIVE'
    assert detail['recommendation']['measured'] is False
    assert detail['recommendation']['changes'] == []
    assert not any(file['name'] == 'screening.json'
                   for file in detail['evidence'].get('files', []))


def test_catalog_labels_screening_as_simulated(api):
    client, _, _ = api
    catalog = client.get('/api/repositories/catalog').json()
    assert catalog['screening']['adapter_id'] == 'architecture-screening-v1'
    assert catalog['screening']['evidence_kind'] == 'simulated'
    assert catalog['screening']['label'] == 'SIMULATED'
