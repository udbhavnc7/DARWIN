"""Locust traffic driver. Run only as a child process of the benchmark worker."""
from locust import HttpUser
from locust.env import Environment

import argparse
import json
from pathlib import Path
import time

import gevent
import psutil
import win32job

from darwin.performance import schedule, WARMUP_S, WINDOW_S
from darwin.windows_job import usage


class Shopper(HttpUser):
    abstract = True


def request(user, item, start):
    began = time.perf_counter()
    checkout = item['operation'] == 'checkout'
    try:
        if checkout:
            response = user.client.post('/shop/checkout', headers={'Idempotency-Key': item['key']},
                                        json={'sku': item['sku'], 'quantity': 1}, timeout=6, allow_redirects=False)
        else:
            response = user.client.get('/shop/catalog', timeout=6, allow_redirects=False)
        status = response.status_code
        body = response.json() if status == 200 else None
        ok = status == 200 and (isinstance(body, dict) and body.get('status') == 'confirmed'
                                if checkout else isinstance(body, list) and len(body) == 3)
        error = None if ok else f'Unexpected response ({status})'
    except (ValueError, OSError) as exc:
        status, ok, error = 0, False, type(exc).__name__
    finally:
        user.client.close()
    ended = time.perf_counter()
    return {**item, 'started_s': began - start, 'finished_s': ended - start,
            'latency_ms': (ended - began) * 1000, 'status': status, 'ok': ok, 'error': error}


def drive(environment, plan, seconds):
    start = time.perf_counter()
    pending = []
    for item in plan:
        gevent.sleep(max(0, start + item['offset_s'] - time.perf_counter()))
        user = Shopper(environment)
        user.client.trust_env = False
        pending.append(gevent.spawn(request, user, item, start))
    gevent.sleep(max(0, start + seconds - time.perf_counter()))
    return [task.get() for task in pending], time.perf_counter() - start


def main():
    parser = argparse.ArgumentParser()
    for argument in ('host', 'profile', 'job', 'folder'):
        parser.add_argument(argument)
    parser.add_argument('seed', type=int)
    args = parser.parse_args()
    folder = Path(args.folder)
    environment = Environment(host=args.host)
    Shopper.host = args.host
    plan = schedule(args.profile, args.seed)
    def save(name, data):
        (folder / name).write_text(json.dumps(data, indent=2), encoding='utf-8')
    save('schedule.json', plan)
    warm, _ = drive(environment, [{'offset_s': i / 2, 'operation': 'catalog'} for i in range(WARMUP_S * 2)], WARMUP_S)
    save('warmup.json', warm)
    if not all(row['ok'] for row in warm):
        raise RuntimeError('Catalog warm-up failed')
    handle = win32job.OpenJobObject(win32job.JOB_OBJECT_QUERY, False, args.job)
    try:
        before = usage(handle)
        cpu = time.process_time()
        samples, elapsed = drive(environment, plan, WINDOW_S)
        harness_cpu = time.process_time() - cpu
        after = usage(handle)
    finally:
        handle.Close()
    save('samples.json', samples)
    lag = max(s['started_s'] - s['offset_s'] for s in samples)
    save('resources.json', {'application_start': before, 'application_end': after,
         'load_generator_cpu_seconds': harness_cpu,
         'load_generator_peak_working_set_mb': psutil.Process().memory_info().peak_wset / 2**20,
         'window_and_drain_s': elapsed, 'max_dispatch_lag_s': lag})
    if lag > .5 or elapsed > WINDOW_S + 8:
        raise RuntimeError('Load generator missed the fixed schedule; inspect resources.json')


if __name__ == '__main__':
    main()
