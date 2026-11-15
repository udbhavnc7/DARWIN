# DARWIN — REAL PROJECT MODE
## OpenCode implementation directive, exhibition redesign, and technical acceptance contract

**Project:** DARWIN — Better Backends. Built on Evidence.  
**Date:** 15 November 2026  
**Base repository:** https://github.com/udbhavnc7/DARWIN (`master`)  
**First external reference project:** https://github.com/udbhavnc7/Sanchay (`main`)  
**Status of this document:** Implementation **instructions**, not a claim that these features are already implemented.  
**Audience:** OpenCode coding agent, DARWIN maintainer, exhibition demonstrator, and technical judge.  
**Ultimate goal:** A visitor can select a genuine GitHub project, immediately understand its system, run a narrowly scoped real experiment, see a defensible result and learn why a configuration won or was rejected.

> **STOP AND READ FIRST — Source reality check.** Sanchay is **not** a server backend. Its current visible application is React 19 + TypeScript, hosted in an Android WebView with `localStorage` persistence. Its Kotlin/Compose/Room modules are inherited and are not wired to the visible Sanchay dashboard. It does not have a deployed checkout API whose replicas, server-side Redis, payment retries, or PostgreSQL outbox can be optimized by DARWIN. The first honest Sanchay demo must be called **Local App Evaluation / Reporting Pipeline Optimization**, not backend-server architecture evolution. Keep DARWIN's existing checkout architecture lab as the genuine **Backend Architecture Evolution** mode. Importantly, do not pretend either mode uses capabilities it doesn't.

---

# PART A — One-minute mission

**The problem:** DARWIN already runs rigorous experiments, but the current multi-workspace workflow is difficult for a new visitor to understand, and some experiments take minutes. A full evolutionary search is inappropriate for an interactive two-minute exhibition.

**The new experience:**

1. Select **Sanchay** or paste a public GitHub repository URL.
2. DARWIN inspects the actual source at a **pinned commit** and displays a simple architecture map: what the application contains, how data flows, and what operations can actually be tested.
3. The user selects one supported experiment — for Sanchay v1, **Financial Reports: Original vs Single-Pass Aggregation**. DARWIN shows the changed behavior, synthetic transaction workload, correctness rules and expected test duration **before** starting.
4. The user presses **Evaluate**. DARWIN runs **real comparable code** in an isolated, explicitly authorized environment, records measurements, and checks that computed finance outputs match the original implementation.
5. A verdict screen appears: **Verified Improvement**, **Baseline Retained**, **No Verified Winner**, **Rejected (Incorrect)**, or **Unmeasured**. It shows the measured latency, relative change, how many tests passed, provenance, and one short reason.
6. **Explore evidence** reveals detailed logs, candidate source diffs, per-run metrics and correctness traces — without requiring the judge to understand NSGA-II or Pareto fronts first.

The present checkout demo remains one click away as **Backend Architecture Lab**, with its existing search, simulation, fault injection, invariants, experiments, shop, and evidence fully intact.

**Key product principle:** The first screen gives an answer a human understands. The second screen gives enough evidence for an engineer to trust it.

---

# PART B — Verified current state; do not duplicate or destroy

## B1. DARWIN today

Repository source paths inspected on 15 November 2026:

- `backend/darwin/main.py`: FastAPI control plane.
- `backend/darwin/search.py` and `search_api.py`: bounded NSGA-II, random and hill-climbing search, and search API.
- `backend/darwin/experiments.py`, `experiment_api.py`: experiment lifecycle and evidence persistence.
- `backend/darwin/simulator.py`, `calibration.py`: simulation and screening.
- `backend/darwin/invariants.py`, `fault_suite.py`, `docker_sandbox.py`, `measured_sandbox.py`: verification and measured execution.
- `backend/darwin/exhibition.py`: **already existing** judge-ready scenarios, duration estimates, and saved-run selection. Extend/reuse, do not duplicate.
- `frontend/src/main.tsx`: existing five-workspace navigation and showcase live/recorded modes.
- `frontend/src/Architecture.tsx`, `Experiments.tsx`, `Search.tsx`, `Shop.tsx`: preserve fully.
- `frontend/src/showcase.ts`: GitHub Pages recorded showcase and local bench connection. Preserve explicit **recorded vs live** labeling.
- `scripts/demo.py`: local startup manager; already checks readiness and manages only owned processes. Extend carefully.
- `tests/test_search.py`, `test_exhibition.py`, `test_auth.py`, `test_docker.py`: extend existing tests.
- `README.md`, `CONTEXT.md`, `docs/ARCHITECTURE.md`, `docs/PHASE_10.md`: authoritative context; check latest before editing.

DARWIN's current backend lab uses one controlled checkout stack, four controls (replicas 1/2/3, cache 0/10/30 seconds, notification sync/queued, retry none/idempotent-only), three workloads, three fault families, and five business invariants. Its search works, but real measured evolution can take many minutes. Never claim a full search completed in seconds if only a preview or recorded result was shown.

## B2. Sanchay today

Verified from the repository README, `web/package.json`, and actual source paths:

