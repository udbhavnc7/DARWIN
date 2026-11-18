# DARWIN components, in plain language

This guide explains every control, label, and metric in the app so you can explain them yourself, without reading the code. It is deliberately concrete: each term gets *what it is*, *why it matters*, and *a small example*.

The short version: DARWIN is an architecture experimentation laboratory. It builds deployable checkout configurations, runs them under traffic and injected failures, verifies the business rules first, and only then ranks the trade-offs. Speed is a tiebreaker, not permission to cheat.

---

## 0. The whole app in one paragraph

DARWIN sits alongside AWS, Kubernetes, Redis, Locust, Prometheus and chaos tools; it does not replace them. It coordinates one decision: which architecture should carry the next 10,000 users. The workflow has six stages: **Overview → Project Workspace → Architecture → Experiments → Evolution → Solution**. In the app, **Overview** frames the decision. **Project Workspace** connects a pinned public backend and carries it through Connect → Understand → Challenge → Evolve → Prove. **Architecture** lets you shape a deployable checkout configuration (replicas, catalog cache, notification delivery, retries). **Experiments** runs it under traffic and injects database delays, outages and duplicate requests; five invariants run before timing counts. **Evolution** proposes many configurations with NSGA-II, random search or hill climbing, screens them cheaply, and keeps a Pareto front of measured trade-offs. **Solution** turns the recorded verdict into a decision with its measured trade-off, reviewable change, rollback notes and evidence bundle. **Demo shop** is the smallest reproduction of the correctness idea: repeating a request with the same key must never create a second order or a second charge.

---

## 1. Overview (home page)

The home page states the product direction before you run anything:

1. **What decision is this?** The hero — *Growth forces a decision. Evidence settles it.* — introduces the **Illustrative decision** board. Three configurations: **A Basic**, **B Cached** (choose), **C Distributed** (rejected). C is fastest and still loses because it fails the duplicate-payment rule.
2. **Why does the decision appear?** The *"One server works. Then the traffic arrives."* section explains the growth problem: at 100 customers one backend and one database are enough; at 10,000, pages slow down, writes time out and payments fail. The question card asks which configuration should carry the next 10,000 users.
3. **What does the example look like?** An A/B/C table with shape, monthly cost, response time, recovery, duplicate-payment pass/fail, and the decision. The costs (₹10,000 / ₹20,000 / ₹35,000) are **hypothetical** and footnoted as an illustration of the decision rule, not a DARWIN result.
4. **What is the workflow?** **One project, from question to solution** — Overview, Project Workspace, Architecture, Experiments, Evolution and Solution — with a link from each stage to the page that performs it. The outcome strip names the deliverable: evidence-backed architecture recommendations.
5. **Why not just AWS, Kubernetes and load tests?** A comparison table lists what each existing tool provides and what it does not decide, then shows DARWIN's coordinating role. The callout repeats the rule: a fast configuration that double-charges is a rejected candidate with evidence.
6. **What is real today?** Two scope cards separate **Runs today** (controlled checkout lab, five invariants, two public backends, guarded Linux Docker execution, labelled simulation) from **Product direction** (arbitrary repositories, more frameworks, cloud execution, cost comparison, deploy). The right card is roadmap, not shipped functionality.
7. **What is the analogy?** A racing test bench: you would not guess an engine by feel; you would measure each combination, reject the ones that fail safety, and keep the best overall trade-off.
8. **What can I run right now?** The baseline checkout stack, **Execution environment**, and **Machine readiness** (a preflight report of required and optional tools). When the hosted recorded build is open, the cards say **Recorded** instead of pretending to be live.

**One sentence to say it out loud:** "This page is the lab's thesis: growth forces an architecture decision, and the fastest configuration is not automatically the winner — the six stages are how we settle it with evidence."

---

## 2. Architecture: what the four knobs mean

A configuration in DARWIN is called a *genome*. It has exactly four controls, and every combination is a legitimate candidate:

| Knob | Values | Plain meaning |
|---|---|---|
| `app_replicas` | 1, 2, 3 | How many identical checkout API processes sit behind the gateway |
| `catalog_cache_ttl_s` | 0, 10, 30 | How long product descriptions may be reused from Redis before being read from PostgreSQL again |
| `notification_mode` | `sync`, `queued` | Whether the order confirmation tries to notify the customer inline, or hands that job to a background worker |
| `retry_policy` | `none`, `idempotent_only` | Whether a failed downstream call is retried once with the same request key, or not at all |

There are 3 × 3 × 2 × 2 = **36 possible configurations**. That small, fully enumerable space is intentional: the search can explore all of it, and you can still reason about any single candidate by hand.

The **baseline** is `{1 replica, 0 s cache, sync notifications, idempotent retries}`. It is the simplest system that works. The **cached** preset is `{3 replicas, 10 s cache, queued notifications, idempotent retries}`: the "scale it up" instinct, which may or may not survive measurement.

### 2.1 API replicas (1, 2, 3)

Each replica is another copy of the checkout API behind the gateway. More replicas can serve more concurrent requests, and the gateway spreads traffic across them.

