# DARWIN

DARWIN searches supported backend configurations, tests performance and business correctness, and records reproducible evidence of the best observed tradeoffs.

DARWIN runs the search and demonstration workflow locally on Windows. The dashboard can simulate a configuration, run fault experiments, and compare measured configurations that pass the feasibility gate. The safe configuration passed three full fault repetitions, and the duplicate-payment fixture was rejected in all three. The local simulator fit averaged 27.0% p95 error across nine held-out repetitions. See the [roadmap](ROADMAP.md), [search guide](docs/PHASE_8.md), and [validation and demonstration guide](docs/PHASE_10.md).

## Run locally (PowerShell)

Use Python 3.11+ and Node 20.19+ (or a compatible newer release). This workspace was verified with Python 3.11.15 and Node 20.20.1.

```powershell
# From the repository root; first-time setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
npm --prefix frontend ci

# Required for native Windows fault experiments and search
.\scripts\setup_toxiproxy.ps1

# Terminal 1: API
.\.venv\Scripts\python.exe -m uvicorn darwin.main:app --host 127.0.0.1 --port 8000

# Terminal 2: UI (from the repository root)
npm --prefix frontend run dev

# Terminal 3: interactive demo shop (from the repository root)
.\.venv\Scripts\python.exe scripts/run_shop.py
```

Open [the dashboard](http://127.0.0.1:5173/) or the [interactive API documentation](http://127.0.0.1:8000/docs). Use Ctrl+C in each terminal to stop. The native shop and native experiments require PostgreSQL binaries on PATH. Cached native candidates require Redis. [Setup, reset, and integration tests](docs/PHASE_2.md)

```powershell
.\.venv\Scripts\python.exe -m pytest
npm --prefix frontend run build
```

## Repository

- `backend/darwin/`: FastAPI application and versioned Pydantic contracts.
- `frontend/`: React/TypeScript UI and Vite development proxy.
- `tests/`: request-validation and evidence-contract checks.
- `docs/`: scope, architecture, contract semantics, and phase acceptance records.
- `artifacts/experiments/`: SQLite run history, source snapshots, manifests, and per-repetition evidence; ignored by Git.

## Current endpoints

| Endpoint | Purpose |
| --- | --- |
| GET /api/health | Process health and project identity |
| GET /api/project | Baseline and planning defaults |
| POST /api/experiments/validate | Validate a request without running or persisting it |
| POST /api/experiments | Queue a smoke check or measured comparison |
| GET /api/experiments/{id} | Check progress, cleanup, and evidence |
| POST /api/experiments/{id}/cancel | Cancel pending or running work |
| POST /api/simulate | Estimate performance and show calibration scope |
| POST /api/genomes/compose | Download a Compose file for the selected architecture |
| POST /api/searches | Start bounded NSGA-II, random, or hill-climbing search |
| GET /api/searches/{id} | Read generations, lineage, measured results, and the Pareto front |

See the [Phase 4 execution guide](docs/PHASE_4.md) for event streaming, artifact downloads, and reruns.

The dashboard selects Docker when it detects a local Linux engine and lets you switch to Native under **Run settings**. Docker measurements require cgroup v2. The Docker acceptance suite passed on Docker Desktop. See the [Docker acceptance results](docs/DOCKER_ACCEPTANCE.md).

Use **Architecture** to adjust the checkout stack, see the service graph update, simulate it, or hand the selected configuration to **Experiments**. Save a downloaded Compose file at the repository root to run that configuration with Docker Compose.

Use **Theme** to choose Greenhouse, Hazard, Rosewire, Terracotta, or Ink & Paper. The choice persists in your browser and also applies to the Three.js splash screen, which you can replay from the theme picker.

The local release bundle is `artifacts/demo/darwin-workspace.zip`. It contains the app source, verified run evidence, and a recorded demonstration of the earlier interface. Extract it before opening `recorded-demo.html`.

Implementation references: [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/) and [Vite setup](https://vite.dev/guide/).

