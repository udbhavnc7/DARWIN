# DARWIN architecture change

- Source: https://github.com/docker/awesome-compose at `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`
- Adapter: `flask-redis-compose-v1` `1.0.0`
- Verdict: **BASELINE_RETAINED** — Baseline retained
- Evidence: live isolated Linux Docker runs, mode `quick`, challenge `faster`
- Evaluation: `01b40c18-88a6-4beb-8d86-c20236eecc17`

## Measured comparison

| Candidate | Replicas | Workers | p95 ms | req/s | CPU s | Peak MB | Recovery s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Original: 1 replica × 1 worker | 1 | 1 | 3.659900000457128 | 6.0 | 0.1858 | 55.387 | None |
| Two stateless replicas × 1 worker | 2 | 1 | 5.976299999929324 | 6.0 | 0.2448 | 97.273 | None |
| One replica × 2 gunicorn workers | 1 | 2 | 4.4797999998991145 | 6.0 | 0.1921 | 75.715 | None |

## Decision

No measured candidate beat the original architecture on the selected challenge.

## Apply

- Baseline topology: 1 replica(s) × 1 worker(s).
- Recommended topology: 1 replica(s) × 1 worker(s).
- Deploy that many replicas of the same reviewed image behind the gateway and keep the shared Redis service. Do not copy the repository Compose file or Dockerfile; DARWIN generated and tested its own stack.

## Rollback

- Restore 1 replica(s) × 1 worker(s). No data migration is required because both topologies share the same Redis state.

## Limits

- Measured on one host with the load generator and the service sharing CPU. Absolute numbers are lab-only and do not establish production performance.
- Only the reviewed workload path and oracles were exercised. HTTP availability alone is not business correctness; counter monotonicity was the oracle here.
- Simulation results never authorise a change in this document.