But a replica is not free. In the Docker rendering each API replica is capped at 0.4 CPU and 384 MiB, and the native runner enforces analogous limits. More replicas also mean more connections to the database, more cache clients, and more processes that can fail independently. The app never assumes "more is better"; it measures it.

*Example:* one replica handling 4 requests/s is comfortable. During the flash-sale burst of 12 requests/s, one replica may queue requests and raise p95; three replicas may keep p95 flat while CPU is spread across processes. Whether that actually happens on this machine is exactly what the benchmark decides.

### 2.2 Catalog cache (0 s, 10 s, 30 s)

The catalog endpoint returns product names, prices, and current stock. With a cache TTL above zero, the API stores the *descriptions* (SKU, name, price) in Redis under a key derived from the configuration hash, and reuses them for that many seconds.

Important detail: **stock is never cached.** Availability is always read from PostgreSQL, so a cache cannot make the shop oversell. The cache only saves repeated reads of the slow-changing description rows.

With 0 s, no Redis service is deployed at all: the configuration is genuinely simpler, not "cache disabled at runtime." With 10 s or 30 s, Redis becomes part of the topology, shared by all API replicas, so a cache miss in one replica warms it for the others.

*Example:* the normal workload is about 4 requests/s, 75% of them catalog reads — roughly 3 catalog requests/s, about 36 in a 12-second window. Every one of those still reads stock from PostgreSQL, because availability must be live. What the cache removes is the *second* query for product descriptions: with a 10-second TTL roughly 34 of the 36 requests are description-cache hits, and with 30 seconds roughly 35 are. So the saving is a query per request, not the whole database call, and each hit costs a small Redis lookup instead. The trade-off is one more service (0.25 CPU, 128 MiB in Docker) and descriptions that can be up to 10 or 30 seconds old. In the demo shop prices do not change mid-run, so the visible effect is latency and CPU, not correctness.

### 2.3 Notification mode (`sync` vs `queued`)

Every confirmed order creates a notification job in an outbox table.

- **`sync`**: after the order commits, the same API process tries to deliver the notification immediately. The customer's checkout response can carry that cost, and if the receiver is unavailable the job stays pending for later recovery.
- **`queued`**: the checkout commits the order and the outbox row, then returns. A separate worker service polls the outbox and delivers notifications in the background. Checkout latency is insulated from the notification receiver, at the price of one more process (0.25 CPU, 256 MiB in Docker) and delivery that is eventual rather than immediate.

Either way, invariant I-05 says an accepted notification must survive a process crash and eventually finish with matching delivery evidence. The fault test kills the delivering process (the API in sync mode, the worker in queued mode) mid-acknowledgment to prove it. Queued mode is not a way to lose notifications more politely; it is a way to decouple latency while keeping the same guarantee.

### 2.4 Retry policy (`none` vs `idempotent_only`)

- **`none`**: one attempt. If a downstream call fails transiently, the checkout returns 503 and the client must retry with the same idempotency key.
- **`idempotent_only`**: one bounded retry (two attempts total, a short delay between them, inside the checkout deadline), reusing the identical payload and request key. Business errors like out-of-stock are not retried; only transient failures are.

The retry is safe because inventory reservations, payment captures, and order rows are all keyed by the request key. Retrying the same key cannot double-reserve or double-charge. The contrast is the **unsafe retry fixture**, used deliberately on the Experiments page to show what happens when a payment is retried *without* that discipline: one request, three payment effects, gate rejected.

### 2.5 Service connections (the topology picture)

The diagram is the rendered shape of the configuration, not a decoration. It is derived from the same genome that produces the actual deployment:

- the gateway routes to `api-1 … api-N`;
- every API connects to inventory, payment, and PostgreSQL;
- every API also connects to Redis when the cache TTL is above zero;
- inventory, payment, and the notification worker each connect to PostgreSQL;
- the worker exists only in queued mode.

So moving a slider literally changes the number of processes, containers, and edges. The "services / connections / replicas" summary is the count of what would be deployed. In Docker, the selected configuration is rendered into a real Compose project with those service names and fixed per-service CPU and memory caps.

### 2.6 Configuration hash

The hash is a SHA-256 of the four controls written as canonical JSON (sorted keys, no whitespace). It is a **name**, not a security signature.

The same four values always produce the same hash; changing any one value produces a different one. DARWIN uses it as:

- the identity of a candidate in search results, lineage, and the Pareto front;
- the Redis cache namespace, so configurations cannot read each other's cache;
- the Docker Compose project name (`darwin-` plus the first 12 hex characters), so two runs of different configurations cannot collide.

*Example:* `{"app_replicas":1,"catalog_cache_ttl_s":0,"notification_mode":"sync","retry_policy":"idempotent_only"}` always hashes to the same baseline identifier. If you switch notifications to `queued`, the hash changes, and that candidate is a different object everywhere.

### 2.7 Simulated performance

The Architecture page can simulate the configuration before spending real time. The simulator is a discrete-event model of the same shop: requests arrive on the seeded plan, API capacity is divided among replicas, a description-cache hit skips the description query (stock is still read live), queued notifications move work off the request path, and the model can account for a database delay in milliseconds.

