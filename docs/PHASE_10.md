# Phase 10 — Validation and demonstration

Run the API and UI using README, install the locked dependencies and Toxiproxy, and put PostgreSQL and Redis binaries on PATH. Native experiments create private database clusters and own their service processes. Each repetition starts with fresh data. The separate interactive demo shop uses `scripts/run_shop.py`.

## Equal-budget comparison

```powershell
.\.venv\Scripts\python.exe scripts/validate_searches.py --output artifacts/validation/search-comparison-72.json
```

Add `--resume` with the same output path and seed to preserve completed strategies and retry an interrupted one. Interrupted searches and their consumed attempts remain in the report.

The script runs NSGA-II, random search, hill climbing, and NSGA-II with simulation disabled. Each search receives six measured attempts, two generations, one promoted candidate per generation, three repetitions per configuration, and a maximum of eight distinct proposals. Seed 72 supplies repetition seeds 72–74, separate from the simulator's fitting data. The workload is normal traffic. All four searches use application outage, ambiguous payment response, the stock race, concurrent replay and notification acknowledgment crash. The earlier full fault acceptance separately covers database latency and disconnection.

Each search includes the original baseline. Comparisons must report both feasible and rejected outcomes, the consumed attempts, source provenance and measured spread. A small local experiment can produce a negative or inconclusive result. The saved JSON is the authoritative record.

The no-simulator variant changes promotion inputs while retaining budgets and measured gates. The no-correctness-gate ablation is computed retrospectively from the same isolated measured results by ranking completed candidates on latency while preserving their original rejection flags. The unsafe retry fixture provides the explicit duplicate-payment negative control.

### Results

| Strategy | Measured attempts | Feasible configurations | Best feasible median p95 |
| --- | ---: | ---: | ---: |
| NSGA-II with simulation | 6 | 2 | 273.9 ms |
| Random search | 6 | 2 | 351.8 ms |
| Hill climbing | 6 | 1 | 586.8 ms |
| NSGA-II without simulation | 6 | 2 | 410.9 ms |

In the NSGA-II run with simulation, queued notifications reduced median p95 from 315.8 to 273.9 ms against its paired baseline. Median application CPU increased from 6.30 to 7.59 seconds, and median recovery increased from 5.0 to 5.5 seconds. Both configurations are on that run's Pareto front. These results compare one search seed per strategy, with three measured repetitions per configuration. The same baseline's median p95 varied from 315.8 to 745.8 ms across searches, so the observed ordering does not establish a general algorithm advantage.

The hill-climbing baseline was rejected when recovery was censored in one repetition. Its first search attempt was separately interrupted by a 121.09-second dispatch lag and consumed four attempts. The comparison retains that run and uses the completed same-input retry in the equal-budget table. The no-simulator search elapsed time includes queueing behind the unsafe replay and workload holdout. Proposal and screening overhead was below 0.02 seconds in each measured search, at the resolution of the host timer.

The recorded unsafe fixture had 408.4 ms median p95 versus 483.0 ms in the matching safe configuration's full fault run, with identical benchmark workload and seeds. Ranking on benchmark latency alone would place the unsafe fixture first in that pair. The oracle rejected it for duplicate payment effects.

The full suite passed 103 tests, including the PostgreSQL and Redis integrations. The frontend build passed. A separate audit matched saved p95 against 2,016 raw samples, found owned resources absent across 14 runs, and reproduced the four searches' proposal sequences from stored feedback.

## Held-out workload and fresh rejection

The checkout-heavy experiment `8d117f8e-17fb-48fe-ab54-bb96a4088495` compared the original baseline with the queued notification configuration at seeds 101–103. All six runs had zero measured errors. The baseline median p95 was 520.1 ms (515.8–524.3), and queued notifications measured 426.8 ms (417.9–1,150.3). Median CPU time rose from 11.09 to 12.55 seconds. The median latency improvement carried over to this workload, with substantially more variation. This run measured performance only.

