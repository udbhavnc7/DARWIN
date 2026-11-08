# DARWIN

DARWIN searches supported backend configurations, tests performance and business correctness, and records reproducible evidence of the best observed tradeoffs.

**Current stage: Phase 5 performance measurements.** Run repeatable Locust workloads on Windows, compare real configurations across three repetitions, and inspect latency samples, errors, CPU time and peak memory. The smoke runner remains available. See the [benchmark guide](docs/PHASE_5.md), [execution guide](docs/PHASE_4.md) and [roadmap](ROADMAP.md).

## Run locally (PowerShell)

Use Python 3.11+ and Node 20.19+ (or a compatible newer release). This workspace was verified with Python 3.11.15 and Node 20.20.1.

```powershell
# From the repository root; first-time setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
npm --prefix frontend ci

# Terminal 1: API
.\.venv\Scripts\python.exe -m uvicorn darwin.main:app --host 127.0.0.1 --port 8000

# Terminal 2: UI (from the repository root)
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173. Interactive API documentation: http://127.0.0.1:8000/docs. Use Ctrl+C in each terminal to stop. Start the separate shop with `.\.venv\Scripts\python.exe scripts/run_shop.py` (requires local PostgreSQL binaries); see the Phase 2 guide for Docker and integration-test commands. API keys are not required.

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

See the [Phase 4 execution guide](docs/PHASE_4.md) for event streaming, artifact downloads, and reruns.

Docker is not installed on the inspected machine and WSL2 prerequisites are disabled. Local PostgreSQL allows shop verification now; the container acceptance checks still require a working Linux-container Docker engine and Compose. See [Phase 2 record](docs/PHASE_2.md).

Implementation references: [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/) and [Vite setup](https://vite.dev/guide/).