It is **calibrated, not guessed**. A service-time scale factor is fitted from successful native benchmark samples, so the model's latency is anchored to measurements from this code on this class of machine. The honest limits are visible in the repo's results: mean absolute p95 error around 27% across held-out samples, with one holdout as high as 53.9%. That is useful for ranking and screening; it is not proof.

Two labels matter:

- **`fitted_limited_evidence`** means this exact genome and workload appeared in the calibration fit set, so the scale applies directly, and the panel shows how many held-out repetitions exist and their errors.
- No calibration label (or a fallback scale of 1.0) means the model is extrapolating. Valid for exploration, not for a verdict.

The simulation card also says **"Correctness gate unchecked."** A simulator can estimate latency; it cannot prove that a payment happened once. Simulated results are never promoted to measured evidence, never enter the Pareto front, and never become the answer.

### 2.8 The configuration screenshot, summarized

Architecture = "here is the system I am proposing." The four knobs change the topology, the hash names it, and the simulator gives a first, cheap opinion. Nothing here is a result yet.

---

## 3. Experiments: scenarios, types, and metrics

### 3.1 What an experiment actually is

An experiment takes one or two configurations, deploys them **one at a time** into an isolated sandbox (own ports, own private database, own processes or containers), runs the same seeded workload, and records everything: request samples, CPU and memory counters, fault traces, the business ledger, and hashes of every artifact.

In a measured run, each configuration is run **three times** (three repetitions, with seeds 42, 43, 44 when the run seed is 42). The UI reports the median and the min–max range across those three runs for p95, throughput, errors, CPU, and peak memory, so you can see noise instead of a single lucky number; recovery is shown scenario by scenario under each repetition. That is why a two-configuration comparison is six full deployments, not two.

### 3.2 The four scenario presets

These are shortcuts that fill in a known-good request. They use the same engine as a manual run; they do not simulate or skip gates.

**Quick checkout smoke** — a functional handshake, not a performance test. It starts the baseline stack, reads the catalog twice, then for two different products sends a checkout and immediately replays the exact same request with the same idempotency key, checking that the response is identical. It then runs the ledger verifier and waits for the notification queue to drain. The evidence is labelled `smoke_only`, and the gate is `not_checked`. It is the fastest way to answer: "does this machine and this build still work?" (Roughly 20–30 seconds native.)

**Normal baseline vs candidate** — the core performance comparison. Baseline `{1, 0 s, sync, idempotent}` versus candidate `{2 replicas, 10 s cache, queued, idempotent}` on the normal workload. Three repetitions each, so six measured attempts. The result is a spread of p95 latency, requests/s, error rate, CPU seconds, and peak memory for both. (Roughly 3 minutes native; several minutes in Docker.) The card's expectation line also mentions recovery spread; recovery is only measured when the run includes fault scenarios, which a pure performance comparison does not. Treat this preset as the latency/CPU comparison, and use the fault type or a search for recovery evidence.

**Flash sale comparison** — baseline versus `{3 replicas, 30 s cache, queued, idempotent}` under the flash-sale workload: the same steady 4 requests/s, but with a burst of 12 requests/s for four seconds. It shows whether extra replicas and a longer cache hold the line when traffic spikes, and what they cost in CPU and complexity.

**Payment timeout with unsafe retry** — a correctness demonstration, not a speed one. The stack runs in queued mode with the unsafe fixture: the payment reply is dropped for 1.2 seconds, the client retries, and the retry is deliberately *not* protected by the idempotency key. The expected result is a rejected gate with business invariant **I-01** and three payment effects for one request key. It is the clearest possible answer to "can a fast configuration still be wrong?"

### 3.3 Experiment types

The **Experiment type** select changes what the run proves:

- **Compare performance** (`benchmark`): deploy, apply load, measure latency/CPU/throughput/errors on a healthy system. No fault injection, so the feasibility gate stays `not_checked` and no business invariants are exercised.
- **Verify failure recovery** (`faults`): everything above plus the chosen fault scenarios and the three mandatory checks (replay, stock race, notification crash). This is the only type that produces a feasibility verdict with a gate and recovery numbers.
- **Unsafe retry fixture** (`faults` with `unsafe_retry`): the fault type with the correctness trap switched on; the configuration is fixed, because the point is the trap.
- **Checkout smoke check** (`smoke`): the handshake described above.

If the selected runtime cannot support measurement (for example Docker is not running), only the smoke check is available; the page says so instead of failing halfway.

The scenario cards and the type selector are two views of the same request. "Quick checkout smoke" is the card that fills in a **Checkout smoke check**; "Normal baseline vs candidate" is the card that fills in a **Compare performance** run with the candidate preselected; "Payment timeout with unsafe retry" fills in the **Unsafe retry fixture**. Choosing a card does not skip the type; it just sets it for you.

### 3.4 The configuration picker

- **Preset** uses one of the two named configurations (`cached`) from the Architecture page.
- **Baseline** uses the reference configuration, useful for re-running the reference or for the smoke check.
- **Custom** uses whatever you last edited in the Architecture builder.

