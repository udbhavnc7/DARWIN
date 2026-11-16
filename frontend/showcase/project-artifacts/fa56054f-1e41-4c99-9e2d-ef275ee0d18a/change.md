# DARWIN architecture change

- Source: https://github.com/dockersamples/nginx-node-redis at `2cd75d3b61385ab4cd490af9d0facc5d8595bca7`
- Adapter: `node-redis-compose-v1` `1.0.0`
- Verdict: **BASELINE_RETAINED** — Baseline retained
- Evidence: live isolated Linux Docker runs, mode `quick`, challenge `faster`
- Evaluation: `fa56054f-1e41-4c99-9e2d-ef275ee0d18a`

## Measured comparison

| Candidate | Replicas | Workers | p95 ms | req/s | CPU s | Peak MB | Recovery s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Original: 1 replica | 1 | 1 | 3.780900000492693 | 6.0 | 0.2159 | 39.852 | None |
| Two stateless replicas | 2 | 1 | 3.819000001385575 | 6.0 | 0.3008 | 64.719 | None |

## Decision

No measured candidate beat the original architecture on the selected challenge.

## Apply

- Keep the baseline topology: 1 replica(s) × 1 worker(s).
- No candidate cleared the gates, so no deployment change is proposed.

## Rollback

- Restore 1 replica(s) × 1 worker(s). No data migration is required because both topologies share the same Redis state.

## Limits

- Measured on one host with the load generator and the service sharing CPU. Absolute numbers are lab-only and do not establish production performance.
- Only the reviewed workload path and oracles were exercised. HTTP availability alone is not business correctness; counter monotonicity was the oracle here.
- Simulation results never authorise a change in this document.
