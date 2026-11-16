# External backend evolution — gap audit

> Snapshot: 16 November 2026. Branch: `feat/real-project-evaluation`.
> Baseline before this increment: working tree clean at `ee2898b`.
> Status: all gaps below are closed in code and validated live; see
> `EXTERNAL_BACKEND_EVOLUTION.md`, `EXTERNAL_BACKEND_SECURITY.md`,
> `EXTERNAL_BACKEND_VALIDATION.md` and `JUDGE_SCRIPT.md`.

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
   Closed by `adapters/base.py` + `adapters/http_compose.py` + typed
   `backend_manifest.py`; two reviewed manifests share one implementation.
2. No isolated runner that deploys an **external** backend (shop Docker sandbox is shop-specific).
   Closed by `isolated_backend.py`: DARWIN-owned image and Compose, loopback
   gateway, no repository Dockerfile/Compose execution.
3. Sanchay is honestly a local app; it cannot satisfy “evolve a real backend architecture”.
   Kept as a labelled client-pipeline boundary case; the Flask and Node
   samples provide the genuine backend targets.
4. UI is Choose → Understand → Run → Result, not **Connect → Understand → Challenge → Evolve → Prove**.
   Closed in `ProjectEvaluation.tsx` and `ProjectVerdict.tsx` with an
   Advanced evidence disclosure.
5. Support levels `INSPECTABLE` / `EVALUABLE_WITH_SETUP` / `READY_FOR_MEASURED_EVOLUTION` are missing.
   Implemented in `project_capabilities.inspect_source` and `repository_import`.
6. No first genuine public backend with measured replica/worker comparisons.
   Closed: live Flask and Node runs with measured p95, CPU, memory, recovery
   and correctness; see the validation report.
7. Docs `EXTERNAL_BACKEND_*.md` and `JUDGE_SCRIPT.md` are missing.
   Written: evolution, security, validation and judge script.

## 3. Safety constraint on this host

Docker CLI is installed (`desktop-linux` context). During this increment the
Linux engine was **running**, so live measured evaluations were possible on
`linux/amd64` with cgroup v2. A stopped engine is still handled honestly:
inspection remains available, and a measured run returns
`FAILED_INFRASTRUCTURE` with the reason instead of falling back to the host.

Untrusted or even reviewed repository code must **not** be executed on the
Windows host. There is no host-execution path: application source is copied
into a DARWIN-owned image and run only inside the isolated Linux Docker stack
(internal network, loopback publish, read-only rootfs, dropped capabilities,
non-root users, resource limits). When no Linux engine is available, the
product stays read-only or uses an honestly labelled recorded fallback.

## 4. Reference targets

Public sample **Python/Flask + Redis** from `https://github.com/docker/awesome-compose` (`flask-redis/`), CC0, pinned commit `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`.

DARWIN does **not** run that repository’s Compose file or Dockerfile. A reviewed adapter copies only `app.py` and `requirements.txt` into a DARWIN-owned image and Compose stack (official `redis:7-alpine`, generated nginx, gunicorn, loopback publish, no host Docker socket).

The second target, **`dockersamples/nginx-node-redis`** (Apache-2.0, pinned `2cd75d3b61385ab4cd490af9d0facc5d8595bca7`), proves adapter reuse: a different repository, Express runtime, port and counter sentence, with only the typed manifest and file allowlist changing.

## 5. Reuse plan

- Search ranking helpers (`dominates`, `fronts`, `crowding`) for a tiny architecture genome.
- `performance.metrics` for p95 / error rate / throughput from HTTP samples.
- Existing inspection importer, evidence store, FastAPI router, Sanchay adapter, checkout lab.
- New code is additive: `isolated_backend.py`, `http_compose` adapter, verdict policy for architectures, UI stages.
- Implemented as planned. `backend_verdict.py`, `backend_manifest.py`,
  `adapters/registry.py` and the five-stage UI were added; the checkout lab
  and its tables were not modified.
