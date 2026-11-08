import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from darwin.contracts import Evaluation, Metrics
from darwin.main import app

client = TestClient(app)


def test_baseline_and_validation_agree():
    project = client.get('/api/project').json()
    assert project['name'] == 'DARWIN'
    assert project['execution_available'] is True
    assert project['benchmarking_available'] is (os.name == 'nt')
    response = client.post('/api/experiments/validate', json={})
    assert response.status_code == 200
    assert response.json()['budget'] == project['budget']


@pytest.mark.parametrize('payload', [
    {'workload_profile': 'invented'},
    {'production_url': 'https://example.com'},
    {'budget': {'real_test_budget': 2, 'repetitions': 3}},
    {'budget': {'concurrent_deployments': 2}},
    {'constraints': {'max_error_rate': 1.1}},
])
def test_invalid_experiment_requests_are_rejected(payload):
    assert client.post('/api/experiments/validate', json=payload).status_code == 422


def test_simulation_cannot_claim_verification():
    with pytest.raises(ValidationError, match='simulation cannot certify'):
        Evaluation(evaluation_id=uuid4(), candidate_id=uuid4(), tier='simulated',
                   seed=42, repetition=0, status='completed', source_revision='test', gate='passed')


def test_missing_measurements_cannot_pass():
    with pytest.raises(ValidationError, match='passing requires'):
        Evaluation(evaluation_id=uuid4(), candidate_id=uuid4(), tier='measured',
                   seed=42, repetition=0, status='completed', source_revision='test', gate='passed')


def test_impossible_percentiles_are_rejected():
    with pytest.raises(ValidationError, match='percentiles must be ordered'):
        Metrics(p50_ms=100, p95_ms=50, p99_ms=200, requests_per_s=10,
                error_rate=0, cpu_seconds=1, memory_peak_mb=50, sample_count=100)
