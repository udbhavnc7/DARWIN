"""Deliberately broken synthetic payment receiver for the isolated rejection fixture."""
import os

from darwin.shop.db import connection
from darwin.shop.services import base_app, Capture, capture

if os.environ.get('DARWIN_ISOLATED_FAULT_TEST') != '1':
    raise RuntimeError('Unsafe fixture requires an isolated fault-test sandbox')

app = base_app('unsafe-payment-fixture')


@app.post('/capture')
def unsafe_capture(request: Capture):
    with connection() as conn:
        repeated = conn.execute('SELECT 1 FROM captures WHERE request_key=%s', (request.request_key,)).fetchone()
        if repeated:
            conn.execute('INSERT INTO payment_effects(request_key,order_id,amount_cents) VALUES (%s,%s,%s)',
                         (request.request_key, request.order_id, request.amount_cents))
    return capture(request)
