"""Transparent verdict policy for Real Project Mode.

The policy is intentionally conservative. A candidate is eligible for promotion
only when it passes every correctness check and the measured improvement clears
a product threshold with consistent paired evidence. No p-values are implied.
"""
from __future__ import annotations

from math import ceil
from statistics import median

MIN_IMPROVEMENT_PCT = 5.0
REGRESSION_LIMIT_PCT = 5.0
MIN_PAIRED_WIN_RATE = 0.80


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _per_size(summaries: list[dict]) -> list[dict]:
    sizes = sorted({item['size'] for item in summaries})
    result = []
    for size in sizes:
        rows = [item for item in summaries if item['size'] == size]
        baseline = [value for item in rows for value in item.get('baseline_samples_ns', [])]
        candidate = [value for item in rows for value in item.get('candidate_samples_ns', [])]
        if not baseline or not candidate:
            continue
        baseline_median = median(baseline)
        candidate_median = median(candidate)
        improvement = ((baseline_median - candidate_median) / baseline_median * 100) if baseline_median else 0.0
        wins = sum(1 for base, cand in zip(baseline, candidate) if cand < base)
        paired = [((base - cand) / base * 100) for base, cand in zip(baseline, candidate) if base > 0]
        result.append({
            'size': size,
            'seeds': sorted({item['seed'] for item in rows}),
            'baseline_median_ms': baseline_median / 1_000_000,
            'candidate_median_ms': candidate_median / 1_000_000,
            'baseline_p95_ms': percentile(baseline, 0.95) / 1_000_000,
            'candidate_p95_ms': percentile(candidate, 0.95) / 1_000_000,
            'baseline_range_ms': [min(baseline) / 1_000_000, max(baseline) / 1_000_000],
            'candidate_range_ms': [min(candidate) / 1_000_000, max(candidate) / 1_000_000],
            'change_pct': round(improvement, 2),
            'paired_win_rate': round(wins / len(baseline), 3),
            'paired_lower_decile_pct': round(percentile(paired, 0.10) or 0.0, 2),
            'samples': len(baseline),
        })
    return result


