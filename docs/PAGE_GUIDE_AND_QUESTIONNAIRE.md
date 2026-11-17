# DARWIN page guide and presentation questionnaire

This document explains the five working pages of the DARWIN dashboard — **Real project**, **Architecture**, **Experiments**, **Search**, and **Demo shop** — how each one actually works, the real-world problem each one addresses, and the questions an audience is likely to ask, with answers you can defend.

Every behaviour described here is taken from the page components in `frontend/src/` and the backend modules in `backend/darwin/`. Where the system is limited, the limit is stated instead of hidden. That matters: the credibility of the demo depends on never presenting a simulated number as a measurement.

---

## 1. The thirty-second version

DARWIN is a local architecture lab. You describe a system as a small set of deployment controls, run that system in an isolated sandbox, measure it, break it on purpose, and only then decide whether a change is better.

The five pages are five stages of one argument:

| Page | Route | Question it answers | Output |
|---|---|---|---|
| **Real project** | `#project` | "Can DARWIN understand *this* repository, and what would it change?" | Inspection plus a measured verdict or a clearly labelled simulated screening |
| **Architecture** | `#configuration` | "What is the system made of, and what does this configuration cost?" | Genome, topology, compose file, uncalibrated performance estimate |
| **Experiments** | `#experiments` | "Does it actually work, and how fast is it really?" | Repeated measurements, fault traces, invariant results, artifacts |
| **Search** | `#search` | "Which configuration should we try next, under a budget?" | Pareto front of measured, gate-passing candidates or an explicit rejection |
| **Demo shop** | `#shop` | "Why should anyone trust the measurement?" | A live checkout whose ledger proves idempotency and invariants |

The spine that connects them is:

```
Genome → Experiment → Gate → Evidence
```

- **Genome** = the four deployment controls that define a candidate architecture.
- **Experiment** = the isolated deployment that measures that genome.
- **Gate** = correctness and invariant checks that can veto a fast result.
- **Evidence** = hashed artifacts, traces, and verdicts that survive after the demo.

A page is never allowed to skip a stage. The Architecture page says "correctness gate unchecked". The Search page refuses to rank candidates that did not pass the gate. The Real project page distinguishes **SIMULATED** from **measured** in the verdict itself.

---

## 2. Why this shape exists (the real-world problem)

Most architecture debates fail for one of four reasons:

1. **Opinions are cheaper than measurements.** "Add a cache" and "add replicas" are both plausible; nobody knows which helps until both are measured on the same workload.
2. **Performance work hides correctness regressions.** A change can lower p95 latency and still double-charge a customer. Speed is easy to celebrate; correctness is easy to skip.
3. **Benchmarks are not reproducible.** A number from someone's laptop, with an unknown commit, unknown load, and unknown warm-up, cannot settle a decision.
4. **Exploration is unbounded.** A team can spend weeks trying combinations and still miss the configuration that was two steps away.

DARWIN is designed around those four failures:

- It makes the candidate explicit (the genome).
- It measures on a fixed workload with repeated runs.
- It puts correctness and invariants **before** performance in the decision.
- It bounds the search with an attempt budget and a wall clock.

That is the real-world value proposition. It is not "AI designs your architecture". It is "your architecture claims become testable, and the test can say no".

---

## 3. System map

```
React dashboard (hash routes)
        │
        ├── #configuration ──► /api/genomes/preview, /api/simulate, /api/genomes/compose
        ├── #experiments   ──► /api/experiments, /api/experiments/{id}/events, artifacts
        ├── #search        ──► /api/searches, /api/searches/{id}/events
        ├── #shop          ──► /shop/catalog, /shop/checkout, /shop/ledger, /shop/reset
        └── #project       ──► /api/repositories/*, /api/project-evaluations/*
                                  │
                                  ▼
                        FastAPI control plane
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
          Experiment worker              Repository worker
       (native or Docker sandbox)     (measured adapter or
                    │                  simulated screening)
                    ▼                           │
        Shop + PostgreSQL (+ Redis)             ▼
        Locust load, fault probes,        Verdict policy
        invariant snapshots               (measured vs simulated)
                    │
                    ▼
        SQLite + artifacts (hashes, traces, metrics)
```

Two things are worth saying out loud when presenting:

- **Native and Docker are different evidence tiers with different guarantees.** Native runs on Windows with a per-run isolated backend and a Windows fault adapter. Docker runs the full compose stack with cgroup limits. Both are local. Neither is a cloud environment.
- **The repository worker has two branches.** A reviewed adapter can *measure* a trusted repository. Everything else is either inspection-only or goes through the **simulated** architecture screening model. The UI labels which branch produced the result.

---

## 4. Architecture page (`#configuration`)

### 4.1 What you see

- Four controls: application replicas (`1/2/3`), catalog cache TTL (`0/10/30` seconds), notification mode (`sync` or `queued`), and retry policy (`none` or `idempotent_only`).
- A live topology preview: gateway, API replicas, inventory, payment, database, and optionally Redis and a worker.
- A "Simulated performance" card with p95 latency and requests per second.
- A resource summary: CPU cores and memory the configuration will consume.
- A caveat under the estimate: **"Correctness gate unchecked. Use a fault experiment to verify recovery."**
- A compose download action.

### 4.2 How it works

The four controls form a **genome**. The genome is validated by a strict contract (`backend/darwin/contracts.py`): numbers must be integers, values must come from the allowed sets, and unknown fields are rejected. With the current sets there are `3 × 3 × 2 × 2 = 36` possible genomes.

The genome is canonicalised as sorted JSON and hashed with SHA-256 (`backend/darwin/architecture.py`). That hash is used in three places:

- as the cache namespace inside the running shop,
- as the compose project name (`darwin-<first 12 hex characters>`),
- as the identity of a candidate in experiments and search.

This is what makes a result traceable: the same genome always produces the same hash, and the hash appears in the evidence.

The preview endpoint renders the topology from the genome. The topology is not a drawing invented by the frontend; it is derived from the same compose specification that would be deployed. Adding a second replica adds a real `api-2` service and a real gateway route. Enabling the cache adds a Redis service. Choosing queued notifications adds a worker service.

The compose renderer also enforces a resource envelope. Each service has a fixed CPU and memory cap, and each API replica costs `0.4` CPU and `384 MiB`. The total is computed by `deployment_resources()`. Experiments and search reject genomes that exceed the configured sandbox budget, so "add replicas" is never treated as free.

The `/api/simulate` endpoint runs the SimPy screening model (`backend/darwin/simulator.py`). It uses the **same arrival schedule** as the native benchmark (`backend/darwin/performance.py`): a 3-second warm-up, then 12-second windows, with a `normal`, `flash_sale`, or `checkout_heavy` mix. The model has 8 API workers per replica, 4 database connections, and 1 notification worker. It returns p50/p95/p99, throughput, and a `calibration_status`.

