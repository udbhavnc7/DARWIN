# Phase 1 acceptance record

Completed: 2026-11-03 (Asia/Calcutta).

## Delivered

- [x] DARWIN scope and baseline defined.
- [x] Architecture and repository layout documented.
- [x] Five invariants and retry, cache, notification, timeout, and resource semantics defined.
- [x] Version-one Pydantic contracts for experiments, genomes, candidates, evaluations, metrics, violations, artifacts, and events.
- [x] FastAPI health/project endpoints and request-validation endpoint.
- [x] React/TypeScript UI with live API connection and configuration validation.
- [x] Local startup instructions and pinned dependency snapshots.
- [x] Environment check and next-phase prerequisite recorded.

## Verification

- `python -m pytest -q` in the project virtual environment: 9 passed. One upstream Starlette TestClient deprecation warning for httpx; tests succeed.
- `npm --prefix frontend run build`: TypeScript check and Vite production build passed.
- Browser at `http://127.0.0.1:5173`: API CONNECTED displayed; selected Flash sale, clicked Validate configuration, and observed the success message.
- UI inspected visually; it labels the architecture as planned and reports that no experiments have run.
- Python requirements frozen in `requirements.lock.txt`; npm dependencies pinned in `frontend/package-lock.json`.

## Inspected machine

| Item | Observation |
| --- | --- |
| CPU | Intel Core i5-13450HX, 10 cores / 16 logical processors |
| RAM | 23.7 GiB reported |
| C: free space | Approximately 159.8 GiB before setup |
| Python | System 3.14.3; project virtual environment uses installed 3.11.15 |
| Node / npm | 20.20.1 / 10.8.2 |
| Git | 2.56.0.windows.2 |
| Docker / Compose | Not on PATH; Docker executable absent from standard installation location |
| WSL | Default version 2, but reports required Windows/virtualization features unavailable |

## Next phase

Implement the shop backend and its baseline Compose deployment. Before the container acceptance checks, enable the required WSL2/virtualization features and install/start Docker Desktop with Linux containers. System setup may require administrator interaction and a reboot. This was not attempted during Phase 1. No shop containers or experiment workers currently exist.

The API and Vite preview started for this session listen only on loopback. Their process IDs and logs are in the ignored `.runtime/` directory. Normal manual startup/shutdown instructions are in README.md.
