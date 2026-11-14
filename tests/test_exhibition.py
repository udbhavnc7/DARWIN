from datetime import datetime, timedelta, timezone

import pytest

from darwin.exhibition import (ESTIMATES, SCENARIOS, recorded_duration, recorded_examples,
                               scenario_catalog, scenario_request)


def record(mode, workload, status='completed', seconds=90, fixture='safe', feasible=0):
    started = datetime(2026, 11, 14, tzinfo=timezone.utc)
    candidates = [{'status': 'measured', 'objectives': [1, 1, 1] if index < feasible else None,
                   'evaluations': [{'gate': 'passed'}]}
                  for index in range(3)]
    return {'search_id': str(seconds), 'status': status,
            'started_at': started.isoformat(),
            'finished_at': (started + timedelta(seconds=seconds)).isoformat(),
            'request': {'mode': mode, 'workload_profile': workload, 'fault_fixture': fixture,
                        'algorithm': 'nsga2'},
            'candidates': candidates, 'pareto_ids': []}


def test_catalog_uses_recorded_median_and_falls_back_to_estimates():
    experiments = [record('native_benchmark', 'normal', seconds=170),
                   record('native_benchmark', 'normal', seconds=190),
                   record('native_benchmark', 'normal', status='failed', seconds=9999)]
    catalog = scenario_catalog(experiments, 'native', [], ['native_smoke', 'native_benchmark'])
    scenarios = {item['id']: item for item in catalog['scenarios']}
    assert scenarios['normal_comparison']['recorded_seconds'] == 180
    assert scenarios['normal_comparison']['duration_source'] == 'recorded'
    assert scenarios['flash_sale_stress']['recorded_seconds'] is None
    assert scenarios['flash_sale_stress']['estimated_seconds'] == ESTIMATES['flash_sale_stress']
    assert scenarios['unsafe_payment']['available'] is False


def test_each_scenario_builds_a_valid_measured_request():
    for scenario in SCENARIOS:
        request = scenario_request(scenario['id'], 'docker')
        assert request.mode == f'docker_{scenario["kind"]}'
        assert request.workload_profile == scenario['workload']
        assert len(request.genomes) == len(scenario['genomes'])
        assert request.budget.real_test_budget >= len(request.genomes) * request.budget.repetitions


def test_unknown_scenario_is_rejected():
    with pytest.raises(KeyError):
        scenario_request('invented')


def test_recorded_duration_ignores_failed_and_unrelated_runs():
    experiments = [record('native_faults', 'normal', fixture='safe', seconds=150),
                   record('native_faults', 'normal', fixture='unsafe_retry', seconds=90),
                   record('native_faults', 'normal', fixture='safe', status='cancelled', seconds=900)]
    assert recorded_duration(experiments, 'native_faults', 'normal', 'safe') == 150
    assert recorded_duration(experiments, 'docker_faults', 'normal', 'safe') is None


def test_recorded_examples_prefer_runs_with_multiple_feasible_candidates():
    searches = [record('native_faults', 'normal', feasible=1, seconds=10),
                record('native_faults', 'normal', feasible=3, seconds=20),
                record('native_faults', 'normal', feasible=0, seconds=30)]
    examples = recorded_examples(searches)
    assert examples['feasible']['feasible'] == 3
    assert examples['rejected']['feasible'] == 0
