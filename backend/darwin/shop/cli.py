import argparse
import json
import os
import httpx

from darwin.shop.db import initialize, invariant_report, snapshot
from darwin.shop.services import deliver_notification


def main():
    parser = argparse.ArgumentParser(description='Operate only the dedicated synthetic DARWIN shop database')
    parser.add_argument('command', choices=['init', 'reset', 'inspect', 'verify', 'drain', 'reconcile'])
    parser.add_argument('--confirm-reset', action='store_true')
    args = parser.parse_args()
    if args.command == 'reset' and not args.confirm_reset:
        parser.error('reset requires --confirm-reset; stop workload traffic first')
    if args.command in ('init', 'reset'):
        initialize(reset=args.command == 'reset')
        print('Shop schema and deterministic catalog ready.')
    elif args.command == 'inspect':
        print(json.dumps(snapshot(), default=str, indent=2))
    elif args.command == 'verify':
        report = invariant_report()
        print(json.dumps(report, indent=2))
        raise SystemExit(1 if report['violations'] else 0)
    elif args.command == 'reconcile':
        failures = 0
        for order in snapshot()['orders']:
            if order['status'] == 'pending':
                response = httpx.post(os.environ.get('DARWIN_SHOP_API_URL', 'http://127.0.0.1:8013') + '/checkout',
                                      headers={'Idempotency-Key': order['request_key']},
                                      json={'sku': order['sku'], 'quantity': order['quantity']}, timeout=5, trust_env=False)
                print(order['request_key'], response.status_code)
                failures += response.status_code >= 500
        raise SystemExit(1 if failures else 0)
    else:
        for job in snapshot()['outbox']:
            if job['status'] == 'pending':
                deliver_notification(job['job_key'])
        print('Pending notifications drained.')


if __name__ == '__main__':
    main()