That status is usually `uncalibrated`. The UI says so. A calibrated variant exists (`fitted_limited_evidence`) but it is still an estimate, not a measurement. The page never claims otherwise.

### 4.3 The decision it supports

The Architecture page supports **design-space reasoning before spending measurement budget**:

- Which controls actually change the topology?
- What does each choice cost in CPU and memory?
- Which combinations are even legal under the sandbox budget?
- What does the model *guess* will happen, so we can choose what deserves a real run?

It is a pre-flight page, not a verdict page.

### 4.4 Real-world mapping

| Real-world activity | How this page maps |
|---|---|
| Capacity planning | Replicas and memory are explicit, bounded, and costed instead of hand-waved |
| FinOps review | A candidate that needs more CPU is visibly more expensive before it is deployed |
| Architecture review board | Trade-offs become four named controls with allowed values, not a slide of boxes |
| Pre-benchmark triage | The uncalibrated model ranks hypotheses cheaply; only the promising ones get measured |
| Design for failure | Notification mode and retry policy are first-class architecture decisions, not afterthoughts |

The honest framing: this page is a **model**, and models are for choosing what to test. It is not evidence of production performance.

### 4.5 Demo line

> "This page turns an architecture argument into a constrained design space. Every choice here has a topology consequence and a resource cost, and the estimate is explicitly uncalibrated. The point is not to trust the number — the point is to decide which configuration deserves a real experiment."

### 4.6 Limits to state

- The genome describes the **demo shop**, not an arbitrary user system. There are four controls and 36 combinations.
- The simulation is a queueing approximation with fixed service-time distributions, not a trace-driven model of your traffic.
- The estimate has no error bar in the UI beyond the calibration label.
- Correctness is explicitly **not** checked here. Only a fault experiment can verify recovery and invariants.

---

## 5. Experiments page (`#experiments`)

### 5.1 What you see

- A "New experiment" panel with judge-ready scenarios and a manual setup.
- Four scenario presets:
  - **Quick checkout smoke** — start the stack and repeat one order with the same request key.
  - **Normal baseline vs candidate** — baseline versus two replicas, 10-second cache, queued notifications.
  - **Flash sale comparison** — baseline versus three replicas, 30-second cache, queued notifications, under `flash_sale` load.
  - **Payment timeout with unsafe retry** — deliberately unsafe retry, expected to fail with `I-01` and three payment effects.
- Mode selection: smoke, benchmark, or faults, on native or Docker.
- Workload profile: `normal`, `flash_sale`, `checkout_heavy`.
- Constraints: maximum error rate and optional p95 target.
- Run history with progress, attempts used, candidate summaries, gate state, and artifact links.

### 5.2 How it works

Every experiment is a strict request (`StartExperiment` in `backend/darwin/experiments.py`):

- mode: `native_smoke`, `docker_smoke`, `native_benchmark`, `docker_benchmark`, `native_faults`, or `docker_faults`;
- one or more genomes (up to 36);
- a seed, workload profile, fault scenarios, budget, and constraints;
- an optional fault fixture: `safe` or `unsafe_retry`.

Validation happens before anything runs:

- fault modes require a non-empty, duplicate-free list of fault scenarios;
- the unsafe fixture requires the `timeout_retry_duplicate` scenario;
- non-fault modes may not carry fault scenarios;
- candidate count must fit `max_candidates`;
- `genomes × repetitions` must fit `real_test_budget`;
- duplicate genomes are rejected, because they are not separate candidates;
- every genome must fit the CPU and memory envelope;
- native benchmark and fault modes require Windows and whole logical CPUs.

Each candidate is evaluated `repetitions` times (default 3, minimum 3). That is the difference between a demo and a measurement: a single run cannot distinguish a real change from noise. The report shows **min / median / max** spread for p95, throughput, CPU seconds, peak memory, and error rate.

The experiment worker starts an isolated shop stack per candidate. The stack includes the gateway, API, inventory, payment, PostgreSQL, and optionally Redis and a worker. It applies the genome through environment variables and the canonical cache namespace. Then it runs:

- a **smoke** path: start, check readiness, repeat one checkout with the same idempotency key;
- a **benchmark** path: warm-up, fixed 12-second windows, scheduled catalog and checkout traffic, latency percentiles;
- a **fault** path: inject database delay, service outage, or timeout/retry duplication, then verify recovery and business state.

Artifacts are written per evaluation and hashed: `manifest`, `metrics`, `trace`, `compose`, and `log`. The event stream lets the UI show progress without pretending the run is instantaneous.

The **gate** is computed by `feasibility()` in `backend/darwin/invariants.py`. A candidate fails if any of these is true:

| Gate reason | Meaning |
|---|---|
| `resource_limits_unverified` | The run could not prove cgroup limits were enforced |
| `business_invariant_failed` | I-01…I-05 produced a violation |
| `fault_scenario_incomplete` | A requested fault was not fully exercised |
| `invariant_coverage_incomplete` | Not all five invariants were checked |
| `measurement_error_threshold` | Error rate exceeded the constraint |
| `fault_operation_error_threshold` | Fault-path logical error rate exceeded the constraint |
| `measurement_latency_threshold` | p95 exceeded the constraint |
| `recovery_not_observed` | A recovery time was never observed |

A performance win cannot override any of these. That ordering is the core design decision of the page.

The five invariants are:

- **I-01** — one payment effect per payment key (no double charge).
- **I-02** — stock reconciles with reservations and confirmed orders.
- **I-03** — every confirmed order has matching successful payment evidence.
- **I-04** — no duplicate business records, and replay does not change response or state.
- **I-05** — a confirmed order keeps its notification job, and an accepted notification survives restart and finishes with matching delivery evidence.

### 5.3 The decision it supports

The Experiments page answers: **"Is this change safe enough to consider, and what did it actually cost?"**

It supports three distinct decisions:

1. **Correctness first.** The unsafe-retry scenario is designed to fail. Showing a rejection is as important as showing a win.
2. **Performance with uncertainty.** Repeated runs produce a spread, not a single hero number.
3. **Comparability.** Same seed, same workload schedule, same constraints, same artifact schema.

### 5.4 Real-world mapping

| Real-world activity | How this page maps |
|---|---|
| Pre-production regression testing | The gate catches correctness failures before a performance claim is made |
| SLO validation | p95 and error-rate constraints are explicit inputs, not post-hoc excuses |
| Chaos engineering | Fault scenarios are bounded, recorded, and tied to recovery evidence |
| Incident prevention | I-01/I-03/I-05 encode the failure modes that cause duplicate charges and lost notifications |
| Release evidence | Hashed artifacts give reviewers something to inspect after the demo |

The page's real-world lesson is blunt: **a faster system that loses an order is not an improvement**. The unsafe-payment scenario exists to make that lesson visible in under two minutes.

