# DARWIN — Phased Project Roadmap

All ten MVP phases are complete. Native Windows validation covered four equal-budget searches. Docker Desktop acceptance verified smoke, paired benchmarks, fault gates, and two search generations. Both runtimes rejected the unsafe fixture for I-01 in all three repetitions. The Docker search produced an empty Pareto front after both candidates missed a recovery gate. See the [Phase 10 results](docs/PHASE_10.md) and [Docker acceptance results](docs/DOCKER_ACCEPTANCE.md).

## Project goal

DARWIN generates supported backend configurations, measures them under repeatable workloads and failures, rejects configurations that break defined business rules, and identifies the best observed performance/resource tradeoffs.

This roadmap adapts the supplied EVOLVER X blueprint under the project name DARWIN. The blueprint is reference material. We implement and verify one phase at a time.

## MVP scope

- One local shop application: gateway, catalog/checkout API, mock payment service, inventory service, and PostgreSQL.
- Four supported controls: application replicas, catalog cache TTL, synchronous/queued notifications, and retry policy.
- Redis for catalog caching and a defined notification queue implementation.
- Three workload profiles: normal, flash sale, and checkout-heavy.
- Fault coverage: database delay, service outage, and ambiguous timeout/retry with duplicate delivery.
- Five business invariants: no duplicate capture per payment key; no overselling; confirmed orders have successful payments; replayed request keys cause no extra business effects; notification completion is backed by actual delivery and accepted jobs survive the specified transient-worker-failure test.
- Real Docker experiments, a calibrated simulator, random/hill-climbing baselines, NSGA-II search, persisted evidence, and a dashboard.
- Synthetic data and local sandboxes. Optional LLM explanations and cloud adapters are later extensions.

## Phase 1 — Define DARWIN and prepare the foundation

Build:
- README, architecture overview, repository layout, and local development instructions.
- Freeze MVP requirements, the baseline configuration, and the meaning of each invariant.
- Define genome, experiment, evaluation, metrics, violation, artifact, and event contracts.
- Decide timeout, cache freshness, notification completion, retry, and resource-budget semantics.
- Check available Python, Node, Docker/Compose, memory, and disk; choose sequential testing defaults to suit the machine.

Done when: scope, contracts, acceptance checklist, and development prerequisites are documented; a small API/UI scaffold starts locally.

## Phase 2 — Build the baseline shop application

Build:
- Gateway, catalog/checkout API, inventory, fictitious payment ledger, and PostgreSQL storage.
- Deterministic seed/reset routines, idempotency keys, safe checkout behavior, and health/readiness endpoints.
- Baseline: one application replica, cache off, synchronous notifications, and an explicitly defined safe retry policy.
- Docker Compose startup and shutdown.

Done when: a fresh environment boots, catalog and checkout work, ledgers can be inspected, the happy-path invariants pass, and reset reproduces the initial state.

## Phase 3 — Make configurations change the running system

Build:
- Typed genome validation, canonical serialization, stable hashing, and topology generation.
- Replicas: 1, 2, or 3 behind the gateway.
- Catalog cache: off, 10 seconds, or 30 seconds.
- Notifications: synchronous or queued, with defined acknowledgment/retry behavior.
- Retry policy: none or idempotent-only; unsafe mode restricted to a deliberately vulnerable test fixture.
- Tested generation of candidate Compose configurations from templates.

Done when: each control changes observable container or request behavior; invalid configurations are rejected; the rendered graph matches the deployment. Keep request timeout fixed initially rather than silently adding a fifth search control.

## Phase 4 — Build the experiment runner and evidence store

Build:
- FastAPI experiment endpoints, a local worker, SQLite records, and artifact storage.
- Run lifecycle: queued, running, completed, failed, and cancelled, with candidate/evaluation progress.
- Candidate deployment, readiness, warm-up, execution, collection, and cleanup.
- Candidate count, real-test count, time, CPU/memory, and deployment concurrency limits.
- Seeds, source revision, tool/environment metadata, generated configuration, artifact hashes, and logs.
- Live event stream and candidate rerun support.

Done when: a manually supplied candidate can complete a recorded experiment; failures and cancellation preserve evidence and clean up the sandbox; the saved inputs support rerunning it.

## Phase 5 — Establish real performance measurements

