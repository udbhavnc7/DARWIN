"""Deterministic, uncalibrated architecture screening for inspected repositories.

This module never imports, builds or executes repository code. It turns an
evidence-backed backend profile into a small queueing model, evaluates deployment
variants that only touch architecture controls, and returns a recommendation
that is always labelled ``SIMULATED`` and ``NOT_MEASURED``.

The model is intentionally simple and transparent. Every assumption is listed in
the output so a reader can decide whether a real deployment measurement is worth
running. A recommendation is a validation candidate, never a measured winner.
"""
from __future__ import annotations

import hashlib
import math
from statistics import median

SCREENING_ADAPTER_ID = 'architecture-screening-v1'
SCREENING_ADAPTER_VERSION = '1.0.0'
MODEL_VERSION = 'architecture-screening-v1'
EVIDENCE_KIND = 'simulated'

POLICY = {
    'minimum_improvement_pct': 8.0,
    'regression_limit_pct': 2.0,
    'maximum_error_rate_pct': 2.0,
    'maximum_error_delta_pct': 0.5,
    'maximum_cost_multiplier': 2.5,
    'primary_metric': 'modelled p95 latency',
    'evidence_kind': EVIDENCE_KIND,
}

CONTROL_LABELS = {
    'replicas': 'Service replicas',
    'cache_ttl_s': 'Cache TTL',
    'offload_jobs': 'Background offload',
    'retry_policy': 'Retry policy',
    'db_pool': 'Database pool',
    'read_replicas': 'Read replicas',
    'rate_limit': 'Rate limit',
}

CONTROL_UNITS = {
    'replicas': 'replica(s)',
    'cache_ttl_s': 's',
    'offload_jobs': 'enabled',
    'retry_policy': 'policy',
    'db_pool': 'connections',
    'read_replicas': 'replica(s)',
    'rate_limit': 'req/s',
}

CACHE_HIT_RATES = {0: 0.0, 10: 0.45, 30: 0.65, 90: 0.78, 300: 0.86}
SEEDS = {'quick': (7,), 'full': (7, 21, 2026)}


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _median(values) -> float:
    return float(median(list(values))) if values else 0.0


def _jitter(seed: int, variant_id: str) -> float:
    """Stable pseudo-noise: same seed and variant always produce the same value."""
    digest = hashlib.sha256(f'{seed}:{variant_id}'.encode()).digest()
    return (int.from_bytes(digest[:4], 'big') / 0xFFFFFFFF - 0.5) * 0.06


def _mmc_wait(arrival_rps: float, service_s: float, servers: int) -> float:
    """Erlang-C mean wait in seconds for an M/M/c approximation."""
    if arrival_rps <= 0 or service_s <= 0 or servers < 1:
        return 0.0
    load = arrival_rps * service_s
    if load >= servers:
        return service_s * 50.0
    term = 1.0
    total = 1.0
    for index in range(1, servers):
        term *= load / index
        total += term
    term *= load / servers
    probability_wait = term / (total * (1.0 - load / servers) + term)
    return probability_wait / max(1e-9, servers / service_s - arrival_rps)


def _workload(backend: dict) -> dict:
    routes = backend.get('routes') or []
    read_routes = [route for route in routes
                   if str(route.get('method', '')).upper() in ('GET', 'ANY')]
    read_ratio = len(read_routes) / len(routes) if routes else 0.6
    external = backend.get('external_services') or []
    datastores = backend.get('datastores') or []
    queues = backend.get('queues') or []
    services = backend.get('services') or []
    return {
        'name': 'synthetic architecture screening workload',
        'arrival_rate_rps': 40.0,
        'burst_factor': 1.6,
        'routes': len(routes),
        'read_routes': len(read_routes),
        'read_ratio': _round(read_ratio, 3),
        'write_ratio': _round(1.0 - read_ratio, 3),
        'external_integrations': min(4, len(external)),
        'datastores': len(datastores),
        'queues': len(queues),
        'auth': bool(backend.get('auth')),
        'services': max(1, len(services)),
        'note': (
            'Synthetic request mix derived from detected route methods. It is not observed '
            'production traffic and no repository endpoint was called.'
        ),
    }