The dashboard rerun `749a7055-aedc-4ec7-8856-02303424aae3` reproduced I-01 in all three repetitions after the app restarted. Each trace captured three payment effects for one key. The dashboard displayed the rejection and downloaded the matching report.

## Reproducible evidence bundle

```powershell
.\.venv\Scripts\python.exe scripts/export_evidence.py EXPERIMENT_ID ANOTHER_EXPERIMENT_ID --output artifacts/demo/darwin-evidence.zip
```

The exporter verifies every registered artifact and saved source digest before packaging. The archive includes records, replay requests, source snapshots, a project copy, logs, measurements, fault traces, a checksum index and `recorded-demo.html`. Add `--comparison` with the completed validation report to include all its child experiments, and `--video` with the recorded walkthrough. The updated release bundle is `artifacts/demo/darwin-workspace.zip` and includes the native comparison, live Docker acceptance, and the custom architecture run from the redesigned dashboard. Extract the archive before opening the HTML. The recorded video shows the earlier interface.

For a fresh replay, restore the selected source snapshot into a separate checkout, install its locked dependencies, start that API and submit its saved replay request. The default replay scripts target the currently running API. Actual timings may vary across hosts and runs.

## Exhibition sequence

1. Open the local dashboard and select the completed safe fault run. Show all three passing repetitions and cleanup.
2. Select the unsafe fixture run, expand I-01 and open its fault report. Explain the lost payment response and duplicate effects.
3. Preview a changed configuration and its service graph.
4. Simulate it and show the calibration label and observed error.
5. Open a completed search, show its lineage, measured gates and tradeoff plot.
6. Use the recorded HTML and demonstration video if a live service is unavailable.

Budget five minutes for presenting saved results. A browser rehearsal of the unsafe result, completed search and live checkout replay took 44.7 seconds. The replay returned the same order and left one order, capture, payment effect, outbox job and delivery in the ledger. The captioned backup video runs for 40 seconds. A fresh full search is a separate operation whose measured duration is recorded in its start and finish timestamps.

## Later re-verification (2026-11-14)

The original records above are retained as written. On 2026-11-14 the same workspace was re-checked after the exhibition hardening and UI work:

- A three-seed campaign (72, 101, 202; normal workload; four strategies, equal budget) completed 11 of 12 searches with 68 measured attempts in about 1.3 hours. NSGA-II with simulation had the lowest median-of-best p95 at 357.2 ms, then hill climbing at 394.6 ms, random search at 407.6 ms, and NSGA-II without simulation at 445.1 ms. Three simulator-assisted searches produced no fully feasible candidate. The remaining arm (seed 202, NSGA-II without simulation) was interrupted twice by a connection timeout during a fault measurement and is retained in the report as interrupted.
- The default backend suite passed 108 tests with 14 integration tests skipped; with the dedicated PostgreSQL test database the suite passed 122. The dashboard production build passed.
- CI exposed a duplicate-request race that local runs rarely hit: concurrent identical inserts could violate a secondary unique key and return a transient 503. Duplicate-safe inserts now use a targetless `ON CONFLICT`, and checkout retries lock contention within its request budget. The concurrent checkout test passed ten consecutive runs on PostgreSQL 18.
- The workspace was re-skinned as a backend-architecture bench. The palette register now offers Green Texture, Leather Red, and Carbon Black. Evidence states, gates, and promotion rules are unchanged.
- A stale sandbox from an interrupted Docker run blocked new measurements with `cleanup_status=requires_review`. Its Compose project and image were removed, `darwin.recovery` verified the resources absent, and the API resumed. The experiment record was preserved.

## Environment limits

The measured results in this report use the native Windows adapter with resource jobs and private PostgreSQL clusters. The Docker adapter supports the same workload and fault suite and records measurements from Linux container cgroups. See the [Docker acceptance results](DOCKER_ACCEPTANCE.md).
