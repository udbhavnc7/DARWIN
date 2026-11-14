import os
import json
import logging
import time
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
import psycopg
import redis
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from darwin.shop.db import connection
from darwin.shop.settings import genome

logger = logging.getLogger('darwin.shop')


class Checkout(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sku: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=100, strict=True)


class Reservation(Checkout):
    request_key: str = Field(min_length=1, max_length=128)


class Capture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(min_length=1, max_length=128)
    order_id: UUID
    amount_cents: int = Field(gt=0, strict=True)


def base_app(role):
    app = FastAPI(title=f'DARWIN Shop / {role}')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': role}

    @app.get('/ready')
    def ready():
        try:
            with connection() as conn:
                conn.execute('SELECT sku FROM products LIMIT 1').fetchall()
        except psycopg.Error:
            raise HTTPException(503, 'Database or schema unavailable')
        return {'status': 'ready', 'service': role}

    @app.exception_handler(psycopg.Error)
    async def database_error(request, exc):
        logger.warning('%s %s failed: %s: %s', request.method, request.url.path, type(exc).__name__, exc)
        return JSONResponse(status_code=503, content={'detail': 'Database temporarily unavailable; retry with the same request key'})

    return app


inventory = base_app('inventory')
payment = base_app('mock-payment')
api = base_app('catalog-checkout')


@api.middleware('http')
async def identify_instance(request, call_next):
    response = await call_next(request)
    response.headers['X-Darwin-Instance'] = os.environ.get('DARWIN_INSTANCE_ID', 'api-1')
    return response


@inventory.post('/reserve')
def reserve(request: Reservation):
    with connection() as conn:
        if not conn.execute('SELECT 1 FROM products WHERE sku=%s', (request.sku,)).fetchone():
            raise HTTPException(404, 'Unknown product')
        conn.execute('''INSERT INTO reservations VALUES (%s,%s,%s,'pending')
                        ON CONFLICT DO NOTHING''', (request.request_key, request.sku, request.quantity))
        row = conn.execute('SELECT * FROM reservations WHERE request_key=%s FOR UPDATE', (request.request_key,)).fetchone()
        if row['sku'] != request.sku or row['quantity'] != request.quantity:
            raise HTTPException(409, 'Request key already used for another payload')
        if row['status'] == 'pending':
            changed = conn.execute('''UPDATE products SET available=available-%s
                                      WHERE sku=%s AND available >= %s RETURNING sku''',
                                   (request.quantity, request.sku, request.quantity)).fetchone()
            row['status'] = 'reserved' if changed else 'rejected'
            conn.execute('UPDATE reservations SET status=%s WHERE request_key=%s', (row['status'], request.request_key))
    return JSONResponse(status_code=200 if row['status'] == 'reserved' else 409, content=row)


@payment.post('/capture')
def capture(request: Capture):
    with connection() as conn:
        inserted = conn.execute('''INSERT INTO captures (request_key,order_id,amount_cents) VALUES (%s,%s,%s)
                        ON CONFLICT DO NOTHING RETURNING request_key''',
                        (request.request_key, request.order_id, request.amount_cents)).fetchone()
        row = conn.execute('SELECT * FROM captures WHERE request_key=%s', (request.request_key,)).fetchone()
        if row['order_id'] != request.order_id or row['amount_cents'] != request.amount_cents:
            raise HTTPException(409, 'Payment key already used for another payload')
        if inserted:
            conn.execute('INSERT INTO payment_effects(request_key,order_id,amount_cents) VALUES (%s,%s,%s)',
                         (request.request_key, request.order_id, request.amount_cents))
    return row


