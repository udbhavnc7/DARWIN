# External backend validation report

> Snapshot: 16 November 2026. Branch: `feat/real-project-evaluation`.
> Latest code commit covered here: `5e9b39b` plus documentation.

This report records what was actually executed and observed while adding
external backend evolution. It separates live measurements from simulated
screening, and lists what remains unvalidated.

---

## 1. Environment

| Item | Value |
| --- | --- |
| Host OS | Windows 10.0.26300 (x64) |
| API | FastAPI on `http://127.0.0.1:8000` |
| Python | project `.venv`, `PYTHONPATH=backend` |
| Docker CLI | present, context `desktop-linux` |
| Docker engine | Linux engine available during live runs (`linux/amd64`, cgroup v2) |
| Demo shop | `http://127.0.0.1:8010` (`scripts/run_shop.py`) |
| Proxy | `NO_PROXY=127.0.0.1,localhost` required so loopback traffic bypasses a system proxy |
| Frontend | React 19 + TypeScript + Vite 7 |

No repository code was executed on the Windows host. Every container run used
the DARWIN-owned image and Compose stack described in
[EXTERNAL_BACKEND_SECURITY.md](EXTERNAL_BACKEND_SECURITY.md).

---

## 2. Automated tests

```bash
PYTHONPATH=backend .venv/Scripts/python.exe -m pytest -q
# 202 passed, 14 skipped
```

The 14 skips are the existing environment-gated suites (for example Docker
acceptance scenarios that require a specific setup); they are pre-existing and
unrelated to this increment. External backend tests alone:

```bash
PYTHONPATH=backend .venv/Scripts/python.exe -m pytest tests/test_external_backend.py -q
# 28 passed
```

Coverage in `tests/test_external_backend.py`:

| Area | Tests |
| --- | --- |
| Classification | Flask sample is a container backend; matching source without Docker is `EVALUABLE_WITH_SETUP`; unpinned source is inspection-only; a lookalike app is not given the adapter; wrong markers are rejected |
| Second target | `dockersamples/nginx-node-redis` is reviewed through the same interface; an incompatible repository is `UNSUPPORTED_TARGET` through the API |
| Isolation | Generated Compose matches the security policy; privileged mode and Docker socket are refused; source copy refuses traversal and symlinks |
| Manifest | Candidates expose only declared dimensions; `validate-manifest` accepts the reviewed manifest, rejects a tampered digest and unsafe paths |
| Verdicts | Throughput uses the real window; a recovery win with resource cost is a tradeoff; availability alone does not win; baseline retention produces no "Recommended topology" |
| Evidence | Stray files never become evidence; tampered evidence is refused; symlinked artifacts cannot escape; a folder without a manifest is not bundled; a record without registered evidence fails closed; recorded change is served as markdown; change export is `409` for `BASELINE_RETAINED` |
| API guards | Prerequisite mismatch is refused before execution; unknown challenge rejected; client-pipeline adapter tolerated by the candidates preview; websocket token guard |

The suite grew from 199 passed / 14 skipped before the second target and
manifest route to 202 passed / 14 skipped. No existing test was removed or
weakened; the new tests are listed below.

---

## 3. Live measured runs

All rows below are real runs against a local Linux Docker engine. Evaluation
IDs are from the SQLite evidence store; each has a registered evidence folder
with SHA-256 digests.

### 3.1 Flask + Redis (`docker/awesome-compose`, CC0, `30f4b7f6a6c3`)

Full run `3017d1c9-5755-4c2d-a7c8-c264f62f1b24`, challenge `faster`:

| Metric | Original 1×1 | 2 replicas × 1 worker | Change |
| --- | --- | --- | --- |
| p95 latency | 5.381 ms | 3.773 ms | **29.9% better** |
| Throughput | 6.0 req/s | 6.0 req/s | unchanged |
| CPU seconds / window | 0.1871 | — | **+39.0%** |
| Peak memory | 53.32 MB | — | **+82.7%** |
| Error rate | 0.0 | 0.0 | — |
| Correctness | passed | passed | 3/3 checks |

Verdict: `TRADEOFF_REQUIRES_CHOICE`, winner `replicas-2x1`. The change
document says the operator must choose; it does not call this an automatic
recommendation.

Quick run `01b40c18-88a6-4beb-8d86-c20236eecc17`, challenge `faster`:
baseline p95 3.660 ms; `replicas-2x1` 5.976 ms; `workers-1x2` 4.480 ms.
Verdict `BASELINE_RETAINED`. This is important negative evidence: adding
replicas is not automatically faster on a small bounded window, and DARWIN
keeps the original.

### 3.2 Nginx + Node + Redis (`dockersamples/nginx-node-redis`, Apache-2.0, `2cd75d3b6138`)

Quick run `5c77b62c-2724-489a-8c28-dbd9c98003e3`, challenge `recover`:

