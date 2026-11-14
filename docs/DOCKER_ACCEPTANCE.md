# Docker experiments

DARWIN supports Docker smoke checks, measured benchmarks, fault verification, and measured search. Choose **Docker** under **Execution runtime** in the dashboard when the API detects a local Linux Docker engine. API requests use `docker_smoke`, `docker_benchmark`, or `docker_faults`. Search requests use `"runtime": "docker"`.

The Docker measurement path requires a local Linux engine, the Docker Compose plugin, and cgroup v2 with CPU quotas, swap limits, and `memory.peak`. On Windows, Docker Desktop must be running in Linux container mode. Images are pulled and the application image is built from the saved experiment source. [Docker runtime metrics](https://docs.docker.com/engine/containers/runmetrics/) · [Docker Compose service settings](https://docs.docker.com/reference/compose-file/services/)

After installing the project dependencies from README, run the acceptance suite on a host with that engine:

```powershell
.\.venv\Scripts\python.exe scripts/validate_docker.py --output artifacts/docker-acceptance
```

On Linux, use `.venv/bin/python` for the same command. The suite creates a new evidence directory and runs smoke, paired performance measurements, the full safe fault suite, the unsafe duplicate-payment fixture, and two search generations. It writes run IDs and the final status to `acceptance.json`. Each run retains its own source and reports. A failure stops the suite and preserves the evidence collected so far. Run the same command with `--resume` to verify completed cases and retry from the failed case. On Windows, DARWIN can also discover Docker Desktop's CLI and credential helper in the default per-user or system-wide installation directory.

## Measurement and cleanup

Each repetition creates its own Compose project and database volume. The gateway, the measurement database connection and the fault control API use temporary host ports bound to loopback. Application and payment traffic use the project network. For fault experiments, Toxiproxy handles application database connections and payment calls, while the controller reads the ledger directly. A project volume holds the notification acknowledgment marker so DARWIN can stop the exact container that reached it. [Compose networking](https://docs.docker.com/compose/how-tos/networking/) · [Toxiproxy](https://github.com/Shopify/toxiproxy)

The load generator checks CPU and memory limits inside each application container and records CPU time before and after the workload. The memory metric sums individual container lifetime peaks and gives an upper bound on their simultaneous peak. The seed process and fault tooling sit outside those measurements. Use results from the same runtime and host for direct comparisons.

Cleanup removes the run's containers, project network, volumes, and application image tag. It checks for remaining resources on the same engine. If cleanup needs review, inspect the run's `compose.yaml`, `ownership.json`, and logs. After removing the run's owned resources, use the existing recovery command to verify their absence before resuming the queue.

## Verification status

The official Compose 2.40.3 validator accepted all 108 smoke, benchmark, and fault configurations across the 36 supported genomes. All 108 Python tests passed, including the PostgreSQL and Redis integrations and the Docker Desktop credential-helper regression. The frontend build passed. The native regression run `a5f70ae4-a29e-44c5-9be7-5b6b9c2ad9d9` rejected the duplicate-payment fixture in all three repetitions and completed cleanup.

Live acceptance passed all 21 repetitions on Windows with Docker Desktop Engine 29.9.3, Compose 5.7.0, Linux containers, and cgroup v2. The smoke run completed all three repetitions. The paired benchmark completed all six with zero measured request errors and verified resource limits.

| Configuration | Median p95 | Median CPU time | Median sum of container memory peaks |
| --- | ---: | ---: | ---: |
| Baseline | 107.5 ms | 2.74 s | 333.24 MiB |
| Three replicas, 10-second cache, queued notifications | 89.6 ms | 4.18 s | 533.81 MiB |

All three safe fault repetitions passed every feasibility gate. The longest observed recovery per repetition ranged from 5.33 to 7.98 seconds. All three unsafe repetitions were rejected for I-01, with three payment effects recorded for one key in each repetition.

The NSGA-II search completed two generations and six measured attempts in about 13 minutes. Both promoted configurations had one repetition in which recovery was not observed within the 15-second window. The baseline missed application-outage recovery and the queued configuration missed database-latency recovery. The measured Pareto front was empty. Acceptance checks that the search completes and preserves measured rejections.

A separate smoke experiment started from the dashboard (`f5285707-a3b0-42cb-948b-9ce17a7c35b0`) completed all three repetitions with Docker Desktop discovered from its install directory. This run verified image builds, credential-helper discovery and cleanup using the updated API.

All run-owned containers, volumes, networks, and application image tags were removed. Case IDs and status are recorded in `artifacts/docker-acceptance-live/acceptance.json`. The release bundle in `artifacts/demo/darwin-workspace.zip` includes the Docker runs and the native comparison.
