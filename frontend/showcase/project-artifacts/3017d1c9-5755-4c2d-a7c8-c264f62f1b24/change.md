# DARWIN architecture change

- Source: https://github.com/docker/awesome-compose at `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`
- Adapter: `flask-redis-compose-v1` `1.0.0`
- Verdict: **TRADEOFF_REQUIRES_CHOICE** — Tradeoff — choose
- Evidence: live isolated Linux Docker runs, mode `full`, challenge `faster`
- Evaluation: `3017d1c9-5755-4c2d-a7c8-c264f62f1b24`

## Measured comparison

| Candidate | Replicas | Workers | p95 ms | req/s | CPU s | Peak MB | Recovery s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Original: 1 replica × 1 worker | 1 | 1 | 5.3813 | 6.0 | 0.1871 | 53.32 | 0.45 |
| Two stateless replicas × 1 worker | 2 | 1 | 3.7726 | 6.0 | 0.2601 | 97.41 | 0.0 |
| One replica × 2 gunicorn workers | 1 | 2 | 4.8565 | 6.0 | 0.2167 | 76.109 | 0.548 |

## Decision

Two stateless replicas × 1 worker was 29.9% better on p95_ms but regressed on CPU seconds per window +39.0%, peak memory +82.7%. DARWIN will not hide that cost behind a single winner score.

## Apply

- Baseline topology: 1 replica(s) × 1 worker(s).
- Recommended topology: 2 replica(s) × 1 worker(s).
- Deploy that many replicas of the same reviewed image behind the gateway and keep the shared Redis service. Do not copy the repository Compose file or Dockerfile; DARWIN generated and tested its own stack.

## Rollback

- Restore 1 replica(s) × 1 worker(s). No data migration is required because both topologies share the same Redis state.

## Limits

- Measured on one host with the load generator and the service sharing CPU. Absolute numbers are lab-only and do not establish production performance.
- Only the reviewed workload path and oracles were exercised. HTTP availability alone is not business correctness; counter monotonicity was the oracle here.
- Simulation results never authorise a change in this document.
