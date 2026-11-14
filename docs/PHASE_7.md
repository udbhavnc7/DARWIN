# Phase 7 — Simulator calibration

The SimPy model uses the same seeded arrival schedule and three-second catalog warm-up as the native benchmark. It models finite API and database slots, a shared cache for catalog descriptions, and synchronous or queued notifications. Catalog availability still uses the database when descriptions are cached. Simulation throughput counts completions within the requested window. Latency percentiles include requests that finish during drain.

In the dashboard, select a workload and click **Simulate performance** under **Explore a configuration**. The dashboard requests a 12-second estimate. The API accepts the same request directly.

```powershell
$body = @{ genome = @{}; workload_profile='normal'; seed=42; duration_s=12 } | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8000/api/simulate -Method Post -ContentType application/json -Body $body
```

## Reproduce the fit

```powershell
.\.venv\Scripts\python.exe -m darwin.calibration 89211ce3-ab94-4773-a4d5-a5a12a85a096 510a0c03-b173-409f-a6da-a184ae37dfd2 --holdout-run fd92f01e-dc7e-4515-bf78-fa1c85bc51fe
```

The command verifies the raw sample hashes against the comparison records and checks their arrival schedules. It recomputes measured p95 from those samples. It fits a single shared service-time multiplier by minimizing mean absolute log p95 error across six successful normal and flash-sale repetitions at seeds 42 and 43. It holds out seed 44 from both experiments and all six checkout-heavy repetitions. The checkout-heavy holdout covers an unseen workload and includes the repetition that returned HTTP failures.

The report at `artifacts/experiments/simulation-calibration.json` records the source hashes, evaluation IDs, sample hashes, measured and predicted values, and per-repetition errors. Use `--root` if the API uses a custom experiment directory.

| Holdout | Repetitions | Fitted p95 mean absolute percentage error |
| --- | ---: | ---: |
| Previously seen workload and configuration | 3 | 22.1% |
| Checkout-heavy, unseen workload | 6 | 29.5% |
| All holdouts | 9 | 27.0% |

The fitted multiplier was 2.05. Across all nine holdouts, mean absolute p95 error was 270.1 ms, and mean absolute percentage error fell from 53.7% before fitting to 27.0% after fitting. The cached normal run still missed by 53.9%. In the checkout-heavy run with 18.75% measured HTTP errors, measured p95 was 2,093 ms and predicted p95 was 515 ms. The fit describes aggregate latency and does not identify separate service or database timings.

## Scope and promotion

The API applies the fit only to a workload and configuration present in the fit data, with a 12-second window and no added database delay. It labels these estimates `fitted_limited_evidence` and includes the observed held-out errors for that workload and configuration. Other requests use the uncalibrated model. The available sample is too small for prediction intervals, so the interval remains null. Retry effects, request failures, CPU and memory, and recovery time remain outside the model. The API returns `tier: simulated` and `gate: not_checked` for every estimate.

For the current evidence, all estimates remain uncertain for promotion. The measured budget should cover the baseline when included and use remaining full repetition groups for different configurations, prioritizing differences in genome controls. Use a stable genome order to break ties. Reserve a measured slot for a configuration outside the fitted scope when the budget and candidate pool allow. A predicted p95 alone cannot eliminate a candidate. Phase 8 can use latency to prioritize part of the measured budget once independent repetitions establish a predeclared error threshold for the workload, while retaining slots for uncertain and diverse candidates. Final ranking and correctness depend on measured evidence.

The TypeScript production build, 13 existing foundation and performance tests, and API checks for deterministic responses, calibration scope, and invalid input passed.
