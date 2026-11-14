"""Business-state checks, including replay and delivery acknowledgment evidence."""
from collections import Counter


def check_business(data, history):
    violations = []

    def reject(invariant, detail, key=None):
        violations.append({'invariant_id': invariant, 'detail': detail, 'key': key})

    orders = {row['request_key']: row for row in data['orders']}
    captures = {row['request_key']: row for row in data['captures']}
    deliveries = {row['job_key']: row for row in data['deliveries']}
    outbox = {row['job_key']: row for row in data['outbox']}
    effects = Counter(row['request_key'] for row in data['payment_effects'])
    for key, count in effects.items():
        if count > 1:
            reject('I-01', f'{count} payment effects for one payment key', key)
    for product in data['products']:
        reserved = sum(row['quantity'] for row in data['reservations']
                       if row['sku'] == product['sku'] and row['status'] == 'reserved')
        confirmed = sum(row['quantity'] for row in data['orders']
                        if row['sku'] == product['sku'] and row['status'] == 'confirmed')
        if (product['available'] < 0 or reserved > product['initial_stock'] or
                confirmed > reserved or product['available'] != product['initial_stock'] - reserved):
            reject('I-02', 'Stock does not reconcile with reservations and confirmed orders', product['sku'])
    for key, order in orders.items():
        if order['status'] != 'confirmed':
            continue
        capture = captures.get(key)
        evidence = [row for row in data['payment_effects'] if row['request_key'] == key]
        if (not capture or capture.get('status') != 'captured' or capture['order_id'] != order['order_id'] or
                capture['amount_cents'] != order['amount_cents'] or
                not any(row['order_id'] == order['order_id'] and row['amount_cents'] == order['amount_cents'] for row in evidence)):
            reject('I-03', 'Confirmed order lacks matching successful payment evidence', key)
        if key not in outbox:
            reject('I-05', 'Confirmed order lost its notification job', key)
    for table, key in [('orders', 'request_key'), ('reservations', 'request_key'), ('deliveries', 'job_key')]:
        counts = Counter(row[key] for row in data[table])
        for value, count in counts.items():
            if count > 1:
                reject('I-04', f'Duplicate business records in {table}', value)
    for event in history:
        if event['kind'] == 'replay' and (event['before'] != event['after'] or not event['responses_equal']):
            reject('I-04', 'Replay changed response or business state', event['key'])
        if event['kind'] == 'notification_restart':
            key = event['key']
            accepted = next((row for row in event.get('before', {}).get('outbox', []) if row['job_key'] == key), None)
            if (not event['pending_before_crash'] or key not in outbox or key not in deliveries or
                    not accepted or accepted['order_id'] != outbox[key]['order_id']):
                reject('I-05', 'Accepted notification was not retained through restart', key)
    for key, job in outbox.items():
        delivery = deliveries.get(key)
        if job['status'] != 'completed' or not delivery or delivery['order_id'] != job['order_id']:
            reject('I-05', 'Notification did not finish with matching delivery evidence', key)
    return violations


def feasibility(result, constraints):
    """A performance improvement cannot override any failed hard requirement."""
    reasons = []
    if not result.get('resource_limits_enforced'):
        reasons.append('resource_limits_unverified')
    if result.get('violations'):
        reasons.append('business_invariant_failed')
    if not result.get('faults_verified'):
        reasons.append('fault_scenario_incomplete')
    if set(result.get('invariant_coverage', [])) != {'I-01', 'I-02', 'I-03', 'I-04', 'I-05'}:
        reasons.append('invariant_coverage_incomplete')
    metrics = result['metrics']
    if metrics['error_rate'] > constraints.max_error_rate:
        reasons.append('measurement_error_threshold')
    if result.get('logical_error_rate', 1) > constraints.max_error_rate:
        reasons.append('fault_operation_error_threshold')
    if constraints.max_p95_ms is not None and metrics['p95_ms'] > constraints.max_p95_ms:
        reasons.append('measurement_latency_threshold')
    if any(row['recovery_s'] is None for row in result.get('recovery', [])):
        reasons.append('recovery_not_observed')
    return {'gate': 'failed' if reasons else 'passed', 'gate_reasons': reasons}