Choosing the baseline as the candidate in a performance comparison is rejected by the UI: comparing a configuration with itself proves nothing. The summary line under the picker spells out the four chosen values in words, so there is no ambiguity about what will be deployed.

### 3.5 Runtime: Native vs Docker

Both runtimes execute the *same* shop code, the *same* seeded workload, and the *same* fault protocol. The difference is packaging and enforcement:

- **Native** runs each service as a local Windows process inside a job object, with a private PostgreSQL instance for the run, run-scoped ports, and CPU/memory accounting from the job object. Startup is fast, which makes it the reliable demo path on this machine. It requires Windows and whole-number CPU budgets.
- **Docker** renders the configuration into a Compose project, starts containers with cgroup limits, and reads counters from cgroups. It is closer to how the system would ship and isolates dependencies more strongly, but image and container startup make every deployment slower, and it needs Docker Desktop running. The preflight panel marks it optional when it is unavailable.

A measured result records which runtime produced it. Native and Docker timings should not be mixed in one comparison.

### 3.6 Workloads

All three workloads use the same three SKUs, one checkout key per checkout request, a 3-second catalog warm-up, and a 12-second measurement window. Only the mix changes:

| Workload | Checkout share | Request rate | Shape |
|---|---|---|---|
| **Normal** | 25% checkout, 75% catalog | 4 requests/s | Steady |
| **Flash sale** | 50% checkout | 4 requests/s, then 12/s for seconds 4–8 | A four-second burst |
| **Checkout heavy** | 75% checkout | 4 requests/s | Steady, checkout-dominated |

Checkout is the expensive path: it locks an order row, reserves stock, captures payment, and writes an outbox job. Catalog is the cheap read path. So the checkout share is the main lever on latency. *Example:* normal sends roughly 12 checkouts in 12 seconds; checkout-heavy sends roughly 36. Same rate, very different work.

The flash-sale burst is what makes it a stress test: 12 requests/s for four seconds is three times the steady rate, precisely the moment when a single replica's queue becomes visible in p95.

### 3.7 What happens during one measured attempt

1. The configuration is rendered (topology, compose or native process specs, cache namespace).
2. The isolated sandbox starts: database, inventory, payment, gateway, one API per replica, Redis if cached, worker if queued.
3. A 3-second catalog warm-up must succeed entirely; otherwise the attempt fails rather than measuring a broken system.
4. The seeded 12-second plan runs. Every request records start time, finish time, latency, status, and success.
5. Application CPU and peak memory are read from the job object or cgroups around the window.
6. In fault mode, the fault scenarios and mandatory checks run, with recovery probes at 2 requests/s, and the business ledger is checked against the five invariants.
7. Artifacts are hashed into a manifest and the sandbox is torn down.
8. The three repetitions are summarized: median and min–max for each metric, plus a gate verdict.

### 3.8 Fault scenarios and the mandatory checks

- **Database delay**: Toxiproxy adds 100 ms of latency to database traffic for two seconds, then removes it. Tests whether requests slow gracefully and recover.
- **Database disconnect**: the database proxy is disabled for two seconds. Tests reconnection and bounded failure rather than a hang.
- **Service outage**: the API processes are paused for two seconds, then resumed. Tests whether queued work and clients survive an unresponsive application.
- **Payment timeout with duplicate retry**: the payment reply is lost for 1.2 seconds, so the first checkout appears to fail after the payment has already committed. The retry must return the same receipt and leave one payment effect.

Every fault run also performs three checks that are not optional: **concurrent replay** (four simultaneous replays of one key must return the same response and add no rows), **stock race** (four buyers compete for two units; exactly two succeed), and **notification acknowledgment crash** (the process delivering the notification — the API in sync mode, the worker in queued mode — is killed at the acknowledgment boundary; the notification must still complete after restart). This is why even a run that only selects "database delay" still produces business evidence.

### 3.9 The metrics

**p95 (ms)** — the 95th percentile latency: 95% of requests in the window finished faster than this number, 1 in 20 was slower. It is the "typical worst experience" metric, far more useful than an average that hides a slow tail. DARWIN uses the nearest-rank definition on the measured window. *Example:* 48 requests, sorted by latency; p95 is the 46th value. The app reports the median of the three repetition p95s plus the min–max, so you can see whether a result is stable.

**Requests/s** — completed requests divided by the 12-second window. Useful for spotting a configuration that keeps latency low by doing less work.

**Errors (%)** — the share of requests that failed the success check (non-200, wrong body, transport error). The default limit is 1%. In a 48-request window, a *single* error is 2.1%, so even one failure exceeds the default. That is intentionally strict: the point is to catch correctness regressions, not to tolerate a flaky demo.

**CPU (s)** — total application CPU seconds consumed across the measured window, summed over the shop processes (API replicas, worker, and so on), not per request and not wall time. *Example:* 2.4 CPU s over 12 seconds means the application averaged 0.2 of a core busy; 6.0 CPU s means it averaged half a core. Lower is more efficient, but only if latency and correctness hold.

