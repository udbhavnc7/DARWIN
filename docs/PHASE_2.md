# Phase 2: baseline shop

Status: implementation and local PostgreSQL verification complete; Docker execution acceptance remains pending because Docker/WSL2 is unavailable on this machine.

## Delivered

- Separate gateway, catalog/checkout, inventory, and mock payment HTTP processes.
- PostgreSQL schema, deterministic product seed, explicit reset, read-only ledger inspection, and invariant report.
- Idempotent order/capture/reservation keys, atomic stock decrement, per-order locking, and exact payment evidence checks before confirmation.
- Transactional notification outbox and idempotent synthetic delivery ledger. Synchronous delivery runs after confirmation; pending work is retained.
- Local PostgreSQL runner, Dockerfile, and isolated Compose stack with readiness dependencies and resource limits.
- Live shop controls in the UI, including same-key retry/replay and distinct new orders.

## Start the local shop

Prerequisites: project virtual environment installed, PostgreSQL `initdb` and `pg_ctl` on PATH, and ports 55432 and 8010-8013 available. The installed Scoop PostgreSQL binaries were used on this machine. This starts a dedicated cluster under `.runtime/shop/pgdata`, never an existing user's database.

```powershell
.\.venv\Scripts\python.exe scripts/run_shop.py
```

Keep the runner terminal open. Ctrl+C stops its four services and its PostgreSQL cluster. For the background session started during development:

```powershell
New-Item -ItemType File -Force .runtime/shop/STOP
```

The runner seeds only missing catalog rows on startup. Restarting does not erase orders. Database credentials `darwin:darwin_demo` are synthetic local demo credentials; PostgreSQL listens only on loopback with password authentication. Gateway: http://127.0.0.1:8010/shop/catalog. The normal Vite UI proxies `/shop` to this gateway.

## Inspect, recover, and reset

```powershell
.\.venv\Scripts\python.exe -m darwin.shop.cli inspect
.\.venv\Scripts\python.exe -m darwin.shop.cli verify
.\.venv\Scripts\python.exe -m darwin.shop.cli reconcile
.\.venv\Scripts\python.exe -m darwin.shop.cli drain
# Stop workload requests first. Resets only the selected dedicated shop DB.
.\.venv\Scripts\python.exe -m darwin.shop.cli reset --confirm-reset
```

`reconcile` replays pending orders with their original key and payload. Ambiguous downstream failures leave a pending order and retain its reservation; no stock is released while a payment may have committed. The mock payment provider always captures valid requests. Declines/refunds and automated reconciliation are outside this baseline. Out-of-stock orders fail permanently for their key; a new attempt needs a new key.

Notification receiver delivery and outbox acknowledgment are separate commits, so retrying after acknowledgment loss does not deliver twice. The baseline calls delivery synchronously. A continuously polling queue worker is Phase 3 work.

## PostgreSQL integration checks

The local runner creates a separate `darwin_shop_test` database. The test fixture refuses any database name without the `_test` suffix, starts isolated services on ports 18010-18013, resets only that test DB, and stops its processes after the suite.

```powershell
$env:DARWIN_TEST_DATABASE_URL='postgresql://darwin:darwin_demo@127.0.0.1:55432/darwin_shop_test'
.\.venv\Scripts\python.exe -m pytest -q
```

Verified on 2026-11-03: 17 tests passed (9 foundation + 8 shop integration checks), covering fresh boot/catalog, checkout/ledger consistency, exact reset, replay with unchanged ledgers, concurrent duplicate requests, concurrent overselling prevention, invalid input, ambiguous capture response recovery, capture payload conflicts, and delivery acknowledgment replay. Without the environment variable the integration checks are explicitly skipped, not passed. One existing upstream TestClient deprecation warning remains.

TypeScript and Vite production build passed. Dependencies passed `pip check`. A real checkout and replay through Vite's `/shop` proxy both returned HTTP 200 with the identical order; subsequent ledger verification found zero violations and zero pending notifications. This leaves one synthetic notebook order in the local demo database under key `phase2-proxy-smoke`. Full browser interaction verification for the new shop controls could not run because the browser-control connection failed; live service and proxy checks were used instead.

## Docker deployment (prepared, not executed)

```powershell
docker compose up --build -d --wait
docker compose run --rm seed python -m darwin.shop.cli verify
docker compose down
```

Only the gateway is published, on loopback port 8010. Internal services and PostgreSQL use an internal Compose network. Persistent data uses the named `shop-data` volume. Stop the native runner first to release port 8010. `docker compose down` preserves the data volume. The PostgreSQL 18 volume is mounted at `/var/lib/postgresql`.

To reset a stopped-traffic Compose demo, use `docker compose run --rm seed python -m darwin.shop.cli reset --confirm-reset`. Do not reset while workloads are running.

The Docker image build, Compose startup/readiness, and container shutdown still need a machine with a working Docker engine. Phase 2's full exit gate stays open until those checks pass.

## Limits and next work

The two-second checkout budget bounds scheduling of downstream retries; HTTP connect/read timeouts and PostgreSQL statement/lock limits are independently bounded, so it is not a strict wall-clock cancellation guarantee. End-to-end deadline propagation and fault testing remain later work. Ledger checks must run when workload traffic is quiescent. Passing baseline checks does not stand in for the five adversarial invariant suites planned in Phase 6.

Phase 3 will implement the four configurable controls and verify that every genome field changes deployed behavior.

Implementation references: [PostgreSQL row locks](https://www.postgresql.org/docs/17/explicit-locking.html), [Compose readiness dependencies](https://docs.docker.com/compose/how-tos/startup-order/).