| Metric | Original 1 replica | 2 replicas | Change |
| --- | --- | --- | --- |
| Recovery after web restart | 0.464 s | 0.0 s | **100% better** |
| p95 latency | 3.842 ms | 3.582 ms | 6.8% better |
| CPU seconds / window | 0.2165 | 0.3023 | **+39.6%** |
| Peak memory | 39.41 MB | 64.47 MB | **+63.6%** |
| Correctness | passed | passed | 2/2 checks |

Verdict: `TRADEOFF_REQUIRES_CHOICE`. Zero failed probes means the second
replica served traffic while `web-1` restarted; the user saw no outage.

Quick run `7311728c-daf9-4eb0-a777-597fffdfa7c9`, challenge `faster`:
baseline p95 3.531 ms, candidate 3.385 ms (**4.1% better**), CPU **+32.9%**,
memory **+64.5%**. Verdict `TRADEOFF_REQUIRES_CHOICE` — below the 8% winner
gate but visible enough to report the cost.

Quick run `fa56054f-1e41-4c99-9e2d-ef275ee0d18a`, challenge `faster`:
`BASELINE_RETAINED`; no candidate beat the original.

These Node runs prove adapter reuse: different repository, Express runtime,
port 5000, a different counter sentence and `numVisits` key. The same
isolation, measurement, oracle and verdict code was used.

### 3.3 Sanchay (`sanchay-reporting-v1`)

Full run `e3057b59-3486-49aa-8a42-1043f6d234ff`, challenge `faster`:
`VERIFIED_IMPROVEMENT`. **22.4% faster at 50,000 rows**, 97% paired win rate,
68/68 correctness checks. No measured size regressed by 5% or more.

Quick run `ea35093f-cd67-42e9-af31-5f2631553825`: `VERIFIED_IMPROVEMENT`,
~59.7% faster in the smaller fixture, 40/40 checks.

Sanchay is a client data-processing target, not a server backend. It is
reported as such everywhere.

### 3.4 Simulated screening

`343c346a`, `4aa2c7d3`, `39347c62`: `NOT_MEASURED`, evidence kind
`simulated`. They never appear as measured candidates or winners.

---

## 4. Evidence integrity checks

For the evaluations above:

- `benchmark.json`, `candidate.diff`, `change.md`, `environment.json`,
  `parity.json` and `replay.md` were registered with SHA-256 and byte sizes.
- `/api/project-evaluations/{id}/artifacts/{name}` served only allowlisted
  names.
- `/api/project-evaluations/{id}/bundle` produced a zip containing only
  registered files, after digest verification.
- `environment.json` recorded `repository_compose_used: false` and
  `isolation: linux-docker`.
- Change export worked for the tradeoff runs and returned `409` for
  `BASELINE_RETAINED`.

The tests that tamper with evidence (`test_tampered_evidence_is_refused_not_served`,
`test_symlinked_artifact_cannot_escape_the_evidence_folder`,
`test_stray_files_never_become_evidence`) passed in the full suite.

---

## 5. API smoke checks

After restarting the API on `5e9b39b`:

| Check | Result |
| --- | --- |
| `GET /api/repositories/inspections` | `200` |
| `POST /api/repositories/validate-manifest` with an empty manifest | `200`, `valid: false` |
| `POST` with `FlaskRedisAdapter().manifest.as_dict()` | `200`, `valid: true`, computed SHA-256 equals reviewed SHA-256 |
| `POST` with unknown adapter | `404` (covered by unit test) |

The route is read-only and does not start containers.

---

## 6. Frontend validation

| Check | Command | Result |
| --- | --- | --- |
| Production build | `npm run build` in `frontend/` | passed |
| Showcase/recorded build | `npm run build:showcase` | passed |
| TypeScript | part of both builds | passed |

The five-stage screen (`Connect → Understand → Challenge → Evolve → Prove`)
renders for `backend_architecture` targets and for client-pipeline targets.
Advanced evidence is a disclosure, not the default view. The recorded showcase
serves the captured project evaluations, including the external runs, and is
labelled as recorded.

---

## 7. Not validated

Honest gaps in this increment:

- **No Windows-host execution comparison.** By design there is none; only the
  Linux Docker path is measured.
- **No multi-host, Kubernetes, autoscaling or managed-database evaluation.**
  Candidates are process topology on one host.
- **No production load.** The window is 6 req/s for a few seconds; results are
  comparative, not capacity planning.
- **Base images are not digest-pinned**, and build-time egress is open. See
  the residual-risk section in the security document.
- **The Docker daemon is trusted**; rootless mode and per-run VMs are out of
  scope for this prototype.
- **Only three adapters exist** (two container, one client pipeline). A new
  repository family needs a reviewed adapter and manifest; inspection alone
  does not make it evaluable.
- **The recorded showcase is not proof of a current live run.** It exists for
  exhibition fallback and is labelled as recorded.
- **No real payment, customer or production data** was used. The counters are
  synthetic; Sanchay ledgers are generated.

These limits are surfaced in the product and in
[EXTERNAL_BACKEND_EVOLUTION.md](EXTERNAL_BACKEND_EVOLUTION.md) rather than
being hidden behind a winner claim.