def _baseline_controls(controls: set[str]) -> dict:
    baseline = {'replicas': 1}
    if 'cache_ttl_s' in controls:
        baseline['cache_ttl_s'] = 0
    if 'offload_jobs' in controls:
        baseline['offload_jobs'] = False
    if 'retry_policy' in controls:
        baseline['retry_policy'] = 'none'
    if 'db_pool' in controls:
        baseline['db_pool'] = 4
    if 'read_replicas' in controls:
        baseline['read_replicas'] = 0
    if 'rate_limit' in controls:
        baseline['rate_limit'] = 0
    return baseline


def _metrics(controls: dict, workload: dict, seed: int, variant_id: str) -> dict:
    external = int(workload['external_integrations'])
    datastores = int(workload['datastores'])
    cache_ttl = int(controls.get('cache_ttl_s', 0))
    offload = bool(controls.get('offload_jobs'))
    retry = controls.get('retry_policy') == 'idempotent_only'
    replicas = int(controls.get('replicas', 1))
    db_pool = int(controls.get('db_pool', 0))
    read_replicas = int(controls.get('read_replicas', 0))
    rate_limit = int(controls.get('rate_limit', 0))
    read_ratio = float(workload['read_ratio'])
    hit_rate = CACHE_HIT_RATES.get(cache_ttl, 0.0)

    service_ms = 6.0
    service_ms += 2.5 * external * (0.35 if offload else 1.0)
    service_ms += 2.0 * min(2, datastores) + 1.0 * max(0, datastores - 2)
    service_ms += 1.2 if workload['auth'] else 0.0
    service_ms += 0.8 * max(0, int(workload['services']) - 1)
    if offload and (external or workload['queues']):
        service_ms += 1.0  # enqueue hop
    if retry:
        service_ms += 1.5
    if cache_ttl:
        service_ms *= 1.0 - 0.45 * hit_rate * read_ratio
        service_ms += 0.8 * hit_rate * read_ratio
    service_ms *= 1.0 + _jitter(seed, variant_id)

    arrival = float(workload['arrival_rate_rps'])
    servers = max(1, replicas * 8)
    service_s = service_ms / 1000.0
    utilization = arrival * service_s / servers
    wait_ms = _mmc_wait(arrival, service_s, servers) * 1000.0
    p50_ms = service_ms + wait_ms
    p95_ms = service_ms + wait_ms * 2.2 + service_ms * 0.15

    db_wait_ms = 0.0
    if datastores:
        db_capacity = max(1, db_pool) + read_replicas * 3
        db_service_s = 3.5 * (0.6 if read_replicas else 1.0) / 1000.0
        db_arrival = arrival * (0.7 if read_replicas else 0.9)
        db_arrival *= 1.0 - 0.5 * hit_rate * read_ratio
        db_wait_ms = _mmc_wait(db_arrival, db_service_s, db_capacity) * 1000.0
        db_wait_ms += db_service_s * 1000.0 * 0.2
        p50_ms += db_wait_ms
        p95_ms += db_wait_ms * 1.4

    burst = arrival * float(workload['burst_factor'])
    rejected_ratio = 0.0
    if rate_limit and rate_limit < burst:
        rejected_ratio = min(0.6, (burst - rate_limit) / burst)
        p95_ms *= 1.0 - 0.12 * min(1.0, rejected_ratio * 2.0)

    error_pct = 0.2
    if external:
        error_pct += 1.1 * min(2, external) * (0.35 if retry else 1.0) * (0.5 if offload else 1.0)
    if utilization > 0.9:
        error_pct += (utilization - 0.9) * 20.0
    if db_wait_ms > 60:
        error_pct += min(1.5, (db_wait_ms - 60) / 120.0)
    error_pct += rejected_ratio * 100.0

    throughput = min(arrival, servers / service_s) * (1.0 - rejected_ratio)
    cost_index = (
        replicas
        + (0.25 if cache_ttl else 0.0)
        + (0.35 if offload else 0.0)
        + (0.05 if retry else 0.0)
        + max(0.0, (db_pool - 4) * 0.08)
        + read_replicas * 0.6
        + (0.1 if rate_limit else 0.0)
    )
    return {
        'seed': seed,
        'p50_ms': _round(p50_ms),
        'p95_ms': _round(p95_ms),
        'throughput_rps': _round(throughput),
        'error_rate_pct': _round(error_pct, 3),
        'cost_index': _round(cost_index, 2),
        'utilization': _round(utilization, 3),
        'db_wait_ms': _round(db_wait_ms),
        'rejected_pct': _round(rejected_ratio * 100.0, 2),
    }