@api.get('/catalog')
def catalog(response: Response):
    ttl = genome().catalog_cache_ttl_s
    cache = None
    descriptions = None
    response.headers['X-Darwin-Cache'] = 'off'
    if ttl:
        cache = redis.Redis.from_url(os.environ.get('DARWIN_REDIS_URL', 'redis://127.0.0.1:6380/0'),
                                      socket_timeout=0.2, socket_connect_timeout=0.2, decode_responses=True)
        key = 'darwin:catalog:' + os.environ.get('DARWIN_CACHE_NAMESPACE', 'local')
        try:
            cached = cache.get(key)
            descriptions = json.loads(cached) if cached else None
            response.headers['X-Darwin-Cache'] = 'hit' if descriptions is not None else 'miss'
        except (redis.RedisError, ValueError):
            response.headers['X-Darwin-Cache'] = 'unavailable'
    with connection() as conn:
        if descriptions is None:
            descriptions = conn.execute('SELECT sku,name,price_cents FROM products ORDER BY sku').fetchall()
            if cache is not None:
                try:
                    cache.set(key, json.dumps(descriptions), ex=ttl)
                except redis.RedisError:
                    response.headers['X-Darwin-Cache'] = 'unavailable'
        # Availability is always authoritative, never cached.
        stock = {row['sku']: row['available'] for row in conn.execute('SELECT sku,available FROM products').fetchall()}
    return [{**product, 'available': stock[product['sku']]} for product in descriptions if product['sku'] in stock]


