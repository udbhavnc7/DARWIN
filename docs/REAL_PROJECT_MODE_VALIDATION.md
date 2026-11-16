# DARWIN Real Project Mode - Validation & Evidence Report

**Document status:** Empirical validation report from real benchmark execution and manual UI checks on local hardware.
**Date:** 16 November 2026
**Reference Directive:** `DARWIN_OPENCODE_REAL_PROJECT_MODE (1).md`  
**Base Repository:** `https://github.com/udbhavnc7/DARWIN` (`feat/real-project-evaluation`)

---

## 1. Execution Environment & Provenance

| Parameter | Value |
|---|---|
| **Host OS** | Windows 11 Home (win32, x64) |
| **CPU Model** | 13th Gen Intel(R) Core(TM) i5-13450HX (16 vCPUs) |
| **System Memory** | 24 GB (25,463,480,320 bytes) |
| **Python Runtime** | Python 3.11.15 (with FastAPI 0.115+, pytest 9.2.0) |
| **Node.js Runtime** | Node v26.13.1 (native TypeScript execution support) |
| **Target Repository** | `https://github.com/udbhavnc7/Sanchay.git` |
| **Pinned Target Commit** | `7e1bc4cdd31e53380e7896b4a20a864bbebcee1e` |
| **Adapter ID & Version** | `sanchay-reporting-v1` (v1.0.0) |
| **Evaluation Scope** | Client-side financial report processing (three independent aggregations vs single-pass bundle) |

Sanchay was accessed read-only at the pinned commit. DARWIN did not modify, commit, push, install packages into, or otherwise mutate the Sanchay checkout.

---

## 2. Empirical Benchmark Results

Two full evaluations are retained as evidence. Both passed every correctness gate and returned `VERIFIED_IMPROVEMENT`. They differ in how the source checkout was supplied, which affects whether Sanchay's own test runtime was available.

### 2.1 Recorded exhibition run (`141c9b56-fd17-4052-881f-1708a451768b`)

- **Source:** local pinned Sanchay checkout at `7e1bc4cd`, clean working tree, with installed `node_modules` including Vitest 5.0.5.
- **Workload:** 3 deterministic seeds (`7`, `21`, `2026`), 3 ledger sizes (`1,000`, `10,000`, `50,000` rows), 10 paired repetitions after 2 warm-ups, plus 7 edge fixtures.
- **Samples:** 30 paired samples per measured size (3 seeds x 10 repetitions).
- **Wall-clock duration:** 6.776 s.
- **Source tests:** Vitest `src/utils/reporting.test.ts` passed **29/29** in 472 ms.
- **Verdict:** `VERIFIED_IMPROVEMENT`; 68/68 correctness checks passed.

#### Latency by ledger size

| Ledger Size | Baseline Median | Candidate Median | Delta | Paired Win Rate | Paired Lower Decile | Samples |
|---|---|---|---|---|---|---|
| **1,000 rows** | 0.1313 ms | 0.1178 ms | **10.28% faster** | 90% | -4.66% | 30 |
| **10,000 rows** | 1.3464 ms | 1.1898 ms | **11.63% faster** | 100% | +6.99% | 30 |
| **50,000 rows** | 8.7572 ms | 6.2625 ms | **28.49% faster** | 100% | +15.44% | 30 |

The largest ledger is the primary size under policy: **28.5% faster at 50,000 rows** with a **100% paired win rate**. No measured size regressed.

### 2.2 Live full run from the fetched cache (`e3057b59-3486-49aa-8a42-1043f6d234ff`)

- **Source:** the catalogued Sanchay repository fetched read-only at the same pinned commit into DARWIN's repository cache.
- **Workload:** same full preset and deterministic fixtures.
- **Wall-clock duration:** 6.771 s.
- **Source tests:** **skipped** with the recorded reason: *"The pinned checkout has no installed Vitest runtime; DARWIN did not install packages."*
- **Verdict:** `VERIFIED_IMPROVEMENT`; 68/68 correctness checks passed.

#### Latency by ledger size

| Ledger Size | Baseline Median | Candidate Median | Delta | Paired Win Rate | Samples |
|---|---|---|---|---|---|
| **1,000 rows** | 0.13 ms | 0.12 ms | **10.46% faster** | 87% | 30 |
| **10,000 rows** | 1.35 ms | 1.20 ms | **10.89% faster** | 80% | 30 |
| **50,000 rows** | 8.255 ms | 6.405 ms | **22.41% faster** | 97% | 30 |

The live run is still a defensible verdict because correctness is proved by the 68-check parity harness. It is deliberately **not** presented as having run Sanchay's unit tests. The verdict UI exposes the skip reason next to the source-test chip.

### 2.3 Quick runs

Quick mode uses seed `7`, sizes `10,000` and `50,000`, and 10 repetitions. It does not run the source-test overlay. The recorded showcase contains two quick runs with 59.4% and 59.8% improvements at 50,000 rows; both are labelled as quick, with source tests marked `not_run`, and neither substitutes for the full run.