**Peak MiB** — the highest resident/working-set memory observed during the attempt. It tells you whether a configuration fits the sandbox envelope, especially with three replicas plus Redis plus a worker.

**Recovery (s)** — only from fault runs. The suite records a 5-second pre-fault baseline, injects the fault for 2 seconds, removes it, and then probes the catalog twice per second for up to 15 seconds. Recovery is the time from *fault removal* until a rolling 5-second window (10 probes) shows error rate at or below the limit and p95 at or below 1.2× the pre-fault baseline. If no such window appears within 15 seconds, recovery is recorded as **not observed** (censored), not as a large number. The candidate's recovery objective is each attempt's worst (largest) value across its scenarios, then the median of those three attempt values. *Example:* fault removed at 7.0 s, the first acceptable 5-second window starts at 9.5 s and is confirmed at 14.5 s; recovery is reported as 7.5 s. If a database outage never settles, recovery is `null`, and the candidate cannot be feasible — that is the `recovery_not_observed` reason.

**Why three repetitions** — a single run cannot separate a real difference from machine noise. The spread (min–max) tells you how much the number moves on this computer. A candidate whose latency ranges from 240 to 410 ms across three runs is not meaningfully better than one that sits at 330 ms; the app shows you the range so you can say that out loud.

### 3.10 The feasibility gate and why a candidate is rejected

A gate is a list of hard requirements. Performance never overrides them. The reasons the backend can return:

| Reason | Meaning |
|---|---|
| `resource_limits_unverified` | The run could not prove the sandbox limits were enforced |
| `business_invariant_failed` | At least one of I-01…I-05 failed (double payment, stock mismatch, missing payment evidence, replay side effect, lost notification) |
| `fault_scenario_incomplete` | A selected fault was not actually observed, or the fault evidence is incomplete |
| `invariant_coverage_incomplete` | The run did not exercise all five invariants |
| `measurement_error_threshold` | Request error rate above the limit (default 1%) |
| `fault_operation_error_threshold` | Logical errors during fault operations above the limit |
| `measurement_latency_threshold` | p95 above the configured target — only when a target is set; the default has none |
| `recovery_not_observed` | A fault scenario never returned to acceptable error rate and latency within 15 seconds |

The five invariants, in plain words:

- **I-01** one payment effect per payment key — a retry cannot charge twice.
- **I-02** stock reconciles — available = initial − active reservations, and confirmed orders never exceed reservations.
- **I-03** every confirmed order has a matching captured payment of the same amount.
- **I-04** replay adds nothing — no duplicate orders, reservations, or deliveries, and no changed response.
- **I-05** every confirmed order keeps its notification job, and the job eventually completes with matching delivery evidence, even across a worker crash.

*Example of a rejection you can explain in one breath:* the unsafe-retry fixture produces three payment rows for one key, so I-01 fails, `business_invariant_failed` is added, and the gate is rejected regardless of how fast the checkout was.

---

## 4. Evolution: how DARWIN looks for a better configuration

### 4.1 What a search is doing

Search repeats the experiment loop automatically. In each generation it:

1. **proposes** a handful of new configurations (up to 4 by default);
2. **screens** every proposal with the calibrated simulator — cheap, no deployment;
3. **promotes** one configuration to a real measured run (three repetitions of the full fault protocol);
4. reads the gate results and the three objectives, and uses them to choose parents for the next generation;
5. stops after the generation budget or the wall-clock cap.

The default UI settings are: generations = measured attempts ÷ 3, population 4, one promotion per generation, three repetitions per promoted candidate. So the "Measured attempts" budget is really the number of real deployments the search is allowed to start.

### 4.2 Measured attempts (6, 12, 18)

Each promoted configuration costs three attempts (three repetitions). That gives a clean mapping:

| Budget | Measured configurations | Candidates proposed (screened) | Search wall-clock cap |
|---|---|---|---|
| 6 (default) | 2 | up to 8 | 24 min |
| 12 | 4 | up to 16 | 48 min |
| 18 | 6 | up to 24 | 72 min |

The caps are ceilings, not promises: a run can finish earlier, and Docker runs take much longer per deployment. The progress line "Measured attempts started x / 6" counts real deployments begun, not simulations, so you can always tell how much of the budget has been spent.

*Why so few?* One measured candidate is a full deploy, 3-second warm-up, 12-second load window, fault injection, invariant checks, and teardown — minutes of real work. The design deliberately spends most candidates on cheap screening and reserves real runs for the few that matter. Six attempts is enough to demonstrate the loop; twelve to eighteen is enough to see a front.

### 4.3 Seeds

A seed is a number that makes randomness repeatable. DARWIN uses it for the load schedule (which request goes at which instant, which SKU, checkout or catalog), for the simulator's random draws, and for the search's sampling. Fault request keys also include the seed.

Same seed + same code + same machine ⇒ the same request plan, the same simulated candidates, and comparable runs. That is why a rerun is meaningful: you are repeating the experiment, not rolling new dice.

Different seeds ⇒ independent samples. Running the same configuration or the same search under several seeds is how you check that a result is not luck. The repo's three-seed campaign is exactly that: the same search repeated with different seeds, reporting the spread and the number of searches that produced a feasible candidate, rather than one flattering run.

