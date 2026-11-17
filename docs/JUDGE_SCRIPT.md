# Judge script

> For a live demo of external backend evolution. Times assume a warm machine
> and a running Linux Docker engine. Rehearse the fallback once.

---

## 1. The 60-second pitch

DARWIN is an evidence lab for backend architecture decisions. Most tools tell
you a design is "better" because a diagram looks modern. DARWIN takes a real
public GitHub backend, deploys its original topology inside an isolated Linux
stack it builds itself, applies one small reviewed architectural change, and
measures both under the same traffic with a business-correctness check.

Two examples ship today. A Flask + Redis counter and a Node/Express + Redis
counter. In the Flask full run, two replicas cut p95 latency by **29.9%** —
but CPU rose **39%** and peak memory **83%**. DARWIN did not declare a winner.
It reported a tradeoff and asked the operator to choose. On a smaller quick
run, replicas were slower and DARWIN kept the baseline.

That is the product: not a leaderboard, an honest decision. Every number is
backed by a recorded evidence bundle with SHA-256 digests. Simulated screening
is labelled and can never win. If there is no safe execution environment,
DARWIN says so and stays read-only.

---

## 2. Three-minute walkthrough

### 0:00–0:20 — Set the frame

Open the app. Mention the two modes in one sentence: the controlled checkout
lab is the **The lab** home page and its experiment pages; today we are on
**Guided evaluation → Connect a public backend**.

Say: "The promise is not 'AI optimizes your repo'. The promise is: it measures
a specific, deployable change and refuses to overclaim."

### 0:20–0:55 — Connect

Click the **Flask + Redis sample** card in the catalog. Point out:

- it is a genuine public Docker sample, CC0, pinned to a commit SHA;
- DARWIN downloads source read-only, with consent, and never runs the
  repository's Compose file or Dockerfile;
- the URL box also accepts another public GitHub repo, but it will only be
  inspected unless a reviewed adapter matches.

Click **Inspect this project**.

### 0:55–1:30 — Understand

On **Step 2 · Understand**, read the architecture map and the support level
`READY_FOR_MEASURED_EVOLUTION`. Point out the split between **proven from
source** and features DARWIN cannot claim. Say: "This is file-backed detection,
not a name match. A lookalike app does not get the adapter."

Mention the pinned SHA and the exactly allowlisted files (`app.py`,
`requirements.txt`).

### 1:30–1:55 — Challenge

On **Step 3**, show the four challenges: faster, recover, resources, spike.
Choose **Faster under traffic**. Point out that candidates are constrained to
what the adapter can actually deploy — two replicas or two workers — not an
invented database or framework rewrite.

### 1:55–2:35 — Evolve

Choose **Quick measured comparison** and start it. While it runs, narrate the
four real stages: prepare pinned source, deploy and check correctness, measure
the challenge, derive the verdict. Show the live progress and the topology
graph.

If the run is slow, open a previously recorded external evaluation from the
recent list and explicitly say: "This is recorded evidence from an earlier
live run; I am showing it because the engine is busy, not because it is
simulated." Never silently present recorded data as live.

### 2:35–3:00 — Prove

On **Step 5**, read the verdict and the reason sentence. Then open **Advanced
evidence** and show:

- the comparison table with p95, throughput, CPU, memory and recovery;
- correctness checks (counter monotonicity, restart health);
- `environment.json` with `repository_compose_used: false`;
- the change document: apply/rollback for actionable verdicts, "no deployment
  change" for a retained baseline;
- the evidence bundle and file digests.

Close with: "If the candidate wins but costs more, the verdict is a tradeoff.
If it loses, the baseline stays. Both are successful outcomes."

---

## 3. Fifteen challenging questions

**1. Isn't this just "add replicas"?**
For these two samples, the reviewed candidates are replicas and workers,
because that is what is genuinely deployable without rewriting the apps. The
point is the measurement and verdict machinery: it accepts a different
adapter and manifest for another topology. It is not claiming to invent novel
architectures.

**2. How do I know this is a real repository and not a mock?**
The evaluation records the GitHub URL, owner/repo, requested ref, resolved
commit SHA, file count and license in `source`, and the evidence folder keeps
the manifest and environment. The Flask target is `docker/awesome-compose`,
CC0, pinned `30f4b7f6a6c3`; the Node target is
`dockersamples/nginx-node-redis`, Apache-2.0, pinned `2cd75d3b6138`.

**3. Why not run the repository's own Dockerfile and Compose file?**
Because that is untrusted build and runtime configuration. It can mount the
host, run privileged, fetch scripts or expect secrets. DARWIN copies an
allowlisted subset of source into its own image and generates its own Compose
stack. The tradeoff is fidelity to the repository's packaging; the gain is a
reviewable execution boundary.

**4. 6 requests per second is tiny. Is this meaningful?**
It is a bounded comparative test on one host, not a capacity benchmark. The
window is deliberately short and fixed so baseline and candidate are
comparable and the demo is repeatable. DARWIN reports the load window in
`environment.json`. It does not claim production throughput.

**5. How do you avoid cherry-picking a win?**
The verdict policy is fixed before the run: 8% minimum improvement on the
challenge metric, 5% maximum error rate, 5% maximum regression on any other
metric. All candidates in the mode are compared, and a regression produces a
tradeoff, not a win. Quick mode only compares the baseline and the challenge's
primary candidate; full mode compares all reviewed candidates.