- Main visible product: React + TypeScript + Vite dashboard inside Android WebView.
- Persistence: local `localStorage`, `sanchay.local.v1`; **not a server database**.
- `web/src/utils/reporting.ts`: actual report calculations, including `computeReportTotals`, `computeCategorySpending`, `computeCategoryBreakdown`, and `computePayeeBreakdown`.
- `web/src/utils/spendingComparison.ts`: monthly comparison calculations.
- `web/src/utils/budgetHistory.ts`: budget history logic.
- `web/src/utils/ledgerOps.ts`: immutable finance operations and refund integrity.
- `web/src/data/persistence.ts`: versioned state validation and local saving.
- `web/src/utils/*.test.ts`, `web/src/data/*.test.ts`: existing finance and persistence tests.
- `web/package.json`: `pnpm` (pinned to 10.34.3), `pnpm test`, `pnpm build`, `pnpm lint`.
- Sanchay uses **fictional sample data only when explicitly selected**. It does not move money or connect to UPI or a bank.

This is an attractive real app to demo because the correctness conditions are easy to explain: **finance totals must remain exactly correct after optimization**.

**Do not** confuse the inherited Kotlin/Room modules with the currently active Sanchay dashboard. Do not claim a database backend, cloud synchronization, a transaction processor, or measured mobile-device performance without actually testing them.

## B3. Important planning correction

The GitHub repository `udbhavnc7/ROUTELESS` currently documents a static browser-local demo as well; it is **not currently** a deployed Node/Hono backend. Do not use it as an alternate live backend without first locating and verifying an actual server implementation. The existing DARWIN checkout lab remains the first credible backend demonstration until a third-party backend adapter is genuinely implemented.

---

# PART C — The exhibition product experience

## C1. New navigation without deleting existing pages

Add a top-level **Try a Real Project** entrance and a presenter-friendly **Project Evaluation** page. Keep the existing five workspaces under **Advanced Lab / Explore DARWIN**, reachable in one click. The home screen should lead with the actual business problem, not a complex architecture graph.

**Suggested initial view:**

```text
DARWIN                                     [Exhibition Mode ✓] [Advanced Lab]
Find better ways to run real software — and prove they are correct.

  [1. Choose a project]  [2. Understand it]  [3. Test]  [4. Verdict]

  [ Sanchay · Personal finance ]       [ Paste public GitHub URL ]
  Your chosen project uses: React + WebView + local storage
  Evaluation type: LOCAL-APP DATA PROCESSING — not server architecture

  [Inspect this project]
```

**Architecture inspection view:**

```text
SANCHAY — CURRENT SYSTEM
[React UI] → [Finance logic] → [Browser local storage] → [Android WebView]
What users do: add expenses, view budget, review financial reports.
What DARWIN can test today: financial report calculation strategy.
Not testable as server architecture: API replicas, server queue, cloud failover.

[Original report calculations]  vs  [One-pass reporting candidate]
[Show what changes]   [Run 20-second target comparison]
```

Target 20 seconds is a **performance target after local preparation**, not a promise or a displayed ETA until measured on the actual machine. Always display real, honest stage progress and a cancel action.

**Verdict view, only when measurement supports it:**

```text
SANCHAY — VERIFIED REPORTING COMPARISON
RESULT: VERIFIED IMPROVEMENT / BASELINE RETAINED / ...

Measured: baseline [measured] ms | candidate [measured] ms
Change: [computed from data] %  |  Correctness: [count] / [count] checks
Workload: [number] synthetic transactions | Environment: [Node version / host]

Why? [plain-language reason tied to evidence]
[Inspect proof]  [View code diff]  [Download report]  [Try another workload]
```

**Do not prefill any numeric values, speedups, pass counts or winners.** The placeholders shown above are labels only. A live verdict must come from recorded current-run evidence; a saved verdict must be prominently labeled **Recorded evidence**, with date, source commit and hardware/runtime.

## C2. Mandatory beginner/engineer layering

For **each** stage include:

- One human sentence: e.g. “DARWIN is counting how quickly Sanchay generates a financial summary.”
- What is happening: “Running the same transactions through two real report calculation paths.”
- Why it matters: “A report that is fast but changes someone's budget totals cannot be trusted.”
- Advanced expander containing exact commands, run IDs, commit SHA, JSON and metrics.

Never require the presenter to open five tabs to reach the conclusion. The judge-facing path has at most **four primary interactions** after the project is selected.

## C3. Clear modes, no confusing language

| Mode | Real target | Candidate variation | Correct wording |
|---|---|---|---|
| **Backend Architecture Lab** (existing) | DARWIN checkout service stack | Replicas, caching, queue, retry | “Architectural configuration evolution” |
| **Local App Evaluation — Sanchay** (new v1) | Actual Sanchay reporting code | Original multi-pass vs verified single-pass data pipeline | “Client-side report-processing architecture / computation strategy” |
| **Unrecognized repository** | Real source inspection only | None until a supported adapter exists | “Repository inspected. No runnable optimization adapter yet.” |

Do not call a client-side computation benchmark an AWS/cloud infrastructure optimization. Do not tell judges DARWIN can arbitrarily optimize every GitHub repository.

---

# PART D — Concrete, genuinely measurable Sanchay adapter

## D1. Scope of the first real-project experiment

Build **one deep, convincing adapter** rather than ten fictional ones:

**Adapter ID:** `sanchay-reporting-v1`  
**Display name:** “Sanchay · Financial Reports”  
**Source:** commit-pinned `udbhavnc7/Sanchay/web`  
**Workload:** deterministic, fictional local ledgers; representative distribution of incomes, expenses, refunds, pending items, transfers, categories, and currencies.  
**Baseline:** call the real Sanchay `reporting.ts` functions (or the same real UI report pipeline after inspection) on exact fixture inputs.  
**Candidate:** a real alternate implementation with **shared single-pass aggregation** of report totals, category spending, and payee aggregates instead of redundant independent traversal, *if* source review verifies semantic equivalence can be achieved.  
**Expected benefit hypothesis:** fewer repeated ledger passes for large transaction arrays. This is **not** a guaranteed improvement; overhead may make it slower on small ledgers.