def _evaluate(controls: dict, workload: dict, seeds: tuple[int, ...], variant_id: str) -> dict:
    runs = [_metrics(controls, workload, seed, variant_id) for seed in seeds]
    return {
        'metrics': {
            'p50_ms': _round(_median(run['p50_ms'] for run in runs)),
            'p95_ms': _round(_median(run['p95_ms'] for run in runs)),
            'throughput_rps': _round(_median(run['throughput_rps'] for run in runs)),
            'error_rate_pct': _round(_median(run['error_rate_pct'] for run in runs), 3),
            'cost_index': _round(_median(run['cost_index'] for run in runs), 2),
            'utilization': _round(_median(run['utilization'] for run in runs), 3),
            'db_wait_ms': _round(_median(run['db_wait_ms'] for run in runs)),
        },
        'runs': runs,
    }


def _variant_id(controls: dict) -> str:
    return '|'.join(f'{key}={controls[key]}' for key in sorted(controls))


def _merge(base: dict, patch: dict) -> dict:
    merged = dict(base)
    merged.update(patch)
    return merged


def _apply_changes(baseline: dict, records: list[dict]) -> dict | None:
    """Combine variants only when they do not set the same control differently."""
    merged = dict(baseline)
    chosen: dict = {}
    for record in records:
        for change in record['changes']:
            control = change['control']
            if control in chosen and chosen[control] != change['to']:
                return None
            chosen[control] = change['to']
            merged[control] = change['to']
    return merged


def _single_variants(controls: set[str]) -> list[dict]:
    variants = []
    if 'replicas' in controls:
        variants.append({'replicas': 2})
        variants.append({'replicas': 3})
    if 'cache_ttl_s' in controls:
        variants.append({'cache_ttl_s': 10})
        variants.append({'cache_ttl_s': 30})
        variants.append({'cache_ttl_s': 90})
    if 'offload_jobs' in controls:
        variants.append({'offload_jobs': True})
    if 'retry_policy' in controls:
        variants.append({'retry_policy': 'idempotent_only'})
    if 'db_pool' in controls:
        variants.append({'db_pool': 8})
    if 'read_replicas' in controls:
        variants.append({'read_replicas': 1})
    if 'rate_limit' in controls:
        variants.append({'rate_limit': 60})
        variants.append({'rate_limit': 90})
    return variants


def _control_changes(baseline: dict, candidate: dict) -> list[dict]:
    changes = []
    for key in sorted(candidate):
        if candidate[key] == baseline.get(key):
            continue
        changes.append({
            'control': key,
            'label': CONTROL_LABELS.get(key, key),
            'from': baseline.get(key),
            'to': candidate[key],
            'unit': CONTROL_UNITS.get(key, ''),
        })
    return changes


def _change_phrase(change: dict) -> str:
    control = change['control']
    value = change['to']
    if control == 'cache_ttl_s':
        return f"Cache TTL {int(value)}s"
    if control == 'offload_jobs':
        return 'Background offload' if value else 'Background offload off'
    if control == 'replicas':
        return f"Service replicas ×{value}"
    if control == 'read_replicas':
        return f"{int(value)} read replica" + ('' if int(value) == 1 else 's')
    if control == 'db_pool':
        return f"Database pool {int(value)}"
    if control == 'rate_limit':
        return f"Rate limit {int(value)} req/s"
    if control == 'retry_policy':
        return f"Retry policy {str(value).replace('_', '-')}"
    return f"{change['label']} {change['from']}→{change['to']}"


def _score(change_pct: float, error_delta: float, cost_multiplier: float) -> float:
    return change_pct - max(0.0, error_delta) * 8.0 - max(0.0, cost_multiplier - 1.0) * 2.0


def _qualifies(change_pct: float, error_pct: float, error_delta: float,
               cost_multiplier: float) -> bool:
    return (
        change_pct >= POLICY['minimum_improvement_pct']
        and error_pct <= POLICY['maximum_error_rate_pct']
        and error_delta <= POLICY['maximum_error_delta_pct']
        and cost_multiplier <= POLICY['maximum_cost_multiplier']
    )