### 5.5 Demo line

> "We are not just measuring latency. We are asking whether the system still behaves correctly under retries, database delay, and a service outage. The gate runs first. If correctness fails, the performance number never becomes a recommendation."

### 5.6 Limits to state

- The shop is a synthetic demo, not your production system.
- Native runs are Windows-only; the native fault adapter is not portable.
- Docker search depth is intentionally small; the point is the method, not exhaustive optimization.
- One host and one environment means results are comparable within a session, not automatically across machines.
- Fault injection is bounded and scripted, not a general chaos platform.

---

## 6. Search page (`#search`)

### 6.1 What you see

- Search method: **NSGA-II**, **Random search**, or **Hill climbing**.
- Runtime: native or Docker.
- Workload profile and attempt budget (the UI offers 6, 12, or 18 measured attempts).
- A Pareto chart of measured feasible candidates: latency versus application CPU time.
- A candidate table with configuration, evidence status, p95, CPU seconds, and recovery time.
- An explicit panel when nothing passes: **"No candidate passed all gates"**, with retained gate reasons.
- A candidate dialog with the genome, parents, generation, evaluations, and simulation summary.

### 6.2 How it works

Search treats architecture selection as a **constrained multi-objective optimization** problem (`backend/darwin/search.py`).

The search space is the same 36 genomes. Before proposing a candidate, the engine filters out genomes whose CPU or memory cost exceeds the sandbox budget. The baseline genome is always proposed first, so the comparison always has a control.

Three objectives are computed from measured evidence:

1. **p95 latency** (lower is better),
2. **CPU seconds** (lower is better),
3. **recovery time** (lower is better).

A candidate receives objectives only if **every** repetition is `measured`, `completed`, and `gate == passed`. If any repetition fails the gate, the candidate gets no objectives and a penalty based on its gate reasons. This is the constraint mechanism: an unsafe configuration cannot win on latency.

The three algorithms differ in how they propose the next generation:

- **Random search** takes proposals without using parent feedback. It is the honest baseline for "did the search actually help?"
- **Hill climbing** picks the current incumbent and proposes single-control neighbours. It is cheap and interpretable, but can get stuck.
- **NSGA-II** uses non-dominated sorting and crowding distance to keep a diverse Pareto front. It selects parents by rank, performs uniform crossover over the four controls, and mutates one control. It is the default because architecture decisions are genuinely multi-objective.

When the simulator is enabled, it pre-ranks proposals by modelled p95 before promotion. The promotion step always keeps the baseline and reserves alternate slots for diverse or uncertain proposals. This is a deliberate anti-premature-convergence choice: the search should not spend its whole budget on small variations of the first winner.

Search is **bounded** in three ways: `max_candidates`, `real_test_budget`, and `wall_clock_s`. Each generation creates a child experiment sized to the remaining budget. If the wall clock runs out, the search stops and records that fact. If a child experiment fails, the search fails rather than inventing a result. If the user cancels, the active child is cancelled.

The Pareto front is computed only over **feasible measured** candidates. If there are none, `pareto_ids` is empty and the UI shows the no-feasible-candidate verdict with the reasons. That is not an error state; it is a valid, useful outcome.

### 6.3 The decision it supports

Search answers: **"Given a fixed budget, which configurations are worth a human decision, and which trade-offs are real?"**

It supports:

- **Portfolio decisions** — a Pareto front shows that candidate A is faster but uses more CPU than candidate B. The right choice depends on the business, not the algorithm.
- **Budget discipline** — the search stops when the budget is spent, and it says so.
- **Falsification** — if no candidate clears the gate, the answer is "none of these", not a forced winner.

### 6.4 Real-world mapping

| Real-world activity | How this page maps |
|---|---|
| Architecture modernization | Explore replicas, caching, async work, and retry policy under a fixed evaluation budget |
| Multi-objective trade-offs | Latency, compute cost, and recovery are optimized together, not one at a time |
| Platform engineering | A repeatable search protocol instead of ad-hoc tuning by the loudest engineer |
| FinOps | CPU seconds are a first-class objective; the cheapest feasible candidate is visible |
| Reliability engineering | Recovery time is an objective, so "fast but fragile" does not automatically win |

The important real-world shift is from **"what is the best architecture?"** to **"what is the best architecture *for this workload, under this budget, with these constraints*?"** That is the question companies can actually act on.

### 6.5 Demo line

> "Search does not decide for you. It spends a bounded budget to find the measured trade-off curve, and it refuses to put a candidate on that curve unless every repetition passed the correctness gate. If nothing passes, it tells you that too."

### 6.6 Limits to state

- The search space is 36 genomes, not an arbitrary infrastructure graph.
- The budget is intentionally small; this demonstrates the method, not exhaustive optimization.
- Objectives are local measured metrics, not cloud cost or revenue.
- NSGA-II is constrained by the gate, but the gate is only as good as the five invariants and the fault coverage.
- Search results are comparable within a session and environment; cross-machine comparison requires the recorded environment and artifacts.

---

## 7. Demo shop page (`#shop`)

### 7.1 What you see

- A three-step walkthrough: choose a product, place the order, resend the same request.
- Catalog with stock counts.
- Checkout receipt with order ID, SKU, quantity, and amount.
- A comparison between the original response and the resent response.
- A ledger for the request: orders, captures, payment effects.
- A reset action.
- A clear badge: **"Simulated payments"**.

### 7.2 How it works

The shop is a real small service stack: gateway, API, inventory, payment, PostgreSQL, and optionally Redis and a worker. The page talks to it through the gateway.

A checkout sends `POST /shop/checkout` with an `Idempotency-Key` header. The key is the request identity. The API:

1. reserves stock,
2. verifies the simulated payment,
3. persists the order, capture, payment effect, and outbox job,
4. returns a receipt.

When the page resends the **same** request with the same key, the API must return the existing order rather than creating a second one. The ledger then shows **1 order, 1 capture, 1 payment effect** for that key. The UI compares the two responses and states that the repeat added no second effect.

The ledger is not a frontend invention. It reads persisted rows: `orders`, `captures`, `payment_effects`, `outbox`, and `deliveries`. The invariant checker reads the same tables.

Why this matters for the rest of the demo: the shop is the **physical evidence** behind the gate. When the Experiments page says a candidate passed, it means these tables reconciled. When the unsafe-retry scenario says `I-01` failed, it means this ledger shows more than one payment effect for one key.

### 7.3 The decision it supports

The Demo shop supports the **trust decision**: "Should I believe the rest of the demo?"

It does that by making one narrow, checkable claim: a retried checkout does not double-charge, double-reserve, or lose its notification. That claim is visible in the UI and in the database.

### 7.4 Real-world mapping