**Required build sequence:**

1. Pin repository commit and confirm exact source exports, types and import graph.
2. Build an isolated benchmark harness that imports/calls real baseline code. Never benchmark a handwritten lookalike baseline.
3. Construct optional candidate in a **separate temporary worktree/overlay**. Preserve the user's Sanchay repo.
4. **Wire the candidate through the actual Sanchay reporting call sites in the isolated candidate worktree**, not only a new standalone helper function. If that cannot be completed safely in this iteration, label the result explicitly **function-level prototype**, NOT an optimized app. Run Sanchay's relevant existing unit tests, build, and an expanded equivalence suite against both implementations.
5. Validate **value equality and financially meaningful invariants** across multiple synthetic data seeds.
6. Warm up, then time equivalent work on the same host/runtime; record all raw samples and the result distribution.
7. Show only a justified verdict. Offer a patch/diff artifact, never silently change or push the Sanchay repository.

If a genuine source-compatible candidate cannot be implemented without extensive refactoring, **stop and display “No verified optimization candidate yet”** with a useful analysis. Do not manufacture a winning variant.

## D2. Financial correctness oracle (non-negotiable)

Retain and extend Sanchay's existing financial semantics; confirm against the real code rather than inventing new rules. Mandatory parity/edge cases:

- Exact currency-safe totals; do not combine INR/USD/EUR/etc. into a single amount.
- Completed vs pending/failed/flagged transactions handled identically.
- Transfers excluded from spend/income as defined by existing functions.
- Linked refunds reduce spending as defined by current Sanchay logic; do not double-count.
- Goal deposits/savings contributions retain existing semantics.
- Category and payee outputs preserve ordering/tie behavior where user visible.
- Deterministic repeat calculations with the same input give exactly the same result.
- Original ledger arrays and local persistence remain untouched by benchmark execution.
- Edge sets: empty ledger, single transaction, large ledger, multicurrency, duplicate-looking IDs, malformed/dropped inputs according to existing validation contracts.
- Existing Sanchay tests (reporting, ledger operations, persistence, budgets, payment assistance) must continue passing when exercised against an actual candidate patch.

**Gate:** If even one mandatory correctness check fails, the candidate is **REJECTED** and **never displayed as the winner**, irrespective of throughput/latency.

**Safety:** Synthetic ledger data only. Never import a user's private finances into DARWIN without an explicit separate privacy and security design.

## D3. Honest measured comparison

Use a repeatable benchmark plan:

- **At least three deterministic fixture seeds**, held fixed for both implementations.
- **At least three ledger sizes**, e.g. 1,000 / 10,000 / 50,000 rows *if memory and preparation budget allow*; numbers are targets and may be revised based on host capacity.
- Same language runtime, machine, Node version and dependency lock.
- Warm-ups to avoid comparing cold startup against warmed code; capture warm-up count.
- At least 10 measured repetitions per candidate/size after warm-ups for credible results; tune to fit a measured short demo, but disclose if fewer.
- Alternate the order of candidate execution across seeds or use independent randomized order to limit systematic order bias.
- Record elapsed time using high-resolution monotonic clocks. Label whether it is pure function timing or end-to-end UI timing.
- Record exact input count, checksum, source commit, candidate diff hash, runtime version and environment.
- Use **median**, p95 where sample size is adequate, and range; provide raw samples and confidence caveat.
- If a candidate is less than 5% faster, or if run-to-run variance overlaps substantially, show **Inconclusive** rather than overselling a winner. Treat 5% as an initial product-policy threshold, not a scientific significance test.
- A slower verified candidate is not a winner. If baseline is fastest or evidence is inconclusive, say **Baseline Retained** or **No Proven Improvement**.

Candidate performance counts only after all correctness checks pass. Show improvement per workload size — don't market only the most favorable case.

## D4. Sanchay-specific UI explanation

Use a truthful diagram:

```text
Sanchay GitHub source (read-only, pinned commit)
       ↓
React + TypeScript local finance application
       ↓
Reports calculation from fictional ledger data
       ↓
  [Original reporting pipeline]   [Candidate reporting pipeline]
         \                          /
          same fixtures / same environment
                       ↓
        [Correctness checks] → reject incorrect
                       ↓
           [Measured comparison]
                       ↓
        [Verdict + evidence + code diff]
```

Describe this as real application **data-processing design**, not swapping Django for Flask and not changing the Android app's live installed code.

---

# PART E — Platform architecture to implement in DARWIN

## E1. Proposed additive modules (adapt after inspecting actual project structure)

**Backend (suggested):**

- `backend/darwin/repository_catalog.py` — fixed trusted examples, support metadata.
- `backend/darwin/repository_import.py` — repository URL validation, safe source retrieval, commit pinning, content-addressed checkout, source classification.
- `backend/darwin/project_capabilities.py` — detected stack and supported runnable evaluations. Separate factual evidence from guesses.
- `backend/darwin/adapters/base.py` — typed adapter protocol, optional resources, stage explanations.
- `backend/darwin/adapters/sanchay_reporting.py` — Sanchay-specific setup, candidate generation, benchmark, parity oracle, evidence.
- `backend/darwin/repository_evaluations.py` — lifecycle, bounded tasks, cancellation and evidence integration; prefer reusing `experiments.py`/existing store rather than creating a second worker or another database.
- `backend/darwin/repository_api.py` — additive API endpoints only.

