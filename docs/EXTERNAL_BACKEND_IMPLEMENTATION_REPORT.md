# External backend implementation report

> 16 November 2026 · branch `feat/real-project-evaluation` · head `5e9b39b` + docs.

This is the seven-section delivery report for the external backend evolution
increment. Supporting detail is in
[EXTERNAL_BACKEND_EVOLUTION.md](EXTERNAL_BACKEND_EVOLUTION.md),
[EXTERNAL_BACKEND_SECURITY.md](EXTERNAL_BACKEND_SECURITY.md),
[EXTERNAL_BACKEND_VALIDATION.md](EXTERNAL_BACKEND_VALIDATION.md) and
[JUDGE_SCRIPT.md](JUDGE_SCRIPT.md).

---

## 1. What runs today

Live, measured, on this host (Windows + local Linux Docker engine):

| Target | Repository URL | Pinned SHA | What ran |
| --- | --- | --- | --- |
| Flask + Redis counter | `https://github.com/docker/awesome-compose` (`flask-redis/`) | `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562` | Full and quick measured evaluations; baseline and both replicas/workers candidates |
| Nginx + Node + Redis counter | `https://github.com/dockersamples/nginx-node-redis` | `2cd75d3b61385ab4cd490af9d0facc5d8595bca7` | Quick measured evaluations for `faster` and `recover`; baseline and two-replica candidate |
| Sanchay (client pipeline) | `https://github.com/udbhavnc7/Sanchay` | `7e1bc4cdd31e53380e7896b4a20a864bbebcee1e` | Quick and full client report comparisons in the local Node harness |

The two container targets execute only a DARWIN-owned image and Compose stack:
allowlisted source copy, generated nginx gateway, official Redis, internal
network, loopback publish, read-only rootfs, dropped capabilities, non-root
users, CPU/memory limits. The repository's Compose file, Dockerfile and nginx
config are never executed. `environment.json` records
`repository_compose_used: false`.

Both frontend builds pass, and the backend suite is 202 passed / 14 skipped
(on this machine, 16 November 2026). The full report is in
[EXTERNAL_BACKEND_VALIDATION.md](EXTERNAL_BACKEND_VALIDATION.md).

---

## 2. Recorded, inspection-only, unsupported

**Runs only in recorded mode:** the showcase build serves captured snapshots
of the evaluations above. It is labelled recorded and refuses requests that
would need the engine. It is an exhibition fallback, not a live measurement.

**Inspection-only:** any other public GitHub repository. DARWIN imports it
read-only at a pinned commit, classifies the stack, and shows proven facts and
gaps. Without a reviewed adapter it returns `INSPECTABLE` (or
`EVALUABLE_WITH_SETUP` when an adapter exists but Docker or another
prerequisite is missing) and cannot start a measured run.

**Simulated only:** architecture screening (`architecture-screening-v1`)
models candidates without executing code. It is `NOT_MEASURED`, carries
`evidence_kind: simulated`, and can never occupy a measured winner slot.

**Unsupported:** repositories whose stack does not match a reviewed adapter
for measured evolution; multi-host/Kubernetes/autoscaling targets; managed
database or message-broker topologies; arbitrary code rewrites. These are
reported as unsupported with the reason, not converted into a fake success.

---

## 3. Decisions changed, deployment, raw results and failures

Each candidate changes **deployable process topology**, not application
semantics:

| Target | Baseline | Candidate(s) | Deployed by |
| --- | --- | --- | --- |
| Flask + Redis | 1 replica × 1 gunicorn worker | 2 replicas × 1 worker; 1 replica × 2 workers | DARWIN-generated image + Compose; nginx gateway; shared Redis |
| Node + Redis | 1 Express replica | 2 Express replicas | Same runner; `node:22-alpine`, `npm ci --omit=dev --ignore-scripts` |
| Sanchay | Three report traversals | One shared traversal | Local Node harness, byte-identical output gate |

Raw measured results:

| Evaluation | Challenge | Verdict | Numbers |
| --- | --- | --- | --- |
| Flask `3017d1c9` full | faster | `TRADEOFF_REQUIRES_CHOICE` | p95 5.381 → 3.773 ms (**29.9% better**); CPU **+39.0%**; memory **+82.7%**; 3/3 checks |
| Flask `01b40c18` quick | faster | `BASELINE_RETAINED` | p95 3.660 ms baseline; replicas 5.976 ms; workers 4.480 ms |
| Node `7311728c` quick | faster | `TRADEOFF_REQUIRES_CHOICE` | p95 3.531 → 3.385 ms (**4.1% better**); CPU **+32.9%**; memory **+64.5%** |
| Node `5c77b62c` quick | recover | `TRADEOFF_REQUIRES_CHOICE` | recovery 0.464 s → 0 s (**100% better**); CPU **+39.6%**; memory **+63.6%**; 2/2 checks |
| Node `fa56054f` quick | faster | `BASELINE_RETAINED` | no candidate beat the original |
| Sanchay `e3057b59` full | faster | `VERIFIED_IMPROVEMENT` | **22.4% faster at 50,000 rows**, 97% paired win rate, 68/68 checks |
| Sanchay `ea35093f` quick | faster | `VERIFIED_IMPROVEMENT` | ~59.7% faster, 40/40 checks |

