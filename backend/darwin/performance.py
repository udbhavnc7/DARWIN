"""Versioned local benchmark protocol and repetition summaries."""
import math
import random
from statistics import median

from darwin.contracts import Metrics

WARMUP_S = 3
WINDOW_S = 12
SKUS = ('darwin-notebook', 'darwin-mug', 'darwin-shirt')


def schedule(profile, seed):
    rng = random.Random(seed)
    plan = []
    for second in range(WINDOW_S):
        burst = profile == 'flash_sale' and 4 <= second < 8
        rate = 12 if burst else 4
        checkout_share = {'normal': .25, 'flash_sale': .5, 'checkout_heavy': .75}[profile]
        for slot in range(rate):
            operation = 'checkout' if rng.random() < checkout_share else 'catalog'
            plan.append({'offset_s': second + slot / rate, 'operation': operation,
                         'sku': rng.choice(SKUS), 'key': f'load-{seed}-{len(plan)}'})
    return plan


def latency(samples, quantile):
    values = sorted(s['latency_ms'] for s in samples)
    return values[math.ceil(quantile * len(values)) - 1]


def metrics(samples, cpu_seconds, peak_mb, window_s=WINDOW_S):
    if not samples:
        raise ValueError('Measurement produced no observations')
    if window_s <= 0:
        raise ValueError('Measurement window must be positive')
    return Metrics(p50_ms=latency(samples, .50), p95_ms=latency(samples, .95),
                   p99_ms=latency(samples, .99), sample_count=len(samples),
                   error_rate=sum(not s['ok'] for s in samples) / len(samples),
                   requests_per_s=sum(s['finished_s'] <= window_s for s in samples) / window_s,
                   cpu_seconds=cpu_seconds, memory_peak_mb=peak_mb).model_dump()


def summarize(evaluations, request):
    rows = [ev['metrics'] for ev in evaluations if ev['status'] == 'completed' and 'metrics' in ev]
    if len(rows) != request.budget.repetitions:
        raise ValueError('Incomplete repetition group')
    spread = {}
    for field in ('p95_ms', 'requests_per_s', 'cpu_seconds', 'memory_peak_mb', 'error_rate'):
        values = [row[field] for row in rows]
        spread[field] = {'min': min(values), 'median': median(values), 'max': max(values)}
    limit = request.constraints.max_p95_ms
    passes = all(row['error_rate'] <= request.constraints.max_error_rate and
                 (limit is None or row['p95_ms'] <= limit) for row in rows)
    return {'repetitions': len(rows), 'spread': spread, 'performance_constraints_met': passes,
            'gate': 'not_checked'}