def _variant_record(variant_id: str, controls: dict, baseline_controls: dict,
                    evaluated: dict, baseline: dict) -> dict:
    metrics = evaluated['metrics']
    baseline_metrics = baseline['metrics']
    change_pct = (
        (baseline_metrics['p95_ms'] - metrics['p95_ms']) / baseline_metrics['p95_ms'] * 100.0
        if baseline_metrics['p95_ms'] else 0.0
    )
    error_delta = metrics['error_rate_pct'] - baseline_metrics['error_rate_pct']
    cost_multiplier = (metrics['cost_index'] / baseline_metrics['cost_index']
                       if baseline_metrics['cost_index'] else 1.0)
    changes = _control_changes(baseline_controls, controls)
    return {
        'id': variant_id,
        'label': ' + '.join(_change_phrase(change) for change in changes) or 'Detected baseline',
        'controls': dict(controls),
        'changes': changes,
        'metrics': metrics,
        'runs': evaluated['runs'],
        'change_pct': _round(change_pct, 2),
        'error_delta_pct': _round(error_delta, 3),
        'cost_multiplier': _round(cost_multiplier, 2),
        'qualifies': _qualifies(change_pct, metrics['error_rate_pct'],
                                error_delta, cost_multiplier),
        'score': _round(_score(change_pct, error_delta, cost_multiplier), 2),
    }


def _assumptions(workload: dict, controls: set[str]) -> list[str]:
    return [
        'Traffic is a synthetic 40 request/s workload derived from the inspected route mix; '
        'it is not observed production traffic.',
        'Service and database times are transparent model parameters. They are not benchmarked '
        'from the repository.',
        'The baseline is the detected architecture with one service replica and no cache, '
        'retry, queue offload or read replica unless source evidence proves otherwise.',
        'Cache hit rates are fixed assumptions by TTL (10 s: 45%, 30 s: 65%, 90 s: 78%). '
        'They are not measured cache statistics.',
        'The model assumes the service and database are the bottlenecks. Network jitter, '
        'garbage collection, provider outages and cold starts are not simulated.',
        'Only deployment-level controls are varied. Application code, schemas and business '
        'logic are unchanged.',
        'No repository code, dependency, package manager, container or service was executed.',
        'A recommendation is an uncalibrated candidate for real deployment validation. It is '
        'not a measured winner.',
        f'Applicable controls for this source: {", ".join(sorted(controls)) or "none"}.',
        f'The workload assumes {workload["routes"]} route(s), {workload["datastores"]} data '
        f'store(s), {workload["external_integrations"]} external call target(s) and '
        f'{workload["services"]} service(s).',
    ]


def _limitations() -> list[str]:
    return [
        'No runtime measurement, load test or production trace was collected.',
        'The model is not calibrated against this repository or its deployment.',
        'Relative modelled differences must not be quoted as measured speedups.',
        'Validate the candidate with a real staging deployment and observed traffic before '
        'changing production.',
    ]


def _recommendation(record: dict, baseline: dict, baseline_controls: dict,
                    seeds: tuple[int, ...], mode: str) -> dict:
    baseline_p95 = baseline['metrics']['p95_ms']
    baseline_error = baseline['metrics']['error_rate_pct']
    if record is None:
        return {
            'status': 'BASELINE_RETAINED',
            'label': 'Baseline retained',
            'summary': (
                'No screened architecture variant met the improvement, error-rate and cost '
                'policy. The detected baseline remains the recommendation, and no runtime '
                'was measured.'
            ),
            'candidate_id': 'baseline',
            'controls': dict(baseline_controls),
            'changes': [],
            'modelled_change_pct': 0.0,
            'baseline_p95_ms': baseline_p95,
            'candidate_p95_ms': baseline_p95,
            'error_rate_pct': baseline_error,
            'cost_multiplier': 1.0,
            'measured': False,
            'evidence_kind': EVIDENCE_KIND,
            'seed_sensitivity': {'seeds': list(seeds), 'min_change_pct': 0.0,
                                 'max_change_pct': 0.0},
        }
    controls = record['controls']
    changes = record['changes']
    if record['change_pct'] >= 0:
        summary = (
            f"{record['label']} models p95 latency {record['change_pct']:.1f}% lower with a "
            f"{record['cost_multiplier']:.2f}× cost index. This is a SIMULATED candidate; "
            'validate it on a real deployment before changing production.'
        )
    else:
        summary = (
            f"{record['label']} models p95 latency {abs(record['change_pct']):.1f}% higher with a "
            f"{record['cost_multiplier']:.2f}× cost index. The detected baseline remains the safer "
            'modelled choice.'
        )
    seed_changes = []
    for run in record['runs']:
        seed_changes.append(
            (baseline_p95 - run['p95_ms']) / baseline_p95 * 100.0 if baseline_p95 else 0.0
        )
    return {
        'status': 'IMPROVEMENT_CANDIDATE',
        'label': 'Architecture improvement candidate',
        'summary': summary,
        'candidate_id': record['id'],
        'controls': controls,
        'changes': changes,
        'modelled_change_pct': record['change_pct'],
        'baseline_p95_ms': baseline_p95,
        'candidate_p95_ms': record['metrics']['p95_ms'],
        'error_rate_pct': record['metrics']['error_rate_pct'],
        'cost_multiplier': record['cost_multiplier'],
        'measured': False,
        'evidence_kind': EVIDENCE_KIND,
        'seed_sensitivity': {
            'seeds': list(seeds),
            'min_change_pct': _round(min(seed_changes)) if seed_changes else 0.0,
            'max_change_pct': _round(max(seed_changes)) if seed_changes else 0.0,
        },
        'mode': mode,
    }