**6. What counts as correctness? HTTP 200?**
No. The UI and verdict say explicitly that availability is not business
correctness. For the counters, the business oracle is the shared Redis
counter: the reviewed sentence must be returned and the count must strictly
increase through the gateway; a restarted replica must become healthy. For
Sanchay, reports must match the original byte-for-byte after canonicalisation
across refunds, transfers, currencies and determinism.

**7. How is recovery measured?**
For the `recover` challenge, one web replica is restarted and the gateway is
probed every 50 ms until it returns a healthy response. The time from fault
injection to the first healthy response is the metric. Zero failed probes
means another replica covered traffic. The 0.464 s → 0 s result means the
single-replica baseline exposed a short outage while the two-replica candidate
did not.

**8. Why did the quick Flask run keep the baseline when the full run found a
29.9% p95 win?**
Different bounded window and candidate set. On the quick run, both candidate
topologies were slower than the original, so the honest outcome was
`BASELINE_RETAINED`. That inconsistency is not a bug to hide; it shows the
policy follows the measurements. It is also a warning against treating one
small run as universal truth.

**9. Are the results reproducible?**
The source is pinned, the image and Compose are generated deterministically
from a hashed manifest, the workload is seeded and bounded, and the evidence
records the environment. Runs are not bit-identical — container timing varies
— which is why the verdict is conservative and why raw samples are retained.
The evidence bundle allows re-inspection and a re-run.

**10. What prevents a malicious repository from attacking the host?**
No repository code runs on the host. The generated Compose uses an internal
network, loopback-only publish, read-only rootfs, non-root users, dropped
capabilities, `no-new-privileges`, resource limits, no Docker socket and no
secrets. Source copy rejects traversal and symlinks. These controls are
tested, but the Docker daemon is still trusted; this is a single-operator
prototype, not a hostile multi-tenant sandbox.

**11. What if Docker is not running?**
Inspection and architecture mapping still work. Starting a measured run
returns a clear `FAILED_INFRASTRUCTURE` reason: a Linux Docker engine is
required and DARWIN will not execute repository code on Windows. It does not
silently fall back to simulation or recorded numbers.

**12. Why is Sanchay in the same product if it has no server backend?**
As an honest boundary case. Sanchay is a local-first React app; the adapter
evaluates a client report-computation change, not replicas or a database. The
scope note says exactly that. Mixing it in without that label would be
misleading.

**13. Can simulated screening ever produce a "winner"?**
No. Simulated evaluations are `NOT_MEASURED`, carry `evidence_kind:
simulated`, and the measured verdict policy sets `simulation_cannot_win`. In
the UI they are visually distinct and cannot be exported as a measured
recommendation.

**14. What is actually mocked or hardcoded?**
The three adapters and their manifests are reviewed, hardcoded knowledge about
three targets. The catalog is curated. Load is bounded and the apps are
counters. The source import, container execution, metrics, correctness checks,
verdict computation and evidence hashing are real. The recorded showcase is
snapshots of real runs, labelled as recorded.

**15. What would it take to make this commercial?**
A queue and multi-tenant workers, rootless or VM-isolated execution,
digest-pinned base images, build-time egress control, mandatory auth and
audit identity, more adapters with stronger oracles, longer and larger
workloads, and a retention/cost model. The decision engine and evidence model
are reusable; the sandbox and operational layer are prototype-grade.

---

## 4. Prototype vs commercial boundary

| Capability | Today (prototype) | Commercial bar |
| --- | --- | --- |
| Targets | 2 container samples + 1 client app, curated catalog | Many repository families, versioned adapters, compatibility matrix |
| Execution | Single-host Linux Docker, trusted daemon | Rootless / microVM per run, untrusted multi-tenant |
| Isolation | Read-only rootfs, dropped caps, internal network, loopback | Plus seccomp/AppArmor, digest-pinned images, egress policy, syscall audit |
| Load | 6 req/s, seconds-long bounded window | Sustained, distributed, statistically powered runs |
| Correctness | Adapter-specific oracle (counter, report parity) | Per-repository business oracle and contract tests |
| Evidence | Allowlisted files, SHA-256, local SQLite | Immutable object storage, signatures, audit trail, retention |
| API | Local, optional bearer token | Authenticated multi-user service, RBAC, rate limits |
| UI | Five-stage local exhibition flow | Team workspaces, comparisons over time, approvals |
| Cost model | No financial claims | Only with measured resource and price inputs, explicitly sourced |

---

## 5. Fallback plan for the demo

1. **Warm path:** pre-run one Flask and one Node quick evaluation before the
   audience arrives; keep them in the recent list.
2. **Docker busy or unavailable:** open a recorded evaluation and say it is
   recorded evidence from a live run. Do not call it live.
3. **Network unavailable:** use the cached source if present; otherwise open
   the recorded showcase build, which serves captured responses and refuses
   anything that would need the engine.
4. **A run fails:** show the verdict `FAILED_INFRASTRUCTURE` and the reason.
   This is a feature of the product, not a demo failure; explain that DARWIN
   refuses to invent a result.
5. **Time pressure:** the 60-second pitch plus the Prove screen is enough. The
   full three-minute walkthrough is optional.

Never claim a simulated or recorded result is a live measurement. The
credibility of the demo depends on that line.