Build:
- Seeded normal, flash-sale, and checkout-heavy Locust workloads.
- Raw latency samples or aggregatable histograms, throughput, error rate, CPU time, and peak memory collection.
- Fixed warm-up, measurement duration, resource caps, and reset procedure.
- Baseline and at least one distinct candidate measured under the same conditions.
- At least three measured repetitions for shortlisted configurations, with spread reported.

Done when: stored reports compare actual configurations fairly, calculate p95 correctly, and separate application resource use from test-harness overhead. Define how repeated runs determine constraint compliance before ranking candidates.

## Phase 6 — Add failure injection and correctness rejection

Build:
- Toxiproxy database delay and connection disruption, application outage, and timeout/retry/duplicate-delivery scenarios.
- All five invariant checkers against recorded business state and relevant event history.
- Fault schedules, recovery-time measurement, failure traces, and replay commands.
- A deliberately unsafe retry fixture that demonstrates duplicate capture.
- Hard feasibility gates for deployment, invariants, error threshold, and resource budget.

Done when: the unsafe fixture is reproducibly rejected with an invariant ID and trace; the safe configuration passes the defined scenarios; performance cannot compensate for a failed correctness gate.

## Phase 7 — Build and calibrate the fast simulator

Build:
- SimPy model of arrivals, finite workers, cache behavior, database delays, and notification processing.
- Calibration from Phase 5 measurements and validation on separate runs.
- Prediction-error reporting, uncertainty labels, and documented operating limits.
- Screening and promotion rules that also permit uncertain/diverse candidates to receive real tests.

Done when: simulated results are visibly distinct from measured results, calibration error is reported, and screening does not present untested candidates as verified winners.

## Phase 8 — Add evolutionary search and measured ranking

Build:
- Seeded random search and simple hill climbing first.
- NSGA-II with supported mutation/crossover, valid genomes, deduplication, and bounded generations.
- Simulation screening followed by budgeted real evaluation.
- Pareto ranking of measured feasible candidates for latency, resource proxy, and recovery time.
- Search history, parent relationships, and reproducible candidate proposals.

Done when: DARWIN runs the full propose → simulate → deploy → fault-test → verify → record → evolve loop within its budget. Same-seed proposals are reproducible; measured timings are allowed to vary.

## Phase 9 — Complete the dashboard

Build:
- React/TypeScript experiment setup and progress views.
- React Flow architecture graph, candidate lineage, and live events.
- Measured/simulated labels, metrics comparisons, and feasible Pareto plot.
- Rejection detail with violated invariant, evidence, and rerun controls.
- Cancellation, failure, empty-state, and completed-run handling.

Done when: a user can start a bounded experiment, follow its progress, inspect the actual deployment and rejection evidence, compare measured candidates, and rerun a result through the UI.

## Phase 10 — Validate the results and prepare the demonstration

Build:
- Equal-budget comparisons against the original configuration, random search, and hill climbing.
- No-simulator and no-correctness-gate ablations in the isolated test environment.
- Repeated experiments, unseen workload/seed checks, calibration results, and search overhead reporting.
- Setup/run/reset documentation and a reproducible experiment bundle.
- Small live demo, clearly labeled recorded fallback, backup video, and exhibition script.

Done when: a clean setup can reproduce an experiment and an unsafe-candidate rejection; claims are supported by saved measurements; the demo completes within a measured presentation budget. Report negative results honestly if evolutionary search does not beat the baselines.

## Working rules

1. Start with Phase 1 and complete its exit checks before moving to Phase 2.
2. At each phase boundary, record what changed, the verification evidence, remaining issues, and readiness for the next phase.
3. Use the CLI/API for early end-to-end verification; the full dashboard comes after the engine works.
4. Treat simulation as screening, measured tests as experimental evidence, and passing tests as evidence only for the cases exercised.
5. Add advanced features only after the MVP is complete.

## Later extensions

Surrogate/Bayesian optimization, broader application adapters, richer scenario generation, optional LLM explanations, and isolated cloud/Kubernetes adapters.

## Timing

No delivery dates are committed yet. Estimate each phase after Phase 1 establishes the machine capabilities, available working time, and final scope. The source blueprint's eight-week schedule assumes a focused three-to-four-person team.
