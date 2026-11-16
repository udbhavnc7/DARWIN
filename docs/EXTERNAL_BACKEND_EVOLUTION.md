# External backend evolution

> Status: implemented and measured on a local Linux Docker engine.
> Branch: `feat/real-project-evaluation`. Last verified 16 November 2026.

DARWIN was originally a lab for one demonstration checkout service. This
increment adds a second, separate capability: **inspect a genuine public GitHub
backend, deploy its original topology inside a DARWIN-owned isolated stack,
apply a small reviewed architectural change, and compare the two with live HTTP
measurements and a correctness oracle.**

Nothing in the existing checkout lab, simulator, NSGA-II search, fault suite or
evidence store was replaced. External backend evaluation lives beside it and
reuses the same metric, evidence and verdict machinery.

---

## 1. The user journey

The external backend screen follows five stages. Every stage maps to a real
state transition, not a slide:

| Stage | What the user does | What actually happens |
| --- | --- | --- |
| **Connect** | Pastes a public GitHub URL, or picks a catalogued example | Read-only HTTPS import at a pinned commit; the source is cached locally; the user explicitly consents to the download |
| **Understand** | Reads the architecture map and support level | File-backed detection classifies the source and lists proven facts separately from unsupported features |
| **Challenge** | Picks `faster`, `spike`, `resources` or `recover` | The adapter restricts the eligible candidates to those the challenge can actually measure |
| **Evolve** | Starts a quick or full run | A DARWIN-owned Dockerfile and Compose stack are generated, the baseline and candidates are deployed in turn, and HTTP traffic plus a business oracle are recorded |
| **Prove** | Reads the verdict, comparison table and change proposal | The verdict policy decides; evidence files and a downloadable bundle are registered with SHA-256 digests |

Technical detail is folded into an **Advanced evidence** disclosure on the
result screen: raw metrics, the manifest, environment, replay notes, candidate
diff, parity checks and file digests. The default view stays at the decision.

---

## 2. Supported targets today