| Real-world activity | How this page maps |
|---|---|
| Payment reliability | Idempotency keys and a payment ledger are the standard defence against duplicate charges |
| Inventory consistency | Stock reconciliation is checked against reservations and confirmed orders |
| Notification durability | The transactional outbox pattern plus delivery evidence prevents lost confirmations |
| Incident review | A per-request ledger is exactly what an on-call engineer wants during a duplicate-charge incident |
| Compliance evidence | Persisted, inspectable effects are stronger than a log line saying "success" |

This is the least glamorous page and the most important one. Most production incidents that hurt customers are not p95 regressions; they are duplicate charges, oversold stock, and lost notifications. The shop makes those failure modes concrete.

### 7.5 Demo line

> "This is the ground truth for everything else. Place an order, resend the exact same request, and watch the ledger stay at one order, one capture, one payment effect. If this page is wrong, no performance number on the other pages matters."

### 7.6 Limits to state

- Payments are simulated. No real payment processor is involved.
- The catalog and workload are synthetic.
- The shop is a demonstration of correctness patterns, not a production commerce system.
- The reset action is for demo hygiene, not a production workflow.

---

## 8. Real project page (`#project`)

### 8.1 What you see

A five-step stepper:

1. **Connect** — choose a trusted example or paste any public GitHub repository, choose a ref, give consent.
2. **Understand** — project facts with evidence files, supported and unsupported capabilities, guesses separated from facts, architecture sketch, hotspots.
3. **Challenge** — choose a challenge and a mode (`quick` or `full`), and see the candidates DARWIN would deploy.
4. **Evolve** — watch the stages and progress.
5. **Prove** — a verdict, a decision card, correctness results, cost, recovery, provenance, and evidence files.

The page visibly separates **measured** runs from **simulated** screening. A screening result is labelled `SIMULATED · x% modelled`; a measured result is labelled `−x% measured`.

### 8.2 How it works

#### Step 1 — Connect

DARWIN accepts a repository URL, a ref, and explicit consent. It resolves and pins a commit. The pinned commit is part of the trust boundary: a moving branch is never enough to authorize execution.

There are three trusted examples in the catalog (`backend/darwin/repository_catalog.py`):

- **Sanchay** — a React + TypeScript personal-finance app in an Android WebView, evaluated as `client_data_processing`;
- **Flask + Redis sample** — a containerized backend, evaluated as `backend_architecture`;
- **Nginx + Node + Redis counter** — a containerized backend, evaluated as `backend_architecture`.

Any other public GitHub repository can be **inspected**, but it is inspection-only unless a reviewed adapter matches it. DARWIN does not substitute the demo shop for an unrelated repository.

#### Step 2 — Understand

Inspection is deliberately conservative (`backend/darwin/project_capabilities.py`). The rule is: **a fact requires a source file that proves it.** Package names are not architecture. A Vite/React package is not a Node server. Inherited native modules are not silently promoted to the visible app.

The output has four distinct epistemic categories:

- **facts** — each with evidence file paths;
- **not supported** — capabilities DARWIN will not claim;
- **guesses** — explicitly labelled inferences;
- **hotspots** — evidence-backed places worth challenging.

The page also draws the repository architecture and shows which deployment controls the source actually supports. That prevents the classic demo failure of recommending a Redis cache to an app that has no server.

#### Step 3 — Challenge

For a backend architecture, the available challenges are derived from the adapter:

- **Faster under traffic** — lower latency for the reviewed workload;
- **Recover more reliably** — restart a web replica and measure the outage;
- **Use fewer resources** — compare CPU seconds and peak memory;
- **Handle a traffic spike** — push beyond steady state.

`quick` and `full` presets control seeds, workload sizes, repetitions, warmups, and wall-clock limits. For the Sanchay adapter, `quick` uses one seed and 10k/50k rows; `full` uses three seeds and 1k/10k/50k rows, with ten repetitions and two warmups.

#### Step 4 — Evolve

There are two execution branches, and the UI is explicit about which one is running.

**Measured branch (reviewed adapter):** DARWIN copies only the reviewed source files into a DARWIN-owned overlay, deploys an isolated stack, checks a behaviour oracle, runs the seeded workload and fault probe, and derives a verdict. The stages are `preparing → checking_correctness → measuring → verdict`. This branch produces live evidence and can support a `VERIFIED_IMPROVEMENT` verdict.

**Screening branch (architecture screening):** DARWIN does **not** import, build, or execute repository code. It converts the evidence-backed backend profile into a small queueing model, evaluates deployment variants that only touch architecture controls, and returns a recommendation that is always labelled `SIMULATED` and `NOT_MEASURED`. The stages are `preparing → simulating → evaluating → verdict`.

The screening model (`backend/darwin/project_simulation.py`) supports these controls, as detected from source:

- `replicas`
- `cache_ttl_s`
- `offload_jobs`
- `retry_policy`
- `db_pool`
- `read_replicas`
- `rate_limit`

It uses a deterministic M/M/c approximation, a synthetic workload derived from detected route methods, and deterministic seeds (`quick`: 7; `full`: 7, 21, 2026). It evaluates single-control variants and then combinations of the top variants. Its policy is explicit:

| Screening policy | Value |
|---|---|
| Minimum modelled improvement | 8% |
| Regression limit | 2% |
| Maximum error rate | 2% |
| Maximum error delta | 0.5% |
| Maximum cost multiplier | 2.5× |
| Primary metric | Modelled p95 latency |

The output includes **assumptions**, **limitations**, and **seed sensitivity**. If the modelled improvement changes sign across seeds, the status becomes `INCONCLUSIVE`. If no variant clears the policy, the status is `BASELINE_RETAINED`. The default is not a win.

#### Step 5 — Prove

The measured verdict is produced by `backend/darwin/verdict_policy.py`. It is intentionally conservative:

| Measured policy | Value |
|---|---|
| Minimum improvement | 5% |
| Regression limit on any measured size | 5% |
| Minimum paired win rate | 80% |
| Lower paired decile | Must stay above zero |

The verdict statuses are:

- `VERIFIED_IMPROVEMENT` — correctness passed, the primary size improved by at least 5%, the paired win rate is at least 80%, and the lower paired decile is above zero;
- `BASELINE_RETAINED` — the candidate regressed on any measured size, or the original was faster at the primary size;
- `INCONCLUSIVE` — the improvement was below 5%, or the paired evidence was inconsistent;
- `REJECTED_INCORRECT` — correctness failed, even if the candidate was faster;
- `NOT_MEASURED` — no timed samples, so no performance claim is possible;
- `FAILED_INFRASTRUCTURE` — the runtime did not complete;
- `NO_FEASIBLE_CANDIDATE` — the adapter produced no source-compatible candidate.

The **decision card** makes the outcome usable: it names the winner (or says the original architecture is retained), shows cost, recovery, the measured comparison, the correctness gates, provenance, and evidence files. The **"What this is not"** section prevents overclaiming.

