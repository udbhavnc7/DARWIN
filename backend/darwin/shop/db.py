import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DEFAULT_DSN = 'postgresql://darwin:darwin_demo@127.0.0.1:55432/darwin_shop'


def database_url():
    return os.environ.get('DARWIN_DATABASE_URL', DEFAULT_DSN)


@contextmanager
def connection():
    with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=2,
                         options='-c statement_timeout=1500 -c lock_timeout=1000') as conn:
        yield conn


SCHEMA = '''
CREATE TABLE IF NOT EXISTS products (
 sku text PRIMARY KEY, name text NOT NULL, price_cents integer NOT NULL CHECK(price_cents > 0),
 initial_stock integer NOT NULL CHECK(initial_stock >= 0),
 available integer NOT NULL CHECK(available >= 0 AND available <= initial_stock)
);
CREATE TABLE IF NOT EXISTS orders (
 request_key text PRIMARY KEY, order_id uuid NOT NULL UNIQUE, sku text NOT NULL,
 quantity integer NOT NULL CHECK(quantity > 0), amount_cents integer NOT NULL CHECK(amount_cents > 0),
 status text NOT NULL CHECK(status IN ('pending','confirmed','failed')),
 failure_reason text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reservations (
 request_key text PRIMARY KEY, sku text NOT NULL REFERENCES products(sku),
 quantity integer NOT NULL CHECK(quantity > 0),
 status text NOT NULL CHECK(status IN ('pending','reserved','rejected'))
);
CREATE TABLE IF NOT EXISTS captures (
 request_key text PRIMARY KEY, order_id uuid NOT NULL UNIQUE,
 amount_cents integer NOT NULL CHECK(amount_cents > 0),
 status text NOT NULL DEFAULT 'captured' CHECK(status='captured'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS outbox (
 job_key text PRIMARY KEY, order_id uuid NOT NULL UNIQUE REFERENCES orders(order_id),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed'))
);
CREATE TABLE IF NOT EXISTS deliveries (
 job_key text PRIMARY KEY, order_id uuid NOT NULL UNIQUE,
 delivered_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS payment_effects (
 effect_id bigserial PRIMARY KEY, request_key text NOT NULL,
 order_id uuid NOT NULL, amount_cents integer NOT NULL CHECK(amount_cents > 0)
);
'''

PRODUCTS = [('darwin-notebook', 'DARWIN Notebook', 1299, 20),
            ('darwin-mug', 'DARWIN Mug', 899, 15),
            ('darwin-shirt', 'DARWIN T-shirt', 2499, 10)]


def initialize(reset=False):
    """Explicit CLI operation; never reset automatically at service startup."""
    with connection() as conn:
        # Schema creation and TRUNCATE can flush several tables on slow disks.
        # Keep the shorter request timeout on ordinary shop connections.
        conn.execute("SET LOCAL statement_timeout = '15s'")
        conn.execute(SCHEMA)
        if reset:
            conn.execute('TRUNCATE payment_effects, deliveries, outbox, captures, reservations, orders, products')
        for sku, name, price, stock in PRODUCTS:
            conn.execute('''INSERT INTO products VALUES (%s,%s,%s,%s,%s)
                            ON CONFLICT (sku) DO NOTHING''', (sku, name, price, stock, stock))
        conn.execute('''INSERT INTO payment_effects(request_key,order_id,amount_cents)
                        SELECT request_key,order_id,amount_cents FROM captures c
                        WHERE NOT EXISTS (SELECT 1 FROM payment_effects e WHERE e.request_key=c.request_key)''')


def snapshot(dsn=None):
    with psycopg.connect(dsn or database_url(), row_factory=dict_row, connect_timeout=2,
                         options='-c statement_timeout=3000') as conn:
        return {table: conn.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
                for table in ('products', 'orders', 'reservations', 'captures', 'outbox', 'deliveries', 'payment_effects')}


def invariant_report():
    data = snapshot()
    captures = {r['request_key']: r for r in data['captures']}
    deliveries = {r['job_key']: r for r in data['deliveries']}
    violations = []
    for product in data['products']:
        confirmed = sum(o['quantity'] for o in data['orders'] if o['sku'] == product['sku'] and o['status'] == 'confirmed')
        reserved = sum(r['quantity'] for r in data['reservations'] if r['sku'] == product['sku'] and r['status'] == 'reserved')
        if confirmed > product['initial_stock'] or product['available'] != product['initial_stock'] - reserved:
            violations.append({'invariant_id': 'I-02', 'sku': product['sku']})
    for order in data['orders']:
        payment = captures.get(order['request_key'])
        if order['status'] == 'confirmed' and (not payment or payment['order_id'] != order['order_id'] or payment['amount_cents'] != order['amount_cents']):
            violations.append({'invariant_id': 'I-03', 'order_id': str(order['order_id'])})
    for job in data['outbox']:
        delivery = deliveries.get(job['job_key'])
        if job['status'] == 'completed' and (not delivery or delivery['order_id'] != job['order_id']):
            violations.append({'invariant_id': 'I-05', 'job_key': job['job_key']})
    # Uniqueness supplies static I-01/I-04 checks; replay tests verify business effects.
    for table, key, invariant in [('captures', 'request_key', 'I-01'), ('payment_effects', 'request_key', 'I-01'), ('orders', 'request_key', 'I-04'), ('deliveries', 'job_key', 'I-04')]:
        values = [r[key] for r in data[table]]
        if len(values) != len(set(values)):
            violations.append({'invariant_id': invariant, 'table': table})
    return {'violations': violations, 'pending_notifications': sum(j['status'] == 'pending' for j in data['outbox']),
            'scope': 'Ledger checks. Replay and crash evidence is checked by the isolated fault suite.'}
