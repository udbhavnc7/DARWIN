# Real Project Mode — Stage 0 audit and integration plan

> Snapshot: 15 November 2026. Branch: `feat/real-project-evaluation`.
> Baseline before changes: **108 passed, 14 skipped** (`pytest -q`), working tree clean apart from this directive.

## 1. What already exists and must be preserved

| Area | Existing implementation | Decision |
| --- | --- | --- |
| Checkout lab | `contracts.py`, `experiments.py`, `sandbox.py`, `measured_sandbox.py`, `fault_suite.py`, `invariants.py` | Reuse unchanged. Real Project Mode is additive. |
| Search | `search.py`, `search_api.py` | Reuse unchanged. No search budget or gate changes. |
| Exhibition presets | `exhibition.py` | Reuse unchanged. Scenario data is not merged with project evaluations. |
| Evidence store | SQLite `experiments.sqlite3`, artifact hashes, event sequences | Reuse the same database file and conventions for new tables. |
| API | `main.py`, `experiment_api.py`, token middleware, CORS | Add one router; preserve every existing route. |
| Frontend | Five workspaces, showcase/live distinction, six themes, tour | Add one workspace and one overview entry; do not rewrite existing pages. |
| Startup | `scripts/demo.py`, README quickstart | Reuse; no new required service. Source checkout is fetched on demand. |
| Showcase | `frontend/src/showcase.ts` read-only snapshot and loopback live mode | Preserve. Real-project execution requires a local bench; the showcase must say so rather than fake results. |

## 2. Sanchay facts verified from source

- Local checkout: `C:\Users\LENOVO\Downloads\Sanchay\Sanchay`, remote `https://github.com/udbhavnc7/Sanchay.git`.
- Pinned visible HEAD: `7e1bc4cdd31e53380e7896b4a20a864bbebcee1e` (2026-11-14).
- Visible app: `web/` — React 19 + TypeScript + Vite.
- Host shell: `app/src/main/java/com/ivy/wallet/ui/SanchayModernUI.kt` (`android.webkit.WebView`).
- Persistence: `web/src/data/persistence.ts` (`sanchay.local.v1`, `window.localStorage`).
- Report pipeline: `web/src/utils/reporting.ts` exports `computeReportTotals`,
  `computeCategorySpending`, `computeCategoryBreakdown`, `computePayeeBreakdown`;
  `web/src/components/ReportsTab.tsx` calls the last three independently over the
  same currency-scoped transaction array.
- Currency safety lives in `web/src/utils/money.ts` (minor-unit rounding).
- Existing tests: `web/src/utils/reporting.test.ts` covers refunds, transfers,
  goal deposits, multicurrency isolation, JPY precision, payee grouping and CSV output.

The inherited Kotlin/Room/Gradle modules are present but are not the visible Sanchay
dashboard. Real Project Mode must never describe Sanchay as a server backend.

## 3. Files to reuse

- `backend/darwin/contracts.py` for `Contract`/`Budget` conventions.
- `backend/darwin/experiments.py` for SQLite, event sequencing, cancellation and
  artifact-digest conventions. New tables are added to the same `experiments.sqlite3`.
- `backend/darwin/main.py` lifespan and `include_router` pattern.
- `frontend/src/main.tsx` hash navigation and workspace layout.
- `frontend/src/Action.tsx`, `Status.tsx`, `style.css` tokens and responsive rules.
- `scripts/export_evidence.py` digest conventions (new bundle endpoint mirrors them).

## 4. Files to add

Backend:

- `repository_catalog.py` — trusted example, pinned SHA, adapter metadata.
- `repository_import.py` — strict GitHub URL/ref validation, read-only checkout,
  commit pinning, size/file limits, provenance.
- `project_capabilities.py` — file-backed stack classification, facts versus guesses,
  supported and unsupported evaluations.
- `adapters/base.py` — adapter protocol and support assessment.
- `adapters/sanchay_reporting.py` — real baseline harness, isolated candidate overlay,
  deterministic fixtures, parity oracle, benchmark and evidence.
- `adapters/sanchay_harness/` — committed TypeScript/JavaScript harness templates.
- `verdict_policy.py` — pure, tested result policy.
- `repository_evaluations.py` — lifecycle, bounded worker, events, cancellation, bundle.
- `repository_api.py` — additive routes only.

Frontend:

- `ProjectEvaluation.tsx` — guided four-step evaluation.
- `RepositoryArchitecture.tsx` — facts/unsupported-capability map.
- `ProjectVerdict.tsx` — concise result plus evidence.
- `projectEvaluation.ts` — API contracts and labels.
- small `main.tsx` navigation/overview changes.

Tests:

- `test_repository_import.py`, `test_project_capabilities.py`,
  `test_verdict_policy.py`, `test_sanchay_adapter.py`,
  `test_project_evaluation_api.py`.

## 5. Execution boundary for v1

- Any public HTTPS GitHub repository may be **inspected** with explicit consent.
- Only `udbhavnc7/Sanchay` at the catalogued SHA may **execute** the audited adapter.
- The checkout is read-only; candidates live in a temporary overlay under
  `artifacts/project-evaluations/`.
- No package installation, no lifecycle scripts, no repository shell commands.
- Node runs without DARWIN/GitHub tokens, no network requirement, bounded timeout.
- Unknown repositories return **UNSUPPORTED_PROJECT**, never the checkout lab.
- Sanchay source is never modified, committed or pushed.

## 6. Honest scope of the first verdict

The measured section is the three report aggregations used by the Reports tab:
totals, category spending/breakdown and payee breakdown. Currency filtering and
React rendering are outside the timed region. The candidate is wired into a real
`ReportsTab.tsx` overlay and the overlay is exercised by Sanchay's existing
`reporting.test.ts` when the pinned checkout has its development dependencies.
If that wiring or test run cannot be completed, the result is labelled
**function-level prototype**, not an optimized application.

## 7. Gate mapping

| Gate | This increment |
| --- | --- |
| 0 | This document; baseline tests recorded; branch created. |
| 1 | Repository import, commit pinning, classification, unsupported handling, no execution. |
| 2 | Project Evaluation workspace with four-step flow and existing pages retained. |
| 3 | Real Sanchay reporting functions, deterministic fixtures, parity failure rejected. |
| 4 | Measured candidate, raw samples, policy verdicts, diff/bundle evidence. |
| 5 | Quick/full modes, progress, cancel, recorded/live labels; measured duration documented. |
| 6 | Existing pages, search, showcase and tests unchanged. |
| 7 | Validation doc, README, presenter script and limits. |
