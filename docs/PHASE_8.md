# Phase 8 — Measured architecture search

The search coordinator proposes valid genomes, records simulated estimates, promotes bounded batches, waits for complete measured fault experiments, and uses their outcomes to choose the next generation. Its own SQLite store and event history live under `artifacts/experiments/searches`. Each child experiment retains the existing source snapshots, artifacts, cancellation, resource limits and cleanup checks.

The dashboard defaults to two generations with one measured configuration per generation and three repetitions per configuration. The first generation includes the original baseline. All competitors in a search receive the same repetition seeds and workload. The candidate budget counts every distinct proposal, including screened candidates. Proposals are filtered against configured CPU and memory limits. Failed attempts consume the real-test budget. Generations stop when the proposal, attempt, time or generation budget is exhausted.

Random search samples unseen configurations with a seeded RNG. Hill climbing proposes one-control neighbors of the best measured incumbent, with unseen random proposals when the neighborhood is exhausted. NSGA-II uses constrained nondominated sorting, crowding distance, binary tournaments, uniform crossover and one-control mutation. Environmental selection retains parents and measured offspring. A bounded retry loop and unseen random fill prevent duplicate proposals from stalling the search.

Promotion includes the baseline and alternates estimated-latency and genome-diversity slots when multiple slots are available. Estimates carry their calibration status. With a single promotion slot, the baseline takes precedence and subsequent generations use the estimate ordering. The limited simulator evidence can bias that ordering, so the no-simulator comparison is retained. Random search promotion follows its random proposal order.

## Ranking

Only complete measured candidates whose every repetition passed the fault gate are eligible for the Pareto front. Objectives minimize median p95 milliseconds, application CPU seconds and confirmed recovery seconds. Censored or absent recovery excludes a candidate from this three-objective front. Failed candidates remain available for lineage and rejection inspection. Their gate-failure counts guide constrained parent selection when feasible parents are unavailable.

Same-seed proposals reproduce when supplied the same measured feedback. Host timings can change parent selection in a fresh live rerun. Saved records contain proposals, parent hashes, generation numbers, selected candidates, child experiment IDs and search overhead. Search overhead currently measures proposal generation and simulation screening, excluding deployment and request execution.

## API

- `POST /api/searches` starts a bounded search.
- `GET /api/searches` and `GET /api/searches/{id}` return saved results.
- `GET /api/searches/{id}/events` supports replay by sequence.
- `POST /api/searches/{id}/cancel` requests cancellation and waits for owned child cleanup through the coordinator.
- `POST /api/searches/{id}/rerun` creates a fresh same-input search.

Example request:

```json
{
  "algorithm": "nsga2",
  "seed": 72,
  "generations": 2,
  "population_size": 4,
  "promotions_per_generation": 1,
  "budget": {"real_test_budget": 6, "max_candidates": 8, "wall_clock_s": 1800},
  "fault_scenarios": ["service_outage", "timeout_retry_duplicate"]
}
```

The service permits one active search. The shared experiment worker serializes its child deployments with any manually queued experiments. Wall-clock limits include queue waiting. Cancelling a child experiment stops its search after cleanup. An interrupted coordinator records failure and retains its evidence. The four completed comparisons reproduced their exact proposal order and parent hashes when replayed against their stored feedback.

Reference for nondominated sorting, elitist selection and crowding distance: [Deb et al., NSGA-II](https://homes.cs.washington.edu/~sagarwal/nsga2j.pdf).