The recorded validation evidence for the Sanchay adapter is:

- recorded full run `141c9b56`: **68/68 correctness checks**, **29/29 Vitest tests**, **28.5% latency improvement**, **100% paired wins** at 50,000 rows;
- live full run `e3057b59`: **68/68 checks**, **22.4% improvement**, **97% paired wins**; source tests were skipped because the fetched cache had no installed Vitest runtime, and the verdict shows that reason.

Those numbers belong to the Real project page, not to the demo shop. Do not mix them.

### 8.3 The decision it supports

The Real project page supports the **due-diligence decision**:

- "What is this repository, really?"
- "What would DARWIN change, and why?"
- "Is that a measured result or a model?"
- "What would it cost, and what could go wrong?"
- "Should a human review this candidate?"

It is the page that turns DARWIN from a demo into an evaluation instrument.

### 8.4 Real-world mapping

| Real-world activity | How this page maps |
|---|---|
| Technical due diligence | Inspect an unfamiliar repository and separate facts from guesses |
| Modernization proposal | Show a specific, source-backed change instead of a generic "move to microservices" slide |
| Architecture review | Present measured correctness and latency evidence, with provenance |
| Vendor evaluation | Ask "is this measured or modelled?" and get an explicit answer |
| Migration planning | Use screening to rank hypotheses, then measure only the credible ones |

### 8.5 Demo line

> "This page is honest about two different kinds of knowledge. For a trusted adapter, we deploy and measure. For everything else, we inspect the source and run a transparent model that is labelled SIMULATED. It will tell you when the model is inconclusive, and it will refuse to call a fast but incorrect change an improvement."

### 8.6 Limits to state

- Only three repositories are trusted for evaluation today.
- The measured adapters cover specific change types, not arbitrary refactors.
- The screening model is uncalibrated against the inspected repository and its deployment.
- Relative modelled differences must never be quoted as measured speedups.
- Cloud and Kubernetes environments are out of MVP scope.
- The implementation is one host, one environment, local only.

---

## 9. The end-to-end story (use this as the presentation arc)

If you have ten minutes, tell it as one continuous investigation.

**Minute 1 — Frame the problem.**
"Architecture decisions are usually argued, not tested. And when they are tested, performance wins often hide correctness regressions. DARWIN makes the claim testable and lets correctness veto it."

**Minute 2 — Architecture.**
Open `#configuration`. Change replicas from 1 to 2, enable the cache, switch notifications to queued. Show the topology and the resource cost. Point at the line: "Correctness gate unchecked." Say: "This is a hypothesis, not evidence."

**Minute 3 — Experiments.**
Open `#experiments`. Run or show the normal comparison. Show the repeated runs and the spread. Then show the unsafe-payment scenario failing with `I-01`. Say: "This is the gate doing its job. The fast number never becomes a recommendation."

**Minute 4 — Search.**
Open `#search`. Show the Pareto front. Point out that only measured, gate-passing candidates are on it. Show the no-feasible panel if you have one recorded. Say: "If nothing passes, the search says so."

**Minute 5 — Demo shop.**
Open `#shop`. Place an order, resend the same request, show the ledger staying at 1/1/1. Say: "This is the ground truth the gate is protecting."

**Minutes 6–7 — Real project.**
Open `#project`. Walk the five steps. Show the facts with evidence files, the separate guesses, and the hotspots. Then show a measured verdict and a simulated screening side by side. Say: "Measured and modelled are different evidence tiers, and the UI never blurs them."

**Minute 8 — Evidence.**
Open an artifact or the evidence directory. Show the manifest, metrics, trace, and hashes. Say: "The result is reproducible and reviewable after the demo."

**Minutes 9–10 — Limits and next step.**
State the limits: one host, small search space, Windows-only native faults, no cloud/Kubernetes, no installer. Then say what a company would actually do next: run a pilot on one service, define the invariants that matter, and use DARWIN to produce a reviewable candidate — not to auto-deploy.

---

## 10. Why would a company use DARWIN?

The short answer: **to replace architecture opinion with bounded, reviewable evidence — without giving up human control.**

A longer answer, grouped by buyer:

### Engineering leadership

- It shortens the loop between "we think this will help" and "we measured it under the same workload, with correctness checks".
- It makes trade-offs visible: latency versus CPU versus recovery.
- It produces artifacts that survive the meeting.

### Platform / SRE

- It encodes invariants that matter (duplicate charge, oversold stock, lost notification) and refuses to let a performance win bypass them.
- It provides a repeatable way to test recovery, not just throughput.
- It creates a culture of "show me the evidence" instead of "trust me".

### Architecture

- It turns a design review into a constrained search over named controls.
- It separates facts from guesses when inspecting an unfamiliar repository.
- It forces the question "what would we actually change?" to be answered concretely.

### Finance / FinOps

- CPU seconds and memory are first-class objectives and constraints.
- A candidate that needs more resources is visibly more expensive.
- The cheapest feasible candidate is on the Pareto front, not hidden in a spreadsheet.

### Risk / compliance

- Evidence is hashed and retained.
- Correctness failures are recorded, not suppressed.
- The system distinguishes measured from simulated, which is exactly what an auditor will ask.

**What DARWIN is not:** a production autoscaler, a cloud migration platform, an AI that designs arbitrary systems, or a replacement for architecture review. It is a local lab that produces candidates and evidence for humans to review.

---

## 11. Questionnaire: likely questions and strong answers

The answers below are written to be said out loud. They are grouped by the kind of question, not by page. Where a claim has a limit, the limit is in the answer.

### A. Problem and value

**Q1. What problem does DARWIN actually solve?**

It solves the gap between an architecture opinion and a reviewable decision. Teams usually argue about replicas, caching, async work, and retries using intuition. DARWIN turns those into a small, explicit genome, measures candidates on a fixed workload, and gates the result on correctness. The output is evidence a human can review, not an automatic deployment.

**Q2. Why not just use a load-testing tool?**

Load testing tells you how fast something is. It does not tell you whether the change preserved business correctness, whether the result is comparable across candidates, or whether a search over configurations was bounded. DARWIN wraps load generation in a contract: genome identity, repeated runs, fault scenarios, invariant checks, hashed artifacts, and a verdict policy. The load generator is a component, not the product.

**Q3. Why not use observability or APM in production?**

Production observability is essential, but it is observational and usually single-version. You cannot A/B a risky architecture change on live customer traffic without a safety net. DARWIN is a pre-production lab: it lets you reject a bad candidate before it reaches production. The two are complementary. A mature company would use DARWIN to choose a candidate and APM to confirm it in production.

**Q4. Is this just benchmarking?**

No. Benchmarking is one page. The distinguishing feature is the **gate**: correctness invariants and fault recovery can veto a performance win. The unsafe-payment scenario is a deliberate demonstration that a fast system can be rejected. That is not a benchmark result; it is an engineering decision.

