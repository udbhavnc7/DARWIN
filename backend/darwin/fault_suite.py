"""Bounded, recorded failure scenarios against an owned synthetic shop."""
from concurrent.futures import ThreadPoolExecutor
import json
import time

import httpx
import psycopg

from darwin.experiments import write_json
from darwin.invariants import check_business, feasibility
from darwin.performance import latency
from darwin.shop.db import snapshot


class FaultSuite:
    def __init__(self, sandbox, base, check):
        self.sandbox, self.base, self.check = sandbox, base, check
        self.folder = sandbox.folder
        self.history, self.recovery, self.operations = [], [], []
        self.started = time.monotonic()

    def record(self, kind, **fields):
        event = {'kind': kind, 'elapsed_s': time.monotonic() - self.started, **fields}
        self.history.append(event)
        with (self.folder / 'fault-trace.jsonl').open('a', encoding='utf-8') as trace:
            trace.write(json.dumps(event, default=str) + '\n')
        return event

    def state(self):
        return json.loads(json.dumps(snapshot(self.sandbox.direct_dsn), default=str))

    def request(self, key=None, sku='darwin-notebook'):
        start = time.monotonic()
        try:
            with httpx.Client(timeout=4, trust_env=False) as client:
                if key:
                    response = client.post(self.base + '/checkout', json={'sku': sku, 'quantity': 1},
                                           headers={'Idempotency-Key': key})
                else:
                    response = client.get(self.base + '/catalog')
            body = response.json()
            status = response.status_code
        except (httpx.TransportError, ValueError) as exc:
            status, body = 0, {'error': type(exc).__name__}
        return {'key': key, 'status': status, 'body': body, 'started_s': start - self.started,
                'latency_ms': (time.monotonic() - start) * 1000,
                'ok': status == 200 and (isinstance(body, dict) and body.get('status') == 'confirmed'
                                        if key else isinstance(body, list) and bool(body))}

    def sleep_until(self, deadline):
        while time.monotonic() < deadline:
            self.check()
            time.sleep(min(.05, max(0, deadline - time.monotonic())))

    def finish_order(self, key, sku='darwin-notebook', allow_sold_out=False):
        deadline = time.monotonic() + 12
        while True:
            self.check()
            response = self.request(key, sku)
            self.record('http_attempt', **response)
            ok = response['ok'] and response['body'].get('status') == 'confirmed'
            ok = ok or (allow_sold_out and response['status'] == 409 and response['body'].get('detail') == 'out_of_stock')
            if ok or time.monotonic() >= deadline:
                self.operations.append(ok)
                return response
            self.sleep_until(time.monotonic() + .2)

    def settle(self):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            self.check()
            state = self.state()
            unfinished = [o for o in state['orders'] if o['status'] == 'pending']
            pending_keys = {job['job_key'] for job in state['outbox'] if job['status'] == 'pending'}
            if not unfinished and not pending_keys:
                return
            if self.sandbox.genome.notification_mode == 'sync':
                unfinished += [o for o in state['orders'] if o['request_key'] in pending_keys and o['status'] == 'confirmed']
            for order in unfinished:
                self.finish_order(order['request_key'], order['sku'])
            self.sleep_until(time.monotonic() + .2)
        self.record('settlement_timeout')

    def recovery_scenario(self, name, activate, restore):
        """2 catalog requests/s, 5s baseline, 2s fault, 15s recovery observation."""
        start = time.monotonic()
        futures = []
        restored_at = None
        active = False
        with ThreadPoolExecutor(max_workers=12) as pool:
            try:
                for slot in range(44):
                    self.sleep_until(start + slot * .5)
                    if slot == 10:
                        active = True
                        activate()
                        self.record('fault_started', scenario=name)
                    if slot == 14:
                        restore()
                        active = False
                        restored_at = time.monotonic() - self.started
                        self.record('fault_removed', scenario=name)
                    dispatched = time.monotonic()
                    futures.append((slot, dispatched - start - slot * .5, pool.submit(self.request)))
            finally:
                if active:
                    restore()
            samples = []
            for slot, lag, future in futures:
                row = future.result()
                row.update(slot=slot, dispatch_lag_s=lag)
                samples.append(row)
                self.record('recovery_probe', scenario=name, **row)
        baseline = samples[:10]
        valid = all(row['ok'] for row in baseline) and max(row['dispatch_lag_s'] for row in samples) <= .5
        reference = latency(baseline, .95)
        recovery = None
        for first in range(14, len(samples) - 9):
            window = samples[first:first + 10]
            if window[0]['started_s'] < restored_at:
                continue
            error_rate = sum(not row['ok'] for row in window) / len(window)
            if valid and error_rate <= self.sandbox.request.constraints.max_error_rate and latency(window, .95) <= 1.2 * reference:
                confirmation = max(window[0]['started_s'] + 5,
                                   max(row['started_s'] + row['latency_ms'] / 1000 for row in window))
                recovery = confirmation - restored_at
                break
        observed = any(not row['ok'] or row['latency_ms'] > 1.2 * reference for row in samples[10:14])
        row = {'scenario': name, 'baseline_p95_ms': reference, 'recovery_s': recovery,
               'censored_after_s': 15 if recovery is None else None, 'schedule_valid': valid,
               'fault_observed': observed, 'fault_samples': samples[10:14]}
        self.recovery.append(row)
        self.record('recovery_result', **row)

    def duplicate_payment(self):
        key = f'fault-payment-{self.sandbox.request.seed}'
        self.sandbox.proxy_call('POST', '/proxies/payment/toxics', {
            'name': 'lost-reply', 'type': 'timeout', 'stream': 'downstream', 'toxicity': 1,
            'attributes': {'timeout': 1200}})
        try:
            first = self.request(key)
            committed_before_retry = self.state()
            self.record('payment_reply_lost', **first, ledger=committed_before_retry)
        finally:
            self.sandbox.proxy_call('DELETE', '/proxies/payment/toxics/lost-reply')
        recovered = self.finish_order(key)
        self.record('payment_retry_completed', response=recovered)
        return first['status'] != 200 and any(row['request_key'] == key for row in committed_before_retry['payment_effects'])

    def replay_and_stock(self):
        key = f'fault-replay-{self.sandbox.request.seed}'
        first = self.finish_order(key)
        self.settle()
        before = self.state()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.request(key), range(4)))
        self.settle()
        self.record('replay', key=key, before=before, after=self.state(),
                    responses_equal=all(row['status'] == first['status'] and row['body'] == first['body'] for row in responses),
                    responses=responses)
        with psycopg.connect(self.sandbox.direct_dsn, connect_timeout=2) as conn:
            conn.execute("INSERT INTO products VALUES ('fault-last-units','Last units',100,2,2)")
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda i: self.request(f'fault-stock-{i}', 'fault-last-units'), range(4)))
        for i, response in enumerate(responses):
            self.record('stock_race_attempt', **response)
            self.finish_order(f'fault-stock-{i}', 'fault-last-units', allow_sold_out=True)
        state = self.state()
        stock_orders = [row for row in state['orders'] if row['sku'] == 'fault-last-units']
        outcomes_verified = (sum(row['status'] == 'confirmed' for row in stock_orders) == 2 and
                             sum(row['status'] == 'failed' for row in stock_orders) == 2)
        self.record('stock_race_completed', ledger=state, expected_outcomes_observed=outcomes_verified)
        return outcomes_verified

    def notification_restart(self):
        key = f'fault-notification-{self.sandbox.request.seed}'
        self.sandbox.arm_notification(key, self.check)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.request, key)
            try:
                deadline = time.monotonic() + 12
                while (reached := self.sandbox.notification_marker(self.check)) is None:
                    self.check()
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Notification acknowledgment boundary was not reached')
                    self.sleep_until(time.monotonic() + .05)
                if reached['key'] != key:
                    raise RuntimeError('Notification marker belongs to a different request')
                before = self.state()
                self.sandbox.stop_service(reached['instance'])
                self.record('notification_process_killed', marker=reached, ledger=before)
            finally:
                self.sandbox.disarm_notification()
            self.sandbox.restart_service(reached['instance'], self.check)
            self.record('notification_response', **pending.result())
        self.finish_order(key)
        self.settle()
        self.record('notification_restart', key=key,
                    pending_before_crash=any(row['job_key'] == key and row['status'] == 'pending' for row in before['outbox']),
                    before=before, after=self.state())

    def run(self, result):
        selected = self.sandbox.request.fault_scenarios
        write_json(self.folder / 'fault-schedule.json', {
            'protocol': 'faults-v1', 'seed': self.sandbox.request.seed, 'scenarios': selected,
            'baseline_s': 5, 'fault_s': 2, 'recovery_observation_s': 15, 'catalog_requests_per_s': 2,
            'mandatory_checks': ['concurrent_order_replay', 'stock_race', 'notification_ack_crash']})
        verified = True
        if 'db_delay' in selected:
            self.recovery_scenario('database_latency', lambda: self.sandbox.proxy_call('POST', '/proxies/database/toxics', {
                'name': 'delay', 'type': 'latency', 'stream': 'downstream', 'toxicity': 1,
                'attributes': {'latency': 100, 'jitter': 0}}),
                lambda: self.sandbox.proxy_call('DELETE', '/proxies/database/toxics/delay'))
            self.recovery_scenario('database_disconnect',
                lambda: self.sandbox.proxy_call('POST', '/proxies/database', {'enabled': False}),
                lambda: self.sandbox.proxy_call('POST', '/proxies/database', {'enabled': True}))
        if 'service_outage' in selected:
            paused = []
            self.recovery_scenario('application_outage', lambda: paused.extend(self.sandbox.pause_apis()),
                                   lambda: self.sandbox.resume_apis(paused))
        if 'timeout_retry_duplicate' in selected:
            verified = self.duplicate_payment()
        verified = self.replay_and_stock() and verified
        self.notification_restart()
        self.settle()
        final = self.state()
        write_json(self.folder / 'business-state.json', final)
        result.update(violations=check_business(final, self.history),
                      logical_error_rate=sum(not ok for ok in self.operations) / len(self.operations),
                      recovery=self.recovery, faults_verified=verified and all(row['fault_observed'] for row in self.recovery),
                      invariant_coverage=['I-01', 'I-02', 'I-03', 'I-04', 'I-05'])
        result['metrics']['recovery_s'] = max((row['recovery_s'] for row in self.recovery), default=None) if all(row['recovery_s'] is not None for row in self.recovery) else None
        result.update(feasibility(result, self.sandbox.request.constraints))
        self.record('gate_decision', gate=result['gate'], reasons=result['gate_reasons'], violations=result['violations'])
        write_json(self.folder / 'fault-report.json', result)
        return result