**Frontend (suggested):**

- `frontend/src/ProjectEvaluation.tsx` — guided 4-step project evaluation page.
- `frontend/src/RepositoryArchitecture.tsx` — classified architecture map with proven facts and unsupported labels.
- `frontend/src/ProjectVerdict.tsx` — concise outcome, evidence, code-diff and rerun options.
- `frontend/src/projectEvaluation.ts` — typed API client/contracts and presentable explanations.
- Update `frontend/src/main.tsx` only to add route/navigation and brief entry copy; **keep existing pages**.

**Tests:** `tests/test_repository_import.py`, `tests/test_project_capabilities.py`, `tests/test_sanchay_adapter.py`, `tests/test_verdict_policy.py`, `tests/test_project_evaluation_api.py`, plus optional frontend UI tests.

These are **proposed names**, not existing files. Modify naming to follow source conventions; do not replace the existing search worker or evidence store.

## E2. Adapter contract (conceptual)

```python
class ProjectAdapter(Protocol):
    id: str
    def detect(self, source_tree) -> SupportAssessment: ...
    def describe(self, source_tree) -> ArchitectureFacts: ...
    def prepare(self, source_checkout, budget) -> PreparedEvaluation: ...
    def candidates(self, prepared) -> list[Candidate]: ...
    def measure(self, prepared, candidate, workload, budget) -> Measurements: ...
    def verify(self, prepared, candidate, measurements) -> GateResults: ...
    def explain(self, evidence) -> HumanReadableVerdict: ...
```

The adapter MUST explicitly declare whether it is **backend architecture**, **client data-processing**, or **inspection-only**. Unsupported adapter requests must fail with actionable, nontechnical explanation; never fall back silently to evaluating the unrelated checkout shop.

## E3. Suggested HTTP contract (new, not existing)

```text
POST /api/repositories/inspect     { url, ref? } → { inspection_id, commit_sha, project_type, facts, supported_evaluations }
GET  /api/repositories/{id}        → { source, facts, capabilities, readiness }
POST /api/project-evaluations      { repository_id, adapter_id, workload, budget } → 202 { evaluation_id }
GET  /api/project-evaluations/{id} → { status, stage, progress, times, candidates, verdict?, evidence_refs }
GET  /api/project-evaluations/{id}/events?after=N  → ordered, monotonic sequence
POST /api/project-evaluations/{id}/cancel          → cancellation/cleanup state
GET  /api/project-evaluations/{id}/bundle          → digest-verified evidence archive
```

Use typed Pydantic contracts, schema/version field, immutable source references, strict input limits and actionable error responses. Avoid hidden browser-only state for results: the backend remains the source of truth. Persist every experiment's source revision, candidate diff, environment and gate results; reuse DARWIN's SQLite/artifact conventions where practical.

## E4. Exact result statuses

- `VERIFIED_IMPROVEMENT`: candidate passed all relevant correctness gates; independently measured improvement meets configured policy; eligible for promotion.
- `BASELINE_RETAINED`: baseline is best measured feasible variant or proposed variant lost.
- `INCONCLUSIVE`: data variability or insufficient confidence, even if candidate median is numerically lower.
- `REJECTED_INCORRECT`: a candidate violated correctness or changed business semantics.
- `NO_FEASIBLE_CANDIDATE`: no evaluated variant passed required gates.
- `UNSUPPORTED_PROJECT`: project inspected but no adapter exists; show facts and next steps.
- `NOT_MEASURED`: source inspection/simulation/preview only; cannot count as winner.
- `RECORDED_EVIDENCE`: display overlay/provenance **not** a replacement for one of the statuses above.
- `INTERRUPTED` or `FAILED_INFRASTRUCTURE`: cleanup and remediation; no fabricated metrics.

All verdicts are derived from backend evidence. Add unit tests for each status and the ambiguity/no-winner branches.

---

# PART F — Speed, demo reliability and honesty

## F1. Two time horizons

**Preparation (before exhibition):** Pin the Sanchay revision; download/cache source; verify dependencies; prepare three synthetic datasets; compile the experiment harness; run the full equivalence and benchmark suite; export a signed/digested **recorded evidence** bundle. This may take minutes. It is done before the visitors arrive.

**Visitor interaction:** Select the already-inspected repo; show source map immediately; run a short bounded **fresh measurement** using prepared fixtures and code; open the verdict. Target 15–30 seconds **after actual profiling verifies feasibility**, but if the host cannot achieve it, show honest progress and switch to a clearly labeled recorded full comparison. Never silently replace a fresh result with a saved one.

**Long-running DARWIN engine:** Keep existing full search and Docker adversarial runs in Advanced Lab; add clear warnings (“full search can take many minutes”), progress, cancellation and retained evidence. Do not loosen invariant gates or change search budget globally just to speed up the demo.

## F2. Exhibition experience in one minute