**Q5. What is the smallest useful pilot for a company?**

Pick one service with a clear invariant and a clear performance complaint. Define the invariant in executable terms, define one workload, and run baseline versus one candidate with repeated measurements. If the verdict is `INCONCLUSIVE`, that is still useful: it tells you the evidence is not strong enough to justify the change. Expand only after the first pilot produces a decision someone trusts.

### B. Architecture and change space

**Q6. What kind of architecture are you going to evolve?**

In the demo, the evolvable architecture is a checkout stack with four controls: replicas, catalog cache TTL, notification mode, and retry policy. That yields 36 legal genomes. In Real project mode, the evolvable controls depend on what the source actually supports: replicas, cache TTL, background offload, retry policy, database pool, read replicas, and rate limiting. DARWIN does not claim to evolve an arbitrary microservice graph. It evolves a **bounded, source-backed change space**.

**Q7. Why only four controls in the demo? Is that too simple?**

It is deliberately small because the goal is to demonstrate the method end to end, not to model every knob in a real system. Four controls already produce meaningful trade-offs: replicas cost CPU and memory; caching changes consistency and topology; queued notifications change durability and latency; retry policy changes correctness under failure. The same pattern generalizes: define the legal controls, define the constraints, measure, gate, search. The number of controls is an implementation choice, not the core idea.

**Q8. How do you know the genome captures the architecture?**

We do not claim it captures *all* of architecture. It captures the deployment decisions that the demo can actually deploy and measure. That is the honest boundary. The genome is validated by a strict contract, hashed deterministically, and rendered into the same compose specification that is deployed. If a control is not in the genome, DARWIN does not claim to optimize it.

**Q9. Could DARWIN recommend microservices?**

Not in the current MVP. The change space is deployment controls on an existing service shape, not a re-architecture into microservices. A microservices recommendation would require a different model, different evidence, and a much larger search space. Claiming otherwise would be exactly the kind of unsupported architecture advice DARWIN is designed to avoid.

**Q10. How does the search avoid local maxima?**

It offers three methods. Random search is the baseline. Hill climbing is local and can get stuck. NSGA-II maintains a diverse Pareto front using non-dominated sorting and crowding distance, and the promotion step deliberately reserves slots for diverse proposals. That reduces, but does not eliminate, premature convergence. The budget is small, so the honest claim is "bounded exploration", not "global optimum".

**Q11. Why three objectives?**

Latency, compute cost, and recovery time are the three things that most often trade off in this kind of system. More replicas can lower latency but raise CPU cost. Caching can lower latency but add a consistency surface. Queued notifications can lower checkout latency but change durability. Recovery time captures the "fast but fragile" failure mode. A single score would hide those trade-offs; a Pareto front exposes them.

**Q12. What happens if no candidate is feasible?**

The search returns an explicit no-feasible-candidate result with the retained gate reasons. It does not pick the least-bad candidate and call it a winner. That is a feature. In a real review, "none of these cleared the bar" is a legitimate and valuable outcome.

### C. Evidence and trust

**Q13. If Amazon has a working architecture, why would they change it based on what DARWIN gives them?**

They would not change it *because DARWIN said so*. They would change it only if DARWIN produced a candidate that (a) preserved every correctness check they care about, (b) showed a consistent measured improvement on a workload they recognize, and (c) had a cost and recovery profile their business accepts. DARWIN's job is to make that case **falsifiable**, not to override architecture review.

For a company at Amazon's scale, the value is not a single 20% number. It is the ability to run a bounded, reproducible experiment on one service, with invariants and artifacts, and to reject a plausible-sounding change before it reaches production. A working architecture is not a reason to stop evolving; it is a reason to demand stronger evidence before evolving. DARWIN raises the quality of the evidence, and it is equally willing to say "retain the baseline".

Also be precise about scope: the current MVP cannot ingest an arbitrary Amazon stack, and only reviewed adapters can be measured. For an unfamiliar repository, DARWIN inspects and screens; it does not execute it. A real engagement would start with one service and a reviewed adapter, not with a company-wide migration.

**Q14. What stops DARWIN from recommending a fast but incorrect change?**

The gate. A candidate receives objectives only if every repetition is measured, completed, and `gate == passed`. The gate checks five business invariants, fault-scenario completeness, invariant coverage, resource-limit enforcement, error thresholds, latency thresholds, and recovery observation. A performance improvement cannot override a failed hard requirement. The unsafe-payment scenario is the visible proof: it is fast enough to be tempting and is still rejected.

**Q15. How do I know the numbers are real?**

Three things: the evidence tier, the artifacts, and the repetition spread. The UI labels a result as measured or simulated. Measured runs produce hashed artifacts (`manifest`, `metrics`, `trace`, `compose`, `log`) that can be inspected after the fact. Repeated runs produce min/median/max, not a single number. If you want to be strict, ask for the run ID and open the artifacts.

**Q16. What is the difference between `SIMULATED` and measured?**

`SIMULATED` means no repository code was executed. The screening model converts a source-backed profile into a queueing model, evaluates deployment variants, and returns a recommendation labelled `NOT_MEASURED`. Measured means an isolated stack was deployed, a workload was run, faults were injected where requested, and correctness was checked. The measured branch can support `VERIFIED_IMPROVEMENT`; the screening branch cannot. The UI uses different wording and different labels so the two are never confused.

**Q17. Why should I trust the verdict policy?**

You should not trust it blindly; you should inspect it. It is deliberately simple and published in the code and UI: minimum 5% improvement, no 5% regression on any measured size, at least 80% paired wins, and a lower paired decile above zero. It is conservative by design. It does not use p-values, and it does not claim statistical significance. It is a product policy, not a law of nature. A company can change the thresholds, but it should do so explicitly.

**Q18. What if the workload is wrong?**

Then the measurement is wrong for your decision. The workload is a fixed, seeded schedule with three profiles; it is not a replay of your production traffic. That is why the page shows the profile and the constraints, and why the honest claim is "measured under this workload", not "measured in production". The right pilot is to define a workload that resembles your traffic and validate it before trusting the ranking.

**Q19. How do you prevent cherry-picking?**

Repeated runs, a fixed seed, the same workload schedule for baseline and candidate, a primary size chosen by the policy (largest measured ledger size), and a regression check on every measured size. The policy also requires a paired win rate, not just a median. Cherry-picking is still possible in the choice of workload and constraints, which is why those are explicit inputs and should be agreed before the run.

**Q20. Why no p-values or confidence intervals?**

The MVP uses a conservative, explainable policy rather than a statistical test. It reports spread, paired win rate, and the lower paired decile. That is enough to reject an inconsistent result, but it is not a formal hypothesis test. Saying otherwise would overclaim. A production version could add confidence intervals, but it would also need a much larger sample budget.

