# Phase 5 — Repeatable performance measurements

The Windows benchmark compares shop configurations on this machine using real HTTP traffic through the gateway. Each repetition gets its own PostgreSQL cluster, application processes, optional Redis instance and worker, database stock, and request schedule. The shared demo shop can stay online.

## Reproduce a comparison

Install the locked Python dependencies and put PostgreSQL's `initdb`, `pg_ctl` and `postgres` on PATH. Cached configurations also require `redis-server`. Start the API and frontend as described in the README. Choose a workload in **Prepare an experiment**, then select **Compare performance** and **Start performance comparison**. The dashboard compares the baseline to three API replicas, a 10-second catalog cache and queued notifications. Expand a repetition to download its request samples, resource counters or manifest.

From PowerShell, use the same API to select profiles, genomes and thresholds:

```powershell
$body = @{
    mode = 'native_benchmark'
    workload_profile = 'normal'
    seed = 42
    genomes = @(@{}, @{app_replicas=3; catalog_cache_ttl_s=10; notification_mode='queued'})
    constraints = @{max_error_rate=0.01; max_p95_ms=750}
} | ConvertTo-Json -Depth 5
$run = Invoke-RestMethod http://127.0.0.1:8000/api/experiments -Method Post -ContentType application/json -Body $body
Invoke-RestMethod "http://127.0.0.1:8000/api/experiments/$($run.experiment_id)"
```

A complete experiment stores `comparison.json` in its experiment directory. The status API includes the same candidate summaries. Each repetition has its own manifest, measurements, exact schedule, raw samples, separate warm-up samples, service logs and resource observations. The experiment also saves the code snapshot and dependency lock. Rerun a single candidate through the Phase 4 rerun endpoint.

## Measurement protocol

- The benchmark uses a fresh private cluster and seeds 1,000 units of each product before warm-up. All requests target the isolated gateway. Each measured operation makes one client HTTP attempt and each checkout gets its own idempotency key. Shop-internal retries follow the candidate's configured policy.
- Each repetition warms the catalog for three seconds at two requests per second, then offers a seeded sequence for twelve seconds. Normal traffic offers four requests per second with a 25% checkout probability. Checkout-heavy traffic uses the same rate with a 75% checkout probability. Flash-sale traffic offers four requests per second in the first and last four seconds and twelve per second in the middle four, with a 50% checkout probability throughout. The other operations read the catalog.
- Arrival times are independent of previous responses. The seed controls operation and SKU selection. Each repetition increments the seed and every candidate receives the same schedule for that seed. Candidate order rotates by repetition and only one sandbox runs at a time. Warm-up, startup and teardown latency are excluded.
- Latency runs from actual request start through response validation, including failed operations. Nearest-rank p95 is sample number `ceil(0.95 × n)` in the sorted raw latencies. Throughput counts completed operations within the fixed window per second. Latency and error rate include every offered operation, including those finishing during drain. Errors include HTTP failures and invalid success payloads. The generator records dispatch lag and fails the measurement when lag exceeds 0.5 seconds or drain exceeds eight seconds.
- Each run uses the same Windows job budget, by default four logical CPUs and 4,096 MiB of committed memory shared by PostgreSQL and all shop services. CPU affinity enforces the selected processors. Commit limits apply to the entire job. The benchmark verifies PostgreSQL membership at startup. Application CPU is the difference in cumulative kernel and user CPU time across the measured window and drain, including exited database workers. Peak memory is the maximum job commit from startup through measurement. The Locust subprocess runs outside the application job and separately reports its own CPU and peak working set. Generator and application memory use different OS counters.
- A candidate summary requires all requested repetitions to complete with cleanup. Report the median and min–max of individual repetition metrics. Each repetition must satisfy the error-rate threshold and the optional p95 ceiling. An exceeded threshold remains visible on a completed measurement. The Phase 6 fault and correctness gate stays `not_checked`. A partial group cannot produce a comparison summary.

These short, low-volume profiles measure local behavior. Docker execution and container performance remain pending. The native benchmark uses aggregate Windows limits. The Compose file in each manifest describes the corresponding topology with per-service container limits.

Implementation references: [Locust library usage](https://docs.locust.io/en/stable/use-as-lib.html) and [Windows job limits and accounting](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

## Verification record

On 2026-11-07, all 86 tests passed with the real PostgreSQL and Redis integration checks enabled. Tests cover paired schedules, rotation of candidate order, nearest-rank percentiles, completion-window throughput, failed repetition thresholds, and the existing smoke runner, cancellation, artifact integrity and event replay behavior. The TypeScript and Vite production build and dependency consistency check passed. One upstream Starlette TestClient deprecation warning remains.

Normal-traffic experiment `89211ce3-ab94-4773-a4d5-a5a12a85a096` completed six repetitions on 2026-11-06. Both candidates used the same schedules at seeds 42, 43 and 44. The table shows median and min–max across three repetitions.

| Metric | Baseline | 3 replicas, 10s cache, queued notifications |
| --- | --- | --- |
| p95 milliseconds | 491.57 (472.47–518.84) | 325.94 (320.73–329.83) |
| Completed requests per second | 3.92 (3.92–4.00) | 4.00 (3.92–4.00) |
| Application CPU seconds | 6.95 (5.67–7.38) | 8.80 (7.88–8.97) |
| Peak application commit MiB | 279.28 (276.32–284.95) | 459.86 (459.76–460.45) |
| Errors | 0% | 0% |

The candidate reduced observed latency while consuming more CPU and memory. This comparison applies to the saved short normal-traffic profile on this machine. Independent recomputation matched every stored metric across all 288 samples. Artifact hashes matched, paired schedule files were identical, and maximum measured dispatch lag was 0.020 seconds. The report remained available after the API restarted. Recorded process identities, listening ports and private database directories were absent after cleanup.

Flash-sale experiment `510a0c03-b173-409f-a6da-a184ae37dfd2` completed three baseline repetitions with 240 samples and zero errors. Median p95 was 520.32 ms, ranging from 489.38 to 586.07 ms. Artifact hashes, raw-metric recomputation and cleanup checks passed. Maximum measured dispatch lag was 0.016 seconds.

The interrupted normal run `0ef24443-410e-4575-8b71-b59662649b8b` and checkout-heavy run `83dfd57e-a549-4cff-a757-da43647feecd` exhausted their wall-clock budgets during long host-execution gaps. Both retained failed records and completed cleanup. Resource-absence checks passed on 2026-11-07. These failed groups produce no candidate summary.

Browser-started checkout-heavy comparison `fd92f01e-dc7e-4515-bf78-fa1c85bc51fe` completed all six repetitions. The baseline's median p95 was 648.97 ms (524.59–822.21), with zero errors in each repetition. The candidate's median p95 was 665.09 ms (416.49–2,093.13). At seed 43 the candidate returned nine HTTP 503 responses in 48 operations, an 18.75% error rate. Its summary correctly reports `performance_constraints_met: false` against the default 1% threshold, even though the median error rate across repetitions is zero. This result is retained for the subsequent fault and correctness work.

On 2026-11-08, independent verification reproduced the checkout-heavy metrics from all 288 samples, confirmed identical paired schedules and every artifact hash, and found no recorded processes, listening ports or private cluster directories remaining. Maximum dispatch lag was 0.033 seconds. The dashboard start and validation controls and downloads through the frontend proxy were exercised. The final frontend production build passed. Across the three successful experiments, 15 repetitions retained 816 measured operations.