---

## 3. Correctness & Parity Oracles

Correctness gates strictly override throughput and latency. All 68 checks passed in both full runs.

### Check composition

1. **Wiring checks (3/3):**
   - The candidate is called from the real `ReportsTab.tsx` call site.
   - `ReportsTab.tsx` no longer calls the three original aggregation traversals.
   - `web/src/utils/reporting.ts` re-exports the candidate entry point used by that call site.
2. **Timed-fixture parity (36/36 across 9 fixtures):**
   - Baseline and candidate produce identical report values.
   - The candidate is deterministic.
   - The ledger input is not mutated.
   - Every measured repetition returns the same result.
3. **Edge fixtures (29/29 across 7 fixtures):**
   - Empty ledger returns zeroes without throwing.
   - Single expense sets a 100% category share correctly.
   - Linked refunds reduce spending without double-counting.
   - Transfers and goal contributions stay outside operational spending.
   - Pending and failed transactions are ignored by both implementations.
   - JPY zero-decimal precision is preserved.
   - Currency scoping selects the expected rows before computation (one extra scoping assertion).

The candidate overlay is isolated: the original checkout is copied into a temporary harness, the candidate modules and the `ReportsTab.tsx` call-site patch are applied only there, and the repository itself remains untouched.

---

## 4. Policy Verdict & Reasoning

Policy thresholds:

| Rule | Value |
|---|---|
| Minimum improvement at the primary size | 5.0% |
| Maximum allowed regression at any measured size | 5.0% |
| Minimum paired win rate at the primary size | 80% |
| Primary size | Largest measured ledger |
| Correctness | Must pass every check before performance is considered |

Recorded full-run reason:

> *"All 68 correctness checks passed. The candidate was 28.5% faster at 50,000 rows with a 100% paired win rate, and no measured size regressed by 5% or more."*

Live full-run reason:

> *"All 68 correctness checks passed. The candidate was 22.4% faster at 50,000 rows with a 97% paired win rate, and no measured size regressed by 5% or more."*

A faster but incorrect candidate is rejected with `REJECTED_INCORRECT`; a candidate that fails the performance gates retains the baseline; insufficient evidence yields `INCONCLUSIVE` or `NOT_MEASURED`; an interrupted run yields `INTERRUPTED`. No winner is manufactured when evidence is missing.

---

## 5. Evidence Artifact Bundle

Registered artifacts for the recorded run `141c9b56-fd17-4052-881f-1708a451768b`:

| Artifact | Size | SHA-256 Digest (prefix) | Description |
|---|---|---|---|
| `benchmark.json` | 22,780 B | `2420704e948d...` | Raw timing samples, per-fixture medians, ranges, p95 |
| `candidate.diff` | 5,775 B | `1154eb338246...` | Unified diff of `reportBundle.ts`, `reporting.ts`, and `ReportsTab.tsx` |
| `environment.json` | 5,173 B | `973f28098698...` | Host CPU, OS, Node version, memory, harness commands |
| `parity.json` | 9,786 B | `382fca98054e...` | Individual outcomes for all 68 checks |
| `replay.md` | 6,488 B | `f7c41ce136b4...` | Self-contained instructions to re-execute the evaluation |
| `source-tests.json` | 805 B | `b243f3e86ef7...` | Vitest log, suite name, exit code, 29/29 pass counts |
| `source.json` | 561 B | `e08caa0beb8a...` | Commit SHA, repository URL, provenance metadata |
| `verdict.json` | 3,116 B | `c6dd05dd2504...` | Policy evaluation, thresholds, per-size table, verdict |
| `workload.json` | 4,632 B | `22dc7e610347...` | Seeds, fixture sizes, transaction counts, generation config |
| `manifest.json` | 1,193 B | `35e25e6d0294...` | Checksum manifest for the registered files (digest computed separately) |
| **Evidence archive** | 14,420 B | `62df5969dd5e...` | Digest-verified bundle served by `/api/project-evaluations/{id}/bundle` |

The digest-verified bundle is also stored as `darwin-project-evidence-141c9b56-fd17-4052-881f-1708a451768b.zip` inside the evidence directory.

---

## 6. Truthful Architecture & Honest Scope

1. **Local app data pipeline, not a server backend:**
   - Sanchay is a client-side React 19 + TypeScript application running in an Android WebView with browser-local `localStorage` persistence.
   - It is **not** a cloud backend with microservices, Redis caches, or database replicas.
   - The measured optimization covers pure in-memory report aggregation across transaction arrays. Currency filtering and React rendering are outside the timed region.
2. **Safe source handling:**
   - Sanchay was inspected and executed only at commit `7e1bc4cdd31e53380e7896b4a20a864bbebcee1e`.
   - The candidate exists solely as an isolated overlay and a patch artifact. No commits, branches, or remote changes were made to Sanchay.