Failures and non-wins are part of the result: two quick runs retained the
baseline, and both container wins were reported as tradeoffs because CPU and
memory regressed. No deployed-run infrastructure failure was staged during
final validation; that path is covered by tests (`FAILED_INFRASTRUCTURE`,
isolation refusal, prerequisite refusal), not by an artificial outage. Early
development defects (hardcoded Flask detection, a Sanchay preview 500) were
fixed before the runs above; they were implementation bugs, not measured
verdicts.

The displayed topology comes from the same candidate object that generated
the Compose file; the runner records `compose_sha256` and cleanup status per
candidate. Cleanup status is visible in the evaluation record.

**Measured search scope:** `full` mode measures every reviewed candidate and
computes a Pareto view of p95 / errors / replicas. It is bounded enumeration,
not evolutionary search. NSGA-II remains the checkout-lab search; a generic
evolutionary search over external topologies is not implemented because the
runner may only deploy reviewed topologies. That limitation is stated in the
adapter capabilities (`search: bounded_measured_comparison`) and in the docs.

---

## 4. Correctness tested, and what remains unknown

Tested:

- Flask and Node: `GET /` returns the reviewed counter sentence; the Redis
  viewed/visit count strictly increases through the gateway; a restarted web
  replica becomes healthy again on loopback. The verdict note explicitly says
  HTTP availability alone is not business correctness.
- Sanchay: totals, category spending, payee amounts, refund handling,
  transfer exclusion, currency scoping, determinism and input immutability
  match the original after canonicalisation (68/68 in the full run). The
  recorded full run also ran Sanchay's source reporting tests (29/29); the
  fetched-cache live run reported source tests as skipped because the Vitest
  runtime was not installed, and showed that reason instead of claiming a
  pass.

Not tested / unknown:

- No repository test suites are installed or run for the Flask and Node
  samples; the adapter verifies its HTTP oracle only.
- No payment, inventory, order or data-loss invariants: these samples have
  no such domain logic.
- No crash-consistency, disk-failure, network-partition or multi-host fault
  beyond a single service restart.
- No concurrency/race testing beyond counter monotonicity under the bounded
  load.
- No long-run memory leakage or soak behaviour.

---

## 5. Business value demonstrated

DARWIN turns an architecture argument into a reviewed, repeatable decision
artefact:

- it shows the **actual** deploy topology and the exact bounded change;
- it compares baseline and candidate under the same workload and reports cost
  regressions instead of a single score;
- it refuses to call a simulated, recorded or unsupported result a win;
- it produces an exportable change document with apply/rollback or an explicit
  "no deployment change" when the baseline is retained;
- it preserves evidence with digests so a reviewer can audit the claim.

The commercial direction is B2B architecture-decision verification: paid
evaluations, execution on private infrastructure, and team subscriptions.
**No customers, revenue or cost savings are claimed**; none exist for this
prototype.

---

## 6. How to start and show a three-minute demo

```bash
# from the repository root, Windows Git Bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt
NO_PROXY=127.0.0.1,localhost PYTHONPATH=backend \
  .venv/Scripts/python.exe -m uvicorn darwin.main:app --host 127.0.0.1 --port 8000

# optional demo shop for the checkout lab
PYTHONPATH=backend .venv/Scripts/python.exe scripts/run_shop.py

# frontend (dev)
cd frontend && npm install && npm run dev
```

Requires a running Linux Docker engine for measured external runs. Open the
app at the Vite URL, go to **Real project**, pick **Flask + Redis sample**,
inspect, choose **Faster under traffic**, run **Quick measured comparison**,
and read **Step 5 · Prove** plus **Advanced evidence**. The full script,
including fallbacks and 15 challenging Q&As, is in
[JUDGE_SCRIPT.md](JUDGE_SCRIPT.md).

If the engine is unavailable, the walkthrough still works through inspection
and recorded evidence; say clearly that it is recorded.

---

## 7. Test/build results, security limits, next step

| Check | Result |
| --- | --- |
| Backend suite | `202 passed, 14 skipped` |
| External backend tests | `28 passed` |
| Frontend production build | passed (`index-CYvNB9W8.js`) |
| Showcase build | passed (`index-BnEtw5wV.js`), snapshots copied |
| Manifest validation smoke | reviewed manifest `valid: true`; empty/tampered manifest `valid: false` |
| Evidence digest checks | served only allowlisted, digest-verified files; tampering and symlink escapes refused |

Security limits: the Docker daemon is trusted; base images are not
digest-pinned; build-time egress is open for package installation; no
seccomp/AppArmor profile is supplied; the API is local and unauthenticated by
default (optional bearer token); no real payment or customer data is allowed.
Full detail and residual risk are in
[EXTERNAL_BACKEND_SECURITY.md](EXTERNAL_BACKEND_SECURITY.md).

Smallest next step toward a pilot: take **one design partner repository**,
write one reviewed adapter and manifest with a real business oracle, and run
their architecture comparison on a dedicated rootless/VM-isolated Linux
worker with longer, statistically powered workloads. Keep the decision and
evidence model; harden the execution layer before any multi-tenant use.
