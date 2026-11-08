import pytest

from darwin.contracts import ExperimentRequest
from darwin.performance import metrics, schedule, summarize, WINDOW_S


def test_paired_plans_and_burst():
    normal = schedule('normal', 42)
    assert normal == schedule('normal', 42)
    assert normal != schedule('normal', 43)
    assert len({row['key'] for row in normal}) == len(normal) == 4 * WINDOW_S
    heavy = schedule('checkout_heavy', 42)
    assert sum(row['operation'] == 'checkout' for row in heavy) > sum(row['operation'] == 'checkout' for row in normal)
    burst = schedule('flash_sale', 42)
    assert len([row for row in burst if 4 <= row['offset_s'] < 8]) == 48
    assert len(burst) == 80


def test_percentile_errors_and_drain_boundary():
    samples = [{'latency_ms': i, 'ok': i != 20, 'finished_s': WINDOW_S + (i == 20)}
               for i in range(1, 21)]
    report = metrics(samples, .25, 60)
    assert (report['p50_ms'], report['p95_ms'], report['p99_ms']) == (10, 19, 20)
    assert report['error_rate'] == 1/20
    assert report['requests_per_s'] == 19 / WINDOW_S
    assert report['sample_count'] == 20


def test_all_repetitions_must_meet_constraints():
    observations = [{'latency_ms': 1, 'ok': True, 'finished_s': .1}]
    row = metrics(observations, .1, 100)
    evaluations = [{'status': 'completed', 'metrics': dict(row, p95_ms=p95)} for p95 in (1, 2, 100)]
    request = ExperimentRequest(constraints={'max_p95_ms': 10})
    result = summarize(evaluations, request)
    assert result['spread']['p95_ms'] == {'min': 1, 'median': 2, 'max': 100}
    assert result['performance_constraints_met'] is False
    assert result['gate'] == 'not_checked'
    with pytest.raises(ValueError, match='Incomplete'):
        summarize(evaluations[:2], request)


def test_measured_engine_pairs_seeds_and_keeps_correctness_gate_unchecked(tmp_path):
    import os
    import time
    from darwin.experiments import Engine, StartExperiment, TERMINAL

    if os.name != 'nt':
        pytest.skip('Native measurements require Windows')
    calls = []

    class MeasuredAdapter:
        def run(self, check):
            return {'metrics': metrics([{'latency_ms': 25, 'ok': True, 'finished_s': .1}], .1, 100),
                    'resource_limits_enforced': True}

        def close(self):
            pass

    def factory(request, candidate, folder, source):
        calls.append((request.seed, candidate['genome']['app_replicas']))
        return MeasuredAdapter()

    engine = Engine(tmp_path, factory)
    try:
        record = engine.submit(StartExperiment(mode='native_benchmark', genomes=[{}, {'app_replicas': 3}]))
        deadline = time.monotonic() + 10
        while record['status'] not in TERMINAL and time.monotonic() < deadline:
            time.sleep(.02)
            record = engine.store.get(record['experiment_id'])
        assert record['status'] == 'completed'
        assert calls == [(42, 1), (42, 3), (43, 3), (43, 1), (44, 1), (44, 3)]
        assert record['measurement_kind'] == 'measured'
        assert all(c['summary']['performance_constraints_met'] for c in record['candidates'])
        assert all(e['gate'] == 'not_checked' for c in record['candidates'] for e in c['evaluations'])
    finally:
        engine.close()
