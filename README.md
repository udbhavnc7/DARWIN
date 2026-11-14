<div align="center">

# DARWIN

**Better backends. Built on evidence.**

A local-first architecture lab that designs, deploys, breaks, verifies, and ranks real checkout backends.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node](https://img.shields.io/badge/Node-20.19%2B-5FA04E?logo=nodedotjs&logoColor=white)](https://nodejs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-96%20passing%20%C2%B7%2013%20integration-2ea44f)](#testing)
[![Status](https://img.shields.io/badge/status-MVP%20complete%20%C2%B7%20~75%25%20to%20production-176541)](#project-status)
[![License: MIT](https://img.shields.io/badge/license-MIT-176541.svg)](LICENSE)

</div>

![DARWIN overview](docs/images/overview.png)

> **Status:** all ten MVP phases are complete and the app is roughly **75% of the way to a production-ready release**. Everything described here runs locally today. The remaining work is hardening and generalization, not missing core functionality. See [Project status](#project-status) or the detailed [project context](CONTEXT.md).

---

## Contents

- [Why DARWIN](#why-darwin)
- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [The dashboard](#the-dashboard)
- [Quickstart](#quickstart)
- [Measured evidence](#measured-evidence)
- [Architecture](#architecture)
- [API](#api)
- [Testing](#testing)
- [Project status](#project-status)
- [Project context](CONTEXT.md)
- [Exhibition runbook](docs/EXHIBITION.md)
- [Documentation](#documentation)
- [License](#license)

---

## Why DARWIN

Most architecture tools stop at a diagram. You move boxes around, look at an estimated score, and hope the production system behaves the same way.

DARWIN closes that loop:

- Every candidate is a **real, deployable checkout backend**, not a model of one.
- Every result comes from **measured or replayed runs** with saved seeds, artifacts, and hashes.
- **Correctness gates override speed.** A fast configuration that double-charges a customer is rejected, not ranked.
- Search results are **reproducible**: candidate lineage, fault traces, and replay commands are stored with the evidence.
- Simulation is only a **screening tool**. Simulated numbers are labeled and can never be presented as winners.

The result is a lab where a backend decision can be argued with data instead of intuition.

---

## What it does

DARWIN runs one checkout application under controlled variation and adversarial conditions.

### Four supported controls

| Control | Options | What actually changes |
| --- | --- | --- |
| **API replicas** | 1, 2, 3 | Stateless checkout instances behind the gateway |
| **Catalog cache** | Off, 10 s, 30 s | Redis-backed cache for descriptive catalog reads only; prices and stock stay authoritative |
| **Notifications** | Synchronous, Queued | Inline delivery, or a transactional outbox drained by a background worker |
| **Retries** | None, Idempotent-only | Whether transient failures are retried with the original request key. Unsafe retries exist only in a deliberately vulnerable test fixture |

The genome is typed and hashed. Invalid combinations are rejected before anything is deployed. Request timeout is intentionally fixed rather than exposed as a fifth control, so comparisons stay comparable.

### Three workload profiles

| Profile | Shape |
| --- | --- |
| **Normal traffic** | Mixed catalog and checkout traffic at a steady rate |
| **Flash sale** | Sudden demand concentration with stock contention |
| **Checkout heavy** | Checkout-dominant traffic that stresses payment and inventory paths |

### Three fault families

- **Database delay and disconnection** through Toxiproxy
- **Application service outage** during live checkout traffic
- **Ambiguous timeouts and duplicate delivery**, including unsafe retry behavior

### Five business invariants

| ID | Invariant |
| --- | --- |
| **I-01** | At most one successful capture per payment idempotency key |
| **I-02** | Confirmed quantities never exceed seeded stock |
| **I-03** | Every confirmed order references a successful capture for its exact amount |
| **I-04** | Replaying a request key creates no extra business effects; a changed payload is rejected |
| **I-05** | Completed notifications have receiver evidence, and accepted jobs survive a specified worker failure |

A configuration must pass deployment, all repetitions, every executed invariant, the error threshold, and the resource budget before its performance is allowed to count.

---

## How it works

```mermaid
flowchart LR
    A[Design<br/>genome] --> B[Screen<br/>SimPy]
    B --> C[Deploy<br/>isolated sandbox]
    C --> D[Measure<br/>load + resources]
    D --> E[Break<br/>inject faults]
    E --> F[Verify<br/>5 invariants]
    F -->|feasible| G[Rank<br/>Pareto front]
    F -->|violation| H[Reject<br/>with evidence]
    G --> I[Evolve<br/>next generation]
    H --> I
    I --> B
```

1. **Design.** Pick a supported configuration from the typed genome space.
2. **Screen.** The calibrated simulator estimates latency so search can spend its real-run budget wisely. Simulated results are always labeled and never promoted as winners.
3. **Deploy.** The candidate starts in an isolated Compose project or a private native sandbox with fresh data.
4. **Measure.** Seeded Locust workloads record raw latency, throughput, errors, CPU seconds, peak memory, and recovery time.
5. **Break.** Fault schedules inject database latency, service outages, ambiguous responses, and duplicate delivery.
6. **Verify.** The invariant oracle inspects recorded business state before ranking. Performance cannot compensate for a failed gate.
7. **Evolve.** NSGA-II, random search, or hill climbing proposes the next generation from measured feedback.

Each run preserves its generated configuration, source snapshot, seeds, manifests, logs, fault traces, artifact hashes, and a replay request. See [Measured evidence](#measured-evidence).

---

## The dashboard

The React dashboard is the primary interface to the lab. A five-step product tour explains the whole system, from the design-measure-verify-evolve loop to the correctness gate and measured search. Open it from the sidebar, from **How DARWIN works** on the overview, or directly with [`?tour=1`](http://127.0.0.1:5173/?tour=1).

![Product tour](docs/images/tour.png)

| Workspace | What you do there |
| --- | --- |
| **Overview** | See the workflow, baseline stack, and a machine-readiness panel that separates required tools from optional ones |
| **Architecture** | Shape the checkout topology, preview the service graph, simulate, or export Compose |
| **Experiments** | Run smoke checks, benchmarks, fault verification, request validation, or a judge-ready scenario with its observed duration |
| **Search** | Run NSGA-II, random, or hill-climbing searches; inspect lineage, measured gates, and the Pareto plot; open a saved feasible or rejected run offline |
| **Demo shop** | Place a simulated checkout and resend the same request to see idempotency, payment effects, and ledger counters |

![Architecture builder](docs/images/architecture.png)

The search workspace separates **proposed**, **simulated**, and **measured** evidence. Rejected candidates expose their violated invariant, the trace, and the original artifact downloads. When no measured candidate passes every gate, the workspace shows a "No candidate passed all gates" verdict with the rejection reasons and safe next choices; it never promotes a rejected candidate. A saved-run fallback is labelled **Recorded run** and cannot be mistaken for a live execution.

![Search results](docs/images/search.png)

Five palettes (Greenhouse, Hazard, Rosewire, Terracotta, Ink & Paper) persist per browser. The layout is responsive from desktop down to 360 px; the sidebar becomes a compact sticky header with a scrollable section bar.

<p align="center">
  <img src="docs/images/mobile.png" width="300" alt="DARWIN on a phone-sized viewport" />
</p>

---

## Quickstart

### Prerequisites

| Requirement | Needed for |
| --- | --- |
| **Python 3.11+** | API, worker, simulator, search, shop services |
| **Node 20.19+** | Dashboard build and dev server |
| **PostgreSQL binaries** (`initdb`, `pg_ctl`) on `PATH` | Native experiments and the interactive demo shop |
| **Redis** | Cache-enabled native configurations |
| **Toxiproxy** | Native fault experiments |
| **Docker Desktop** (optional) | Docker measurements and the containerized demo shop |

Verified with Python 3.11.15, Node 20.20.1, and Docker Desktop Engine 29.9.3 (Linux containers, cgroup v2) on Windows.

### Install

```powershell
# From the repository root
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
npm --prefix frontend ci

# Provisions the local Toxiproxy binary used by native fault runs
.\scripts\setup_toxiproxy.ps1
```

On Linux or macOS, use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`. The native fault adapter is implemented for Windows; outside Windows, use the Docker runtime for measured and fault experiments.

### Run

Start these in three terminals from the repository root:

```powershell
# Terminal 1 — control plane
.\.venv\Scripts\python.exe -m uvicorn darwin.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — dashboard
npm --prefix frontend run dev

# Terminal 3 — interactive demo shop
.\.venv\Scripts\python.exe scripts/run_shop.py
```

Then open:

- Dashboard: [http://127.0.0.1:5173/](http://127.0.0.1:5173/)
- Product tour: [http://127.0.0.1:5173/?tour=1](http://127.0.0.1:5173/?tour=1)
- Interactive API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Demo shop through Vite: [http://127.0.0.1:5173/#shop](http://127.0.0.1:5173/#shop)

The demo shop uses simulated payments, synthetic credentials, and a dedicated PostgreSQL cluster under `.runtime/shop/` on loopback only. It never touches an existing database. Press `Ctrl+C` in each terminal to stop.

### Docker demo shop

```powershell
docker compose up -d --build
# Gateway: http://127.0.0.1:8010/shop/catalog
docker compose down -v   # also removes the demo database volume
```

Docker measurements require a local Linux engine with cgroup v2 CPU quotas, swap limits, and `memory.peak`. See the [Docker acceptance guide](docs/DOCKER_ACCEPTANCE.md).

### First five minutes

1. Open the product tour.
2. On **Overview**, confirm **Machine readiness**. Required tools must be green; optional ones (for example Docker or Toxiproxy) are named with a remedy and their runs stay disabled.
3. In **Architecture**, change replicas, cache, notifications, and retries; watch the topology update.
4. In **Experiments**, start **Quick checkout smoke** (~30 s) or a larger comparison. Each preset records its own duration source.
5. In **Search**, inspect a completed run, its lineage, and the measured Pareto plot, or open the recorded feasible and rejected examples. The rejected example shows the no-feasible verdict without a live run.
6. In **Demo shop**, place an order, then resend it. The receipt is identical, stock is unchanged, and the ledger stays at one order, one capture, and one payment effect.

For a timed presentation checklist and the captured baseline, use the [exhibition runbook](docs/EXHIBITION.md).

---

## Measured evidence

These are actual results recorded by the project, not targets. They come from one search seed per strategy with three measured repetitions per configuration, so the ordering is evidence for these runs, not a general claim that one algorithm always wins.

| Strategy | Measured attempts | Feasible configs | Best feasible median p95 |
| --- | ---: | ---: | ---: |
| NSGA-II with simulation | 6 | 2 | **273.9 ms** |
| Random search | 6 | 2 | 351.8 ms |
| Hill climbing | 6 | 1 | 586.8 ms |
| NSGA-II without simulation | 6 | 2 | 410.9 ms |

The winning NSGA-II configuration used queued notifications and reduced median p95 from 315.8 ms to 273.9 ms versus its paired baseline, at the cost of higher CPU time (6.30 s → 7.59 s) and slightly longer recovery (5.0 s → 5.5 s). Both configurations sit on that run's Pareto front.

Other recorded findings:

- **Correctness beats latency.** The unsafe fixture measured 408.4 ms median p95 versus 483.0 ms for the matching safe configuration, yet it was rejected for I-01 after producing three payment effects for one key.
- **A fresh dashboard rerun** reproduced the duplicate-payment rejection in all three repetitions.
- **The simulator is screening, not proof.** After calibration, mean absolute p95 error across nine held-out repetitions was **27.0%**; one cached-normal holdout still missed by 53.9%.
- **The Docker search produced an empty Pareto front.** Both promoted candidates missed a recovery window in one repetition. The project reports that outcome instead of hiding it.
- **The held-out checkout-heavy run** kept the latency improvement (520.1 ms → 426.8 ms median p95) with substantially more variance (up to 1,150.3 ms).

Full reports: [Phase 10 validation](docs/PHASE_10.md) and [Docker acceptance](docs/DOCKER_ACCEPTANCE.md).

### Evidence and reproducibility

Each experiment stores:

- the generated configuration and its hash
- the exact source snapshot used for deployment
- seeds, tool versions, host metadata, and replay requests
- raw measurements or mergeable histograms
- fault schedules, traces, and invariant reports
- logs, manifests, artifact digests, and cleanup records

Runs live in `artifacts/experiments/` (ignored by Git). Export a verifiable bundle with:

```powershell
.\.venv\Scripts\python.exe scripts/export_evidence.py EXPERIMENT_ID --output artifacts/demo/darwin-evidence.zip
```

The exporter verifies every registered artifact and source digest before packaging. A fresh replay restores the saved source snapshot into a separate checkout, installs its locked dependencies, starts that API, and submits the saved replay request.

---

## Architecture

```mermaid
flowchart TD
    UI[React dashboard] --> API[FastAPI control plane]
    API --> Worker[Budgeted experiment worker]
    Worker --> Search[Random / hill climbing / NSGA-II]
    Search --> Sim[Calibrated SimPy screening]
    Sim --> Runner[Compose or native sandbox runner]
    Runner --> Shop[Shop services + PostgreSQL + optional Redis]
    Runner --> Tests[Locust workloads + fault injection + invariant checks]
    Tests --> Evidence[SQLite records + manifests + metrics + traces]
    Evidence --> Search
    Evidence --> API
```

One Python control-plane application runs the API and worker. The frontend talks to FastAPI over HTTP and WebSocket; Vite proxies `/api`, `/shop`, and `/ws` in development. Each measured shop configuration runs in its own isolated sandbox with fresh data and owned cleanup.

### Repository layout

| Path | Contents |
| --- | --- |
| `backend/darwin/` | FastAPI app, contracts, experiments, simulator, search, invariants, sandboxes, shop services |
| `frontend/` | React 19 + TypeScript + Vite dashboard, React Flow topology, Three.js overview art |
| `tests/` | Contract, architecture, experiment, fault, performance, search, shop, and Docker checks |
| `docs/` | Scope, architecture, contract semantics, phase acceptance records, guides, README screenshots |
| `scripts/` | Setup, demo shop, Docker and search validation, evidence export, demo rendering |
| `examples/` | Baseline and cached-queued genome examples |
| `compose.yaml` | Containerized demo shop with resource limits and health checks |
| `artifacts/` | Local run evidence and bundles (ignored by Git) |

Detailed contracts and scope: [Architecture](docs/ARCHITECTURE.md) and [Contracts](docs/CONTRACTS.md).

---

## API

The control plane exposes a JSON API with versioned Pydantic contracts. Unknown fields are rejected.

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Process health and project identity |
| `GET /api/project` | Baseline, runtime capabilities, and planning defaults |
| `GET /api/preflight` | Machine readiness, execution modes, optional-tool remedies; `?refresh=true` bypasses the 15 s cache |
| `GET /api/exhibition/scenarios` | Judge-ready presets with recorded or estimated durations and saved example IDs |
| `POST /api/exhibition/scenarios/{id}` | Start a preset as an ordinary measured experiment (`?runtime=native\|docker`) |
| `POST /api/experiments/validate` | Validate a request without running or persisting it |
| `POST /api/experiments` | Queue a smoke check, benchmark, or fault verification |
| `GET /api/experiments` | List saved experiments |
| `GET /api/experiments/{id}` | Progress, cleanup, metrics, and evidence |
| `POST /api/experiments/{id}/cancel` | Cancel pending or running work |
| `GET /api/experiments/{id}/events` | Replay lifecycle events from a sequence |
| `WS /ws/experiments/{id}` | Live event stream |
| `GET /api/candidates/{id}` | Candidate genome, parents, evaluation, and violations |
| `POST /api/candidates/{id}/rerun` | Rerun a candidate as a new evaluation |
| `GET /api/experiments/{id}/artifacts/{evaluation_id}/{name}` | Download a registered artifact |
| `POST /api/simulate` | Estimate performance with calibration scope and error labels |
| `POST /api/genomes/preview` | Resolve a genome into its deployment preview |
| `POST /api/genomes/compose` | Download a Compose file for the configuration |
| `POST /api/searches` | Start a bounded NSGA-II, random, or hill-climbing search |
| `GET /api/searches` | List saved searches |
| `GET /api/searches/{id}` | Generations, lineage, measured results, and Pareto front |
| `GET /api/searches/{id}/events` | Replay search events |
| `POST /api/searches/{id}/cancel` | Cancel a running search |
| `POST /api/searches/{id}/rerun` | Rerun a search as a new run |

Interactive schema: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Execution and event-stream details: [Phase 4 guide](docs/PHASE_4.md).

---

## Testing

```powershell
# Fast suite (PostgreSQL/Redis integrations skip when those services are not configured)
.\.venv\Scripts\python.exe -m pytest -q

# Shop integration against a dedicated disposable database (name must end in _test)
$env:DARWIN_TEST_DATABASE_URL = 'postgresql://darwin:darwin_demo@127.0.0.1:55432/darwin_shop_test'
.\.venv\Scripts\python.exe -m pytest -q tests/test_shop.py

# Type-check and production build
npm --prefix frontend run build

# Full Docker acceptance: smoke, paired benchmarks, faults, unsafe fixture, search
.\.venv\Scripts\python.exe scripts/validate_docker.py --output artifacts/docker-acceptance

# Equal-budget search comparison
.\.venv\Scripts\python.exe scripts/validate_searches.py --output artifacts/validation/search-comparison.json
```

Latest local run (2026-11-14):

- **104 passed, 14 skipped.** The skipped tests are the PostgreSQL and Redis integrations; they are explicitly skipped, not silently passed.
- **14 shop integration tests passed** against the dedicated `darwin_shop_test` database, including replay, concurrency, ledger, and reset.
- **Frontend production build passed**, including `tsc --noEmit`.
- **Quick checkout smoke completed in 18 s** with three measured attempts and verified cleanup; the unsafe-payment scenario rejected all three repetitions.
- **Docker acceptance passed all 21 repetitions** on Docker Desktop Engine 29.9.3, including cleanup verification. The Docker daemon was not running during the latest exhibition check, so Docker options are shown as disabled.
- **Product tour checks passed 10/10**: deep link, focus, step navigation, dots, link routing, and close behavior.

Known build note: the Three.js overview scene produces a separate 528 kB chunk and Vite warns about the 500 kB threshold. It is lazy-loaded, so it does not block the dashboard.

---

## Project status

**MVP: complete (10/10 phases). Production readiness: ~75%.**

What is done:

- Typed genome, canonical hashing, topology generation, and Compose export
- Real native and Docker sandboxes with lifecycle, budgets, cancellation, and cleanup
- Seeded workloads, measured metrics, and paired repetitions
- Fault injection and all five invariant checks, including a reproducible unsafe fixture
- Calibrated simulator used only for screening
- NSGA-II, random search, hill climbing, lineage, and measured Pareto ranking
- React dashboard with evidence inspection, reruns, search history, responsive layout, and a guided tour
- Exhibition layer: machine preflight, four judge-ready scenarios, explicit no-feasible verdict, labelled saved-run fallback, and demo-shop ledger/reset
- Saved evidence bundles with digest verification and replay instructions

What remains to reach a production-ready v1:

- **CI and release automation.** No workflow pipeline is committed yet; builds and tests are run locally.
- **Control-plane security.** The API currently assumes a trusted local operator and has no authentication or project isolation.
- **Broader validation.** Search comparisons currently use one seed per strategy; multi-seed, multi-host runs are needed before making general algorithm claims.
- **Docker search depth.** The accepted Docker search ended with an empty Pareto front; a larger budget should confirm recovery behavior.
- **Cross-platform native adapter.** Native fault experiments are Windows-specific; Docker is the route on Linux.
- **Packaging.** A one-command installer or containerized control plane would remove the manual three-terminal setup.
- **Demo assets.** The saved-search fallback is current, but the older walkthrough video predates the interface and should be re-recorded.
- **Later extensions.** Cloud/Kubernetes adapters, broader scenario matrices, and optional LLM explanations.

The project deliberately keeps negative and inconclusive results. They are part of the evidence, not something to tune away.

---

## Documentation

| Document | Contents |
| --- | --- |
| [Project context](CONTEXT.md) | Completion map, exact scope, verified evidence, gaps, and glossary |
| [Roadmap](ROADMAP.md) | Scope, ten phases, working rules, and extensions |
| [Architecture](docs/ARCHITECTURE.md) | System design, shop behavior, invariants, and scope boundary |
| [Contracts](docs/CONTRACTS.md) | Schema, lifecycle, budgets, comparability, and gate semantics |
| [Phases 1–10](docs/) | Acceptance records and implementation detail for each phase |
| [Exhibition runbook](docs/EXHIBITION.md) | Machine baseline, readiness checks, scenario durations, demo script, validation record, and limits |
| [Docker acceptance](docs/DOCKER_ACCEPTANCE.md) | Container runtime requirements, measurements, and cleanup verification |

For a guided walkthrough of the codebase, start with `backend/darwin/contracts.py`, then `experiments.py`, `fault_suite.py`, `search.py`, and finally `frontend/src/main.tsx`.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 udbhavnc7.