def post_safe(url, payload, deadline):
    """One bounded retry, with identical payload and key, on transient failures."""
    attempts = 1 if genome().retry_policy == 'none' else 2
    for attempt in range(attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(503, 'Checkout deadline reached; retry with the same key')
        try:
            with httpx.Client(timeout=min(0.7, remaining), trust_env=False) as client:
                response = client.post(url, json=payload)
            if response.status_code < 500:
                return response
        except httpx.TransportError:
            pass
        if attempt + 1 < attempts and deadline - time.monotonic() > 0.1:
            time.sleep(0.1)
    raise HTTPException(503, 'Dependency unavailable; retry with the same key')


def deliver_notification(job_key):
    # Synthetic receiver has its own committed ledger, so replay is idempotent even
    # if the process stops after delivery but before outbox acknowledgment.
    with connection() as conn:
        job = conn.execute('SELECT * FROM outbox WHERE job_key=%s', (job_key,)).fetchone()
        if not job:
            return
        conn.execute('INSERT INTO deliveries(job_key,order_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                     (job_key, job['order_id']))
    control = os.environ.get('DARWIN_FAULT_CONTROL_FILE')
    if control and os.environ.get('DARWIN_ISOLATED_FAULT_TEST') == '1':
        from darwin.fault_hooks import pause_acknowledgment
        pause_acknowledgment(control, job_key)
    with connection() as conn:
        conn.execute("UPDATE outbox SET status='completed' WHERE job_key=%s", (job_key,))


def settle_order(key, request):
    """Advance one order to a final state while duplicate requests queue behind it.

    Repeating a request is safe because the inventory and payment calls are
    idempotent on the request key. If the row lock times out under a burst of
    duplicates, retry within the checkout budget instead of reporting a
    transient database error for a request that will succeed moments later.
    """
    settle_deadline = time.monotonic() + 8
    while True:
        deadline = time.monotonic() + 2
        try:
            # Serialize repeated requests for this order, independently of inventory/payment transactions.
            with connection() as conn:
                order = conn.execute('SELECT * FROM orders WHERE request_key=%s FOR UPDATE', (key,)).fetchone()
                if order['sku'] != request.sku or order['quantity'] != request.quantity:
                    raise HTTPException(409, 'Request key already used for another payload')
                if order['status'] == 'pending':
                    reserved = post_safe(os.environ.get('DARWIN_INVENTORY_URL', 'http://127.0.0.1:8011') + '/reserve',
                                         {'request_key': key, **request.model_dump()}, deadline)
                    if reserved.status_code == 409 and reserved.json().get('status') == 'rejected':
                        conn.execute("UPDATE orders SET status='failed',failure_reason='out_of_stock' WHERE request_key=%s", (key,))
                        order.update(status='failed', failure_reason='out_of_stock')
                    elif reserved.status_code != 200:
                        raise HTTPException(503, 'Reservation could not be verified')
                    else:
                        paid = post_safe(os.environ.get('DARWIN_PAYMENT_URL', 'http://127.0.0.1:8012') + '/capture',
                                         {'request_key': key, 'order_id': str(order['order_id']), 'amount_cents': order['amount_cents']}, deadline)
                        if paid.status_code != 200:
                            raise HTTPException(503, 'Payment could not be verified; retry with the same key')
                        evidence = paid.json()
                        if (evidence.get('status') != 'captured' or evidence.get('request_key') != key or
                                evidence.get('order_id') != str(order['order_id']) or evidence.get('amount_cents') != order['amount_cents']):
                            raise HTTPException(503, 'Payment evidence mismatch')
                        conn.execute("UPDATE orders SET status='confirmed' WHERE request_key=%s", (key,))
                        conn.execute('INSERT INTO outbox(job_key,order_id) VALUES (%s,%s) ON CONFLICT DO NOTHING', (key, order['order_id']))
                        order['status'] = 'confirmed'
                return order
        except (psycopg.errors.LockNotAvailable, psycopg.errors.QueryCanceled, psycopg.errors.DeadlockDetected):
            if time.monotonic() >= settle_deadline:
                raise HTTPException(503, 'Order update is still busy; retry with the same key')
            time.sleep(0.05)


@api.post('/checkout')
def checkout(request: Checkout, idempotency_key: Annotated[str, Header(min_length=1, max_length=128)]):
    key = idempotency_key
    with connection() as conn:
        product = conn.execute('SELECT * FROM products WHERE sku=%s', (request.sku,)).fetchone()
        if not product:
            raise HTTPException(404, 'Unknown product')
        conn.execute('''INSERT INTO orders(request_key,order_id,sku,quantity,amount_cents,status)
                        VALUES (%s,%s,%s,%s,%s,'pending') ON CONFLICT DO NOTHING''',
                     (key, uuid5(NAMESPACE_URL, 'darwin:shop:' + key), request.sku, request.quantity, product['price_cents'] * request.quantity))
    order = settle_order(key, request)
    if order['status'] == 'failed':
        return JSONResponse(status_code=409, content={'order_id': str(order['order_id']), 'status': 'failed', 'detail': order['failure_reason']})
    if genome().notification_mode == 'sync':
        try:
            deliver_notification(key)
        except psycopg.Error:
            pass  # Confirmation is already committed; outbox work stays pending.
    return {'order_id': str(order['order_id']), 'status': order['status'], 'sku': order['sku'],
            'quantity': order['quantity'], 'amount_cents': order['amount_cents']}


@api.get('/ledger')
def ledger(request_key: str | None = None):
    """Read-only counters that make duplicate effects visible in the demo."""
    with connection() as conn:
        totals = conn.execute('''SELECT
            (SELECT count(*) FROM orders) AS orders,
            (SELECT count(*) FROM captures) AS captures,
            (SELECT count(*) FROM payment_effects) AS payment_effects,
            (SELECT count(*) FROM outbox) AS outbox,
            (SELECT count(*) FROM deliveries) AS deliveries''').fetchone()
        result = dict(totals)
        if request_key:
            result['for_request'] = dict(conn.execute('''SELECT
                (SELECT count(*) FROM orders WHERE request_key=%s) AS orders,
                (SELECT count(*) FROM captures WHERE request_key=%s) AS captures,
                (SELECT count(*) FROM payment_effects WHERE request_key=%s) AS payment_effects''',
                (request_key, request_key, request_key)).fetchone())
    return result


@api.post('/reset')
def reset():
    """Reset the synthetic demo shop. Never points at production or personal data."""
    with connection() as conn:
        conn.execute('''TRUNCATE TABLE payment_effects, deliveries, outbox, captures, reservations, orders
                        RESTART IDENTITY''')
        conn.execute('UPDATE products SET available=initial_stock')
    return {'status': 'reset'}
