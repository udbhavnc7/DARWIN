from copy import deepcopy
import pytest

from darwin.contracts import Constraints
from darwin.experiments import StartExperiment
from darwin.invariants import check_business, feasibility


def ledger():
    return {
        'products': [{'sku': 'a', 'available': 1, 'initial_stock': 2}],
        'orders': [{'request_key': 'k', 'order_id': 'o', 'amount_cents': 10, 'status': 'confirmed', 'sku': 'a', 'quantity': 1}],
        'reservations': [{'request_key': 'k', 'sku': 'a', 'quantity': 1, 'status': 'reserved'}],
        'captures': [{'request_key': 'k', 'order_id': 'o', 'amount_cents': 10, 'status': 'captured'}],
        'payment_effects': [{'request_key': 'k', 'order_id': 'o', 'amount_cents': 10}],
        'outbox': [{'job_key': 'k', 'order_id': 'o', 'status': 'completed'}],
        'deliveries': [{'job_key': 'k', 'order_id': 'o'}],
    }


def test_each_invariant_detects_its_counterexample():
    data = ledger()
    assert check_business(data, []) == []
    changes = [
        ('I-01', lambda d: d['payment_effects'].append(dict(d['payment_effects'][0]))),
        ('I-02', lambda d: d['products'][0].update(available=2)),
        ('I-03', lambda d: d['captures'][0].update(amount_cents=9)),
        ('I-04', lambda d: d['deliveries'].append(dict(d['deliveries'][0]))),
        ('I-05', lambda d: d['outbox'][0].update(status='pending')),
    ]
    for invariant, change in changes:
        broken = deepcopy(data)
        change(broken)
        assert invariant in {v['invariant_id'] for v in check_business(broken, [])}


def test_replay_history_and_accepted_job_loss_are_checked():
    history = [{'kind': 'replay', 'key': 'k', 'before': {}, 'after': {'changed': True}, 'responses_equal': True},
               {'kind': 'notification_restart', 'key': 'lost', 'pending_before_crash': True}]
    assert {v['invariant_id'] for v in check_business(ledger(), history)} == {'I-04', 'I-05'}


def test_fast_but_incorrect_candidate_cannot_pass():
    result = {'resource_limits_enforced': True, 'faults_verified': True,
              'invariant_coverage': ['I-01', 'I-02', 'I-03', 'I-04', 'I-05'],
              'metrics': {'error_rate': 0, 'p95_ms': .01}, 'logical_error_rate': 0,
              'recovery': [{'recovery_s': 5}], 'violations': []}
    assert feasibility(result, Constraints())['gate'] == 'passed'
    for key, value in [('violations', [{'invariant_id': 'I-01'}]), ('resource_limits_enforced', False),
                       ('logical_error_rate', .1), ('faults_verified', False),
                       ('invariant_coverage', []), ('recovery', [{'recovery_s': None}])]:
        assert feasibility({**result, key: value}, Constraints())['gate'] == 'failed'


@pytest.mark.parametrize('body', [
    {'mode': 'native_faults'},
    {'mode': 'native_faults', 'fault_scenarios': ['db_delay', 'db_delay']},
    {'mode': 'native_faults', 'fault_fixture': 'unsafe_retry', 'fault_scenarios': ['db_delay']},
    {'mode': 'native_benchmark', 'fault_fixture': 'unsafe_retry'},
])
def test_fault_requests_cannot_silently_skip_requested_work(body):
    with pytest.raises(ValueError):
        StartExperiment.model_validate(body)


def test_cleanup_failure_overrides_passing_fault_report(tmp_path):
    import json
    import os
    import time
    from darwin.experiments import Engine, TERMINAL, write_json
    if os.name != 'nt':
        pytest.skip('Native fault verification requires Windows')

    class Adapter:
        def __init__(self, request, candidate, folder, source):
            self.folder = folder

        def run(self, check):
            result = {'gate': 'passed', 'gate_reasons': [], 'violations': [], 'recovery': [],
                      'metrics': {}, 'resource_limits_enforced': True}
            write_json(self.folder / 'fault-report.json', result)
            return result

        def close(self):
            raise RuntimeError('Owned process survived')

    engine = Engine(tmp_path, Adapter)
    try:
        record = engine.submit(StartExperiment(mode='native_faults', fault_scenarios=['service_outage']))
        deadline = time.monotonic() + 10
        while record['status'] not in TERMINAL and time.monotonic() < deadline:
            time.sleep(.02)
            record = engine.store.get(record['experiment_id'])
        assert record['status'] == 'failed'
        evaluation = record['candidates'][0]['evaluations'][0]
        folder = tmp_path / record['experiment_id'] / evaluation['evaluation_id']
        assert evaluation['gate'] == 'failed'
        for name in ('manifest.json', 'measurement.json', 'fault-report.json'):
            assert json.loads((folder / name).read_text())['gate'] == 'failed'
    finally:
        engine.close()
