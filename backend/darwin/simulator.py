"""Discrete-event screening on the same arrival schedule as the native benchmark."""
import math
import random

import simpy

from darwin.contracts import Genome
from darwin.performance import WARMUP_S, WINDOW_S, latency, schedule

MODEL_VERSION = 'shop-simulation-v2'


def simulate(genome: Genome, profile: str, seed: int, duration_s: int = 60,
             database_delay_ms: float = 0.0, workers: int = 8, *, service_scale: float = 1.0):
    if not 1 <= duration_s <= 3600 or workers < 1:
        raise ValueError('Invalid simulation bounds')
    if not math.isfinite(database_delay_ms) or database_delay_ms < 0:
        raise ValueError('Database delay must be finite and nonnegative')
    if not math.isfinite(service_scale) or service_scale <= 0:
        raise ValueError('Service scale must be positive and finite')

    rng = random.Random(seed)
    env = simpy.Environment()
    api = simpy.Resource(env, capacity=genome.app_replicas * workers)
    database = simpy.Resource(env, capacity=4)
    notifications = simpy.Resource(env, capacity=1)
    cache_until = 0.0
    samples = []

    def notify(seconds):
        with notifications.request() as slot:
            yield slot
            yield env.timeout(seconds)

    def request(arrival, operation, measured, db_seconds, checkout_seconds, notify_seconds):
        nonlocal cache_until
        with api.request() as slot:
            yield slot
            hit = operation == 'catalog' and cache_until > env.now
            if hit:
                yield env.timeout(.004 * service_scale)
            # Catalog availability still uses the database on a description-cache hit.
            with database.request() as db_slot:
                yield db_slot
                description_seconds = .020 * service_scale if operation == 'catalog' and not hit else 0
                yield env.timeout(db_seconds + description_seconds + database_delay_ms / 1000)
            if operation == 'catalog' and not hit and genome.catalog_cache_ttl_s:
                cache_until = env.now + genome.catalog_cache_ttl_s
            if operation == 'checkout':
                yield env.timeout(checkout_seconds)
                if genome.notification_mode == 'sync':
                    yield env.timeout(notify_seconds)
                else:
                    env.process(notify(notify_seconds))
            if measured:
                samples.append({'latency_ms': (env.now - arrival) * 1000,
                                'finished_s': env.now - WARMUP_S})

    def arrivals():
        plan = [(i / 2, 'catalog', False) for i in range(WARMUP_S * 2)]
        for start in range(0, duration_s, WINDOW_S):
            for item in schedule(profile, (seed + start // WINDOW_S) % 2**32):
                offset = start + item['offset_s']
                if offset < duration_s:
                    plan.append((WARMUP_S + offset, item['operation'], True))
        for arrival, operation, measured in plan:
            yield env.timeout(max(0, arrival - env.now))
            times = [rng.expovariate(1 / mean) * service_scale for mean in (.040, .080, .030)]
            env.process(request(arrival, operation, measured, *times))

    env.process(arrivals())
    env.run()
    return {
        'tier': 'simulated', 'gate': 'not_checked', 'model_version': MODEL_VERSION,
        'seed': seed, 'duration_s': duration_s, 'configuration': genome.model_dump(),
        'workload_profile': profile,
        'assumptions': {
            'warmup_s': WARMUP_S, 'api_workers_per_replica': workers,
            'database_connections': 4, 'notification_workers': 1, 'service_scale': service_scale,
            'checkout_mean_ms': 80 * service_scale, 'database_mean_ms': 40 * service_scale,
            'cache_hit_overhead_ms': 4 * service_scale, 'description_miss_overhead_ms': 20 * service_scale,
            'notification_mean_ms': 30 * service_scale, 'database_delay_ms': database_delay_ms,
        },
        'metrics': {
            'p50_ms': latency(samples, .50), 'p95_ms': latency(samples, .95),
            'p99_ms': latency(samples, .99), 'sample_count': len(samples),
            'requests_per_s': sum(row['finished_s'] <= duration_s for row in samples) / duration_s,
            'error_rate': None,
        },
        'calibration_status': 'uncalibrated', 'prediction_interval': None,
    }