*What to say:* "The seed is the dice roll we wrote down. Same seed, same experiment; different seeds, a robustness check."

### 4.4 The three search methods

**NSGA-II (default)** — a genetic algorithm built for several competing objectives. It keeps a population of candidates, sorts them into non-dominated fronts (nobody in front is worse on all three objectives and better on one), and prefers candidates that are spread along a front rather than clustered. Parents are chosen by tournament, combined by taking each gene from one parent or the other, and then one gene is mutated. It is the right default when latency, CPU, and recovery genuinely trade off.

Plain version: "It breeds configurations, keeps the ones that are not beaten on every axis, and deliberately keeps some variety so it does not converge on one narrow answer."

**Hill climbing** — start from the baseline, look at all neighbors that differ in exactly one knob, measure the best-looking one, and repeat from there. It is simple, explainable, and good at incremental tuning. Its weakness is the local optimum: if every one-step move looks worse, it stops, even if a two-step move would have been better. It also tends to spend its budget near the starting point.

**Random search** — pick configurations arbitrarily, subject only to the sandbox resource budget, and measure them. It is not a strawman: with 36 configurations, random sampling is a legitimate baseline, and it answers "did the clever search actually beat guessing?" It has no memory and no lineage.

All three always include the baseline as the first proposal, so every search has a reference point. All three use the same screening, promotion, and gate rules; only the choice of what to propose changes. Screened candidates are never counted as results.

### 4.5 Screening and promotion: why some candidates never get measured

Before spending a real test, each proposal gets a calibrated simulation. Promotion then picks, in this order:

- the **baseline**, whenever it is among the proposals — which it is in every search's first generation — so the run has a reference;
- otherwise the candidate with the **lowest simulated p95**, the model's best guess at a winner.

The promotor also has a diversity rule: when more than one candidate is promoted from the same generation, it alternates between the next-lowest estimate and the candidate **furthest** from what has already been selected. The UI's default promotes one per generation, so in practice you will see the baseline first and then the estimated-best proposal; the diversity rule becomes visible if the promotion count is raised.

This is also why the candidate list is mostly "screened": with four proposals and one measured slot per generation, three proposals lose the slot every round. They are not failures — they are estimates the search chose not to pay for.

### 4.6 The six candidate labels

| Label | What it means | Is it a result? |
|---|---|---|
| **Simulated · screened** | Proposed and simulated, not promoted to a real run | No — a cheap estimate |
| **Promoted · measuring** | Selected for measurement; its three repetitions are running now | In progress |
| **Measured · feasible** | Three measured repetitions completed, every gate passed, and all three objectives are available | Yes — the real result |
| **Measured · incomplete** | A real run happened but there is no complete three-repetition summary (the run was cut short, cancelled, or an attempt failed) | Evidence, but not a verdict |
| **Measured · rejected** | Three measured repetitions completed but the gate failed; the rejection reasons are listed | Yes — a result, and a negative one |
| **Measured · recovery unavailable** | The run's gate line says passed, but at least one ranking value needed to place it on the front is missing (most often recovery was not captured), so the app refuses to call it feasible | Not feasible |

Two subtleties worth saying out loud:

- A candidate can be **measured and still rejected** for a reason that has nothing to do with speed — a single error, a missing invariant check, a double payment. That is the product's whole point.
- **Incomplete is not rejected.** It means "we do not have a full measurement", and the app refuses to guess. A green "feasible" badge always means three clean measured runs, not a good-looking simulation.

The objectives themselves are only computed when all three repetitions are completed, measured, and gate-passed, with finite non-negative p95, CPU, and recovery values. Each objective is the median of the three repetitions: median p95, median CPU seconds, and the median of each attempt's worst recovery across scenarios.

### 4.7 The Pareto front and "no feasible candidate"

The scatter chart plots measured p95 against measured CPU for every feasible candidate. **Filled** points are on the Pareto front: no other feasible candidate is at least as good on p95, CPU, *and* recovery while being strictly better on one. They are the honest trade-offs — the fast-but-hungry option, the efficient-but-slower option — not a single "winner."

If no candidate passed every gate, the chart says so and the verdict panel lists **why** candidates were rejected, with counts: for example `business_invariant_failed × 3`, `measurement_error_threshold × 1`. That is a more useful answer than a fake winner. The panel then offers safe next moves that do not bypass any gate: retry with a larger measured budget, switch to a more demanding workload, or open a recorded feasible run to see what a successful search looks like.

The "no feasible candidate" outcome is a legitimate, explainable result: within this budget, on this workload, nothing both met the business requirements and produced clean measurements. The honest response is more evidence, not a lower bar.

### 4.8 Search overhead, lineage, and the run card

- **Search overhead** is time the coordinator spent simulating, proposing, and selecting — not time inside any measured deployment. It tells you how much of the wall-clock was thinking versus measuring.
- **Candidate lineage** draws which measured candidates influenced each proposal, using parent hashes. It makes the search's reasoning visible rather than magical.
- **Search events** are the coordinator's log: generation started, candidates promoted, repetitions completed, gates evaluated.
- **Rerun search** repeats the same request, including the seed; use it to check reproducibility, not to shop for a better number.

