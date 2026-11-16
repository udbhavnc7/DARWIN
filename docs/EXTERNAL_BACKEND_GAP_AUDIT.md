# External backend evolution — gap audit

> Snapshot: 16 November 2026. Branch: `feat/real-project-evaluation`.
> Baseline before this increment: working tree clean at `ee2898b`.

## 1. What already exists (must be preserved)

| Area | Location | Status |
| --- | --- | --- |
| Checkout lab genome, simulator, NSGA-II | `architecture.py`, `simulator.py`, `search.py` | Intact. Checkout-only. |
| Docker/native sandboxes, faults, invariants | `docker_sandbox.py`, `fault_suite.py`, `invariants.py` | Intact. Bound to the demo shop. |
| Evidence / experiments | `experiments.py`, SQLite, artifacts | Intact. Project tables already coexist. |
| Real Project Mode | `repository_*`, `project_*`, Sanchay adapter | Intact. **Client-side reporting**, not a server backend. |
| Generic read-only architecture map | `project_architecture.py` | Intact. Inspection for many stacks; execution is not. |
| Simulated screening | `project_simulation.py` | Intact. Always labelled `SIMULATED` / `NOT_MEASURED`. |

## 2. Directive gaps this increment closes

1. No generic **BackendAdapter** for deployable architecture candidates.
2. No isolated runner that deploys an **external** backend (shop Docker sandbox is shop-specific).
3. Sanchay is honestly a local app; it cannot satisfy “evolve a real backend architecture”.
4. UI is Choose → Understand → Run → Result, not **Connect → Understand → Challenge → Evolve → Prove**.
5. Support levels `INSPECTABLE` / `EVALUABLE_WITH_SETUP` / `READY_FOR_MEASURED_EVOLUTION` are missing.
6. No first genuine public backend with measured replica/worker comparisons.
7. Docs `EXTERNAL_BACKEND_*.md` and `JUDGE_SCRIPT.md` are missing.

## 3. Safety constraint on this host

Docker CLI is installed (`desktop-linux` context) but the Linux engine is **not running**, and Docker Desktop is not installed at the default path. Untrusted or even reviewed repository code must **not** be executed on the Windows host. Live measured evolution therefore requires a Linux Docker engine; otherwise the product stays read-only plus an honestly labelled recorded fallback when one exists.

## 4. First reference target

Public sample **Python/Flask + Redis** from `https://github.com/docker/awesome-compose` (`flask-redis/`), CC0, pinned commit `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`.

DARWIN will **not** run that repository’s Compose file or Dockerfile. A reviewed adapter copies only `app.py` and `requirements.txt` into a DARWIN-owned image and Compose stack (official `redis:7-alpine`, generated nginx, gunicorn, loopback publish, no host Docker socket).

## 5. Reuse plan

- Search ranking helpers (`dominates`, `fronts`, `crowding`) for a tiny architecture genome.
- `performance.metrics` for p95 / error rate / throughput from HTTP samples.
- Existing inspection importer, evidence store, FastAPI router, Sanchay adapter, checkout lab.
- New code is additive: `isolated_backend.py`, `http_compose` adapter, verdict policy for architectures, UI stages.