3. **Execution guardrails:**
   - Arbitrary GitHub repositories are inspection-only.
   - Only the catalogued adapter at its pinned commit is executable.
   - Unsupported repositories display `UNSUPPORTED_PROJECT` and no run control; the unrelated checkout lab is never substituted.
4. **Recorded vs live labels:**
   - The hosted showcase displays a `RECORDED BENCH` status and a banner saying the evidence is recorded, not live.
   - A live local evaluation is labelled `Live measurement`; a saved showcase evaluation is labelled `Recorded evidence`.
   - Recorded artifacts open in an inline viewer. Bundle downloads are disabled when no live bench is connected.

---

## 7. Manual UI Validation (16 November 2026)

| Scenario | Result |
|---|---|
| **Live full run** | `e3057b59` completed with `VERIFIED_IMPROVEMENT`, 68/68 checks, 22.4% faster at 50,000 rows, 97% paired wins. Source tests showed `skipped` plus the visible reason that the cached checkout has no Vitest runtime. |
| **Recorded showcase** | `http://127.0.0.1:4173/DARWIN/` showed `RECORDED BENCH`, the recorded-evidence banner, 4 saved evaluations, and no live-execution claims. The 22:11 full run showed 68/68 checks and 29/29 source tests. |
| **Recorded artifact viewer** | Clicking `benchmark.json` opened the recorded content inline; all 10 evidence controls resolved, with 0 broken anchors. The evidence bundle download stayed disabled. |
| **Unsupported repository** | `https://github.com/octocat/Hello-World` at ref `master` produced `INSPECTION ONLY` / `UNSUPPORTED_PROJECT`, an actionable warning, and no run button. |
| **Cancellation** | A cancelled run ended as `cancelled` / `INTERRUPTED` with 0 measurements and no `benchmark.json`. |
| **Keyboard-only inspection** | URL -> ref -> Space to consent -> Tab to the enabled submit button -> Enter completed the inspection without a mouse. |
| **360 px layout** | No document-level horizontal overflow on step 1, step 2, or the recorded verdict. The section nav scrolls horizontally by design, and the verdict table scrolls inside its own container. |
| **Stepper gating** | Steps 3 and 4 stay disabled until an evaluation or verdict exists. |

Fixes made during this validation:

- Corrected stepper gating so inspection alone cannot open the run or verdict steps.
- Reworked the recent-evaluation grid so long repository names and verdict chips wrap at 360 px.
- Added `min-width: 0` to verdict columns so the measured-workloads table scrolls internally instead of widening the page.
- Added the inline recorded-artifact viewer and replaced dead recorded anchors.
- Made the verdict evidence chip depend on the view: `Live measurement` for a live bench, `Recorded evidence` for the hosted showcase.
- Added the visible source-test skip reason to provenance.
- Fixed the proof-list status chip class interpolation.

---

## 8. Automated Validation

| Check | Result |
|---|---|
| Backend suite (`.\.venv\Scripts\python.exe -m pytest -q`) | **158 passed, 14 skipped, 1 warning** |
| Frontend production build (`npm --prefix frontend run build`) | Passed, including `tsc --noEmit` |
| Showcase build (`npm --prefix frontend run build:showcase`) | Passed, including `tsc --noEmit` and snapshot copy |

The 14 skipped tests are optional PostgreSQL/Redis integration tests that require those services; they are not skipped project-mode tests.

---

## 9. Reproduction

Start the local stack:

```powershell
.\.venv\Scripts\python.exe scripts\demo.py start
```

Open `http://127.0.0.1:5173/#project`, choose the catalogued Sanchay example, accept the read-only consent, and run the quick or full comparison.

Replay an evaluation through the API:

```powershell
$body = @{
  inspection_id = "72e23dbc-eb42-4ceb-9d38-e341c0f2e0e1"
  adapter_id = "sanchay-reporting-v1"
  mode = "full"
  consent = $true
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations `
  -Method Post -ContentType application/json -Body $body
```

Record a fresh exhibition evaluation from a clean local pinned checkout:

```powershell
.\.venv\Scripts\python.exe scripts\record_project_evaluation.py `
  --source C:\Users\LENOVO\Downloads\Sanchay\Sanchay
```

A full evaluation can execute Sanchay's own tests only when that checkout has an installed Vitest runtime. The harness does not run package installation. If the runtime is absent, the result is labelled `skipped` and the reason is shown in the verdict.

Run the automated gates:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run build
npm --prefix frontend run build:showcase
```

---

## 10. Limitations

- Results come from one host, one Node version, and a microbenchmark of pure report aggregation. They are not production latency claims.
- The live fetched-cache run skipped Sanchay's unit tests because DARWIN intentionally does not install dependencies into a fetched repository. The recorded full run covers those tests with 29/29 passing.
- Quick mode is a screening preset and does not run the source-test overlay.
- Only the catalogued Sanchay commit is executable. Other public repositories remain inspection-only.
- The simulator, checkout lab, searches, fault injection, and their recorded/live labels are unchanged and are validated separately.