---

## 5. Solution: the decision record

The **Solution** page is where a run stops being a chart and becomes something a team can act on. It reads the project evaluations that recorded a verdict and presents the newest one by default.

| Part of the page | What it tells you |
|---|---|
| Decision selector | Every recorded verdict, newest first: project, commit, verdict label and date |
| Decision card | The verdict label and reason, source repository, pinned commit, challenge, mode, repetitions, correctness count, evidence kind and date |
| Measured panels | Original versus recommended median and p95, the percentage change, and any metric that regressed |
| Recommendation | Whether the evidence supports applying the change, or keeping the original as the fallback |
| Evidence to keep | The artifact files and digest prefixes in the bundle |
| Truth boundary | What the decision carries and what it explicitly does not claim |

The badge is the authority. A measured verdict reads **Measured** (or **Live · this computer** on a live bench); a simulated screening reads **SIMULATED · NOT MEASURED** and hides the measured latency panels, because a model's recommendation is a direction to test, never a measured winner.

A recorded decision is presented exactly as recorded. If the evidence retained the original architecture, the page says so instead of inventing a winner. If a metric regressed, the cost of the change is shown next to the improvement. **Download evidence bundle** is enabled only when the page is connected to a live bench; on the hosted showcase it stays disabled and the page keeps reading recorded evidence.

DARWIN never edits, commits or pushes the project repository. The change is a reviewable diff with apply and rollback notes, and the decision remains a local result for one host and one workload window.

**One sentence to say it out loud:** "The last stage is the one a team actually needs: not a chart, but a decision with its evidence and its way back."

---

## 6. The demo shop, simply

The demo shop is a tiny, self-contained checkout used to *show* the idempotency idea without any load, faults, or timing. It is the page to open when someone asks, "What does 'safe retry' actually mean?"

### The three-step walkthrough

1. **Place an order.** The browser generates a unique `Idempotency-Key` and posts a checkout for one notebook. The order moves from pending to confirmed: stock is reserved, payment is captured once, and a notification job is written.
2. **Resend the same request.** The button reuses the *same key* and the same payload. The API recognizes the key, finds the existing order, and returns the same receipt. Nothing is charged again and no stock is taken again.
3. **Compare the ledgers.** The table shows the same order ID, one simulated payment capture, and unchanged catalog stock. The ledger line reads **1 order · 1 capture · 1 payment effect**, with the note that the repeat added no second effect.

**Reset demo shop** truncates the demo tables and restores the seed stock, so you can run the story again from a clean slate. It only ever touches the demo shop's own database.

### A concrete example

The seeded catalog has a notebook at $12.99 with 20 units. You check out one unit with key `K`:

- before: 20 available, 0 orders, 0 payment effects;
- after the first request: 19 available, 1 confirmed order, 1 capture, 1 payment effect;
- after pressing **Resend same request** five times: still 19 available, still 1 order, still 1 payment effect, and every response is byte-for-byte the same receipt.

Without the key, five retries could mean five orders and five charges. With it, "retry" means "remind me what happened," not "do it again."

### The everyday analogy

Think of a coat-check ticket. You hand over the ticket; the attendant brings *your* coat. Hand over the same ticket twice and you still get one coat, not two. The idempotency key is the ticket number; the payment ledger is the rack. The shop's rule is: a ticket identifies an outcome, not an action.

### How it connects to the rest

The demo shop is the safe version of the exact situation the **unsafe retry fixture** breaks on purpose. In the fixture, the payment reply is lost and the retry is not protected by the key, so the ledger ends with three payment effects and invariant I-01 fails. The demo shop shows the guarantee; the experiment shows the cost of losing it.

---

## 7. How the pieces fit together

The six stages map onto the pages:

1. **Overview** — frames the decision: which architecture should carry the next 10,000 users, and why the fastest option can still be rejected.
2. **Project Workspace** — pins one exact commit, maps the backend, separates facts from guesses, and runs the guided Connect → Understand → Challenge → Evolve → Prove flow.
3. **Architecture** — proposes a deployable configuration and gives a cheap, calibrated estimate. Correctness is not checked here.
4. **Experiments** — measures one or two systems for real: load, CPU, latency, errors, database delays, outages and duplicate requests; the five invariants run before timing counts.
5. **Evolution** — automates the measurement loop across candidates, using the simulator only to decide what deserves a real test, and keeps a Pareto front of measured trade-offs.
6. **Solution** — turns the recorded verdict into a recommendation with its measured trade-off, reviewable change, rollback notes and evidence bundle.

**Demo shop** is the smallest reproduction of the correctness idea that protects all six stages: repeating a request with the same key must never create a second order or a second charge.

The governing sentence for the whole app: *a configuration is only a result when it was measured, and it is only feasible when the business checks passed first.*

The governing sentence for the workflow: *the fastest configuration is a candidate; the correct one is a conclusion.*

---

## 8. Numbers worth remembering

