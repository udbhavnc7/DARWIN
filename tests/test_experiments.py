import hashlib
import json
import threading
import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from darwin.experiments import Engine, StartExperiment, Store, TERMINAL


def wait(worker, ident):
    until = time.monotonic() + 10
    while time.monotonic() < until:
        record = worker.store.get(ident)
        if record['status'] in TERMINAL:
            return record
        time.sleep(.02)
    pytest.fail('Worker did not finish')


class Adapter:
    def __init__(self, folder, closed, running=None, fail=False):
        self.folder, self.closed, self.running, self.fail = folder, closed, running, fail

    def run(self, check):
        self.folder.joinpath('test.log').write_text('Execution evidence')
        if self.running:
            self.running.set()
            while True:
                check()
                time.sleep(.01)
        if self.fail:
            raise RuntimeError('Readiness failed')
        return {'measurement_kind': 'smoke_only'}

    def close(self):
        self.closed.append(True)


def test_completion_artifacts_events_and_persistence(tmp_path):
    closed = []
    worker = Engine(tmp_path, lambda r, c, f, s: Adapter(f, closed))
    try:
        record = worker.submit(StartExperiment())
        result = wait(worker, record['experiment_id'])
        assert result['status'] == 'completed'
        assert result['attempts_used'] == len(closed) == 3
        assert result['resource_limits_enforced'] is False
        for evaluation in result['candidates'][0]['evaluations']:
            assert evaluation['gate'] == 'not_checked'
            for artifact in evaluation['artifacts']:
                path = tmp_path / result['experiment_id'] / evaluation['evaluation_id'] / artifact['name']
                assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact['sha256']
        events = worker.store.events(result['experiment_id'])
        assert [e['sequence'] for e in events] == list(range(1, len(events)+1))
        assert worker.store.events(result['experiment_id'], 2) == events[2:]
    finally:
        worker.close()
    assert Store(tmp_path).get(record['experiment_id'])['status'] == 'completed'


def test_active_and_queued_cancellation(tmp_path):
    running = threading.Event()
    closed = []
    worker = Engine(tmp_path, lambda r, c, f, s: Adapter(f, closed, running))
    try:
        first = worker.submit(StartExperiment())
        assert running.wait(5)
        second = worker.submit(StartExperiment())
        assert worker.cancel(second['experiment_id'])['status'] == 'cancelled'
        worker.cancel(first['experiment_id'])
        result = wait(worker, first['experiment_id'])
        assert result['status'] == 'cancelled'
        assert result['attempts_used'] == len(closed) == 1
        assert result['cleanup_status'] == 'completed'
    finally:
        worker.close()


def test_failure_still_cleans_and_retains_logs(tmp_path):
    closed = []
    worker = Engine(tmp_path, lambda r, c, f, s: Adapter(f, closed, fail=True))
    try:
        result = wait(worker, worker.submit(StartExperiment())['experiment_id'])
        assert result['status'] == 'failed'
        assert result['attempts_used'] == len(closed) == 1
        assert result['candidates'][0]['evaluations'][0]['artifacts']
    finally:
        worker.close()


def test_budget_timeout_runs_cleanup(tmp_path, monkeypatch):
    closed = []
    running = threading.Event()
    worker = Engine(tmp_path, lambda r, c, f, s: Adapter(f, closed, running))
    original = worker.check
    def expire(stop, deadline):
        if running.is_set():
            raise TimeoutError('Experiment wall-clock budget exhausted')
        original(stop, deadline)
    monkeypatch.setattr(worker, 'check', expire)
    try:
        result = wait(worker, worker.submit(StartExperiment())['experiment_id'])
        assert result['status'] == 'failed'
        assert 'budget' in result['error']
        assert len(closed) == 1
    finally:
        worker.close()