1. “This is my real GitHub project, Sanchay.” Click it.
2. “DARWIN reads the actual code and notices that it is an offline personal finance app, not a server.” Show truthful architecture map.
3. “We can still experiment with how its reports are calculated.” Choose report pipeline comparison.
4. “Both variants get the exact same fictional transactions. The totals and refunds must match exactly.” Start fast run.
5. “Here is the measured result. If a candidate is faster **and** correct, we can recommend it; otherwise DARWIN tells you why not.” Open verdict and source diff.
6. Optional 15-second contrast: switch to the existing Checkout Lab and open its saved unsafe-payment rejection to show real backend fault injection and invariant I-01.

**Important:** Do not merge the finance-report benchmark metrics into the original checkout search Pareto chart. Different applications/metrics/environment are not directly comparable.

## F3. Presenter mode design

Add **Presenter View** with optional prepared cards:

- **What is this project?** from actual repo facts.
- **What are we changing?** explicit candidate diff and expected mechanism.
- **What stays unchanged?** user data/finance semantics or checkout invariants.
- **What did we measure?** metric, unit, work size, runtime.
- **Did it pass safety checks?** clear pass/reject details.
- **What do we recommend?** measured verdict, including baseline/no winner.

Visual hierarchy: big project title, simple system diagram, one key metric, one correctness indicator, one verdict. Advanced details collapsed by default. Ensure keyboard navigation, contrast, mobile and offline state; no unsolicited 3D splash during an active presentation.

## F4. Transparent live vs recorded

Every result must carry one of:

- **LIVE · run started at [timestamp] · [commit]**
- **RECORDED · captured at [timestamp] · [commit] · [machine label]**
- **INSPECTION ONLY · no measurement run**

Never say “optimizing now” when the UI only loads a saved JSON. Never precompute a winning verdict and present it as current. Preserve current GitHub Pages showcase's recorded/live distinction.

---

# PART G — Execution security and non-destructive source handling

A pasted repository is **untrusted executable code**. Even public repositories may contain malicious scripts, package post-install hooks, data theft instructions, or destructive commands.

Minimum requirements:

1. **Explicit user action/consent** before downloading and especially before executing repository code.
2. Restrict first release to HTTPS GitHub repository URLs and allowlisted example repos; reject malformed URLs, local network addresses, path traversal, credentials in URLs and overly large repositories. Use appropriate redirect validation.
3. Resolve branch/tag to exact commit SHA; label source provenance and cache by commit plus adapter version.
4. Read-only clone/archive in a bounded directory; never run repo-provided shell commands as trusted input or auto-execute setup instructions from README.
5. Only execute known, audited adapter commands; disable package lifecycle scripts when feasible; require resource-limited temporary container/VM with **no host secrets, no GitHub tokens, no host filesystem write**, limited network, CPU, RAM, process count and timeout.
6. Running arbitrary code inside a container is not automatically safe. For v1 **trusted Sanchay allowlist** is acceptable if a robust sandbox is not available; do not enable general public-repo code execution until isolation is validated.
7. Synthetic data only; private finance data and bank IDs are not ingested or exported.
8. Temporary worktrees for candidates; no commits, pushes, branches, remote mutations, account changes or deployment to users' production apps without explicit separate approval.
9. Track owned child processes/container IDs; cancellation, crash recovery and cleanup must not touch unrelated user resources.
10. Preserve existing DARWIN's local-only security assumption; do not expose unauthenticated execution endpoints to a public network. Inspect existing auth features before integrating.

If isolation is insufficient, implement **inspection-only for arbitrary GitHub URLs**, and enable execution only for explicitly permitted known adapters.

---

# PART H — Step-by-step OpenCode work plan with acceptance gates

## Stage 0 — Audit before edits (MANDATORY)

OpenCode must first:

- Confirm current branch, working tree status, pending user changes and HEAD commit.
- Read the repository's README, CONTEXT, existing AGENTS.md (if any), docs, `main.py`, search, experiment and exhibition APIs, frontend navigation, tests, showcase mode and start script.
- Verify Sanchay at its current pinned HEAD and read reporting, money, ledger, persistence, fixtures, tests, package lock and actual exports.
- Produce a **gap report** identifying relevant existing functionality. Explicitly list files to reuse and files to add.
- Create a feature branch, e.g. `feat/real-project-evaluation`, or a separate worktree. Do **not** overwrite current work or rewrite the repo from scratch.
- Record baseline tests/build before changes. If existing failures occur, distinguish them from regressions.

**Gate 0:** readable audit, bounded implementation plan, tests baseline, no changed code or removed functionality yet.

## Stage 1 — Repository import + truthful capability detection

Implement approved GitHub repository inspection; commit SHA pinning; clear Sanchay architecture facts; unsupported-repo handling; source provenance and structured capability status. No code execution yet.

**Gate 1:** Sanchay classified as client/local-first, not server; arbitrary unsupported URL gets safe inspection-only response; malicious URL/path cases rejected; existing DARWIN tests pass.

## Stage 2 — One-click exhibition UI

Add Project Evaluation navigation and wizard with Sanchay example, source map, short plain-language explanations, eligibility and run option. Existing pages remain visible and functional.

**Gate 2:** judge reaches evaluation screen in ≤4 deliberate actions; 360px responsive; keyboard usable; recorded/live always visible.

## Stage 3 — Actual Sanchay baseline and correctness harness

Use the real Sanchay reporting source from pinned checkout. Generate deterministic fiction-only fixture ledgers. Run correct baseline and equivalent alternative only when implemented. Include parity tests with existing Sanchay semantics and keep raw outputs. Identify the actual Reports UI call sites; patch those in an isolated candidate worktree before claiming the **project** is optimized rather than merely a standalone function.