| Number | Where it comes from | Why it matters |
|---|---|---|
| 36 | 3 × 3 × 2 × 2 controls | The entire configuration space is enumerable |
| 3 s + 12 s | Warm-up + measurement window | Every attempt uses the same protocol |
| 3 | Repetitions per measured configuration | Median and min–max instead of one sample |
| 4 / 12 req/s | Steady rate / flash-sale burst | The burst is where queues show up |
| 25 / 50 / 75% | Checkout share by workload | Checkout is the expensive path |
| 2 req/s | Recovery probe rate | Recovery is sampled, not guessed |
| 5 s / 2 s / 15 s | Baseline / fault / observation | The recovery measurement window |
| 1.2× | Recovery latency allowance | "Back to normal" means close to the pre-fault p95 |
| 1% | Default error-rate gate | One error in a 48-request window already fails |
| 6 / 12 / 18 | Measured attempts | 2 / 4 / 6 configurations actually measured |
| 5 | Invariants I-01…I-05 | Correctness outranks speed |

---

## 9. One-line explanations (cue card)

- **Quick checkout smoke:** "Start the shop and prove a repeated order returns the same receipt — a handshake, not a benchmark."
- **Normal baseline vs candidate:** "Compare the reference system with a two-replica, cached, queued variant under the normal workload, three runs each."
- **Experiment type:** "Performance measures speed; faults also break things and check recovery and correctness; smoke just checks the stack works."
- **Configuration:** "The four knobs that define the system: replicas, cache TTL, notification mode, retry policy."
- **Native vs Docker:** "Same shop and same tests; native runs local processes fast, Docker runs containers closer to deployment but slower."
- **Workload:** "How much checkout traffic, at what rate, with a burst or not."
- **API replicas:** "More copies of the checkout API behind the gateway — more capacity, more connections, more cost."
- **Cache 10 s / 30 s:** "Reuse product descriptions for that long; stock is always read live, so the cache cannot oversell."
- **Notifications sync vs queued:** "Deliver inline and pay the latency, or hand it to a worker and decouple it — both must survive a crash."
- **Retries none vs idempotent:** "One attempt, or one safe retry with the same key; the key is what prevents a double charge."
- **p95:** "The line 95% of requests finish under; one in twenty is slower."
- **CPU s:** "Total application CPU consumed during the window — lower is more efficient if nothing else regresses."
- **Recovery s:** "Time from removing the fault until a five-second window is back to normal error rate and near-baseline latency."
- **Simulated performance:** "A calibrated estimate used to rank candidates cheaply; useful, roughly 27% typical p95 error, never proof."
- **Service connections:** "The edges the configuration actually deploys: gateway to APIs, APIs to inventory/payment/database/cache, worker to database."
- **Configuration hash:** "A stable name for the four values; same values, same hash, different values, different hash."
- **NSGA-II:** "Breed configurations, keep the ones not beaten on all three objectives, preserve variety."
- **Hill climbing:** "Start at the baseline and take the best one-knob step until nothing looks better."
- **Random search:** "Measure arbitrary configurations — the honest baseline for 'did the smart search help?'"
- **Measured attempts:** "Real deployments the search may start; three attempts per configuration."
- **Seed:** "The dice roll written down, so the same experiment can be repeated and different seeds can test robustness."
- **Screened:** "Simulated proposal that did not win a real test slot."
- **Promoted:** "Chosen for real measurement right now."
- **Measured feasible:** "Three clean measured runs and every gate passed."
- **Measured rejected:** "Real evidence, negative verdict — the gate reasons say exactly why."
- **Measured incomplete:** "A real run without a full three-repetition summary; not a guess, not a verdict."
- **Demo shop:** "One order, one capture, one payment effect — retry with the same key returns the same receipt."
- **Overview:** "The decision, the six stages, what is shipped, and where measurement happens."
- **Project Workspace:** "One pinned commit, understood from source, then measured through a reviewed adapter or screened and labelled simulated."
- **Solution:** "The recorded verdict, its measured trade-off, the reviewable change, the rollback notes, and the evidence bundle."
- **Six stages:** "Overview, Project Workspace, Architecture, Experiments, Evolution, Solution — correctness before speed."
- **Why not just AWS, Kubernetes and load tests:** "They supply infrastructure and measurements; DARWIN coordinates the architecture decision and rejects candidates that break the business rules."

---

## 10. What this evidence is not

Being clear about limits makes the rest credible:

- **The simulator is a screen, not a certificate.** It is calibrated on this code and machine class, with meaningful held-out error, and it never produces feasibility.
- **Measured evidence is local and synthetic.** The shop, payments, and inventory are deliberately fake; the numbers describe this machine, not a production cluster.
- **A single seed is one sample.** The three-repetition spread and multi-seed campaigns exist precisely because one run is not enough.
- **The default gate has no latency target.** It enforces correctness, error rate, recovery, and resource-limit verification. Add a p95 target explicitly if you want latency to be a hard requirement.
- **The API is unauthenticated and local-only.** It is designed to run on `127.0.0.1` with synthetic data; it should not be exposed to a network.

If you can explain those five limits alongside the wins, you can explain DARWIN accurately.