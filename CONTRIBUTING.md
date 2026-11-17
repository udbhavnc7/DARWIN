# Contributing to DARWIN

Thanks for taking an interest. DARWIN is an evidence machine: a change is only
as good as the run that demonstrates it. This guide covers setup, verification,
and the conventions the repository already follows.

## Ground rules

- **Keep results honest.** Never invent a metric, a duration, or a pass. If a
  measurement is simulated, recorded, skipped, or unavailable, say so in the
  code, the UI, and the docs.
- **Correctness before speed.** A faster configuration that breaks an invariant
  must still be rejected. Do not relax a gate to make a candidate rank.
- **Keep the scope boundary.** DARWIN measures one checkout backend. Cloud and
  Kubernetes adapters and optional LLM explanations are explicitly out of MVP
  scope.
- **Evidence is local.** Do not commit run artifacts, database dumps, tokens, or
  machine-specific paths. `artifacts/` and `.runtime/` are local scratch space.
- Be decent to other contributors. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| Python | 3.11+ | Backend, worker, tests |
| Node.js | 20+ | Dashboard build |
| Docker Desktop / Engine | recent, Linux containers | Measured Docker runs and acceptance |
| PostgreSQL client tools | 15+ | Shop integration tests (or Docker) |
| Redis | 7+ | Real-cache tests (or Docker) |

Native measured runs additionally use the Windows-only adapter; on Linux use
the Docker path. The dashboard and unit tests work without Docker.

## Setup

PowerShell (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e .
npm --prefix frontend ci
```

POSIX shells use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.

## Verify before opening a pull request

```powershell
# Fast unit suite: no PostgreSQL or Redis needed
.\.venv\Scripts\python.exe -m pytest -q -m "not integration"

# Full suite: the shop tests reuse the demo cluster or start disposable
# PostgreSQL/Redis containers, then clean up after themselves
.\.venv\Scripts\python.exe -m pytest -q

# Type-check and production build
npm --prefix frontend run build
```

Both suites must pass. The full suite is the one CI runs on Linux with
PostgreSQL and Redis services; a second CI job runs the suite natively on
Windows. Docker acceptance remains a manual workflow:

```powershell
.\.venv\Scripts\python.exe scripts/validate_docker.py --output artifacts/docker-acceptance
```

## Where things live

| Path | Responsibility |
| --- | --- |
| `backend/darwin/contracts.py` | Genome, experiment, candidate, metrics, and violation contracts |
| `backend/darwin/experiments.py` | Lifecycle, worker, budgets, persistence |
| `backend/darwin/fault_suite.py` | Fault schedules, recovery, invariant orchestration |
| `backend/darwin/invariants.py` | I-01 through I-05 against recorded business state |
| `backend/darwin/search.py` | NSGA-II, random, hill climbing, fronts |
| `backend/darwin/simulator.py` | SimPy screening model |
| `backend/darwin/shop/` | The checkout shop under test |
| `frontend/src/` | React dashboard |
| `tests/` | Unit and integration suites (`tests/conftest.py` provisions integration resources) |
| `docs/` | Architecture, contracts, phase records, runbooks |
| `scripts/` | Launchers, acceptance suites, validators |

## Change checklist

- Add or update a test for behavior changes. Unit tests go next to the existing
  suites; anything needing PostgreSQL or Redis belongs under the `integration`
  marker.
- Update `README.md` and `CONTEXT.md` when a claimed result, count, or gap
  changes. `CONTEXT.md` is the current-state document; `docs/PHASE_*.md` are
  historical records and keep their original numbers.
- Keep user-facing claims tied to something reproducible: a command, a stored
  run, or a linked report.
- Run the full suite and the frontend build before pushing.

## Commits and pull requests

- Branch from `master`. Keep one focused change per branch.
- Write imperative, scoped commit subjects, for example
  `fix: keep replayed checkouts from capturing twice` or
  `docs: explain the Docker acceptance budget`.
- In the pull request, state what changed, how it was verified (commands and
  observed results), and any remaining limitation.
- CI must be green, including the Windows native job. A skipped test is
  acceptable only when the reason is explicit, for example a missing Docker
  engine.

## Reporting problems

Open a GitHub issue with the command you ran, the observed output, the expected
behavior, and your Python/Node/Docker versions. For security concerns, avoid
posting tokens, database URLs, or full evidence bundles.