**Gate 3:** verified real functions run, real fixtures/outputs stored; no Sanchay repo mutation; corrupted/incorrect candidate rejected with meaningful reason.

## Stage 4 — Measured candidate + defensible verdict

Implement real reporting candidate in isolated overlay, paired benchmark, evidence artifacts, verdict policy, source-diff download, error/inconclusive/no-winner states.

**Gate 4:** a real run produces numeric evidence and may produce a valid winner; all incorrect candidates are rejected even when faster; baseline-retained and no-winner cases are tested.

## Stage 5 — Fast demo and evidence replay

Preflight/prepare fixtures, caching, separate **Quick Live** and **Full Recorded** results; cancellation; stage events; clear time taken; export digest verified evidence; error fallback; test in browser.

**Gate 5:** time the exhibition flow on the exact laptop; deliver a measured demo duration in `docs/REAL_PROJECT_MODE_VALIDATION.md`, not an optimistic promise. Rehearse failure/no-Docker/no-node/offline states.

## Stage 6 — Preserve and connect original Backend Lab

Retain all existing checkout workflows and search functions; add a prominent “Show backend fault testing” link to a recorded unsafe-payment scenario and a feasible measured search. Keep original charts, fixtures, tours, themes and APIs.

**Gate 6:** existing regressions/tests/build/acceptance still pass; current search, architecture export, Docker/native and live/recorded modes remain accessible.

## Stage 7 — Final QA and learning material

Deliver installation/run instructions, screenshots and a 90-second judge script plus FAQ. Record true test counts, real run timings, known platform limitations and exact source commit; do not quietly claim production support.

**Gate 7:** automated test results and recorded manual UI walkthrough available, no stale fake numbers, no broken links, user can explain results without engineering jargon.

---

# PART I — Specific automated tests OpenCode must add

## Source/classification tests

- Valid pinned Sanchay URL returns real `react_webview_local_app` facts.
- No Node backend falsely inferred from an unrelated `package.json`.
- Inherited Kotlin/Room modules are distinguished from visible WebView storage.
- Unsupported repository shows no executable adapter, never quietly runs the checkout demo as a substitute.
- Poison URLs, redirects, oversized repos, missing branches, untrusted package scripts and malformed `ref` rejected safely.

## Financial/candidate tests

- Invariant equality across multiple transaction counts and seeds.
- Multicurrency reports scoped correctly.
- Refund, transfers, pending/flagged, goal deposit, future date and invalid input behavior follow actual Sanchay contracts.
- Existing Sanchay utility tests relevant to modified code still pass.
- Intentionally incorrect fixture fails, even if its benchmark is faster.
- Modified candidate cannot silently write `localStorage`, banking data or original source.

## Experiment/verdict tests

- Fresh measured run has pinned source SHA and reproducible fixture seed.
- Incomplete run is not ranked or promoted.
- Candidate with one failing check is never declared a winner.
- Very small delta and overlapping results yield inconclusive under configured policy.
- Correct slower candidate yields baseline retained.
- All candidates rejected yields no feasible winner.
- Recorded result is distinguishable from live on every UI path and PDF/JSON export.
- Kill/cancel leaves no orphan processes and no unrelated resources deleted.
- Lack of benchmark runtime gives actionable message, not a fabricated result.
- Existing DARWIN original search and exhibition tests remain green.

## User acceptance checks

- “Can a non-programmer tell me what Sanchay is in 10 seconds?”
- “Can the judge point to exactly what changed between two variants?”
- “Can we answer 'which won, why, and with what evidence?' in 15 seconds?”
- “Can DARWIN say no winner without hiding it?”
- “Can we explain a rejected fast option in terms of a money calculation?”
- “Can an engineer reproduce the run from a pinned repo and artifact bundle?”

---

# PART J — Delivery artifacts expected FROM OpenCode

Do not declare project completion until these are produced:

1. Actual working Project Evaluation code integrated in DARWIN, on a feature branch.
2. Sanchay supported adapter or an explicitly documented technical blocker; not a simulated pretend adapter.
3. Unit/integration/UI tests with logged actual counts and output.
4. Provenance- and digest-backed recorded sample, generated **from a real source run** (if measured runtime available).
5. At least one genuine candidate code diff (or evidence explaining why candidate cannot yet be safely made).
6. `docs/REAL_PROJECT_MODE_VALIDATION.md`: exact machine, SHA, adapter version, real timing, metrics, limits and what was actually tested.
7. Updated user README and architecture docs marking **real backend** versus **local app data pipeline** modes.
8. 90-second script; simple component glossary; FAQ; one-minute backup playback with recorded label if available.
9. A final change log stating every existing feature preserved and any limitations.

**Forbidden:** mock values called measured; predetermined victor; architectural diagrams that pretend Sanchay has a server; rewriting the codebase; making changes directly to Sanchay; skipping gates to get a pretty chart; switching from real work to a new generic ChatGPT-style coding assistant.

---

# PART K — Direct first message to paste in OpenCode