### D. Operations and production fit

**Q21. Can this run in CI/CD?**

The individual pieces can: the test suite, the contrast check, the accessibility audit, and the build. The full experiment path needs a host with the sandbox prerequisites, and Docker measurements need a Linux engine with cgroup v2. The MVP is a local lab, not a turnkey CI service. A company would wrap it in a job with a pinned environment and retain the artifacts.

**Q22. Does it need Kubernetes?**

No. The MVP is a single Python control plane with a local worker and Docker Compose sandboxes. Kubernetes is out of scope. That is a deliberate trade-off: fewer moving parts, clearer evidence, easier demo. It also means the results are not a Kubernetes scheduling benchmark.

**Q23. What are the host requirements?**

A Windows host for native benchmark and fault modes, with whole logical CPUs available. Docker modes require a local Linux engine with cgroup v2 CPU quotas, swap limits, and `memory.peak`. The repository worker needs the prerequisites shown in the UI; if they are missing, it says so and does not pretend execution is available.

**Q24. How long does a run take?**

It depends on the mode and scenario. The scenario catalog shows recorded durations when available and falls back to estimates. Quick smoke is on the order of tens of seconds; normal and flash-sale comparisons are on the order of minutes; a full Real project run is longer. The UI shows the source of the duration (`recorded` or `estimate`) rather than hiding it.

**Q25. What happens if a run is interrupted?**

It is recorded as interrupted or failed, and no winner is reported. The repository worker explicitly marks interrupted evaluations and writes an empty verdict. The experiment store retains terminal states. The design rule is: **no metrics, no claim**.

**Q26. Can it run concurrently?**

Experiments are bounded by `concurrent_deployments = 1`. The repository worker runs one bounded evaluation at a time and has a queue limit. Search runs one active search at a time. This is intentional: concurrency would contaminate measurements on a single host.

**Q27. How does it handle secrets and untrusted code?**

The demo shop is synthetic and has no real payment credentials. Real project inspection pins a commit and requires consent. Measured adapters run only allowlisted source files in a DARWIN-owned overlay; the repository's Compose file, Dockerfile, and gateway config are not executed. Unsupported repositories are inspection-only. This is a security boundary, not a sandbox for arbitrary hostile code, and it should be described that way.

**Q28. What about data privacy?**

The MVP runs locally on `127.0.0.1` and does not expose the stack to the network. Repository inspection reads source files with size limits. It does not send source to a third-party LLM. If a company wants to evaluate a private repository, the same local model applies, but the trust boundary and network policy need review.

### E. Limits, failure modes, and honesty

**Q29. What can DARWIN not do?**

It cannot:
- execute an arbitrary repository (only reviewed adapters are executable);
- measure cloud or Kubernetes behaviour;
- replay your production traffic;
- prove statistical significance;
- replace architecture review or production monitoring;
- guarantee that a measured improvement generalizes to another host or workload;
- install itself as a packaged product (there is no installer).

Stating this list is part of the pitch. It is what separates evidence from marketing.

**Q30. What is the biggest risk of misusing DARWIN?**

Quoting a simulated screening number as a measured speedup. The system labels it, but a presenter can still blur it. The defence is procedural: always show the label, always name the evidence tier, and never put a simulated percentage on a slide without the word "modelled". The second risk is treating a local result as a production guarantee. The workload and environment are explicit for exactly that reason.

**Q31. Why is the Docker search depth small?**

Because the goal is to demonstrate bounded search, not to exhaustively optimize a demo. A deeper search would take longer, cost more, and still be limited by the 36-genome space and the single host. The method is the deliverable; the depth is a budget choice.

**Q32. Why is the native fault adapter Windows-only?**

Native execution uses Windows job objects and a Windows-specific fault path. Docker is the portable path. The limitation is real and should be stated rather than hidden. A company standardizing on Linux would use the Docker modes, with the corresponding cgroup prerequisites.

**Q33. Is the accessibility claim complete?**

No. The audit covers automated axe-core rules and scripted keyboard checks across 144 page/theme/viewport states, plus 23 palette colour pairs per theme. It does not include screen-reader testing or a user study. Say "automated and keyboard coverage passed", not "fully accessible".

### F. Comparisons

**Q34. How is this different from chaos engineering?**

Chaos engineering usually runs in a real or near-real environment to discover unknown failure modes. DARWIN runs bounded, known fault scenarios in an isolated sandbox to decide whether a candidate is safe enough to consider. It is closer to pre-production verification than to exploratory chaos. The fault traces are recorded, and the gate requires recovery evidence.

**Q35. How is this different from FinOps tooling?**

FinOps tells you what you spent. DARWIN tells you what a candidate would cost in CPU and memory before you deploy it, and makes cost a constraint and an objective. It is a design-time tool, not a billing-analysis tool.

**Q36. How is this different from DORA metrics?**

DORA measures delivery performance across an organization. DARWIN measures a specific architecture candidate against a specific workload and correctness gate. They operate at different levels. DARWIN could produce evidence that feeds a delivery decision, but it does not measure team performance.

**Q37. How is this different from an AI coding assistant?**

An AI coding assistant proposes code. DARWIN measures a deployment configuration and can reject it. The value is not generation; it is falsification. In Real project mode, DARWIN can also produce a specific source-backed change, but the measured adapter and the verdict are what make it credible.

**Q38. Why not just use a cloud cost calculator?**

A cost calculator estimates spend from instance types. DARWIN measures latency, CPU, memory, and recovery under a workload on a real stack, then gates the result on correctness. It answers "does this change work?" rather than "what would this list price be?".

### G. Business and adoption

**Q39. What is the ROI story?**

The ROI is avoided bad changes and faster good decisions. A rejected candidate that would have caused duplicate charges is a direct loss avoided. A measured candidate that clears the gate shortens the debate. The MVP does not produce a dollar ROI; it produces evidence. A pilot should define the decision it wants to accelerate and measure the time saved, not invent a percentage.

**Q40. Who is the buyer?**

Three likely buyers: an engineering leader responsible for reliability or modernization, a platform/SRE team that wants repeatable pre-production evidence, and an architecture group that wants to replace opinion with a bounded experiment. Finance is a secondary stakeholder because CPU and memory are explicit.

**Q41. What would a paid product need?**

At minimum: adapters for the customer's stack, a way to define invariants and workloads safely, a runner that fits their environment (including Linux and Kubernetes), retention and access control for evidence, and a policy configuration that matches their risk appetite. The MVP demonstrates the method; a product would industrialize the adapters and the runner.

**Q42. What is the adoption path?**

Start with one service and one invariant. Run a baseline and one candidate. Review the artifacts together. If the verdict is trusted, add a second workload and a second candidate. Only then expand the change space. Do not start with a company-wide migration; start with a decision someone actually needs to make.

