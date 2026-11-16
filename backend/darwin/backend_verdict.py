"""Honest architecture comparison policy. Simulation never wins."""
from __future__ import annotations

from statistics import median

from darwin.backend_manifest import CHALLENGES

MIN_IMPROVEMENT_PCT = 8.0
MAX_ERROR_RATE = 0.05
REGRESSION_LIMIT_PCT = 5.0


def _pct(old: float, new: float, invert: bool = True) -> float:
    if not old:
        return 0.0
    change = (old - new) / old * 100
    return change if invert else -change


def decide_architecture(*, challenge: str, checks: list[dict],
                        baseline: dict, candidates: list[dict],
                        infrastructure_ok: bool = True,
                        infrastructure_error: str | None = None,
                        isolation_reason: str | None = None,
                        incomplete_reason: str | None = None) -> dict:
    policy = {
        'minimum_improvement_pct': MIN_IMPROVEMENT_PCT,
        'maximum_error_rate': MAX_ERROR_RATE,
        'regression_limit_pct': REGRESSION_LIMIT_PCT,
        'challenge': challenge,
        'evidence_kind': 'live',
        'primary_metric': CHALLENGES.get(challenge, {}).get('primary', 'p95_ms'),
        'simulation_cannot_win': True,
    }
    failed = [item for item in checks if not item.get('passed')]
    correctness = {
        'passed': not failed,
        'checks_passed': sum(1 for item in checks if item.get('passed')),
        'checks_total': len(checks),
        'failures': failed[:8],
        'note': 'HTTP availability is not business correctness. Counter monotonicity is the oracle for this adapter.',
    }

    def result(status, label, reason, winner=None, extra=None):
        payload = {
            'status': status, 'label': label, 'reason': reason, 'policy': policy,
            'correctness': correctness, 'per_size': [], 'winner_id': winner,
            'baseline_id': (baseline or {}).get('candidate_id'),
            'baseline_metrics': (baseline or {}).get('metrics'),
            'candidate_metrics': extra,
        }
        if extra:
            payload.update(extra)
        return payload

    if not infrastructure_ok:
        return result('FAILED_INFRASTRUCTURE', 'Infrastructure failed',
                      infrastructure_error or 'The isolated runner did not complete.')
    if isolation_reason:
        return result('FAILED_INFRASTRUCTURE', 'Isolated runner unavailable', isolation_reason)
    if not candidates:
        return result('NO_FEASIBLE_CANDIDATE', 'No candidate to evaluate',
                      'The adapter produced no deployable architecture candidate.')
    if failed:
        return result('REJECTED_INCORRECT', 'Rejected — correctness failed',
                      f'A candidate failed a required check: {failed[0].get("name")}. '
                      'Availability smoke tests are not enough to call an architecture safe.')
    if incomplete_reason:
        return result('INCONCLUSIVE', 'Inconclusive', incomplete_reason)

    measured = [item for item in candidates if item.get('metrics')]
    if not measured:
        return result('INCONCLUSIVE', 'Inconclusive',
                      'No live HTTP samples were retained, so no architecture is recommended.')

    primary = policy['primary_metric']
    base_metrics = baseline.get('metrics') or {}
    rows = []
    for item in measured:
        metrics = item['metrics']
        row = {
            'candidate_id': item['candidate_id'],
            'label': item.get('label') or item['candidate_id'],
            'p95_ms': metrics.get('p95_ms'),
            'requests_per_s': metrics.get('requests_per_s'),
            'error_rate': metrics.get('error_rate'),
            'cpu_seconds': metrics.get('cpu_seconds'),
            'memory_peak_mb': metrics.get('memory_peak_mb'),
            'recovery_s': item.get('recovery_s'),
            'replicas': item.get('replicas'),
            'workers': item.get('workers'),
        }
        rows.append(row)

    errors = [item for item in rows if (item.get('error_rate') or 0) > MAX_ERROR_RATE]
    if errors and challenge != 'recover':
        return result('BASELINE_RETAINED', 'Baseline retained',
                      f'{errors[0]["label"]} exceeded the {MAX_ERROR_RATE:.0%} error-rate gate.')

    def score(row):
        value = row.get(primary)
        if value is None:
            return None
        return value

    feasible = [row for row in rows if score(row) is not None]
    if not feasible:
        return result('INCONCLUSIVE', 'Inconclusive',
                      f'The primary metric {primary} was not measured for this challenge.')

    invert = primary in {'p95_ms', 'cpu_seconds', 'recovery_s'}
    ranked = sorted(feasible, key=lambda row: (score(row) if invert else -score(row), row['candidate_id']))
    best = ranked[0]
    base_value = base_metrics.get(primary) if primary != 'recovery_s' else baseline.get('recovery_s')
    cand_value = best.get(primary)
    if base_value in (None, 0) or cand_value is None:
        return result('INCONCLUSIVE', 'Inconclusive',
                      'Baseline and candidate could not be compared on the challenge metric.')
    improvement = _pct(float(base_value), float(cand_value), invert=invert)

    extra = {
        'change_pct': round(improvement, 2),
        'baseline_p95_ms': base_metrics.get('p95_ms'),
        'candidate_p95_ms': best.get('p95_ms'),
        'baseline_rps': base_metrics.get('requests_per_s'),
        'candidate_rps': best.get('requests_per_s'),
        'baseline_recovery_s': baseline.get('recovery_s'),
        'candidate_recovery_s': best.get('recovery_s'),
        'comparison': rows,
    }

    # A win on the primary metric must not hide a regression elsewhere. Cost,
    # tail latency and CPU count as part of the architecture decision.
    regressions = []
    for field, lower_is_better, label in (
            ('p95_ms', True, 'p95 latency'),
            ('cpu_seconds', True, 'CPU seconds per window'),
            ('memory_peak_mb', True, 'peak memory'),
            ('requests_per_s', False, 'requests per second')):
        if field == primary:
            continue
        base_v = base_metrics.get(field)
        cand_v = best.get(field)
        if not base_v or cand_v is None:
            continue
        worse = (cand_v > base_v * (1 + REGRESSION_LIMIT_PCT / 100) if lower_is_better
                 else cand_v < base_v * (1 - REGRESSION_LIMIT_PCT / 100))
        if worse:
            regressions.append({
                'metric': field,
                'label': label,
                'baseline': base_v,
                'candidate': cand_v,
                'change_pct': round((cand_v - base_v) / base_v * 100, 2),
            })
    extra['regressions'] = regressions
    if challenge == 'recover':
        extra['recovery_notes'] = [
            'Recovery is measured from fault injection until the gateway returns a healthy response.',
            'The gateway is probed every 50 ms while web-1 restarts. A run with zero failed '
            'probes means another replica served traffic and users saw no outage.',
        ]
    if regressions:
        detail = ', '.join(
            f'{item["label"]} {item["change_pct"]:+.1f}%' for item in regressions)
        return result(
            'TRADEOFF_REQUIRES_CHOICE', 'Tradeoff — choose',
            f'{best["label"]} was {improvement:.1f}% better on {primary} but regressed on '
            f'{detail}. DARWIN will not hide that cost behind a single winner score.',
            winner=best['candidate_id'], extra=extra,
        )

    if best['candidate_id'] == baseline.get('candidate_id'):
        return result('BASELINE_RETAINED', 'Baseline retained',
                      'No measured candidate beat the original architecture on the selected challenge.',
                      winner=best['candidate_id'], extra=extra)

    if improvement < MIN_IMPROVEMENT_PCT:
        return result('INCONCLUSIVE', 'Inconclusive',
                      f'{best["label"]} changed {primary} by {improvement:.1f}%, below the '
                      f'{MIN_IMPROVEMENT_PCT:.0f}% threshold. That difference may be noise.',
                      extra=extra)

    # Resource vs latency tradeoff: more replicas that are faster still cost more.
    if challenge == 'faster' and (best.get('replicas') or 1) > (baseline.get('replicas') or 1):
        return result('TRADEOFF_REQUIRES_CHOICE', 'Tradeoff — choose',
                      f'{best["label"]} was {improvement:.1f}% better on {primary} but uses more replicas. '
                      'DARWIN will not pick a winner when the objective does not include cost.',
                      winner=best['candidate_id'], extra=extra)

    explanation = (
        f'Your application currently uses {baseline.get("replicas", 1)} replica(s) and '
        f'{baseline.get("workers", 1)} worker(s). We tested {best["label"]} under a seeded HTTP '
        f'workload using an isolated Docker stack. {best["label"]} was {improvement:.1f}% better on '
        f'{primary} while {correctness["checks_passed"]}/{correctness["checks_total"]} correctness '
        f'checks passed. We recommend it for this challenge on this host only. This does not establish '
        f'production performance outside this isolated lab.'
    )
    extra['explanation'] = explanation
    return result('VERIFIED_IMPROVEMENT', 'Verified improvement', explanation,
                  winner=best['candidate_id'], extra=extra)


def pareto_rows(candidates: list[dict]) -> list[dict]:
    """Non-dominated candidates on (p95, error_rate, replica count)."""
    rows = []
    for item in candidates:
        metrics = item.get('metrics') or {}
        if not metrics:
            continue
        rows.append({
            'candidate_id': item['candidate_id'],
            'label': item.get('label'),
            'objectives': [
                float(metrics.get('p95_ms') or 0),
                float(metrics.get('error_rate') or 0),
                float(item.get('replicas') or 1),
            ],
            'penalty': 0,
            'genome_hash': item['candidate_id'],
        })
    if not rows:
        return []
    from darwin.search import fronts
    return [{'candidate_id': row['candidate_id'], 'objectives': row['objectives']}
            for row in fronts(rows)[0]]
