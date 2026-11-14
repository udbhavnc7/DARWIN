# Phase 6 — Fault injection and correctness gates

Phase 6 adds `native_faults` to the Windows runner. Each repetition uses a fresh private PostgreSQL cluster and the Phase 5 Windows job limits. It first measures the selected workload, then executes the selected failures and all five business checks. The dashboard offers **Verify failure recovery** and **Unsafe retry fixture**. A completed experiment can contain rejected candidates: completion means the evidence was collected, while the feasibility gate decides acceptance.

## Setup and execution

Use the Phase 5 prerequisites, then install the pinned official Toxiproxy binary:

```powershell
./scripts/setup_toxiproxy.ps1
```

The installer verifies the downloaded binary against the release's SHA-256 checksums. The runner uses `DARWIN_TOXIPROXY`, an executable on PATH, or `.runtime/tools/toxiproxy-server.exe`. It records the binary version and hash. The proxy binds loopback interfaces and is owned and cleaned up by the experiment runner. Its overhead is outside the application resource budget, like the workload generator.

Start the API/UI as described in README, select **Verify failure recovery**, and start the experiment. The dashboard submits three repetitions with seeds 42–44, one API replica, cache off, queued notifications and idempotent retries. To submit through the API:

```powershell
$body = @{
    mode = 'native_faults'
    genomes = @(@{notification_mode='queued'})
    fault_scenarios = @('db_delay', 'service_outage', 'timeout_retry_duplicate')
    fault_fixture = 'safe'
} | ConvertTo-Json -Depth 5
$run = Invoke-RestMethod http://127.0.0.1:8000/api/experiments -Method Post -ContentType application/json -Body $body
Invoke-RestMethod "http://127.0.0.1:8000/api/experiments/$($run.experiment_id)"
```

For the isolated negative control, use `fault_fixture='unsafe_retry'` and select `timeout_retry_duplicate`. This fixture deliberately adds duplicate synthetic payment effects when an already captured key reaches the provider again. It cannot be imported without the isolated-fault-test environment flag, is not a supported genome, and is never used by the ordinary shop deployment.

## Failure protocol and recovery

Every application database connection traverses Toxiproxy. The checker uses a separate direct connection to observe committed state even during network faults.

| Scenario | Mechanism and evidence |
| --- | --- |
| Database latency | Toxiproxy adds 100 ms downstream latency, without jitter |
| Database disconnection | Disable and then re-enable the database proxy |
| Application outage | Suspend all API processes and their descendants, then resume them |
| Ambiguous payment response | A downstream timeout hides a committed payment response; verify the effect exists before removing the fault, then retry the same key |
| Concurrent replay | Replay one completed order four times concurrently; compare responses and complete business snapshots |
| Stock contention | Four distinct orders compete for two units; require exactly two confirmations and two out-of-stock failures |
| Notification acknowledgment crash | Pause after receiver delivery commits but before outbox acknowledgment, kill the actual worker, restart it, and verify retained job identity and eventual completion |

The last three checks always run, including when only a subset of network scenarios is selected. With synchronous notifications the acknowledgment crash kills and restarts the API process instead of a worker. The isolated pause hook applies only to the test's unique notification key; the normal shop never enables it.

Each latency, disconnection and application-outage scenario offers two catalog requests per second for a five-second baseline, two-second fault, and fifteen-second recovery observation. The baseline must succeed and dispatch lag must stay within 0.5 seconds. The injected fault must visibly cause a failed response or latency above 120% of baseline p95. Recovery is confirmed after the first continuous five-second window whose error rate is within the configured threshold and whose nearest-rank p95 is at most 120% of baseline. The recorded duration includes observing that entire window, so it is at least approximately five seconds. Unobserved recovery is null and censored, never zero.

## Invariants and acceptance

| ID | Executed check |
| --- | --- |
| I-01 | At most one committed payment effect per payment key |
| I-02 | Nonnegative stock, reservations and confirmed quantities reconcile without overselling |
| I-03 | Every confirmed order has matching successful payment and effect evidence |
| I-04 | Unique business keys and identical replay responses with unchanged business state |
| I-05 | Confirmed orders retain notification jobs; completion has matching delivery evidence; the accepted job survives the acknowledgment crash |

The payment-effect table intentionally permits duplicate keys, allowing the checker to observe a broken provider even when its response ledger is unique. Safe payment effects and their capture ledger entry commit in one transaction.

A passing gate requires verified resource enforcement, all five checks covered, actual selected faults observed, no invariant violations, measured workload error and optional latency thresholds satisfied, fault business operations recovered, observed recovery where applicable, and successful cleanup. Every requested repetition must pass. Cleanup failure overrides an earlier passing report. Performance improvements cannot override any failed gate.

Error denominators are explicit: the Phase 5 workload measures every offered operation, while fault business operations count their final bounded logical outcomes. Expected out-of-stock responses are successful outcomes only in the stock-contention check. Individual failed HTTP attempts remain in the trace. The recovery probes separately measure fault-period failures and post-fault recovery; intentionally injected failures are not silently added to or removed from the ordinary workload denominator. CPU time and peak-commit metrics cover the Phase 5 measurement interval described in that guide; the Windows resource cap remains active through the entire fault suite.

## Evidence and replay

Each evaluation retains `fault-schedule.json`, `fault-trace.jsonl`, `business-state.json`, `fault-report.json`, proxy metadata/logs, benchmark samples, resource evidence and the artifact manifest. Trace events include before/after snapshots, actual HTTP attempts, process-crash identity, observed faults, recovery windows and the gate decision. The final fault report and evaluation include authoritative cleanup status. The dashboard exposes invariant details and artifact downloads through the existing hash-verified artifact API.

Run the evaluation's `replay.ps1` while the local API is available to submit its saved `replay-request.json`. This repeats that candidate's original seed group using the currently running source. A source snapshot and dependency lock are preserved separately; replay does not automatically restore that source or promise identical wall-clock timings.

These are bounded local synthetic tests, not a proof of correctness for all failures. The safe acceptance configuration uses one uncached API and queued notifications. Other genomes, synchronous-crash behavior and higher loads require their own acceptance runs. Docker fault execution remains pending; `native_faults` is Windows-only. Application outage is suspension/resumption, while the notification scenario performs a real process kill and restart.

Implementation reference: [official Toxiproxy API and toxic definitions](https://github.com/Shopify/toxiproxy).

## Verification record

The safe configuration passed all three repetitions in `6fd81054-f3db-4014-b50d-8034d97e634d` with no invariant violations. All nine recovery measurements were observed, ranging from 5.00 to 13.47 seconds. The unsafe fixture `af2368bf-103d-4479-8e9c-4e29257574fe` was rejected in all three repetitions for I-01. The oracle found three payment effects for one payment key each time. Both runs completed cleanup. An independent check matched all 174 registered artifact hashes and found the recorded processes, ports and private database directories absent.

An earlier safe group, `d2a193bf-998c-47f1-bf2d-06dcc1235cde`, was rejected when recovery was censored at seed 43. The passing group repeated the same thresholds and scenarios. The earlier result remains visible as evidence of variation in local recovery. The cancelled experiment `8e59611f-cb63-4fe4-bb0c-dfaacc69a3a7` also remains in history. Docker fault execution remains unverified.