**Q43. How do you prevent the demo from becoming a science fair?**

Tie every page to a decision the audience recognizes. Architecture: what does this cost? Experiments: does it still work? Search: which trade-off do we accept? Shop: would this double-charge a customer? Real project: what would we change, and is it measured? If a page cannot answer a decision question, cut it from the presentation.

### H. Tough and cynical questions

**Q44. Isn't this just a toy shop?**

The shop is deliberately small, but the method is not. The interesting part is the contract around it: genome identity, repeated measurement, fault injection, invariants, hashed evidence, and a verdict policy. A toy shop is the right size to make the method inspectable. The Real project page is where the method meets an actual repository, with a measured adapter and a simulated screening branch.

**Q45. The simulated screening sounds like guesswork. Why include it?**

Because inspection alone is not a recommendation, and executing an arbitrary repository is unsafe. Screening is a transparent, deterministic model that turns source-backed facts into a ranked hypothesis, with assumptions, limitations, and seed sensitivity. It is explicitly `NOT_MEASURED`. Its job is to help decide what deserves a real measurement, not to replace one.

**Q46. Why should I believe the 28.5% number?**

Because it is attached to a recorded run with 68/68 correctness checks, 29/29 source tests, and a 100% paired win rate at 50,000 rows, and the artifacts are retained. But the honest framing is: it is a measured improvement for that adapter, that workload, and that environment. It is not a universal claim about the repository or about your production system. The live run showed 22.4% with 97% paired wins, which is a useful reminder that results vary.

**Q47. What if the audience asks for a production deployment?**

Say clearly that the MVP does not deploy to production. It produces a candidate and evidence for a human review. A production rollout would need environment-specific adapters, change management, rollback, and monitoring. DARWIN is the evidence layer before that process, not a replacement for it.

**Q48. What if the audience asks why not use AI to generate the architecture?**

Because generation without verification is the problem, not the solution. DARWIN's value is the verification loop: a bounded change space, measured runs, correctness gates, and a verdict that can say no. AI can help propose candidates, but the evidence has to come from execution.

**Q49. What happens if the gate is wrong?**

Then the evidence is wrong, and the system can approve a bad change or reject a good one. That is why the invariants are explicit, the fault scenarios are recorded, and the artifacts are inspectable. The gate is not infallible; it is auditable. A company should review the invariants and add the ones that matter to its domain.

**Q50. Why is this better than a senior engineer's judgment?**

It is not a replacement for judgment. It is a way to give judgment better inputs. A senior engineer still decides which invariants matter, which workload is representative, and whether the cost trade-off is acceptable. DARWIN makes those inputs explicit and the result reviewable. The best framing is "judgment plus evidence", not "automation instead of judgment".

---

## 12. What you can and cannot claim

Use this table as a guardrail before any presentation.

| Claim | Allowed? | Correct wording |
|---|---|---|
| "DARWIN measured a 28.5% improvement" | Yes, with scope | "The recorded Sanchay full run measured 28.5% at 50,000 rows with 68/68 checks and 100% paired wins" |
| "DARWIN makes systems 28.5% faster" | No | Overgeneralizes beyond the adapter, workload, and host |
| "The screening says 12% faster" | Only with label | "The screening model estimates 12% lower p95; this is simulated and not measured" |
| "The demo shop proves idempotency" | Yes, narrowly | "The demo shop shows one order, one capture, and one payment effect after a repeated request" |
| "DARWIN guarantees exactly-once delivery" | No | The shop demonstrates an outbox and delivery evidence; distributed exactly-once is not claimed |
| "DARWIN is production-ready" | No | "DARWIN is a local MVP lab; production rollout needs adapters, change management, and monitoring" |
| "The search finds the optimal architecture" | No | "The search finds a bounded Pareto front of measured, gate-passing candidates" |
| "No candidate passed" | Yes | "No candidate passed all gates; the gate reasons are retained" |
| "Accessibility is fully verified" | No | "Automated axe rules and scripted keyboard checks pass; screen-reader and user testing are not covered" |
| "The Docker benchmark improved p95 from 102.75 ms to 77.65 ms" | Yes, with scope | "In the recorded Docker benchmark, median p95 moved from 102.75 ms to 77.65 ms" |

---

## 13. Glossary

| Term | Meaning |
|---|---|
| **Genome** | The four deployment controls that define a candidate: replicas, cache TTL, notification mode, retry policy |
| **Genome hash** | SHA-256 of the canonical genome JSON; used as identity and cache namespace |
| **Gate** | Correctness and invariant checks that can reject a candidate regardless of performance |
| **Invariant** | A business rule that must hold, e.g. one payment effect per key (I-01) |
| **Measured** | An isolated stack was deployed, a workload ran, and evidence was recorded |
| **Simulated** | A model produced a recommendation; no repository code was executed |
| **Pareto front** | The set of candidates where no other candidate is better on every objective |
| **NSGA-II** | A multi-objective evolutionary algorithm using non-dominated sorting and crowding distance |
| **Paired win rate** | The fraction of paired baseline/candidate repetitions where the candidate is faster |
| **Verdict** | The policy decision: verified improvement, baseline retained, inconclusive, rejected, not measured, or infrastructure failed |
| **Artifact** | A hashed evidence file: manifest, metrics, trace, compose, or log |
| **Adapter** | A reviewed, source-specific evaluation path for a trusted repository |
| **Screening** | The uncalibrated architecture model used when execution is not available or not appropriate |

---

## 14. One-page cheat sheet

**The spine:** Genome → Experiment → Gate → Evidence.

**Page in one line each:**

- **Real project** — inspect a repository, separate facts from guesses, then measure a trusted adapter or screen the architecture. Never blur `SIMULATED` and measured.
- **Architecture** — choose four controls, see the topology and resource cost, get an uncalibrated estimate. Correctness is not checked here.
- **Experiments** — deploy the stack, repeat the measurement, inject faults, check the invariants. A fast failure is still a failure.
- **Search** — spend a bounded budget to find the measured Pareto front. If nothing passes, say so.
- **Demo shop** — resend the same checkout and watch the ledger stay at 1 order, 1 capture, 1 payment effect. This is the ground truth.

**The three sentences to repeat:**

1. "A performance improvement cannot override a failed correctness check."
2. "Simulated and measured are different evidence tiers, and the UI never blurs them."
3. "The output is a candidate for human review, not an automatic deployment."

**The honest limits to volunteer:**

- One host, one environment, local only.
- The demo genome is four controls and 36 combinations.
- Only three repositories are trusted for evaluation today.
- Screening is uncalibrated and always `NOT_MEASURED`.
- Native fault execution is Windows-only; Docker requires cgroup v2.
- No cloud, Kubernetes, installer, or statistical significance claim.
- Accessibility coverage is automated rules plus keyboard, not screen-reader or user testing.
