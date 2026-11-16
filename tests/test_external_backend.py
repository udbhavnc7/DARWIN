"""External backend adapter: trust boundary, isolation, and honest verdicts.

These tests never start Docker. They cover the decisions that protect the host
and the rules that prevent a forced winner.
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from darwin.adapters.base import EvaluationBudget
from darwin.adapters.flask_redis import FlaskRedisAdapter
from darwin.backend_verdict import decide_architecture
from darwin.backend_manifest import CandidateDimension
from darwin.isolated_backend import (
    IsolationError, assert_safe_compose, copy_allowlisted_source, generate_compose,
)
from darwin.main import app
from darwin.performance import metrics
from darwin.project_capabilities import inspect_source
from darwin.repository_catalog import (
    FLASK_REDIS_COMMIT, NODE_REDIS_COMMIT, NODE_REDIS_REPOSITORY,
)
from darwin.repository_evaluations import _change_text, default_adapters
from darwin.repository_import import RepositoryImporter

APP = """from flask import Flask
from redis import Redis
app = Flask(__name__)
redis = Redis(host='redis', port=6379)
@app.route('/')
def hello():
    count = redis.incr('hits')
    return f'This webpage has been viewed {count} times'
"""


def flask_tree(root: Path) -> Path:
    (root / 'flask-redis').mkdir(parents=True)
    (root / 'flask-redis/app.py').write_text(APP, encoding='utf-8')
    (root / 'flask-redis/requirements.txt').write_text('flask\nredis\n', encoding='utf-8')
    return root


NODE_APP = """const express = require('express');
const redis = require('redis');
const app = express();
const redisClient = redis.createClient({host: 'redis', port: 6379});

app.get('/', function (req, res) {
  redisClient.get('numVisits', function (err, numVisits) {
    res.send('Number of visits is: ' + (parseInt(numVisits) || 0));
  });
});

