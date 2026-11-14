"""Judge-facing demonstration scenarios built on the existing measured engine.

Scenarios only arrange existing experiment requests. They do not simulate,
skip gates, or change acceptance criteria; every run still produces the same
isolated measurements, fault traces and invariant checks as a manual run.
"""
from __future__ import annotations

from datetime import datetime
from statistics import median

from darwin.contracts import Budget, Genome
from darwin.experiments import StartExperiment

# Fallbacks are the durations recorded in docs/PHASE_10.md and the local
# experiment store. A live matching run replaces them when one exists.
ESTIMATES = {
    'quick_smoke': 30,
    'normal_comparison': 184,
    'flash_sale_stress': 180,
    'unsafe_payment': 100,
}

SCENARIOS = [
    {
        'id': 'quick_smoke',
        'kicker': 'Fast check',
        'title': 'Quick checkout smoke',
        'description': 'Start the isolated checkout stack and repeat one order with the same request key.',
        'expectation': 'One confirmed order and one payment effect after the repeat.',
        'kind': 'smoke',
        'workload': 'normal',
        'fault_fixture': 'safe',
        'fault_scenarios': [],
        'genomes': [Genome().model_dump()],
    },
    {
        'id': 'normal_comparison',
        'kicker': 'Performance',
        'title': 'Normal baseline vs candidate',
        'description': 'Compare the baseline with two replicas, a 10-second catalog cache and queued notifications.',
        'expectation': 'Measured latency, CPU and recovery spread for both configurations.',
        'kind': 'benchmark',
        'workload': 'normal',
        'fault_fixture': 'safe',
        'fault_scenarios': [],
        'genomes': [Genome().model_dump(),
                    Genome(app_replicas=2, catalog_cache_ttl_s=10,
                           notification_mode='queued', retry_policy='idempotent_only').model_dump()],
    },
    {
        'id': 'flash_sale_stress',
        'kicker': 'Stress',
        'title': 'Flash sale comparison',
        'description': 'Replay the flash-sale workload against the baseline and a three-replica cached candidate.',
        'expectation': 'A measured comparison under sustained concurrent checkout traffic.',
        'kind': 'benchmark',
        'workload': 'flash_sale',
        'fault_fixture': 'safe',
        'fault_scenarios': [],
        'genomes': [Genome().model_dump(),
                    Genome(app_replicas=3, catalog_cache_ttl_s=30,
                           notification_mode='queued', retry_policy='idempotent_only').model_dump()],
    },
    {
        'id': 'unsafe_payment',
        'kicker': 'Correctness',
        'title': 'Payment timeout with unsafe retry',
        'description': 'Lose the payment reply, retry without idempotency, and check the payment ledger.',
        'expectation': 'Gate rejection with I-01 and three payment effects for one request key.',
        'kind': 'faults',
        'workload': 'normal',
        'fault_fixture': 'unsafe_retry',
        'fault_scenarios': ['timeout_retry_duplicate'],
        'genomes': [Genome(notification_mode='queued').model_dump()],
    },
]


def _seconds(record):
    try:
        started = datetime.fromisoformat(record['started_at'])
        finished = datetime.fromisoformat(record['finished_at'])
        return max(0.0, (finished - started).total_seconds())
    except (KeyError, TypeError, ValueError):
        return None


def recorded_duration(experiments, mode, workload, fixture=None):
    durations = []
    for record in experiments:
        request = record.get('request', {})
        if record.get('status') != 'completed' or request.get('mode') != mode:
            continue
        if request.get('workload_profile') != workload:
            continue
        if fixture is not None and request.get('fault_fixture') != fixture:
            continue
        duration = _seconds(record)
        if duration:
            durations.append(duration)
    return round(median(durations)) if durations else None


def scenario_catalog(experiments, runtime='native', searches=None, available_modes=None):
    scenarios = []
    for scenario in SCENARIOS:
        mode = f'{runtime}_{scenario["kind"]}'
        recorded = recorded_duration(experiments, mode, scenario['workload'],
                                     scenario['fault_fixture'] if scenario['kind'] == 'faults' else None)
        item = {key: value for key, value in scenario.items() if key != 'genomes'}
        item.update(
            mode=mode,
            genome_count=len(scenario['genomes']),
            runtime=runtime,
            recorded_seconds=recorded,
            estimated_seconds=ESTIMATES[scenario['id']],
            duration_source='recorded' if recorded else 'estimate',
            available=available_modes is None or mode in available_modes,
        )
        scenarios.append(item)
    return {'scenarios': scenarios, 'saved_examples': recorded_examples(searches or [])}


def scenario_request(ident, runtime='native'):
    scenario = next((item for item in SCENARIOS if item['id'] == ident), None)
    if scenario is None:
        raise KeyError(ident)
    genomes = [Genome.model_validate(genome) for genome in scenario['genomes']]
    budget = Budget(real_test_budget=max(6, len(genomes) * 3), max_candidates=len(genomes),
                    repetitions=3, wall_clock_s=1800)
    return StartExperiment(
        mode=f'{runtime}_{scenario["kind"]}',
        workload_profile=scenario['workload'],
        fault_fixture=scenario['fault_fixture'],
        fault_scenarios=scenario['fault_scenarios'],
        genomes=genomes,
        budget=budget,
    )


def _feasible(record):
    return [candidate for candidate in record.get('candidates', []) if candidate.get('objectives')]


def _measured(record):
    return [candidate for candidate in record.get('candidates', [])
            if candidate.get('status') == 'measured']


def recorded_examples(searches):
    """Pick a completed feasible run and an explicit rejected run, if present."""
    completed = [record for record in searches if record.get('status') == 'completed']
    feasible = sorted((record for record in completed if len(_feasible(record)) >= 2),
                      key=lambda record: record.get('finished_at') or '', reverse=True)
    rejected = sorted((record for record in completed
                       if not _feasible(record) and _measured(record)),
                      key=lambda record: record.get('finished_at') or '', reverse=True)
    def summary(record):
        if not record:
            return None
        request = record.get('request', {})
        return {
            'search_id': record['search_id'],
            'algorithm': request.get('algorithm'),
            'workload': request.get('workload_profile'),
            'status': record.get('status'),
            'feasible': len(_feasible(record)),
            'pareto': len(record.get('pareto_ids', [])),
            'candidates': len(record.get('candidates', [])),
            'finished_at': record.get('finished_at'),
        }
    return {'feasible': summary(feasible[0] if feasible else None),
            'rejected': summary(rejected[0] if rejected else None)}