> I am implementing **DARWIN Real Project Mode** in this existing repository. Read `DARWIN_OPENCODE_REAL_PROJECT_MODE.md` completely, and treat it as the project requirements and implementation acceptance contract. Begin with **Stage 0 audit**: read existing documentation and relevant backend/frontend/tests, inspect Sanchay's actual repository at a pinned commit, and report the smallest safe integration plan. Preserve the current working search, experiment runner, fault injection, checkout lab, themes, GitHub Pages showcase, evidence, and UI. Then implement **Stages 1–2**, run the existing test suite and frontend build, and report exactly what changed. Continue to **Stages 3–7** in small test-backed increments; do not claim completion without running the acceptance gates. Never fake winner metrics or misidentify Sanchay as a server backend. Work on a new branch/worktree, never push or modify Sanchay without explicit approval. If an implementation issue is solvable, fix it and continue; otherwise record a precise blocker and leave the build stable. Provide a final verified status with exact run commands, tests, and demo path.

**OpenCode setup:** Open the *local DARWIN checkout* in OpenCode, copy this Markdown file to the DARWIN project root, and paste the above message. OpenCode's current documentation recommends repo-specific `AGENTS.md` for persistent rules. If DARWIN already has `AGENTS.md`, merge only a concise pointer to this directive and preservation rules; **do not overwrite it**. Documentation: https://opencode.ai/docs/instructions

---

# PART L — Presenter cheat sheet (read before the exhibition)

## L1. What DARWIN is, in 20 seconds

“DARWIN is a software experimentation engine. We give it a real program and an allowed design choice to test. It runs the original and the candidate on controlled workloads, checks that important outputs stay correct, and compares measured results. It recommends a change only when there's enough proof.”

## L2. Why this is not just ChatGPT, Cursor, or an ordinary profiler

- A coding assistant *suggests* changes; DARWIN should **execute, compare and verify a constrained candidate**.
- A profiler reports where time is spent; DARWIN tests alternative configurations/implementations **under explicit correctness gates**, with reproducibility and a verdict.
- A standard benchmark measures speed; DARWIN also tests **domain semantics** (e.g., refunds and account totals for Sanchay, duplicate payment captures for checkout).
- This integration is a distinctive product design, **not a patent claim or proof that no competitor has it**.

## L3. What we optimize in Sanchay vs checkout

- **Sanchay:** calculation pipeline of a local personal finance application. “Do its reporting calculations become faster without changing any financial result?” This is client-data processing, not cloud deployment optimization.
- **DARWIN checkout lab:** actual server-side design settings: number of API replicas, cache TTL, synchronous/queued notification and retry policy. “Does this configuration improve latency and still avoid duplicate payment effects or overselling?”

## L4. Technical vocabulary in plain English

| Word | Easy explanation |
|---|---|
| Architecture | How software parts are arranged and communicate |
| Framework | Code toolkit, like Django, FastAPI or React; not itself an architecture |
| Candidate | One proposed configuration or implementation to test |
| Baseline | The original system used for comparison |
| Workload | A realistic set of actions and input sizes that stresses a system |
| Benchmark | Controlled measurement of how it performs |
| Invariant | A rule that must always be true |
| Fault injection | Deliberately introducing a failure to test recovery/correctness |
| Idempotency | Repeating the same request should not create an extra business effect |
| Simulation | An estimate used to shortlist; **not** a real deployed measurement |
| NSGA-II | Algorithm that explores several objectives (e.g. latency and resource use) without assuming one perfect choice |
| Pareto front | Choices where improving one metric typically requires compromising another |
| Evidence provenance | Record of the source, data, environment, commands and runs behind a result |

## L5. Business model, in 30 seconds

“DARWIN targets engineering teams at SaaS companies, e-commerce operators and software agencies. The first product to sell is a **scoped, paid architecture evaluation pilot** on a supported backend with clear business rules. After real customer validation, the long-term model is B2B subscriptions and private enterprise deployment. The business advantage is reducing repeated manual engineering experiments and producing trustworthy evidence, not promising every possible system can be optimized automatically. Running experiments costs compute, so customer-hosted staging is a cost-control strategy.”

**Pricing is a hypothesis, not existing revenue.** Do not tell judges that a customer has paid or that the tool already supports any production repository.

## L6. Hard judge questions and safe answers

**Q1. Does DARWIN optimize any GitHub repo?**  
No. The new mode inspects source and reports what adapter is supported. It can only measure systems with implemented, approved benchmark and correctness adapters. Unknown repos remain inspection-only.

**Q2. Is Sanchay's architecture microservices or Django?**  
Neither. Its visible application is React in an Android WebView with browser-local storage. The proposed first evaluation compares financial-report computation strategies. The checkout lab is the separate real backend example.

**Q3. Are you changing Sanchay's production app?**  
No. Candidates run in isolated source overlays. DARWIN can produce a tested patch, but applying it requires developer review and approval.

**Q4. What's your one unique quality?**  
Correctness-gated experimentation: a faster candidate is rejected if it changes an important business rule. We combine measured comparisons with domain-specific verification.

**Q5. Why is a faster design sometimes rejected?**  
A faster finance summary that miscounts refunds, or a faster checkout that charges twice, is worse for the user. Correctness is a gate, not a negotiable score.

**Q6. Does it use AI?**  
The original DARWIN search uses evolutionary optimization, including NSGA-II, plus simulation for screening. That's algorithmic AI/optimization, not necessarily an LLM. The Sanchay v1 evaluator can start with bounded, predefined candidate strategies; do **not** say it uses NSGA-II unless actually connected to that search.

**Q7. What if no candidate wins?**  
DARWIN says **no proven improvement**, retains the baseline, and explains the missing evidence or failed gates. That's a trustworthy outcome.