app.listen(5000, function () {
  console.log('Web application is listening on port 5000');
});
"""


def node_tree(root: Path) -> Path:
    (root / 'web').mkdir(parents=True, exist_ok=True)
    (root / 'web/server.js').write_text(NODE_APP, encoding='utf-8')
    (root / 'web/package.json').write_text(json.dumps({
        'name': 'web', 'version': '1.0.0',
        'dependencies': {'express': '^4.17.2', 'redis': '3.1.2'},
    }), encoding='utf-8')
    (root / 'web/package-lock.json').write_text(json.dumps({
        'name': 'web', 'lockfileVersion': 3, 'packages': {},
    }), encoding='utf-8')
    return root


def ready(monkeypatch, available: bool) -> None:
    note = (True, 'Linux Docker engine with cgroup v2') if available else (
        False, 'A local Linux Docker engine is not running.')
    monkeypatch.setattr('darwin.adapters.http_compose.runner_available', lambda: note)
    monkeypatch.setattr('darwin.isolated_backend.runner_available', lambda: note)


def test_flask_redis_is_classified_as_a_container_backend(tmp_path, monkeypatch):
    ready(monkeypatch, True)
    result = inspect_source(flask_tree(tmp_path), 'https://github.com/docker/awesome-compose',
                            'docker', 'awesome-compose', FLASK_REDIS_COMMIT, True)
    assert result['project']['type'] == 'containerized_backend'
    assert result['project']['is_server_backend'] is True
    assert result['support_level'] == 'READY_FOR_MEASURED_EVOLUTION'
    assert result['evaluation_status'] == 'NOT_MEASURED'
    adapter = result['supported_evaluations'][0]
    assert adapter['adapter_id'] == 'flask-redis-compose-v1'
    assert adapter['execution_allowed'] is True
    assert adapter['capabilities']['faults'] == ['service_restart']
    labels = {item['label'] for item in result['facts']}
    assert {'Web application', 'Server runtime', 'Gateway', 'Shared state'} <= labels
    unsupported = {item['capability'] for item in result['not_supported']}
    assert 'Repository Compose / Dockerfile' in unsupported


def test_matching_source_without_docker_is_evaluable_with_setup(tmp_path, monkeypatch):
    ready(monkeypatch, False)
    result = inspect_source(flask_tree(tmp_path), 'https://github.com/docker/awesome-compose',
                            'docker', 'awesome-compose', FLASK_REDIS_COMMIT, True)
    assert result['support_level'] == 'EVALUABLE_WITH_SETUP'
    adapter = result['supported_evaluations'][0]
    assert adapter['execution_allowed'] is False
    assert 'Linux Docker engine' in adapter['prerequisite']
    assert result['prerequisites']


def test_unpinned_flask_redis_is_inspection_only(tmp_path, monkeypatch):
    ready(monkeypatch, True)
    result = inspect_source(flask_tree(tmp_path), 'https://github.com/docker/awesome-compose',
                            'docker', 'awesome-compose', 'a' * 40, False)
    assert result['supported_evaluations'] == []
    assert result['support_level'] == 'INSPECTABLE'
    assert result['evaluation_status'] == 'UNSUPPORTED_PROJECT'


def test_lookalike_flask_app_is_not_given_the_reviewed_adapter(tmp_path, monkeypatch):
    ready(monkeypatch, True)
    (tmp_path / 'flask-redis').mkdir()
    (tmp_path / 'flask-redis/app.py').write_text(
        "from flask import Flask\napp = Flask(__name__)\n@app.route('/')\n"
        "def hello():\n    return 'hello'\n", encoding='utf-8')
    (tmp_path / 'flask-redis/requirements.txt').write_text('flask\n', encoding='utf-8')
    result = inspect_source(tmp_path, 'https://github.com/docker/awesome-compose',
                            'docker', 'awesome-compose', FLASK_REDIS_COMMIT, True)
    assert result['supported_evaluations'] == []
    assert result['support_level'] == 'INSPECTABLE'
    assert result['evaluation_status'] == 'UNSUPPORTED_PROJECT'


def test_detect_rejects_wrong_markers(tmp_path, monkeypatch):
    ready(monkeypatch, True)
    (tmp_path / 'flask-redis').mkdir()
    (tmp_path / 'flask-redis/app.py').write_text('from flask import Flask\n', encoding='utf-8')
    (tmp_path / 'flask-redis/requirements.txt').write_text('flask\n', encoding='utf-8')
    assessment = FlaskRedisAdapter().detect(tmp_path, FLASK_REDIS_COMMIT, True)
    assert assessment.supported is False
    assert 'markers' in assessment.reason


def test_generated_compose_matches_the_security_policy():
    adapter = FlaskRedisAdapter()
    candidate = adapter.manifest.candidates[1]
    config = generate_compose(adapter.manifest, candidate, 'darwin:app')
    assert_safe_compose(config)
    gateway = config['services']['gateway']
    assert gateway['ports'][0]['host_ip'] == '127.0.0.1'
    assert gateway['ports'][0]['published'] == 0
    assert config['networks']['sandbox']['internal'] is True
    for service in config['services'].values():
        assert service.get('privileged') is None
        assert 'docker.sock' not in json.dumps(service)
        assert service.get('security_opt') == ['no-new-privileges:true']
        assert service.get('cap_drop') == ['ALL']
    assert config['services']['redis']['user'] == '999:999'
    assert config['services']['web-1']['user'] == '65534:65534'
    assert sum(1 for name in config['services'] if name.startswith('web-')) == 2


def test_compose_refuses_privileged_or_docker_socket():
    with pytest.raises(IsolationError):
        assert_safe_compose({'services': {'evil': {'image': 'x', 'privileged': True}}})
    with pytest.raises(IsolationError):
        assert_safe_compose({'services': {'evil': {'image': 'x',
                                                   'volumes': ['/var/run/docker.sock:/sock']}}})


def test_source_copy_rejects_escape_and_symlink(tmp_path):
    source = tmp_path / 'src'
    source.mkdir()
    (source / 'app.py').write_text('x', encoding='utf-8')
    dest = tmp_path / 'dest'
    with pytest.raises((IsolationError, ValueError)):
        copy_allowlisted_source(source, dest, ['../outside.py'])
    if hasattr(Path, 'symlink_to'):
        try:
            (source / 'link.py').symlink_to(source / 'app.py')
        except (OSError, NotImplementedError):
            pytest.skip('symlinks are unavailable on this host')
        with pytest.raises(IsolationError):
            copy_allowlisted_source(source, dest, ['link.py'])


def test_throughput_uses_the_actual_window():
    samples = [{'ok': True, 'latency_ms': 3.0, 'finished_s': index / 6}
               for index in range(36)]
    row = metrics(samples, 0.1, 10.0, window_s=6)
    assert row['requests_per_s'] == 6.0
    with pytest.raises(ValueError):
        metrics(samples, 0.1, 10.0, window_s=0)


def _runs():
    return [
        {'candidate_id': 'baseline-1x1', 'label': 'Baseline', 'replicas': 1, 'workers': 1,
         'metrics': {'p95_ms': 4.4, 'requests_per_s': 6.0, 'error_rate': 0.0,
                     'cpu_seconds': 0.18, 'memory_peak_mb': 53.0, 'recovery_s': None},
         'recovery_s': 0.45},
        {'candidate_id': 'replicas-2x1', 'label': 'Two replicas', 'replicas': 2, 'workers': 1,
         'metrics': {'p95_ms': 4.2, 'requests_per_s': 6.0, 'error_rate': 0.0,
                     'cpu_seconds': 0.26, 'memory_peak_mb': 97.0, 'recovery_s': None},
         'recovery_s': 0.0},
    ]


def test_recovery_win_with_resource_cost_is_a_tradeoff():
    runs = _runs()
    verdict = decide_architecture(challenge='recover', checks=[{'passed': True}],
                                  baseline=runs[0], candidates=runs)
    assert verdict['status'] == 'TRADEOFF_REQUIRES_CHOICE'
    assert verdict['winner_id'] == 'replicas-2x1'
    metrics_changed = {item['metric'] for item in verdict['candidate_metrics']['regressions']}
    assert {'cpu_seconds', 'memory_peak_mb'} <= metrics_changed
    assert 'will not hide that cost' in verdict['reason']


def test_availability_smoke_alone_does_not_win():
    runs = _runs()
    verdict = decide_architecture(
        challenge='recover', baseline=runs[0], candidates=runs,
        checks=[{'passed': False, 'name': 'counter oracle'}])
    assert verdict['status'] == 'REJECTED_INCORRECT'


def test_change_document_has_apply_and_rollback():
    runs = _runs()
    verdict = decide_architecture(challenge='recover', checks=[{'passed': True}],
                                  baseline=runs[0], candidates=runs)
    record = {
        'source': {'url': 'https://github.com/docker/awesome-compose',
                   'commit_sha': FLASK_REDIS_COMMIT},
        'adapter_id': 'flask-redis-compose-v1', 'adapter_version': '1.0.0',
        'evaluation_id': 'e1', 'mode': 'quick', 'evidence_kind': 'live',
        'workload': {'challenge': 'recover'},
    }
    text = _change_text(record, verdict)
    assert '## Apply' in text
    assert '## Rollback' in text
    assert 'Two replicas' in text
    assert 'lab-only' in text
    assert 'Recommended topology' not in text
    assert 'operator choice' in text


def test_change_document_retains_the_baseline_without_a_winner():
    record = {
        'source': {'url': 'https://github.com/dockersamples/nginx-node-redis',
                   'commit_sha': NODE_REDIS_COMMIT},
        'adapter_id': 'node-redis-compose-v1', 'adapter_version': '1.0.0',
        'evaluation_id': 'e2', 'mode': 'quick', 'evidence_kind': 'live',
        'workload': {'challenge': 'faster'},
    }
    verdict = {
        'status': 'BASELINE_RETAINED', 'label': 'Baseline retained',
        'reason': 'No candidate cleared the gates.',
        'baseline_id': 'baseline-1x1', 'winner_id': 'baseline-1x1',
        'comparison': [{'candidate_id': 'baseline-1x1', 'label': 'Original',
                        'replicas': 1, 'workers': 1}],
    }
    text = _change_text(record, verdict)
    assert 'Keep the baseline topology' in text
    assert 'Recommended topology' not in text
    assert 'deployment change is proposed' in text


def test_manifest_candidates_expose_only_declared_dimensions():
    manifest = FlaskRedisAdapter().manifest
    assert {item.candidate_id for item in manifest.candidates} == {
        'baseline-1x1', 'replicas-2x1', 'workers-1x2'}
    assert {item.replicas for item in manifest.candidates} <= {1, 2}
    assert {item.workers for item in manifest.candidates} <= {1, 2}
    budget = EvaluationBudget(mode='quick', seeds=(7,), sizes=(1,), repetitions=1,
                              warmups=1, wall_clock_s=60)
    assert budget.challenge == 'faster'


# ---------------------------------------------------------------------------
# Platform wiring: candidates preview, prerequisite refusal, change export
# ---------------------------------------------------------------------------

SUPPORT = {
    'adapter_id': 'flask-redis-compose-v1', 'adapter_version': '1.0.0',
    'display_name': 'Architecture: replicas and gunicorn workers',
    'evaluation_type': 'backend_architecture',
    'summary': 'Measure the original topology against reviewed changes.',
    'change_summary': 'Replicas behind nginx.', 'mechanism': 'Isolated Compose.',
    'correctness_rules': ['GET / returns the reviewed counter sentence.'],
    'scope_note': 'Deployable process topology only.',
    'modes': [], 'execution_allowed': True, 'execution_note': 'Reviewed adapter matches.',
    'evidence': ['flask-redis/app.py'], 'challenges': ['faster', 'recover', 'resources'],
}


def inspection(root: Path, *, allowed: bool = True, level: str = 'READY_FOR_MEASURED_EVOLUTION',
               prereq=None):
    support = {**SUPPORT, 'execution_allowed': allowed}
    return {
        'schema_version': 1, 'inspection_id': str(uuid4()),
        'created_at': '2026-11-16T10:00:00+00:00', 'status': 'inspected',
        'source': {
            'url': 'https://github.com/docker/awesome-compose', 'owner': 'docker',
            'repo': 'awesome-compose', 'requested_ref': 'master',
            'commit_sha': FLASK_REDIS_COMMIT, 'short_sha': FLASK_REDIS_COMMIT[:12],
            'trusted': True, 'cache_key': 'x', 'file_count': 2, 'size_bytes': 100,
            'metadata': {},
        },
        'project': {
            'type': 'containerized_backend', 'display_type': 'Flask + Redis',
            'summary': 'Docker Flask + Redis sample.', 'application_host': 'Nginx gateway',
            'persistence': 'Redis', 'is_server_backend': True,
            'languages': ['Python'], 'adapter_checks': {},
            'backend': {'detected': True, 'services': [], 'route_count': 1},
        },
        'architecture': {'nodes': [], 'edges': [], 'flow': [], 'summary': 'Test graph'},
        'hotspots': [],
        'facts': [{'label': 'Web application', 'value': 'Flask + Redis', 'evidence': ['app.py']}],
        'not_supported': [],
        'supported_evaluations': [support],
        'screening': {'available': False, 'controls': [], 'reason': 'Measured adapter.'},
        'guesses': [],
        'readiness': {'node_available': True, 'node_version': 'v24.0.0',
                      'source_paths_present': True, 'adapter_approved': True,
                      'source_tests_available': False},
        'warnings': [],
        'execution_allowed': allowed,
        'support_level': level,
        'prerequisites': prereq or [],
        'evaluation_status': 'NOT_MEASURED' if allowed else 'UNSUPPORTED_PROJECT',
        '_source_root': str(root),
        'policy': {'download': 'consent'},
    }


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('DARWIN_EXPERIMENT_DIR', str(tmp_path / 'experiments'))
    with TestClient(app) as client:
        engine = app.state.repositories
        engine.adapters = {FlaskRedisAdapter().id: FlaskRedisAdapter()}
        yield client, engine, tmp_path


def test_candidates_preview_lists_reviewed_dimensions(api):
    client, engine, root = api
    flask_tree(root)
    record = inspection(root)
    engine.store.save_inspection(record)
    preview = client.get(f'/api/repositories/inspections/{record["inspection_id"]}/candidates')
    assert preview.status_code == 200
    body = preview.json()
    assert body['eligible'] is True
    assert body['adapter_id'] == 'flask-redis-compose-v1'
    assert body['challenges'] == ['faster', 'recover', 'resources']
    assert {item['candidate_id'] for item in body['candidates']} == {
        'baseline-1x1', 'replicas-2x1', 'workers-1x2'}
    assert all('replicas' in item['dimension'] for item in body['candidates'])


def test_prerequisite_mismatch_is_refused_before_any_execution(api):
    client, engine, root = api
    flask_tree(root)
    record = inspection(root, allowed=False, level='EVALUABLE_WITH_SETUP',
                        prereq=['A local Linux Docker engine is running.'])
    engine.store.save_inspection(record)
    response = client.post('/api/project-evaluations', json={
        'inspection_id': record['inspection_id'], 'mode': 'quick', 'challenge': 'recover',
    })
    assert response.status_code == 409
    assert 'Linux Docker engine' in response.json()['detail']
    assert engine.list_evaluations() == []


def test_unknown_challenge_is_rejected(api):
    client, engine, root = api
    flask_tree(root)
    record = inspection(root)
    engine.store.save_inspection(record)
    response = client.post('/api/project-evaluations', json={
        'inspection_id': record['inspection_id'], 'mode': 'quick', 'challenge': 'win',
    })
    assert response.status_code == 422


def test_change_is_not_exported_for_baseline_retained(api):
    client, engine, _ = api
    ident = str(uuid4())
    engine.store.save_evaluation({
        'evaluation_id': ident, 'created_at': '2026-11-16T10:00:00+00:00',
        'status': 'completed', 'stage': 'completed',
        'verdict': {'status': 'BASELINE_RETAINED', 'reason': 'No candidate improved.'},
        'evidence': {'dir': 'ev-none', 'files': []},
    }, 'done')
    response = client.get(f'/api/project-evaluations/{ident}/change')
    assert response.status_code == 409
    assert 'No measured architecture change' in response.json()['detail']


def recorded_evaluation(ident: str, directory: str,
                        verdict: str = 'BASELINE_RETAINED') -> dict:
    """A minimal completed record that can own a real evidence folder."""
    return {
        'evaluation_id': ident, 'created_at': '2026-11-16T10:00:00+00:00',
        'status': 'completed', 'stage': 'completed',
        'inspection_id': str(uuid4()),
        'adapter_id': 'flask-redis-compose-v1', 'adapter_version': '1',
        'mode': 'quick', 'workload': {'challenge': 'faster'},
        'source': {'url': 'https://github.com/docker/awesome-compose',
                   'commit_sha': FLASK_REDIS_COMMIT},
        'verdict': {'status': verdict, 'reason': 'Recorded for the test.',
                    'comparison': [], 'winner_id': None, 'baseline_id': None},
        'evidence': {'dir': directory, 'files': []},
    }


def test_recorded_change_is_served_as_markdown(api):
    client, engine, _ = api
    ident = str(uuid4())
    folder = engine.store.root / 'ev-change'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'change.md').write_text('# Measured change\n\n## Apply\n\n## Rollback\n',
                                      encoding='utf-8')
    record = recorded_evaluation(ident, 'ev-change', 'TRADEOFF_REQUIRES_CHOICE')
    engine._register_evidence(record, folder)
    engine.store.save_evaluation(record, 'done')
    response = client.get(f'/api/project-evaluations/{ident}/change')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/markdown')
    assert '## Rollback' in response.text


def test_stray_files_never_become_evidence(api):
    client, engine, _ = api
    ident = str(uuid4())
    folder = engine.store.root / 'ev-stray'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'verdict.json').write_text('{"status": "BASELINE_RETAINED"}', encoding='utf-8')
    (folder / 'notes.txt').write_text('host context that must not ship', encoding='utf-8')
    record = recorded_evaluation(ident, 'ev-stray')
    engine._register_evidence(record, folder)
    assert {item['name'] for item in record['evidence']['files']} == {
        'verdict.json', 'manifest.json'}
    engine.store.save_evaluation(record, 'done')

    assert client.get(
        f'/api/project-evaluations/{ident}/artifacts/notes.txt').status_code == 404
    bundle = client.get(f'/api/project-evaluations/{ident}/bundle')
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert 'notes.txt' not in archive.namelist()
        assert 'verdict.json' in archive.namelist()


def test_tampered_evidence_is_refused_not_served(api):
    client, engine, _ = api
    ident = str(uuid4())
    folder = engine.store.root / 'ev-tampered'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'verdict.json').write_text('{"status": "BASELINE_RETAINED"}', encoding='utf-8')
    record = recorded_evaluation(ident, 'ev-tampered')
    engine._register_evidence(record, folder)
    engine.store.save_evaluation(record, 'done')
    (folder / 'verdict.json').write_text('{"status": "VERIFIED_IMPROVEMENT"}', encoding='utf-8')

    assert client.get(
        f'/api/project-evaluations/{ident}/artifacts/verdict.json').status_code == 404
    assert client.get(f'/api/project-evaluations/{ident}/bundle').status_code == 409


@pytest.mark.skipif(not hasattr(Path, 'symlink_to'), reason='No symlink support')
def test_symlinked_artifact_cannot_escape_the_evidence_folder(api, tmp_path):
    client, engine, _ = api
    ident = str(uuid4())
    folder = engine.store.root / 'ev-symlink'
    folder.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / 'outside.json'
    outside.write_text('{"secret": "not evidence"}', encoding='utf-8')
    try:
        (folder / 'verdict.json').symlink_to(outside)
    except OSError as exc:
        pytest.skip(f'Symlinks are unavailable here: {exc}')
    manifest = {'schema_version': 1, 'files': {
        'verdict.json': hashlib.sha256(outside.read_bytes()).hexdigest()}}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    record = recorded_evaluation(ident, 'ev-symlink')
    record['evidence']['files'] = [
        {'name': 'verdict.json', 'sha256': manifest['files']['verdict.json'], 'bytes': 0}]
    engine.store.save_evaluation(record, 'done')

    assert client.get(
        f'/api/project-evaluations/{ident}/artifacts/verdict.json').status_code == 404
    assert client.get(f'/api/project-evaluations/{ident}/bundle').status_code == 409


def test_bundle_refuses_a_folder_without_an_evidence_manifest(api):
    """An interrupted run keeps the adapter's own manifest; it is not evidence."""
    client, engine, _ = api
    ident = str(uuid4())
    folder = engine.store.root / 'ev-interrupted'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'manifest.json').write_text(json.dumps({'runtime': 'native'}), encoding='utf-8')
    record = recorded_evaluation(ident, 'ev-interrupted')
    record['status'] = 'failed'
    engine.store.save_evaluation(record, 'failed')

    assert client.get(f'/api/project-evaluations/{ident}/bundle').status_code == 409