def screen_repository(analysis: dict, mode: str = 'quick') -> dict:
    """Screen one inspected project and return a simulated recommendation."""
    if mode not in SEEDS:
        raise ValueError('Unknown screening mode')
    screening = analysis.get('screening') or {}
    if not screening.get('available'):
        raise ValueError('Architecture screening is not available for this source')
    backend = (analysis.get('project') or {}).get('backend') or {}
    if not backend.get('detected') or not backend.get('services'):
        raise ValueError('No backend service was detected for screening')

    controls = set(screening.get('controls') or [])
    controls.add('replicas')
    baseline_controls = _baseline_controls(controls)
    workload = _workload(backend)
    seeds = SEEDS[mode]
    baseline_id = _variant_id(baseline_controls)
    baseline = _evaluate(baseline_controls, workload, seeds, baseline_id)

    records = []
    seen = {baseline_id}
    for patch in _single_variants(controls):
        controls_for_variant = _merge(baseline_controls, patch)
        variant_id = _variant_id(controls_for_variant)
        if variant_id in seen:
            continue
        seen.add(variant_id)
        evaluated = _evaluate(controls_for_variant, workload, seeds, variant_id)
        records.append(_variant_record(variant_id, controls_for_variant, baseline_controls,
                                       evaluated, baseline))

    ranked = sorted(records, key=lambda item: item['score'], reverse=True)
    top = ranked[:4]
    combos: list[dict] = []
    if top:
        combined = _apply_changes(baseline_controls, top[:2 if mode == 'quick' else 3])
        if combined is not None:
            combos.append(combined)
        if mode == 'full':
            for index, left in enumerate(top):
                for right in top[index + 1:]:
                    pair = _apply_changes(baseline_controls, [left, right])
                    if pair is not None:
                        combos.append(pair)
    for controls_for_variant in combos:
        variant_id = _variant_id(controls_for_variant)
        if variant_id in seen:
            continue
        seen.add(variant_id)
        evaluated = _evaluate(controls_for_variant, workload, seeds, variant_id)
        records.append(_variant_record(variant_id, controls_for_variant, baseline_controls,
                                       evaluated, baseline))

    records.sort(key=lambda item: item['score'], reverse=True)
    qualifying = [record for record in records if record['qualifies']]
    best = qualifying[0] if qualifying else ranked[0] if ranked else None
    if best is not None and not best['qualifies']:
        if best['change_pct'] >= POLICY['regression_limit_pct']:
            status = 'INCONCLUSIVE'
        else:
            status = 'BASELINE_RETAINED'
        recommendation = _recommendation(None, baseline, baseline_controls, seeds, mode)
        if status == 'INCONCLUSIVE':
            summary = (
                f"The best screened variant modelled p95 latency {best['change_pct']:.1f}% lower, "
                'but it did not clear the policy without an unacceptable error-rate or cost '
                'trade-off. No runtime was measured, so the screening is inconclusive.'
            )
        else:
            summary = (
                'No screened architecture variant cleared the improvement policy without an '
                'unacceptable error-rate or cost trade-off. No runtime was measured, so the '
                'detected baseline remains the recommendation.'
            )
        recommendation.update({
            'status': status,
            'label': 'Inconclusive screening' if status == 'INCONCLUSIVE'
            else 'Baseline retained',
            'summary': summary,
            'candidate_id': best['id'],
            'controls': best['controls'],
            'changes': best['changes'],
            'modelled_change_pct': best['change_pct'],
            'candidate_p95_ms': best['metrics']['p95_ms'],
            'error_rate_pct': best['metrics']['error_rate_pct'],
            'cost_multiplier': best['cost_multiplier'],
        })
    elif best is not None:
        recommendation = _recommendation(best, baseline, baseline_controls, seeds, mode)
        sensitivity = recommendation['seed_sensitivity']
        if sensitivity['min_change_pct'] < 0:
            recommendation.update({
                'status': 'INCONCLUSIVE',
                'label': 'Inconclusive screening',
                'summary': (
                    'The modelled improvement changes sign across deterministic seeds. '
                    'No runtime was measured, so this is not a stable recommendation.'
                ),
            })
    else:
        recommendation = _recommendation(None, baseline, baseline_controls, seeds, mode)

    variants = [{
        'id': baseline_id,
        'label': 'Detected baseline',
        'controls': dict(baseline_controls),
        'changes': [],
        'metrics': baseline['metrics'],
        'runs': baseline['runs'],
        'change_pct': 0.0,
        'error_delta_pct': 0.0,
        'cost_multiplier': 1.0,
        'qualifies': True,
        'score': 0.0,
    }] + records
    variants.sort(key=lambda item: (item['change_pct'], item['score']), reverse=True)

    verdict = {
        'status': 'NOT_MEASURED',
        'label': 'Simulated architecture recommendation',
        'reason': recommendation['summary'],
        'policy': {
            'evidence_kind': EVIDENCE_KIND,
            'label': 'SIMULATED',
            'not_measured': True,
            'minimum_improvement_pct': POLICY['minimum_improvement_pct'],
            'regression_limit_pct': POLICY['regression_limit_pct'],
            'maximum_error_rate_pct': POLICY['maximum_error_rate_pct'],
            'maximum_cost_multiplier': POLICY['maximum_cost_multiplier'],
            'primary_rule': 'modelled p95 latency, gated by error rate and cost index',
        },
        'per_size': [],
        'correctness': {
            'passed': True,
            'checks_passed': 0,
            'checks_total': 0,
            'failures': [],
            'note': 'No repository code was executed. Model assumptions are listed in screening.assumptions.',
        },
        'recommendation': recommendation,
    }
    addressed = []
    for hotspot in analysis.get('hotspots') or []:
        control = hotspot.get('control')
        addressed.append({
            'hotspot': hotspot.get('id'),
            'title': hotspot.get('title'),
            'control': control,
            'addressed': bool(control and any(
                change['control'] == control for change in recommendation['changes']
            )),
        })
    return {
        'adapter_id': SCREENING_ADAPTER_ID,
        'adapter_version': SCREENING_ADAPTER_VERSION,
        'model_version': MODEL_VERSION,
        'evaluation_type': 'architecture_screening',
        'evidence_kind': EVIDENCE_KIND,
        'label': 'SIMULATED',
        'not_measured': True,
        'mode': mode,
        'seeds': list(seeds),
        'workload': workload,
        'controls': sorted(controls),
        'baseline': {
            'label': 'Detected baseline',
            'controls': dict(baseline_controls),
            'metrics': baseline['metrics'],
            'runs': baseline['runs'],
        },
        'variants': variants,
        'recommendation': recommendation,
        'verdict': verdict,
        'policy': dict(POLICY),
        'assumptions': _assumptions(workload, controls),
        'limitations': _limitations(),
        'hotspots_addressed': addressed,
    }


def empty_screening_verdict(reason: str) -> dict:
    """A cancelled or failed screening must never look like a recommendation."""
    recommendation = {
        'status': 'INCONCLUSIVE',
        'label': 'No recommendation',
        'summary': reason,
        'candidate_id': 'baseline',
        'controls': {},
        'changes': [],
        'modelled_change_pct': 0.0,
        'measured': False,
        'evidence_kind': EVIDENCE_KIND,
    }
    return {
        'status': 'NOT_MEASURED',
        'label': 'Screening did not complete',
        'reason': reason,
        'policy': {'evidence_kind': EVIDENCE_KIND, 'label': 'SIMULATED',
                   'not_measured': True, **POLICY},
        'per_size': [],
        'correctness': {'passed': False, 'checks_passed': 0, 'checks_total': 0,
                        'failures': []},
        'recommendation': recommendation,
    }