def test_restart_preserves_interruption_and_blocks_new_work(tmp_path):
    store = Store(tmp_path)
    ident = str(uuid4())
    store.save({'experiment_id': ident, 'status': 'running'}, 'Started')
    worker = Engine(tmp_path)
    try:
        assert worker.store.get(ident)['cleanup_status'] == 'requires_review'
        with pytest.raises(RuntimeError, match='review'):
            worker.submit(StartExperiment())
    finally:
        worker.close()


@pytest.mark.parametrize('payload', [
    {'genomes': [{}, {'app_replicas': 2}, {'app_replicas': 3}]},
    {'genomes': [{}, {}]}, {'workload_profile': 'flash_sale'},
    {'fault_scenarios': ['db_delay']}, {'budget': {'sandbox_cpu_cores': 1}}, {'constraints': {'max_p95_ms': 300}},
])
def test_invalid_or_unimplemented_work_is_rejected(payload):
    with pytest.raises(ValidationError):
        StartExperiment.model_validate(payload)


def test_cleanup_failure_blocks_already_queued_work(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    calls = []
    class BrokenCleanup(Adapter):
        def run(self, check):
            entered.set()
            assert release.wait(5)
            return super().run(check)
        def close(self):
            raise RuntimeError('cleanup failed')
    def factory(r, c, f, s):
        calls.append(True)
        return BrokenCleanup(f, [])
    worker = Engine(tmp_path, factory)
    try:
        first = worker.submit(StartExperiment())
        assert entered.wait(5)
        second = worker.submit(StartExperiment())
        release.set()
        assert wait(worker, first['experiment_id'])['cleanup_status'] == 'requires_review'
        assert wait(worker, second['experiment_id'])['status'] == 'failed'
        assert len(calls) == 1
    finally:
        release.set()
        worker.close()


def test_api_rerun_artifact_integrity_and_websocket_resume(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from darwin.experiment_api import router
    worker = Engine(tmp_path, lambda r, c, f, s: Adapter(f, []))
    app = FastAPI()
    app.include_router(router)
    app.state.engine = worker
    try:
        with TestClient(app) as client:
            started = client.post('/api/experiments', json={})
            assert started.status_code == 202
            record = wait(worker, started.json()['experiment_id'])
            ident = record['experiment_id']
            candidate = record['candidates'][0]
            assert client.get(f'/api/experiments/{ident}').json()['status'] == 'completed'
            assert client.get(f'/api/candidates/{candidate["candidate_id"]}').status_code == 200
            evaluation = candidate['evaluations'][0]
            base = f'/api/experiments/{ident}/artifacts/{evaluation["evaluation_id"]}'
            assert client.get(base + '/test.log').text == 'Execution evidence'
            assert client.get(base + '/unregistered.txt').status_code == 404
            (tmp_path / ident / evaluation['evaluation_id'] / 'test.log').write_text('tampered')
            assert client.get(base + '/test.log').status_code == 409
            expected = worker.store.events(ident, 2)
            with client.websocket_connect(f'/ws/experiments/{ident}?after=2') as websocket:
                received = [websocket.receive_json() for _ in expected]
            assert received == expected
            rerun = client.post(f'/api/candidates/{candidate["candidate_id"]}/rerun')
            assert rerun.status_code == 202
            assert rerun.json()['experiment_id'] != ident
            assert wait(worker, rerun.json()['experiment_id'])['rerun_of'] == candidate['candidate_id']
            assert client.get(f'/api/experiments/{uuid4()}').status_code == 404
    finally:
        worker.close()


def test_recovery_does_not_clear_live_database(tmp_path, monkeypatch):
    from darwin import recovery
    record = {'experiment_id': str(uuid4()), 'request': {'mode': 'native_smoke'},
              'candidates': [{'evaluations': [{'evaluation_id': str(uuid4())}]}]}
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): return self
        def fetchone(self): return (1,)
    monkeypatch.setattr(recovery.psycopg, 'connect', lambda *a, **k: Conn())
    with pytest.raises(RuntimeError, match='database'):
        recovery.verify_absent(Store(tmp_path), record)