def test_record_without_registered_evidence_fails_closed(api):
    client, engine, _ = api
    ident = str(uuid4())
    folder = engine.store.root / 'ev-legacy'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'verdict.json').write_text('{"status": "BASELINE_RETAINED"}', encoding='utf-8')
    (folder / 'change.md').write_text('# Unverified change\n', encoding='utf-8')
    record = recorded_evaluation(ident, 'ev-legacy', 'TRADEOFF_REQUIRES_CHOICE')
    record['evidence'] = {'dir': 'ev-legacy', 'files': None}
    engine.store.save_evaluation(record, 'done')

    assert client.get(
        f'/api/project-evaluations/{ident}/artifacts/verdict.json').status_code == 404
    change = client.get(f'/api/project-evaluations/{ident}/change')
    assert 'Unverified change' not in change.text
    assert 'No deployable change is exported' in change.text


class StubGit:
    def resolve(self, url, ref):
        return NODE_REDIS_COMMIT


def test_second_repository_is_reviewed_through_the_same_interface(api, monkeypatch):
    """A different repository reuses the adapter base, not the Flask manifest."""
    client, engine, root = api
    monkeypatch.setattr('darwin.adapters.http_compose.runner_available',
                        lambda: (True, 'Linux Docker engine with cgroup v2'))
    engine.adapters = default_adapters()
    tree = node_tree(root / 'node-source')
    engine.importer = RepositoryImporter(
        cache_root=root / 'cache', git=StubGit(),
        source_override={NODE_REDIS_REPOSITORY: tree}, resolve_override=NODE_REDIS_COMMIT,
    )

    inspected = client.post('/api/repositories/inspect', json={
        'url': NODE_REDIS_REPOSITORY, 'ref': 'main', 'consent': True})
    assert inspected.status_code == 200
    record = inspected.json()
    assert record['execution_allowed'] is True
    assert [item['adapter_id'] for item in record['supported_evaluations']] == [
        'node-redis-compose-v1']

    preview = client.get(
        f"/api/repositories/inspections/{record['inspection_id']}/candidates").json()
    assert preview['adapter_id'] == 'node-redis-compose-v1'
    assert {item['candidate_id'] for item in preview['candidates']} == {
        'baseline-1x1', 'replicas-2x1'}
    assert preview['eligible'] is True


def test_incompatible_repository_is_unsupported_through_the_api(api, monkeypatch):
    client, engine, root = api
    monkeypatch.setattr('darwin.adapters.http_compose.runner_available',
                        lambda: (False, 'A local Linux Docker engine is not running.'))
    engine.adapters = default_adapters()
    tree = root / 'docs-only'
    tree.mkdir()
    (tree / 'README.md').write_text('# Notes only\n', encoding='utf-8')
    engine.importer = RepositoryImporter(
        cache_root=root / 'cache', git=StubGit(),
        source_override={'https://github.com/example/notes-only': tree},
        resolve_override='a' * 40,
    )

    inspected = client.post('/api/repositories/inspect', json={
        'url': 'https://github.com/example/notes-only', 'ref': 'main', 'consent': True})
    assert inspected.status_code == 200
    record = inspected.json()
    assert record['execution_allowed'] is False
    assert record['supported_evaluations'] == []
    assert record['evaluation_status'] == 'UNSUPPORTED_PROJECT'

    refused = client.post('/api/project-evaluations', json={
        'inspection_id': record['inspection_id'], 'mode': 'quick'})
    assert refused.status_code == 409
    assert 'No approved executable adapter' in refused.json()['detail']
    assert engine.list_evaluations() == []
