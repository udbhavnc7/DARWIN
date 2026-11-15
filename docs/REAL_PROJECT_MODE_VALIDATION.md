# DARWIN Real Project Mode — Validation & Evidence Report

**Document status:** Empirical validation report from real benchmark execution on local hardware.  
**Date:** 15 November 2026  
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

---

## 2. Empirical Benchmark Results

### Full Run (`8e3d4ef1-1edd-490a-b846-544b0439a2ee`)

- **Workload:** 3 deterministic seeds (`7`, `21`, `2026`), 3 ledger sizes (`1,000`, `10,000`, `50,000` rows), plus 7 edge fixtures (empty, single expense, refund reduction, goal/transfer isolation, pending/failed exclusion, JPY zero-decimal precision, multicurrency scoping).
- **Repetitions:** 10 paired repetitions per seed/size after warm-up.
- **Total wall-clock duration:** ~7.8 seconds.

#### Latency by Ledger Size

| Ledger Size | Baseline Median | Candidate Median | Delta (%) | Paired Win Rate | Paired Lower Decile |
|---|---|---|---|---|---|
| **1,000 rows** | 0.13 ms | 0.12 ms | **+10.9%** | 86.7% | +4.2% |
| **10,000 rows** | 1.36 ms | 1.18 ms | **+13.5%** | 93.3% | +6.8% |
| **50,000 rows** | 7.85 ms | 6.21 ms | **+20.9%** | 100.0% | +13.1% |

### Quick Run (`d2dabb56-3a23-444b-a7e5-5069e21b7d35`)

- **Workload:** 1 seed (`2026`), 2 ledger sizes (`10,000`, `50,000` rows), 10 paired repetitions.
- **Total wall-clock duration:** ~2.8 seconds.
- **Latency at 50,000 rows:** Baseline 8.02 ms -> Candidate 3.26 ms (**+59.4%**, paired wins 100%).

---

## 3. Correctness & Parity Oracles

Under DARWIN policy, correctness gates strictly override throughput and latency.

### Correctness Checks: 68/68 Passed (100%)

1. **Wiring Checks (3/3):**
   - Candidate is wired directly into `ReportsTab.tsx` call site via `computeReportBundle`.
   - `ReportsTab.tsx` no longer calls the three independent traversal hooks.
   - Reporting module re-exports `computeReportBundle` and `ReportBundle` type.
2. **Deterministic Parity Checks (58/58):**
   - Exact value equality of `totals` (`income`, `spending`, `saved`, `net`).
   - Exact value equality of category spending breakdown percentages and amounts.
   - Exact value equality of top-payee breakdown arrays and transaction counts.
   - Strict currency isolation (INR, USD, EUR, GBP, JPY) with minor-unit precision.
3. **Edge Case Fixtures (7/7):**
   - Empty ledger returns zeroes without throwing.
   - Single expense correctly sets 100% category share.
   - Linked refunds reduce spending totals identically without double-counting.
   - Transfers and goal contributions are isolated from operational expenses.
   - Pending and Failed transactions are ignored identically.
   - JPY zero-decimal precision preserved.
   - Non-active currency rows scoped out prior to computation.
4. **Sanchay Source Unit Tests (29/29 Passed):**
   - Executed against temporary isolated overlay in `artifacts/project-evaluations/.../source-tests`.
   - Ran `src/utils/reporting.test.ts` with Vitest 5.0.5 in 481 ms.
   - Result: `1 passed (1 test file), 29 passed (29 tests)`.

---

## 4. Policy Verdict & Reasoning

- **Verdict Status:** `VERIFIED_IMPROVEMENT`
- **Verdict Label:** Verified improvement
- **Deterministic Reason:**
  > *"All 68 correctness checks passed. The candidate was 20.9% faster at 50,000 rows with a 100% paired win rate, and no measured size regressed by 5% or more."*

---

## 5. Evidence Artifact Bundle

Registered artifacts generated under `artifacts/experiments/project-evaluations/8e3d4ef1-1edd-490a-b846-544b0439a2ee/`:

| Artifact | Size | SHA-256 Digest (prefix) | Description |
|---|---|---|---|
| `benchmark.json` | 22,778 B | `d1ad5248f468...` | Raw timing samples (ns), per-fixture medians, ranges, p95 |
| `candidate.diff` | 5,775 B | `1154eb338246...` | Unified diff of `reportBundle.ts`, `reporting.ts`, and `ReportsTab.tsx` |
| `environment.json` | 6,548 B | `bf3c3715ef02...` | Host CPU, OS, Node version, memory, command arguments |
| `parity.json` | 11,163 B | `e3627de787aa...` | Individual verification outcomes for all 68 assertions |
| `replay.md` | 6,488 B | `fab30e6d97a7...` | Self-contained instructions to re-execute on this computer |
| `source-tests.json` | 2,190 B | `24e3eee052c8...` | Vitest execution log, suite name, exit code, test pass counts |
| `source.json` | 561 B | `ceca2c78914a...` | Commit SHA, repo URL, provenance metadata |
| `verdict.json` | 4,501 B | `c69f7dd0830f...` | Policy evaluation, thresholds, per-size table, verdict status |
| `workload.json` | 4,632 B | `22dc7e610347...` | Workload seeds, fixture sizes, transaction counts, generation config |
| `manifest.json` | 1,193 B | `8e18c096d4db...` | Checksum manifest of all registered files |
| **Evidence Archive** | ~18 KB | `.zip` | Digest-verified bundle available via `/api/project-evaluations/{id}/bundle` |

---

## 6. Truthful Architecture & Honest Scope

1. **Local App Data Pipeline, NOT Server Architecture:**
   - Sanchay is a client-side React 19 application running in an Android WebView with browser-local `localStorage` persistence.
   - It is **not** a cloud backend with microservices, Redis caches, or database replicas.
   - The tested optimization measures pure in-memory report aggregation across transaction arrays.
2. **Safe Source Handling:**
   - Sanchay's repository was accessed read-only at commit `7e1bc4cdd31e53380e7896b4a20a864bbebcee1e`.
   - The candidate exists solely as an isolated overlay and patch artifact. No commits, branches, or remote modifications were made to Sanchay.
3. **Execution Guardrails:**
   - Untrusted repository execution is strictly disabled.
   - Only explicitly catalogued adapters with audited commands are executable. Arbitrary GitHub URLs are restricted to read-only inspection.
