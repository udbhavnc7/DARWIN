# Phase 4: experiment runner and evidence store

Status: local execution implemented and verified. Docker adapter is implemented but container execution remains unverified because Docker/WSL2 is unavailable. Final live checks: 2026-11-06.

## Delivered

- A single worker with a durable SQLite experiment queue record, candidate/evaluation IDs, lifecycle status, and a 20-active-request admission limit.
- Manual candidate submission, deduplication, repetition/candidate/attempt budgets, execution deadline, and cancellation.
- Fresh sandbox per repetition: unique database, loopback ports, and native processes, or unique Compose project/volume in Docker mode.
- Startup/readiness, two catalog warm-up requests, seeded checkout-and-replay checks, quiescent ledger verification, notification drain, and cleanup.
- Source snapshots, source digest, generated Compose file, package/platform metadata, request evidence, service logs, ledger output, ownership records, and SHA-256 manifests.
- Persistent ordered events with REST and WebSocket replay cursors.
- Candidate reruns, registered artifact downloads, and hash verification on download.
- Browser controls to start/cancel a native experiment and inspect each repetition's artifacts.

## What a completed run means

This phase executes smoke checks, not a performance benchmark or adversarial feasibility gate. Every evaluation is marked `measurement_kind: smoke_only` / `gate: not_checked`. No latency, resource-use measurement, Pareto ranking, or claim of improvement is fabricated. The `normal` profile currently means the small deterministic smoke sequence; flash-sale/checkout-heavy execution, latency constraints, and fault schedules are rejected until their later phases.

`native_smoke` uses real local HTTP services, PostgreSQL, and optional Redis. It does not enforce OS CPU/memory limits and records that limitation. `docker_smoke` generates per-container limits and rejects configurations whose summed limits exceed the request. Docker enforcement still needs real validation. Native configured-budget checks are planning checks only.

## Startup

Use the README's backend/UI commands. Run only one control-plane process per evidence directory; a file lock prevents multiple workers from owning it. Do not run multiple Uvicorn workers.

The native adapter needs a running dedicated PostgreSQL cluster with CREATE/DROP DATABASE privileges. The existing local shop runner supplies one at port 55432:

```powershell
.\.venv\Scripts\python.exe scripts/run_shop.py
.\.venv\Scripts\python.exe -m uvicorn darwin.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

Use separate terminals. If the existing runner already owns port 55432, reuse it. Experiment services use dynamic ports, so the live shop can stay open. Each attempt creates and deletes only its own `darwin_run_<evaluation UUID>` database. Redis must be on PATH for cached native candidates. Override the PostgreSQL DSN using `DARWIN_NATIVE_DATABASE_URL` if needed; do not use a production database. Full environment variables and credentials are not dumped into evidence.

Default persistence: `artifacts/experiments/experiments.sqlite3` and one directory per experiment. Override the root with `DARWIN_EXPERIMENT_DIR`. Source files used by services are copied into each run's `source/` directory, including uncommitted backend changes, with a source-file hash manifest. Local Python package versions and the lock file are also recorded. No Git commit is claimed where one does not exist.

## API

| Route | Behavior |
| --- | --- |
| POST /api/experiments | Validate and enqueue manual genomes; returns 202 |
| GET /api/experiments | List stored runs, newest submitted first |
| GET /api/experiments/{id} | Status, budget usage, candidates, evaluations and artifacts |
| POST /api/experiments/{id}/cancel | Request cancellation; queued work cancels immediately |
| GET /api/experiments/{id}/events?after=N | Persisted events after sequence N |
| WS /ws/experiments/{id}?after=N | Replay then stream events through terminal status |
| GET /api/candidates/{id} | Candidate genome and evaluations |
| POST /api/candidates/{id}/rerun | New experiment/evaluation IDs with the same genome, seed and request settings |
| GET /api/experiments/{id}/artifacts/{evaluation_id}/{name} | Download only a registered artifact; reject altered hashes |

Reruns execute the current checkout snapshot and record its new digest. They do not silently pretend to reproduce an older implementation; compare source hashes before interpreting differences. Historical snapshots remain on disk for explicit replay. Pareto and adversarial trace APIs are deferred to the phases that generate those results.

Example submission:

```json
{
  "mode": "native_smoke",
  "seed": 42,
  "genomes": [{"app_replicas": 1, "catalog_cache_ttl_s": 0,
    "notification_mode": "sync", "retry_policy": "idempotent_only"}],
  "budget": {"max_candidates": 12, "real_test_budget": 6,
    "repetitions": 3, "wall_clock_s": 900}
}
```

The complete requested repetition groups must fit in the budget before admission. Failed attempts consume a slot. Execution stops on the first failure; remaining candidates are not presented as tested. Cancellation is cooperative around bounded HTTP/database calls and subprocess polling. Cleanup has its own bounded grace period and can extend past the experiment execution deadline. A terminal status is stored after cleanup has been attempted.

## Failure and restart recovery

Normal completion, failure, and cancellation stop owned processes/drop owned databases, or run Compose teardown for the unique project. Logs remain on disk. If cleanup fails, new and already queued experiments are blocked from deployment. An interrupted nonterminal run is marked failed on API restart and requires resource review rather than being retried automatically.

Inspect that run's saved `ownership.json`, service logs, and Compose file. Clean up only its recorded resources after verifying identity; historical PIDs alone are not proof of ownership. Then stop the API and run:

```powershell
.\.venv\Scripts\python.exe -m darwin.recovery --root artifacts/experiments
```

This command checks for remaining matching processes, occupied recorded ports, owned databases, or labeled Docker resources. It does not delete resources. It clears the recovery block only when resources are absent. Restart the API afterward. An unavailable database or Docker daemon prevents recovery verification.

## Verification

- Full suite: 81 tests passed, including the real PostgreSQL/Redis integration suite.
- After adding explicit rejection of unsupported latency constraints, the affected experiment subset passed: 14 tests.
- Frontend TypeScript and production build passed; dependency consistency passed.
- A real native baseline experiment completed three fresh repetitions, with all logs/manifests retained and cleanup complete.
- Browser-started run `693cfebe-36f0-4d7b-8368-b2e7161d7c60` completed three repetitions with three API replicas, Redis, and a queued notification worker. After restarting the API, the run was still accessible, its downloaded manifest matched the stored SHA-256 digest, and the recorded sandbox resources were absent.
- Run `47e7fdd6-5716-4be1-a1ad-0a5e58274a69` was cancelled after it started sandbox processes. Its terminal status was `cancelled` after one attempt. The independent recovery check found no remaining recorded processes, listening ports, or evaluation database. A live WebSocket client reconnected through the frontend proxy after event 2 and received events 3–5, ending with cancellation; the replay matched the persisted REST event history.
- Unit/API checks cover queued/active cancellation, timeout cleanup, readiness failure, cleanup failure blocking queued work, restart interruption handling, persisted event ordering, WebSocket resume, new IDs on rerun, artifact registration, and tamper rejection.

The native smoke path is validated locally. Container image build/startup/shutdown, actual Docker resource enforcement, crash injection at every possible process-start boundary, and performance measurements remain unverified or scheduled for later phases.
