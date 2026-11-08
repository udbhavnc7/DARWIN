# Contract semantics (schema version 1)

Executable definitions live in `backend/darwin/contracts.py`. Unknown fields are rejected. Times are timezone-aware; serialize UTC. IDs are UUIDs, artifact/genome digests are lowercase SHA-256. Contracts define structure; future workers must enforce execution-time checks.

| Record | Responsibility |
| --- | --- |
| Genome | Four supported controls; cache 0 means off |
| ExperimentRequest | Shop, workload, faults, seed, budgets, constraints |
| Experiment | Request, identifier, lifecycle state, creation time |
| Candidate | Genome/hash, experiment, generation and parents |
| Evaluation | Candidate, repetition, tier, source revision, measurements and gate |
| Metrics | Latency percentiles, rate, errors, CPU time, memory, recovery and sample count |
| Violation | Invariant, candidate, trace artifact and reproduction state |
| Artifact | Evaluation, relative file path, type, digest and timestamp |
| Event | Experiment, increasing sequence, timestamp, type, status and optional related IDs |

## Lifecycle and delivery

Allowed experiment transitions: queued → running → completed/failed/cancelled; queued → cancelled. Terminal runs are immutable. A rerun creates new evaluation IDs. The worker will assign monotonic per-experiment event sequence numbers, persist events before publishing, and support reconnect/replay from the last sequence. Event references must match the event type and refer to entities in the same experiment. Artifact paths must resolve inside the experiment's artifact directory before reads/writes.

## Budgets and comparability

Default: at most 12 unique proposals, 6 real evaluation attempts, 3 repetitions per shortlisted configuration, 900 seconds overall, one sandbox at a time, 4 aggregate sandbox CPU cores, and 4096 MB aggregate sandbox memory. These are starting limits, not benchmark claims. The 6 attempts can cover two configurations with three runs each. Failed attempts consume budget; incomplete repetition groups remain unverified. Every workload/fault schedule is stored and shared across competitors. An evaluation is one configuration under a selected workload and fault schedule; multiple fault scenarios are scheduled within it. Broader scenario matrices need separate evaluations and budgets.

Measure errors as unsuccessful logical workload operations divided by attempted logical operations; also record individual HTTP attempts/retries in raw evidence. Record p95 from raw samples or mergeable histograms. Require every repetition to satisfy invariant, error, optional p95, and resource constraints; aggregate objectives using the median per-run result and report spread. Do not call an average of p95 values a pooled p95. Recovery means the first continuous five-second window after a fault ends in which error rate is within the limit and p95 is within 120% of the pre-fault p95, at the same offered load. If recovery is not observed, record a censored outcome in evidence and exclude the candidate from recovery-objective ranking. Null recovery without a fault is not zero.

Measured feasibility requires successful deployment, complete repetitions, no executed invariant failures, and satisfied constraints. Simulated evaluations cannot have a passing gate. CPU seconds is a local resource proxy; memory is also bounded. Simulated and measured rankings remain separate. The coordinator, rather than the data model alone, establishes whether evidence justifies passing a gate.

## Phase 4 interface status

Experiment start/list/status/cancel, event polling/streaming, candidate inspection/rerun, and artifact download are implemented. See PHASE_4.md. Pareto and fault-trace endpoints remain deferred. Smoke evaluation records use `gate: not_checked`. Phase 5 measured evaluations carry the Metrics contract described above.


## Phase 5 measurements

`native_benchmark` accepts each workload profile, the seed, manual genomes and optional latency ceiling. Successful measured evaluations include the Metrics contract, the actual paired repetition seed, and a manifest of the raw schedule, results and resource counters. Candidate summaries report per-run median and range, and require every repetition to meet the configured performance thresholds. Fault verification belongs to Phase 6. For exact denominator, resource scope and percentile definitions see [Phase 5](PHASE_5.md).