| Target | Type | Adapter | License | Pinned commit | Support level |
| --- | --- | --- | --- | --- | --- |
| [Sanchay](https://github.com/udbhavnc7/Sanchay) | Client data processing (no server backend) | `sanchay-reporting-v1` | not declared in the catalog | `7e1bc4cdd31e` | `READY_FOR_MEASURED_EVOLUTION` (local Node harness) |
| [docker/awesome-compose `flask-redis`](https://github.com/docker/awesome-compose) | Flask + Redis backend | `flask-redis-compose-v1` | CC0-1.0 | `30f4b7f6a6c3` | `READY_FOR_MEASURED_EVOLUTION` (Linux Docker required) |
| [dockersamples/nginx-node-redis](https://github.com/dockersamples/nginx-node-redis) | Node/Express + Redis backend | `node-redis-compose-v1` | Apache-2.0 | `2cd75d3b61385` | `READY_FOR_MEASURED_EVOLUTION` (Linux Docker required) |

The two container targets prove adapter reuse: a different repository, runtime,
port and counter sentence, with only a typed manifest and file allowlist
changing. The adapter base class, isolation boundary, measurement loop,
correctness oracle and verdict policy are shared.

Any other public repository can still be **inspected** read-only. It is never
described as optimized. If no reviewed adapter matches, the inspection returns
`INSPECTABLE` (or `EVALUABLE_WITH_SETUP` when a reviewed adapter exists but a
prerequisite is missing) and the reason.

---

## 3. What counts as a measured change

Candidates are deployment-level topologies that the reviewed adapter can
deploy and observe, not arbitrary rewrites:

- **Flask target:** baseline `1 replica × 1 gunicorn worker`; candidates
  `2 replicas × 1 worker` and `1 replica × 2 workers`. Redis stays shared.
- **Node target:** baseline `1 Express replica`; candidate `2 Express
  replicas`. The app is single-process, so no worker candidate is claimed.
- **Sanchay:** baseline three report traversals; candidate one shared
  traversal. This is a client computation comparison, not a server topology.

Each candidate is described in a reviewed manifest: adapter id and version,
runtime, app port, allowlisted source files, detection markers, candidate
dimensions, allowed challenges, and a SHA-256 over the canonical manifest. A
candidate that the runner cannot deploy is never generated.

### Measurement

| Dimension | How it is measured |
| --- | --- |
| `p50`, `p95`, `p99` | Per-request latency from seeded HTTP samples through the gateway |
| Throughput | Completed requests per second inside a bounded window |
| Error rate | Non-2xx or failed requests among the samples |
| CPU seconds | Docker stats delta over the measurement window |
| Peak memory | Per-container memory high-water mark |
| Recovery | For `recover`, a web replica is restarted and the gateway is probed every 50 ms until a healthy response; zero failed probes means another replica covered traffic |

`quick` mode runs a bounded window for the baseline plus the challenge's
primary candidate. `full` mode runs every reviewed candidate and the fault
restart, then produces a Pareto view of p95 / errors / replicas.

### Correctness, not just HTTP 200

The business oracle for the two container targets is the shared Redis counter:
`GET /` must return the reviewed counter sentence and the viewed-count integer
must strictly increase through the gateway. A restarted replica must become
healthy again. Availability alone is explicitly not treated as business
correctness, and the verdict note says so.

Sanchay's oracle is stronger: totals, category spending, payee amounts,
refund treatment, transfer exclusion, currency scoping, determinism and input
immutability must match the original byte-for-byte after canonicalisation.

---

## 4. Verdict policy

Thresholds live in `backend/darwin/backend_verdict.py`:

- minimum improvement on the challenge metric: **8.0%**
- maximum error rate: **5.0%**
- maximum tolerated regression on any non-primary metric: **5.0%**

| Verdict | Meaning |
| --- | --- |
| `VERIFIED_IMPROVEMENT` | Clears the improvement gate, no correctness failure, no material regression elsewhere |
| `TRADEOFF_REQUIRES_CHOICE` | Wins on the challenge metric but regresses beyond 5% on cost, tail latency or throughput; the operator must choose |
| `BASELINE_RETAINED` | No measured candidate clears the gates; keep the original topology |
| `INCONCLUSIVE` | Sampling incomplete or the challenge metric could not be compared |
| `REJECTED_INCORRECT` | A required correctness check failed |
| `FAILED_INFRASTRUCTURE` | The isolated runner was unavailable or did not complete |
| `NO_FEASIBLE_CANDIDATE` | The adapter produced nothing deployable |
| `UNSUPPORTED_TARGET` | No reviewed adapter matches the source |

Simulated screening can never occupy a measured slot: `simulation_cannot_win`
is asserted in the policy payload, and simulated evaluations carry
`evidence_kind = "simulated"` and `NOT_MEASURED`. The change document changes
with the verdict: a verified improvement says "Recommended topology", a
tradeoff says "operator choice, not an automatic recommendation", a retained
baseline says "no deployment change is proposed". A change bundle is only
exported for `VERIFIED_IMPROVEMENT` and `TRADEOFF_REQUIRES_CHOICE`; everything
else returns `409`.

---

## 5. Measured results on this host

All numbers below are from live runs on a local Linux Docker engine
(`linux/amd64`, cgroup v2), platform `nt`, with `NO_PROXY=127.0.0.1` so
loopback traffic does not go through a system proxy.

| Evaluation | Target | Challenge | Verdict | Headline |
| --- | --- | --- | --- | --- |
| `3017d1c9` (full) | Flask + Redis | faster | `TRADEOFF_REQUIRES_CHOICE` | p95 **29.9% better** (5.38 ms → 3.77 ms), but CPU **+39.0%** and peak memory **+82.7%**; 3/3 correctness checks |
| `01b40c18` (quick) | Flask + Redis | faster | `BASELINE_RETAINED` | Replicas and extra workers were both slower on this small bounded window; original retained |
| `7311728c` (quick) | Nginx + Node + Redis | faster | `TRADEOFF_REQUIRES_CHOICE` | p95 **4.1% better** (3.53 ms → 3.39 ms), CPU **+32.9%**, memory **+64.5%** |
| `5c77b62c` (quick) | Nginx + Node + Redis | recover | `TRADEOFF_REQUIRES_CHOICE` | Recovery **100% better** (0.464 s → 0 s, second replica covered the restart), CPU **+39.6%**, memory **+63.6%**; 2/2 checks |
| `fa56054f` (quick) | Nginx + Node + Redis | faster | `BASELINE_RETAINED` | No candidate beat the original on the bounded window |
| `e3057b59` (full) | Sanchay | faster | `VERIFIED_IMPROVEMENT` | **22.4% faster at 50,000 rows**, 97% paired win rate, 68/68 checks |
| `ea35093f` (quick) | Sanchay | faster | `VERIFIED_IMPROVEMENT` | ~59.7% faster in the smaller quick fixture, 40/40 checks |
| `343c346a`, `4aa2c7d3`, `39347c62` | Various | — | `NOT_MEASURED` | Simulated screening only; excluded from measured claims |

The honest story is the point: two replicas reduce tail latency and can remove
a single-replica outage, but they cost CPU and memory. On a 6 req/s bounded
window the benefit is sometimes not even visible, so DARWIN keeps the baseline
rather than declaring a winner. The UI shows the tradeoff and asks the operator
to choose.

---

## 6. Architecture of the implementation

```
Connect        repository_import.py
               └─ read-only HTTPS GitHub fetch, pinned SHA, size ceilings,
                  symlinks not followed, cached source tree
Understand     project_capabilities.inspect_source
               └─ file-backed classification, support level, prerequisites,
                  supported_evaluations, candidates preview
               adapters/registry.py
               └─ reviewed adapters by id; container adapters only for
                  evaluation_type = backend_architecture
Evolve         adapters/http_compose.py
               └─ detect / describe / candidates / measure / verify / explain
               isolated_backend.py
               └─ DARWIN-owned image + Compose, nginx gateway, loopback bind,
                  read-only rootfs, dropped caps, resource limits
               backend_verdict.decide_architecture
               └─ correctness gate, improvement gate, regression gate
Prove          repository_evaluations.py
               └─ run lifecycle, cancellation, events, evidence registration,
                  change document, bundle
```

Reuse is deliberate:

- `performance.metrics` computes p95/p99/error rate from HTTP samples.
- The evidence store (`experiments.py`, SQLite) already had `repository_inspections`,
  `project_evaluations` and `project_events` tables; no parallel store was added.
- The FastAPI router, event stream and export patterns follow the existing
  experiment/search APIs.
- `project_architecture` remains the generic read-only map for arbitrary stacks.
- `project_simulation` remains the labelled screening path and is never mixed
  into measured verdicts.
- Sanchay keeps its existing client harness and adapter contract.

The dependency direction is one-way: adapters import shared metric/verdict
helpers; the checkout lab does not know about repositories.

---

## 7. HTTP surface

All routes are served on `127.0.0.1` only and inherit the optional
`DARWIN_API_TOKEN` guard. Websockets check the same token.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/repositories/catalog` | Trusted examples, adapter catalog, presets, screening boundary |
| `POST` | `/api/repositories/inspect` | `{url, ref, consent}` — import and classify source; no execution |
| `POST` | `/api/repositories/validate-manifest` | Review a proposed manifest against the hashed reviewed one; no execution |
| `GET` | `/api/repositories/inspections` | Recent inspections |
| `GET` | `/api/repositories/inspections/{id}` | One inspection |
| `GET` | `/api/repositories/inspections/{id}/candidates` | Eligible candidates for a challenge, no execution |
| `POST` | `/api/project-evaluations` | `{inspection_id, adapter_id?, mode, challenge}` — start a run, `202` |
| `GET` | `/api/project-evaluations` | Recent evaluations |
| `GET` | `/api/project-evaluations/{id}` | One evaluation (internal `_` keys stripped) |
| `POST` | `/api/project-evaluations/{id}/cancel` | Cooperative cancellation |
| `GET` | `/api/project-evaluations/{id}/events` | Poll events |
| `WS` | `/ws/project-evaluations/{id}?after=` | Live progress stream |
| `GET` | `/api/project-evaluations/{id}/artifacts/{name}` | Digest-verified evidence file from the allowlist |
| `GET` | `/api/project-evaluations/{id}/diff` | Candidate diff |
| `GET` | `/api/project-evaluations/{id}/change` | Change proposal (409 when no change is authorised) |
| `GET` | `/api/project-evaluations/{id}/bundle` | Zip of allowlisted evidence, digest checked |

`validate-manifest` accepts the manifest body plus its `sha256`. It recomputes
the digest, compares it with the reviewed adapter manifest, re-validates every
relative source path, the runtime and the app port. A valid reviewed manifest
returns `{valid: true}`; a tampered body, unsafe path, unsupported runtime or
bad port returns `{valid: false, errors: [...]}`. The route cannot start
anything.

---

## 8. Evidence

An evaluation registers an allowlisted set of files under
`artifacts/experiments/project-evaluations/<id>/`: `benchmark.json`,
`candidate.diff`, `change.md`, `environment.json`, `parity.json`, `replay.md`
and the manifest/verdict artifacts. Each file is recorded with its SHA-256 and
byte size. `/artifacts/...` and `/bundle` re-verify the digest before serving.
Files outside `ARTIFACT_NAMES` are not served, and the bundle contains only
registered files.

`environment.json` records `isolation: linux-docker`,
`repository_compose_used: false`, the platform and the bounded load window, so
a reader can see exactly what was executed.

---

## 9. Reproduction

Prerequisites: Python 3.11+, Node 20+, a **local Linux Docker engine**
(Docker Desktop or another Linux engine; a stopped engine is fine until a
container run), and network access to GitHub for the first import.

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt   # Windows path
PYTHONPATH=backend .venv/Scripts/python.exe -m uvicorn darwin.main:app \
  --host 127.0.0.1 --port 8000
```

Then open the app, choose **New / Exhibition → External backend**, pick the
Flask or Node example, and run a quick evaluation. Or drive the API:

```bash
curl -s -X POST http://127.0.0.1:8000/api/repositories/inspect \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://github.com/docker/awesome-compose","ref":"master","consent":true}'

curl -s -X POST http://127.0.0.1:8000/api/project-evaluations \
  -H 'Content-Type: application/json' \
  -d '{"inspection_id":"<id>","mode":"quick","challenge":"faster"}'
```

On Windows, set `NO_PROXY=127.0.0.1,localhost` in the shell that starts the
API, otherwise a system proxy can intercept loopback traffic used for the
HTTP samples.

If the Linux engine is not running, inspection still works, but the candidate
preview and start call explain that measured execution is unavailable. DARWIN
does not fall back to running repository code on the host.

---

## 10. Honest limits

- Only the reviewed adapters and their declared topologies are evaluated. This
  is not a general-purpose “optimize any repository” compiler.
- The container targets are small public counters. Load is bounded (6 req/s,
  seconds-long windows) because this is a single-host exhibition lab, not a
  load-testing service. Latency numbers are comparative, not capacity claims.
- The Flask/Node candidates change process topology. They do not add databases,
  rewrite application code, or evaluate Kubernetes, multi-host scheduling,
  message brokers or autoscaling.
- The correctness oracle is the adapter's: counter monotonicity and restart
  health for the counters, byte-identical reports for Sanchay. That is a real
  business check for these apps, not a universal one.
- The API is unauthenticated by default and must stay on `127.0.0.1`. Do not
  expose it to a network, and do not point these targets at real payment or
  customer data.
- Recorded showcase data is labelled as recorded. It exists for exhibition
  fallback, never as a substitute for a live measured run.
