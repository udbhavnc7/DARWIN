# DARWIN — Project Context

> **Snapshot:** 17 November 2026
> **Repository:** [github.com/udbhavnc7/DARWIN](https://github.com/udbhavnc7/DARWIN) (public, MIT)
> **Short version:** the ten-phase MVP is functionally complete. DARWIN is roughly **82% of the way to a production-ready release**; the remainder is multi-host validation, per-user security, deeper packaging, and refreshed demo assets — not missing core features.

This file is the single place to answer: *What is DARWIN, exactly? What has been built? How finished is it? What is still missing?*

---

## 1. What DARWIN is

DARWIN is a **local-first backend architecture lab** for one specific system: a checkout backend.

It generates supported configurations of that backend, deploys each candidate for real, measures it under seeded traffic and injected failures, rejects any candidate that violates defined business rules, and ranks the survivors by latency, CPU time, and recovery. Simulation is used only to decide which candidates deserve a real run.

In one sentence: **DARWIN is an evidence machine for backend architecture decisions, where correctness gates come before performance rankings.**

It is a working application, not a concept deck. The API, worker, sandboxes, fault injection, invariant oracle, simulator, search algorithms, dashboard, guided tour, evidence store, and replay path all exist and have been exercised.

---

## 2. The problem it solves

Ordinary architecture tools let you draw boxes and produce an estimate. That leaves three gaps:

1. **The estimate is not the system.** A diagram does not reveal queueing, contention, retry storms, or cleanup failures.
2. **Speed hides broken semantics.** A faster configuration can duplicate a payment or oversell stock; naive ranking rewards it.
3. **Results are not reproducible.** Without seeds, source snapshots, fault traces, and replay commands, a result cannot be defended later.

DARWIN closes all three: every candidate is deployed, every number comes from a recorded run, every rejection carries an invariant ID and a trace, and every result can be replayed.

---

## 3. Exact scope

DARWIN is deliberately narrow.

### The system under test

One checkout shop made of five services:

| Component | Role |
| --- | --- |
| Gateway | Routes catalog and checkout traffic to API replicas |
| Checkout / catalog API | Owns orders, catalog reads, idempotency keys, and request handling |
| Inventory | Reserves stock atomically; never below zero |
| Mock payment | Records captures against an idempotency key; no real money |
| PostgreSQL | Orders, inventory, payments, outbox, and ledgers |
| Redis (optional) | Catalog cache for cache-enabled genomes, and queue support where applicable |

### The search space

| Dimension | Supported values |
| --- | --- |
| API replicas | 1, 2, 3 |
| Catalog cache | Off, 10 seconds, 30 seconds |
| Notifications | Synchronous, queued through a transactional outbox |
| Retries | None, idempotent-only |
| Workloads | Normal, flash sale, checkout heavy |
| Fault families | Database delay/disconnection, service outage, ambiguous timeout/duplicate delivery |
| Request timeout | Fixed at 700 ms per downstream I/O operation, at most one retry; intentionally not a search control |

### The oracle

| ID | Rule |
| --- | --- |
| I-01 | At most one successful capture per payment idempotency key |
| I-02 | Confirmed quantities never exceed seeded stock |
| I-03 | Every confirmed order references a successful capture for its exact amount |
| I-04 | Replaying a key creates no extra business effects; a changed payload is rejected |
| I-05 | Completed notifications have receiver evidence; accepted jobs survive a specified worker failure |

### What DARWIN is not

- Not a generic cloud or Kubernetes optimizer
- Not a multi-tenant SaaS (the control plane assumes one trusted local operator)
- Not an LLM-driven system; the core loop works without a model
- Not a real payment processor; all payments are simulated
- Not an arbitrary code transformer; only the four typed controls vary
- Not a substitute for production load testing; results apply to this shop and this host

---

## 4. How a run works

```mermaid
flowchart LR
    A[Design genome] --> B[Simulation screen]
    B --> C[Deploy isolated sandbox]
    C --> D[Run seeded workload]
    D --> E[Inject faults]
    E --> F[Check 5 invariants]
    F -->|pass| G[Measure and rank]
    F -->|fail| H[Reject with evidence]
    G --> I[Next generation]
    H --> I
    I --> B
```

1. A typed **genome** selects replicas, cache, notifications, and retries.
2. The **SimPy simulator** estimates performance and ranks candidates for promotion. Its output is labeled simulated and can never pass a gate.
3. A promoted candidate is **deployed** into an isolated Docker Compose project or a private native sandbox with fresh data.
4. **Locust** applies a seeded workload; the runner records latency samples, throughput, errors, CPU time, peak memory, and recovery.
5. **Faults** are injected: database latency/disconnection, service outage, ambiguous payment responses, duplicate delivery.
6. The **invariant oracle** reads recorded business state. A violation rejects the candidate regardless of speed.
7. **Search** (NSGA-II, random, or hill climbing) uses measured feedback to propose the next generation. Feasible candidates are ranked on a measured Pareto front.

Every run stores its configuration, source snapshot, seeds, manifests, logs, fault traces, artifact hashes, and a replay request.

---

## 5. How complete is it?

### Headline

| Measure | State |
| --- | --- |
| MVP phases | **10 / 10 complete** |
| Core user workflows | **All working locally** |
| Production readiness | **~82% (judgment, not a computed metric)** |
| Tests | **216 passing, nothing skipped** locally; the **14 shop integration tests** reuse the demo cluster or start disposable PostgreSQL/Redis containers, and CI runs them with PostgreSQL and Redis services |
| Frontend production build | **Passing**, checked by CI on every push |
| Docker acceptance | **Re-verified on 2026-11-14** on Docker Desktop Engine 29.9.3 (Linux, cgroup v2), including recovery windows and cleanup |
| Exhibition path | **Verified on both runtimes:** native smoke, benchmark, and fault scenarios, plus Docker smoke, benchmark, faults, and search |

### Completion by area

Percentages are engineering estimates based on what is implemented, tested, and operated — not a formal score.

| Area | State | Estimate | What that means |
| --- | --- | ---: | --- |
| Domain model and contracts | Done | 100% | Typed genome, canonical hashing, versioned Pydantic contracts, rejection of unknown fields |
| Shop under test | Done | 95% | Five services, PostgreSQL, idempotency, atomic stock, outbox, seed/reset, ledger inspection; payments are simulated |
| Configuration controls | Done | 100% | Four controls change real deployment and request behavior |
| Experiment runner | Done | 90% | Native and Docker sandboxes, budgets, lifecycle, cancellation, cleanup, reruns |
| Measurement | Done | 90% | Seeded workloads, raw samples, p95, CPU, memory, paired repetitions |
| Faults and invariants | Done | 95% | Three fault families, five checkers, reproducible unsafe fixture |
| Simulator | Done, limited accuracy | 85% | SimPy model calibrated to 27.0% mean p95 error across nine holdouts; some misses are large |
| Search | Done, validation broader | 90% | NSGA-II, random, hill climbing, lineage, Pareto ranking; multi-seed campaign retained with every rejection |
| Dashboard | Done | 95% | Five workspaces, machine-readiness panel, judge scenario presets, saved-run fallback, no-feasible verdict, evidence inspection, reruns, tour, themes, responsive down to 360 px; formal accessibility audit pending |
| Evidence and replay | Done | 90% | SQLite history, artifact digests, source snapshots, export bundle, replay instructions |
| Docker path | Done | 85% | Full acceptance passed; the fresh search found two feasible candidates on its Pareto front |
| Native path | Done on Windows | 80% | Windows resource jobs and private PostgreSQL clusters; not cross-platform |
| Tests | Strong locally and in CI | 90% | 108 pass locally; 14 service integrations skip by default and run in CI with PostgreSQL and Redis; Windows native paths remain local-only |
| Security and multi-user | Partial | 35% | Loopback-only default, optional shared bearer token, no per-user accounts, quotas, or project isolation |
| Packaging and distribution | Partial | 65% | One-command start/stop launcher with readiness checks; no installer, service manager, or containerized control plane |
| Documentation | Strong | 92% | README, contracts, phase records, and an exhibition runbook; phase notes are annotated where later work closed their gaps |
| Demo assets | Partial | 80% | Recorded feasible/rejected search fallback is current; the older walkthrough video still predates the interface |
| CI and release automation | Partial | 55% | GitHub Actions runs the backend suite on Linux and Windows and builds the dashboard; Docker acceptance is a manual workflow; no automated release publishing |

**Why 82% and not 100%:** the MVP is feature-complete for the defined scope, but a production release also needs per-user authentication and isolation, quotas, multi-host validation, cross-platform native support, a packaged control plane, and refreshed demo assets. Those are real work, not polish.

---

## 6. What works today

### In the dashboard

- **Overview** with the product tour and a machine-readiness panel (required vs optional tools, execution modes, remedies)
- **Architecture** with live topology, simulation, Compose export, and hand-off to Experiments
- **Experiments** for smoke checks, benchmarks, fault verification, request validation, and four judge-ready scenario presets with observed durations
- **Search** for NSGA-II, random, and hill-climbing runs with lineage, gates, the Pareto plot, an explicit no-feasible verdict, and a saved feasible/rejected run fallback
- **Demo shop** where the same request key can be replayed against the real local shop
- Six lab themes — Green Texture (green + white default), Leather Red, Blueprint, Amethyst, Carbon Black, Midnight — persisted per browser
- A five-step product tour at `?tour=1`, from the sidebar, or from the overview
- A three.js calibration intro on first load: the gate stack assembles over the test deck, four genome controls sit on the bench, and a measuring beam verifies I-01…I-05 before the workspace takes over. Skippable with Escape, replayed from **Lab appearance → Replay calibration** or `?splash=1`, and static under reduced motion

### Hosted showcase

A read-only build of the same dashboard is published at [udbhavnc7.github.io/DARWIN](https://udbhavnc7.github.io/DARWIN/) so teammates can browse it without installing anything.

- **How it is built:** `npm run build:showcase` (Vite mode `showcase`, base `/DARWIN/`) bundles the JSON snapshots that `scripts/capture_showcase.py` reads from a running local API. A fetch shim in `frontend/src/showcase.ts` answers `/api` and `/shop` GETs from those snapshots, along with previews and simulations for all 36 genomes. Every other request returns 503 with "Needs a local install".
- **What is hosted:** nothing on the backend. No API, shop, database, or WebSocket. That keeps the Priority-0 "no shared deployment" rule intact.
- **Live bench:** from the hosted page, **Connect this computer** probes `127.0.0.1:8000` and, if the local stack answers, the fetch shim forwards `/api` to the API and `/shop` to the shop gateway instead of the snapshots. The API allows the published origin through CORS (with private-network access) but still binds to loopback. Measured smoke runs and shop checkouts were driven this way from the hosted page during verification.
- **Labelling:** a permanent "Recorded evidence from <date>, not a live run" banner appears on every page, switching to a green "Live bench" banner when connected. Without a bench, run, rerun, checkout, reset, and artifact-download controls are disabled.
- **Publishing:** the snapshot lives in `frontend/showcase/`, and `.github/workflows/pages.yml` redeploys on every push to `master`. The current snapshot holds 63 experiments and 12 searches, captured 2026-11-15 from commit `a23e2c1` on the native runtime.

### From the CLI and API

- Start, list, inspect, cancel, and rerun experiments
- Stream lifecycle events over WebSocket or replay them by sequence
- Inspect candidates, evaluations, violations, and downloadable artifacts
- Simulate a genome with explicit calibration scope
- Export a digest-verified evidence bundle
- Run the Docker acceptance suite and equal-budget search comparison
- Start, inspect, and stop the whole local stack with `scripts/demo.py`
- Protect every `/api` route with an optional shared bearer token
- Reset, reconcile, drain, and inspect the local demo shop

### Verified in the current environment

| Check | Result |
| --- | --- |
| Backend suite | 216 passed, nothing skipped; the 14 shop integrations auto-provisioned a disposable `darwin_shop_test` database and Redis on `127.0.0.1:16380` |
| Frontend build | Passed, including `tsc --noEmit`; app code, React, and the graph renderer ship as separate cacheable chunks, and the Three.js intro loads lazily |
| Preflight | Ready; required checks green, Docker and bundled Toxiproxy detected |
| Judge scenarios | Quick smoke completed in 18 s; unsafe payment rejected all 3 repetitions |
| Shop proof | Repeated request returned one order, one capture, one payment effect; reset cleared the ledger |
| Docker acceptance | 21 of 21 repetitions passed, including recovery windows and cleanup; the fresh search kept two feasible Pareto candidates |
| Docker benchmark | Median p95 102.75 ms baseline vs 77.65 ms for three replicas with a 10 s cache and queued notifications; zero measured errors |
| Unsafe fixture | Rejected for I-01 in all repetitions, with three payment effects per key |
| Product tour | 10 of 10 interaction checks passed |
| Calibration intro | Lifecycle check passed: shows on first load, auto-dismisses, remembers the session, replays from the palette register, and skips without console errors. Rendered on desktop and 390 px mobile in light and dark themes, plus reduced motion |
| Search comparison | Single seed: NSGA-II + simulation best at 273.9 ms median p95. Three-seed campaign: 11 / 12 searches completed; NSGA-II + simulation median-of-best 357.2 ms, random 407.6 ms, hill climbing 394.6 ms, NSGA-II without simulation 445.1 ms (2 / 3 completed); one seed-202 arm interrupted by a fault-measurement connection timeout |
| Simulator calibration | 27.0% mean absolute p95 error across nine held-out repetitions |
| Responsive layout | Verified at 1440, 900, 430, 390, and 360 px |
| Showcase deploy | Live at [udbhavnc7.github.io/DARWIN](https://udbhavnc7.github.io/DARWIN/); all five screens checked on desktop and mobile in all six themes, with no `/api` or `/shop` requests leaving the static bundle |
| Fresh-clone quickstart | Cloned from GitHub and followed the README: dependencies installed, Toxiproxy verified, `demo.py start` brought up shop, API, and dashboard |

---

## 7. What is still missing or risky

### Priority 0 — required before any shared deployment

| Gap | Why it matters |
| --- | --- |
| No per-user authentication or isolation | The optional shared token blocks anonymous access but cannot attribute, scope, or revoke a single operator |
| No quotas or rate limits | A token holder can still start expensive runs and consume the artifact disk |
| No project or tenant isolation | One control plane, one artifact root, one operator |

### Priority 1 — required for a credible v1

| Gap | Why it matters |
| --- | --- |
| Docker search is intentionally small | Two generations and six measured attempts found two feasible candidates; a larger budget would cover more of the 36 genomes |
| Native fault adapter is Windows-only | Linux users must use Docker for measured/fault runs |
| Packaging stops at the launcher | No installer, containerized control plane, or service manager |
| Recorded walkthrough video is outdated | It shows an earlier interface; the in-app tour and saved-search fallback are current |
| One host, one environment | No multi-host or cross-platform performance validation |

### Priority 2 — cleanup and polish

| Gap | Why it matters |
| --- | --- |
| Phase records keep their historical numbers | `docs/PHASE_10.md` and earlier phase notes preserve what was true at that capture; current results live in README, CONTEXT, and DOCKER_ACCEPTANCE |
| No formal accessibility audit | Keyboard and focus behavior are implemented, but no WCAG review has been recorded |
| Cloud/Kubernetes adapters | Explicitly out of MVP scope |
| Optional LLM explanations | Explicitly out of MVP scope |

---

## 8. Architecture at a glance

```mermaid
flowchart TD
    UI[React dashboard] --> API[FastAPI control plane]
    API --> Worker[Budgeted worker]
    Worker --> Search[NSGA-II / random / hill climbing]
    Search --> Sim[SimPy screening]
    Sim --> Sandbox[Docker Compose or native sandbox]
    Sandbox --> Shop[Shop + PostgreSQL + optional Redis]
    Sandbox --> Load[Locust + faults + invariant checks]
    Load --> Evidence[SQLite + artifacts + traces]
    Evidence --> Search
    Evidence --> API
```

| Path | Responsibility |
| --- | --- |
| `backend/darwin/contracts.py` | Genome, request, experiment, candidate, evaluation, metrics, violation, artifact, event contracts |
| `backend/darwin/experiments.py` | Experiment lifecycle, worker, budgets, persistence |
| `backend/darwin/fault_suite.py` | Fault schedules, recovery measurement, invariant orchestration |
| `backend/darwin/invariants.py` | I-01 through I-05 against recorded business state |
| `backend/darwin/simulator.py` | SimPy screening model |
| `backend/darwin/search.py` | NSGA-II, random search, hill climbing, lineage, Pareto ranking |
| `backend/darwin/shop/` | Gateway, catalog/checkout API, inventory, payment, worker, ledger CLI |
| `frontend/src/` | Dashboard, React Flow topology, Three.js art, tour, themes, responsive UI |
| `tests/` | Contract, architecture, experiment, fault, performance, search, shop, Docker checks |
| `docs/` | Scope, architecture, contract semantics, phase acceptance records |
| `scripts/` | Validation, evidence export, shop runner, Toxiproxy setup, demo rendering |

---

## 9. Where the evidence lives

| Evidence | Location |
| --- | --- |
| Run history and manifests | `artifacts/experiments/` (Git-ignored) |
| Search reports | `artifacts/validation/` (Git-ignored) |
| Docker acceptance | `artifacts/docker-acceptance*/` (Git-ignored) |
| Evidence bundles | `artifacts/demo/*.zip` (Git-ignored) |
| Committed acceptance narratives | `docs/PHASE_1.md` … `docs/PHASE_10.md`, `docs/DOCKER_ACCEPTANCE.md` |
| Exhibition baseline and runbook | `docs/EXHIBITION.md` |
| Offline search fallback | `frontend/public/recorded-example.json` (compact real runs, labelled recorded) |

A fresh checkout has the code and the written results, but not the historical run artifacts. That is intentional: evidence is produced locally and exported on demand.

---

## 10. How to verify this status yourself

```powershell
# Full suite: expect 216 passed. Integration tests find the demo cluster or start
# disposable Docker containers on demand, then clean them up.
.\.venv\Scripts\python.exe -m pytest -q

# Fast unit-only suite: no PostgreSQL or Redis required
.\.venv\Scripts\python.exe -m pytest -q -m "not integration"

# Start, inspect, and stop the whole local stack
.\.venv\Scripts\python.exe scripts/demo.py start
.\.venv\Scripts\python.exe scripts/demo.py status
.\.venv\Scripts\python.exe scripts/demo.py stop

# Optional: force the shop integration suite onto a specific disposable database
$env:DARWIN_TEST_DATABASE_URL = 'postgresql://darwin:darwin_demo@127.0.0.1:55432/darwin_shop_test'
.\.venv\Scripts\python.exe -m pytest -q tests/test_shop.py

# Type-check and production build
npm --prefix frontend run build

# Full Docker acceptance (requires a Linux Docker engine)
.\.venv\Scripts\python.exe scripts/validate_docker.py --output artifacts/docker-acceptance

# Equal-budget search comparison (requires native prerequisites)
.\.venv\Scripts\python.exe scripts/validate_searches.py --output artifacts/validation/search-comparison.json

# Three-seed campaign on the normal workload
.\.venv\Scripts\python.exe scripts/validate_searches.py --seeds 72,101,202 --workloads normal `
  --output artifacts/validation/search-multiseed.json
```

To exercise the UI:

1. Start the API, Vite dev server, and demo shop as described in the [README](README.md#quickstart).
2. Open `http://127.0.0.1:5173/?tour=1`.
3. Confirm the **Machine readiness** panel on Overview; optional tools should be explained, not failing.
4. Run the **Quick checkout smoke** card from **Experiments**.
5. In **Search**, open a completed run or the recorded feasible/rejected examples; inspect lineage, the Pareto plot, and the no-feasible verdict.
6. Place and replay an order in **Demo shop**; confirm the ledger stays at 1 order / 1 capture / 1 payment effect. The full runbook is in [docs/EXHIBITION.md](docs/EXHIBITION.md).

---

## 11. Phase history

| Phase | Outcome |
| --- | --- |
| 1 | Scope, contracts, repository layout, local scaffold |
| 2 | Baseline shop with gateway, API, inventory, payment, PostgreSQL, seed/reset, idempotency |
| 3 | Typed genome and four controls with real deployment effects and Compose generation |
| 4 | Experiment runner, SQLite evidence, events, artifacts, cancellation, reruns |
| 5 | Seeded workloads and real performance measurements with repetitions |
| 6 | Fault injection and the five-invariant oracle, including the unsafe fixture |
| 7 | Calibrated SimPy simulator used for screening only |
| 8 | NSGA-II, random, hill climbing, lineage, measured Pareto ranking |
| 9 | Dashboard with evidence inspection, React Flow topology, search history, responsive UI, guided tour |
| 10 | Equal-budget validation, Docker acceptance, honest negative results, evidence bundles |
| Post-MVP | Exhibition readiness: preflight panel, judge scenario presets, no-feasible verdict, saved-run fallback, shop ledger/reset, runbook |

---

## 12. Glossary

| Term | Meaning |
| --- | --- |
| **Genome** | The four-control configuration of the shop |
| **Candidate** | A genome proposed by a search or supplied manually |
| **Evaluation** | One candidate under one workload/fault schedule and repetition |
| **Repetition** | One isolated run within an evaluation; three are required for a measured result |
| **Gate** | Deployment, invariant, error, and resource checks that decide feasibility |
| **Feasible** | Every required repetition passed all executed gates |
| **Simulated** | Produced by the SimPy model; never a measured winner |
| **Measured** | Produced by a real deployed run with recorded evidence |
| **Pareto front** | Feasible candidates not dominated on latency, CPU time, and recovery |
| **Censored recovery** | Recovery was not observed inside the measurement window; not treated as zero |
| **Evidence bundle** | A digest-verified archive of results, source, traces, and replay instructions |

---

## 13. Notes for future contributors and AI assistants

- Read this file, the [README](README.md), and [CONTRIBUTING.md](CONTRIBUTING.md) before changing behavior.
- **Never present simulated output as measured evidence.** The separation is a core product guarantee.
- **Never let performance outrank a failed invariant.** I-01 through I-05 are hard gates.
- Preserve negative results. An empty Pareto front or an unimplemented baseline is still evidence.
- Run `pytest` and `npm --prefix frontend run build` before committing.
- `artifacts/` and `.runtime/` are Git-ignored; do not move historical runs into committed docs.
- Keep the public API contracts backward compatible or version them explicitly.
- When a phase changes, update its document rather than leaving a stale status line.
- Use the Docker path for portable measured and fault runs; the native fault adapter is Windows-specific.
