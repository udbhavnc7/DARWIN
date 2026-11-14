import os
import random
import threading
import time

import pytest

from darwin.architecture import deployment_resources, genome_hash
from darwin.contracts import Budget, Genome
from darwin.experiments import Engine, TERMINAL
from darwin.search import SearchEngine, SearchRequest, fronts, objectives, propose, select_population


def candidate(name, values, penalty=0):
    return {'genome_hash': name, 'objectives': values, 'penalty': penalty}


def test_constrained_front_and_crowding_keep_tradeoffs():
    rows = [candidate('a', [1, 3, 2]), candidate('b', [3, 1, 2]),
            candidate('c', [4, 4, 4]), candidate('unsafe', None, 1)]
    assert {row['genome_hash'] for row in fronts(rows)[0]} == {'a', 'b'}
    assert {row['genome_hash'] for row in select_population(rows, 2)} == {'a', 'b'}
    assert fronts(rows)[-1][0]['genome_hash'] == 'unsafe'


def test_partial_or_unchecked_measurements_never_enter_front():
    evaluation = {'gate': 'passed', 'status': 'completed', 'tier': 'measured',
                  'metrics': {'p95_ms': 1, 'cpu_seconds': 1, 'recovery_s': 5}}
    assert objectives({'evaluations': [evaluation] * 3}, 3) == [1, 1, 5]
    assert objectives({'evaluations': [evaluation] * 2}, 3) is None
    assert objectives({'evaluations': [{**evaluation, 'gate': 'not_checked'}] * 3}, 3) is None
    assert objectives({'evaluations': [{**evaluation, 'tier': 'simulated'}] * 3}, 3) is None


@pytest.mark.parametrize('algorithm', ['random', 'hill_climbing', 'nsga2'])
@pytest.mark.skipif(os.name != 'nt', reason='Native measured search requires Windows')
def test_seeded_proposals_are_unique_bounded_and_reproducible(algorithm):
    request = SearchRequest(algorithm=algorithm)
    baseline = Genome()
    parent = {'genome': baseline.model_dump(), 'genome_hash': genome_hash(baseline),
              'objectives': [100, 5, 5], 'penalty': 0}
    seen = {parent['genome_hash']}
    first = propose(request, random.Random(42), seen, [parent])
    assert first == propose(request, random.Random(42), seen, [parent])
    assert len({genome_hash(genome) for genome, _ in first}) == len(first)
    assert not seen & {genome_hash(genome) for genome, _ in first}


@pytest.mark.skipif(os.name != 'nt', reason='Native measured search requires Windows')
def test_proposals_stay_inside_custom_resource_budget():
    request = SearchRequest(population_size=36, budget=Budget(max_candidates=36, sandbox_cpu_cores=3))
    proposals = propose(request, random.Random(42), set(), [])
    assert proposals[0] == (Genome(), [])
    assert 1 < len(proposals) < 36
    assert all(deployment_resources(genome)[0] <= 3 + 1e-9 for genome, _ in proposals)


class MeasuredAdapter:
    def __init__(self, request, genome, folder, source):
        self.folder = folder

    def run(self, check):
        check()
        return {'resource_limits_enforced': True, 'gate': 'passed', 'gate_reasons': [],
                'violations': [], 'recovery': [],
                'metrics': {'p50_ms': 10, 'p95_ms': 20, 'p99_ms': 30, 'sample_count': 48,
                            'requests_per_s': 4, 'error_rate': 0, 'cpu_seconds': 1,
                            'memory_peak_mb': 100, 'recovery_s': 5}}

    def close(self):
        pass


def wait(search, ident):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        record = search.store.get(ident)
        if record['status'] in TERMINAL:
            return record
        time.sleep(.02)
    pytest.fail('Search did not terminate')


@pytest.mark.skipif(os.name != 'nt', reason='Native measured search requires Windows')
def test_search_measures_full_groups_evolves_and_survives_restart(tmp_path):
    engine = Engine(tmp_path, MeasuredAdapter)
    search = SearchEngine(engine)
    try:
        request = SearchRequest(generations=2, promotions_per_generation=1,
                                budget=Budget(real_test_budget=6), use_simulator=False)
        result = wait(search, search.submit(request)['search_id'])
        assert result['status'] == 'completed', result.get('error')
        assert result['attempts_used'] == 6
        assert len(result['experiment_ids']) == 2
        assert len(result['pareto_ids']) == 2
        assert any(row['parent_ids'] for row in result['candidates'] if row['generation'] == 1)
        assert len({row['genome_hash'] for row in result['candidates']}) == len(result['candidates'])
    finally:
        search.close()
        engine.close()
    engine = Engine(tmp_path, MeasuredAdapter)
    search = SearchEngine(engine)
    try:
        assert search.store.get(result['search_id']) == result
    finally:
        search.close()
        engine.close()


@pytest.mark.skipif(os.name != 'nt', reason='Native measured search requires Windows')
@pytest.mark.parametrize('cancel_child', [False, True])
def test_search_cancellation_waits_for_child_cleanup(tmp_path, cancel_child):
    started = threading.Event()
    closed = threading.Event()
    class Blocking(MeasuredAdapter):
        def run(self, check):
            started.set()
            while True:
                check()
                time.sleep(.02)
        def close(self):
            closed.set()
    engine = Engine(tmp_path, Blocking)
    search = SearchEngine(engine)
    try:
        ident = search.submit(SearchRequest(use_simulator=False))['search_id']
        assert started.wait(5)
        if cancel_child:
            child = engine.store.all()[0]
            engine.cancel(child['experiment_id'])
        else:
            search.cancel(ident)
        result = wait(search, ident)
        assert result['status'] == 'cancelled'
        assert result['attempts_used'] == 1
        assert closed.is_set()
    finally:
        search.close()
        engine.close()
