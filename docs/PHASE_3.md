# Phase 3: configurable architectures

Status as of 2026-11-04: implemented and verified locally. Container execution checks remain pending a working Docker/WSL2 environment. Phase 4 has not started.

## Delivered

| Control | Real behavior | Verification |
| --- | --- | --- |
| API replicas: 1, 2, 3 | Separate API services behind round-robin gateway; `X-Darwin-Instance` identifies the responder | Three native API processes each received three of nine requests |
| Catalog cache: off, 10s, 30s | Redis caches catalog descriptions and prices with expiry; availability and checkout price stay authoritative in PostgreSQL | Real Redis command counts, miss/hit headers, both configured TTLs, expiry and fresh stock after checkout |
| Notifications: sync, queued | Sync calls delivery after confirmation; queued returns after transactional enqueue and uses a separate polling worker | Jobs stay pending without a worker, drain on startup, and survive worker stop/restart |
| Retry policy: none, idempotent_only | One or two outbound attempts respectively; retries keep identical request keys and payloads | Real local HTTP responder fails first attempt; observed attempt counts differ correctly |

`Genome` rejects unsupported values, unknown fields, booleans in numeric controls, and unsafe retry modes. The deliberately vulnerable fixture remains Phase 6 work. Canonical sorted JSON produces a stable SHA-256 genome hash. This hash identifies settings, not the implementation version; Phase 4 manifests will also record source/configuration evidence.

The same genome generates a Compose deployment and topology nodes/edges. All 36 combinations are covered by mapping tests. Every generated active service set fits within 4 aggregate CPU cores and 4096 MiB of configured memory limits. These are configured limits, not measured resource use. Native processes do not enforce those Docker caps.

## Run a native candidate

The local runner requires PostgreSQL binaries on PATH and, for caching, `redis-server`. Run one candidate at a time. Stop the current runner with Ctrl+C, or create its `.runtime/shop/STOP` file and wait for it to exit before starting another.

```powershell
.\.venv\Scripts\python.exe scripts/run_shop.py --genome examples/baseline.json
# Or, after stopping the first runner:
.\.venv\Scripts\python.exe scripts/run_shop.py --genome examples/cached-queued.json
```

The cached/queued example starts three API processes, Redis on loopback port 6380, and a notification worker on 8016. Gateway remains on 8010; API replicas use 8013-8015. The runner retains the existing synthetic shop database; switching candidates does not reset it. Use the explicit reset command with traffic stopped before fair comparisons. Redis is ephemeral, namespaced by genome, and closed with the runner. The candidate currently launched for review uses this cached/queued example.

## Generate a deployment bundle

From the source checkout:

```powershell
.\.venv\Scripts\python.exe -m darwin.architecture examples/cached-queued.json --output artifacts/cached-queued
```

Produces `genome.json`, `compose.yaml`, and `topology.json`. The generated Compose file uses this checkout's absolute build path and a genome-specific project name/volume. Regenerate it when moving the checkout. Docker commands below are prepared but have not been executed here:

```powershell
docker compose -f artifacts/cached-queued/compose.yaml config
docker compose -f artifacts/cached-queued/compose.yaml up --build -d --wait
docker compose -f artifacts/cached-queued/compose.yaml down
```

Stop the native shop before using the same published port. The root `compose.yaml` remains the Phase 2 baseline template. Redis and the worker appear only in applicable generated deployments; each API replica has a distinct service name. Docker readiness, image builds, container counts, resource enforcement, and cleanup still need live verification.

## Preview in the application

Open http://127.0.0.1:5173 and use **Explore a configuration**. The preview validates settings and shows their services, connections, and hash. It does not deploy a candidate. The existing baseline diagram is a reference configuration, not a live topology detector.

`POST /api/genomes/preview` accepts the genome and returns its validated representation, hash, and topology with `deployment_verified: false`. The UI was verified in the browser with three replicas, 10-second caching, and queued notifications; the expected three API nodes, Redis, and worker appeared. The shop also displayed connected.

## Verification record

- Full suite: 68 tests passed, including PostgreSQL and Redis integration tests. One existing upstream Starlette/httpx deprecation warning remains.
- After tightening resource caps and replacing the retry stub with a real HTTP responder, the affected architecture/foundation subset passed again: 55 tests.
- Frontend TypeScript check and production build passed; `pip check` found no broken requirements.
- Initial integration attempt found the stopped local database; restarting the dedicated runner resolved it. No application test failure was concealed.

To reproduce the full suite while the local shop cluster is running:

```powershell
$env:DARWIN_TEST_DATABASE_URL='postgresql://darwin:darwin_demo@127.0.0.1:55432/darwin_shop_test'
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run build
```

The integration suite uses the separate `_test` database and its own service/Redis ports. If prerequisites are absent, those tests are explicitly skipped. Worker tests cover queued work across stop/start; comprehensive fault timing, traces, and recovery analysis remain Phase 6 work.

## Remaining limitations

Native behavior checks support local correctness claims, not container-performance claims. The gateway uses round-robin without automatic unhealthy-node removal; outage behavior will be measured in later phases. The cache falls back to PostgreSQL when Redis is unavailable. The worker can attempt a job more than once; its synthetic receiver uses the job key to prevent duplicate effects. The current worker polls the shared PostgreSQL outbox without a lease; broader queue scaling and fault schedules remain outside this phase.

Next implementation phase: the experiment runner, budgets, cancellation, SQLite evidence records, and repeatable candidate execution. Carry the pending Phase 2/3 Docker checks into that integration work; do not mark container acceptance complete until executed.

References: [Redis SET expiration](https://redis.io/docs/latest/commands/set/), [Docker Compose services and limits](https://docs.docker.com/reference/compose-file/services/).