def decide(*, parity_passed: bool, checks: list[dict], summaries: list[dict],
           candidate_count: int = 1, infrastructure_ok: bool = True,
           infrastructure_error: str | None = None) -> dict:
    """Return one of the directive's result statuses plus a plain-language reason."""
    policy = {
        'minimum_improvement_pct': MIN_IMPROVEMENT_PCT,
        'regression_limit_pct': REGRESSION_LIMIT_PCT,
        'minimum_paired_win_rate': MIN_PAIRED_WIN_RATE,
        'primary_rule': 'largest measured ledger size',
        'evidence_kind': 'live',
    }
    if not infrastructure_ok:
        return {
            'status': 'FAILED_INFRASTRUCTURE',
            'label': 'Infrastructure failed',
            'reason': infrastructure_error or 'The benchmark runtime did not complete.',
            'policy': policy,
            'per_size': [],
            'correctness': {'passed': False, 'checks_passed': 0, 'checks_total': len(checks), 'failures': []},
        }
    if candidate_count < 1:
        return {
            'status': 'NO_FEASIBLE_CANDIDATE',
            'label': 'No candidate to evaluate',
            'reason': 'The adapter produced no source-compatible candidate for this revision.',
            'policy': policy,
            'per_size': [],
            'correctness': {'passed': False, 'checks_passed': 0, 'checks_total': len(checks), 'failures': []},
        }
    failed = [item for item in checks if not item.get('passed')]
    if not parity_passed:
        faster = any(
            item.get('candidate_median_ns', 0) < item.get('baseline_median_ns', 0)
            for item in summaries
        )
        detail = failed[0]['name'] + (f": {failed[0]['detail']}" if failed and failed[0].get('detail') else '') if failed else 'correctness comparison failed'
        prefix = 'faster, but ' if faster else ''
        return {
            'status': 'REJECTED_INCORRECT',
            'label': 'Rejected — incorrect result',
            'reason': (
                f'The candidate was {prefix}rejected because {detail}. '
                'A finance report that changes a total is not an improvement.'
            ),
            'policy': policy,
            'per_size': _per_size(summaries),
            'correctness': {
                'passed': False,
                'checks_passed': sum(1 for item in checks if item.get('passed')),
                'checks_total': len(checks),
                'failures': failed[:8],
            },
        }
    if not summaries:
        return {
            'status': 'NOT_MEASURED',
            'label': 'Not measured',
            'reason': 'Correctness checks produced no timed samples, so no performance claim is possible.',
            'policy': policy,
            'per_size': [],
            'correctness': {
                'passed': True,
                'checks_passed': sum(1 for item in checks if item.get('passed')),
                'checks_total': len(checks),
                'failures': [],
            },
        }

    per_size = _per_size(summaries)
    if not per_size:
        return {
            'status': 'NOT_MEASURED',
            'label': 'Not measured',
            'reason': 'Raw timing samples were missing from the evidence.',
            'policy': policy,
            'per_size': [],
            'correctness': {'passed': True, 'checks_passed': len(checks), 'checks_total': len(checks), 'failures': []},
        }
    primary = max(per_size, key=lambda item: item['size'])
    correctness = {
        'passed': True,
        'checks_passed': sum(1 for item in checks if item.get('passed')),
        'checks_total': len(checks),
        'failures': [],
    }
    common = {
        'policy': policy,
        'per_size': per_size,
        'primary_size': primary['size'],
        'baseline_median_ms': round(primary['baseline_median_ms'], 3),
        'candidate_median_ms': round(primary['candidate_median_ms'], 3),
        'change_pct': primary['change_pct'],
        'correctness': correctness,
    }

    regressed = [item for item in per_size if item['change_pct'] <= -REGRESSION_LIMIT_PCT]
    if regressed:
        worst = min(regressed, key=lambda item: item['change_pct'])
        return {
            'status': 'BASELINE_RETAINED',
            'label': 'Baseline retained',
            'reason': (
                f'The candidate regressed by {abs(worst["change_pct"]):.1f}% at {worst["size"]:,} rows. '
                'A regression on any measured workload is not a verified improvement.'
            ),
            **common,
        }
    if primary['change_pct'] <= 0:
        return {
            'status': 'BASELINE_RETAINED',
            'label': 'Baseline retained',
            'reason': (
                f'The original median was faster at {primary["size"]:,} rows '
                f'({primary["baseline_median_ms"]:.2f} ms vs {primary["candidate_median_ms"]:.2f} ms).'
            ),
            **common,
        }
    if primary['change_pct'] < MIN_IMPROVEMENT_PCT:
        return {
            'status': 'INCONCLUSIVE',
            'label': 'Inconclusive',
            'reason': (
                f'The candidate was {primary["change_pct"]:.2f}% faster at {primary["size"]:,} rows, '
                f'below the {MIN_IMPROVEMENT_PCT:.0f}% product threshold. That difference may be noise.'
            ),
            **common,
        }
    if primary['paired_win_rate'] < MIN_PAIRED_WIN_RATE or primary['paired_lower_decile_pct'] <= 0:
        return {
            'status': 'INCONCLUSIVE',
            'label': 'Inconclusive',
            'reason': (
                f'The median improved by {primary["change_pct"]:.1f}%, but only '
                f'{primary["paired_win_rate"] * 100:.0f}% of paired repetitions favoured the candidate '
                'and the lower decile did not stay above zero.'
            ),
            **common,
        }
    return {
        'status': 'VERIFIED_IMPROVEMENT',
        'label': 'Verified improvement',
        'reason': (
            f'All {correctness["checks_passed"]} correctness checks passed. The candidate was '
            f'{primary["change_pct"]:.1f}% faster at {primary["size"]:,} rows with a '
            f'{primary["paired_win_rate"] * 100:.0f}% paired win rate, and no measured size regressed by 5% or more.'
        ),
        **common,
    }