**Q8. Why does the original DARWIN search take minutes?**  
It deploys real services, applies workloads and faults, and repeats tests. Those costs are real. Exhibition Mode separates quick measured microbenchmarks from longer full-system tests and clearly labels saved results.

**Q9. How is this different from benchmarks or existing AIOps tools?**  
Its focused workflow combines candidate generation, measured performance, deliberate failure/correctness gates, and reproducible evidence in one guided experience. Existing optimization and testing tools are real competitors; our differentiator is the domain-correctness-first presentation and integration, not being first to automate performance tuning.

**Q10. How do companies adopt it?**  
Start with a supported, safely isolated, non-production application plus rules and representative workloads. Run a paid evaluation. Expand adapters and security before multi-company SaaS rollout.

**Q11. Who pays and why?**  
Engineering managers and DevOps/SRE teams would pay if pilots prove reduced manual testing effort, better design decisions, or prevented regressions. Those outcomes are to be validated with customers, not presumed.

**Q12. How much does scaling cost?**  
Mainly integration engineering, security, and experiment compute. To reduce our infrastructure cost, run expensive tests in the customer's staging cloud while charging for orchestration/evidence/automation. Any numerical budget is an estimate until workload and pricing research is done.

**Q13. Could optimization hide rare financial errors?**  
Yes; no finite test suite guarantees correctness. We preserve existing semantics with unit/property tests and narrowly defined invariants, state what was tested, and require human review before deployment.

**Q14. Are results general across machines?**  
No. Benchmarks are environment- and workload-specific. DARWIN reports source commit, hardware/runtime, dataset, repetitions and variation so claims can be reproduced.

**Q15. If your candidate is only 2% faster, is it a winner?**  
Not automatically. Improvement can be noise. The new verdict policy should show inconclusive when the evidence is too weak.

**Q16. Is your system a framework-comparison engine?**  
Not yet. It does not automatically rewrite Django into FastAPI or monoliths into microservices. It evaluates **specific supported design decisions**.

**Q17. How can I trust the live demo?**  
Look at the source SHA, synthetic fixture seed, actual test output, raw samples, correctness gates, and a recorded evidence bundle; live/recorded are always explicitly separated.

**Q18. What's your future roadmap?**  
First prove two adapters (local finance computation and backend checkout), then add generic **backend service adapters** such as FastAPI, Spring Boot and Node.js **only with verified workloads and invariants**, followed by secure private deployment and company pilots.

## L7. A simple 90-second live story

“Here is **Sanchay**, an actual project on GitHub. Rather than pretending every project is the same, DARWIN inspects it and identifies that it's a local-first finance app. It shows the data path: user interface → financial calculations → local storage. We choose its financial reporting operation and compare the current code with a candidate that reduces repeated calculations. Both run with the exact same fictional transactions, including refunds, and DARWIN checks every calculated total before comparing speed. Now the result tells us whether there is a verified gain, whether the original is still better, or whether the improvement is too small to trust. I can open the source diff and full evidence. Separately, DARWIN's existing backend lab runs actual checkout services and deliberately breaks them to catch duplicate payments. The key idea is: **no recommendation without measurement and correctness evidence.**”

## L8. Most important sentence

**“DARWIN is not magic GitHub optimization. It is a disciplined experiment engine that understands a supported project, measures a real design choice, and refuses to recommend an unverified change.”**

---

# PART M — Acceptance checklist for sign-off

- [ ] GitHub project import reads actual source at a pinned commit; provenance visible.
- [ ] Sanchay detected as React/WebView/localStorage; backend-only tests visibly unsupported.
- [ ] Genuine Sanchay report workload measured; original Sanchay source used for baseline.
- [ ] A real candidate implementation/diff is tested and wired into a real report call site (or it is transparently labelled function-level only), or an explicit no-candidate reason shown.
- [ ] Finance parity gates pass or reject candidly; no false winners.
- [ ] Results include workload, runtime, repetitions, median/spread, source SHA and diff hash.
- [ ] Quick-live and recorded-full results clearly distinguished; full searches remain available.
- [ ] Existing DARWIN checkout lab, NSGA-II search, fault tests, dashboards, themes and showcase unchanged in behavior.
- [ ] Repository code execution restricted to explicitly trusted adapters and isolated environments.
- [ ] Cancellation and failure cleanup verified.
- [ ] Automated backend/frontend tests and builds pass; results recorded in validation document.
- [ ] Nontechnical visitor can identify project → change → test → verdict in two minutes.
- [ ] Presenter guide and FAQ match actual implemented behavior, not plans.

---

## Source references inspected

- DARWIN repository: https://github.com/udbhavnc7/DARWIN
- DARWIN existing experiment instructions: https://github.com/udbhavnc7/DARWIN/blob/master/README.md
- DARWIN current exhibition scenarios: https://github.com/udbhavnc7/DARWIN/blob/master/backend/darwin/exhibition.py
- Sanchay repository and documented architecture: https://github.com/udbhavnc7/Sanchay
- Sanchay report operations: https://github.com/udbhavnc7/Sanchay/blob/main/web/src/utils/reporting.ts
- Sanchay local persistence: https://github.com/udbhavnc7/Sanchay/blob/main/web/src/data/persistence.ts
- Sanchay package/test scripts: https://github.com/udbhavnc7/Sanchay/blob/main/web/package.json
- ROUTELESS repository README: https://github.com/udbhavnc7/ROUTELESS/blob/main/README.md
- OpenCode instructions: https://opencode.ai/docs/instructions

**End of directive.**
