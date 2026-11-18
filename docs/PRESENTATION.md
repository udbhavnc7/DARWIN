# Presenting DARWIN

A page-by-page script for demonstrating the dashboard, plus the timing plan that keeps a live measurement from turning into an awkward silence. Every number and label below matches the running app; recorded and live values are kept separate on purpose.

---

## 1. The 30-second pitch

DARWIN is an **architecture experimentation laboratory**. It does not replace AWS, Kubernetes, Redis, Locust, Prometheus or chaos tools; those provide the pieces. DARWIN coordinates one decision: which architecture should carry the next 10,000 users.

It builds deployable alternatives, runs them under simulated traffic, injects failures, verifies the business rules, then searches the measured trade-offs across latency, CPU time and recovery. Simulation is used to screen candidates, never to declare a winner. Every result is saved with seeds, artifacts, hashes, and a replay command.

The sentence that anchors the whole demo:

> A fast configuration that double-charges a customer is not a winner. It is a rejected candidate with evidence.

The six stages you are demonstrating:

1. **Overview** — frame the decision: which configuration should carry the next 10,000 users?
2. **Project Workspace** — pin one exact commit and map the services, data stores, cache and workers.
3. **Architecture** — shape deployable candidates: replicas, cache TTL, notification delivery, retry policy.
4. **Experiments** — push seeded traffic through each candidate, inject failures and verify the five business invariants.
5. **Evolution** — NSGA-II, random or hill climbing; failed candidates never enter the ranking.
6. **Solution** — deliver a verdict with the measured trade-off, a reviewable change, rollback notes and an evidence bundle.

Three claims you can defend on every page:

1. **Measured, not estimated.** Candidates are deployed into isolated sandboxes and timed.
2. **Correctness before speed.** The five invariants run before performance is allowed to count.
3. **Negative results stay.** Empty Pareto fronts, failed gates, and interrupted runs are shown rather than hidden.

---

## 2. One hour before the talk

### Start the bench

```powershell
# From the repository root
.\.venv\Scripts\python.exe scripts\demo.py start
.\.venv\Scripts\python.exe scripts\demo.py status
```

`status` should show `ready=true`, the Database/Shop/Python/Node/Toxiproxy checks green, and `api`, `shop`, `ui` listening. Open **http://127.0.0.1:5173/**.

The API and shop are loopback-only. Keep them on `127.0.0.1`; never expose them to the venue network or the internet, and never point `DARWIN_DATABASE_URL` at a personal database.

### Warm the evidence

The local bench already holds 68 experiments and 13 searches, including a feasible run with six Pareto candidates and a rejected run with zero. Do not rely on an empty history.

Before the audience arrives, run two things so you never wait on stage:

1. **Quick checkout smoke** (`Experiments → Quick checkout smoke`). About 20–30 seconds natively. This also proves the shop and database are healthy.
2. **Normal baseline vs candidate** (`Experiments → Normal baseline vs candidate`). About 2.5–3 minutes natively. Let it finish; you will present its result from the saved-run picker.

Do **not** run a measured search for the first time on stage. The default six measured attempts takes minutes, and Docker searches have taken over 12 minutes.

### Stage setup

- Open the local dashboard in the presentation browser, not the hosted page, unless you specifically want to demonstrate the showcase.
- If you must present from **https://udbhavnc7.github.io/DARWIN/**, you can present the recorded evidence with no setup at all — no install, Docker or running server is needed. For live runs, start the bench first and press **Connect this computer**. Allow Chrome's local-network prompt immediately. Keep `scripts/demo.py` running for the whole session. If the bench stops, the page returns to recorded evidence automatically; **Disconnect** does the same on demand.
- Zoom to 110–125%. At 125% the sidebar, metrics, and tables stay readable on a projector.
- Choose **Lab appearance** once: **Green Texture** is the safest projector palette; **Carbon Black** works in a dark room; avoid palettes that wash out on your projector.
- Close chat and notification popups. Disable sleep. Plug in power.
- Keep a second tab open with the hosted showcase in recorded mode. If your local bench fails mid-talk, the audience can still browse saved evidence there and you can keep narrating.
- Optional: if you plan to show the Docker runtime, start Docker Desktop before the talk and confirm **Machine readiness** shows Docker ready. On this machine Docker is currently reported as optional-missing, so the Native runtime is the reliable path.

### Rehearsal target

Rehearse the 10-minute script twice. The hard part is not the clicking; it is **starting a run and leaving it alone while you talk about something else**. Practice that transition.

---

## 3. The idea you are demonstrating

One checkout application. Four supported controls. Three workloads. Three fault families. Five invariants.

| Control | Options | What changes |
| --- | --- | --- |
| API replicas | 1, 2, 3 | Stateless checkout instances behind the gateway |
| Catalog cache | Off, 10 s, 30 s | Redis cache for descriptive catalog reads; prices and stock stay authoritative |
| Notifications | Synchronous, Queued | Inline delivery, or a transactional outbox drained by a worker |
| Retries | None, Idempotent-only | Transient retries reuse the original request key; unsafe retries exist only in a deliberately vulnerable fixture |

| Workload | Story |
| --- | --- |
| Normal traffic | Mixed catalog and checkout traffic at a steady rate |
| Flash sale | Sudden demand concentration with stock contention |
| Checkout heavy | Checkout-dominant traffic stressing payment and inventory |

| Fault family | What it does |
| --- | --- |
| Database delay and disconnection | Toxiproxy in front of PostgreSQL |
| Application service outage | A service disappears during live checkout traffic |
| Ambiguous timeouts and duplicate delivery | A lost reply is retried; the unsafe fixture retries without idempotency |

| ID | Invariant |
| --- | --- |
| I-01 | At most one successful capture per payment idempotency key |
| I-02 | Confirmed quantities never exceed seeded stock |
| I-03 | Every confirmed order references a successful capture for its exact amount |
| I-04 | Replaying a key creates no extra business effects; a changed payload is rejected |
| I-05 | Completed notifications have receiver evidence; accepted jobs survive a specified worker failure |

The loop you are showing: **design → screen (simulator) → deploy → measure → break → verify → evolve**. The simulator is a screening tool with a measured 27% mean absolute p95 error across nine held-out repetitions; it can suggest what to test, but it cannot produce a winner.

### 3.1 Positioning you can repeat

- **A lab, not a replacement.** AWS, Kubernetes, Redis, Locust, Prometheus and chaos tools provide infrastructure, caching, load and failure injection. DARWIN coordinates them into one decision workflow.
- **The differentiator is not any single technique.** It is the combination: deployable alternatives → simulated traffic → injected failures → business-correctness gates → multi-objective search, all attached to evidence.
- **The decision is the product.** The output is not a prettier diagram; it is an evidence-backed recommendation, or an honest "no winner in this run".
- **The fastest candidate can lose.** In the illustrative A/B/C example, the ₹35,000 distributed option is fastest and still rejected because it double-charges. Costs shown there are hypothetical, clearly footnoted; the rule is what matters.
- **Today versus next.** Today: a controlled checkout lab plus two pinned public backends and a guided evaluation. Next: connect arbitrary repositories, auto-understand more frameworks and data stores, execute in isolated cloud environments, compare infrastructure costs, recommend and deploy. The app labels this boundary; repeat the label.

### 3.2 Check your understanding

Five questions to ask the audience (answers below):

1. What decision is DARWIN built to support?
2. Why is the fastest configuration sometimes rejected?
3. Are the ₹10,000 / ₹20,000 / ₹35,000 costs real measurements?
4. What runs today, and what is roadmap?
5. What does the search optimize, and what never enters the ranking?

Answers:

1. Which architecture should carry the next 10,000 users — with measured evidence rather than intuition.
2. Because it failed a business invariant, such as duplicate payment or overselling. Correctness is a gate, not a weight.
3. No. They are hypothetical numbers in an illustrative example; the app footnotes this.
4. Today: the controlled checkout lab, two pinned public backends, guided evaluation, experiments, search and the demo shop. Roadmap: general-purpose repository optimization, cloud execution and cost comparison.
5. Latency, CPU time and recovery time. Candidates that fail correctness never enter the Pareto ranking.

---

## 4. Opening (45 seconds)

The app opens with the three.js calibration intro: five gate frames assemble over the test deck, a measuring beam verifies them, then the workspace takes over. It lasts under four seconds and appears once per browser session.

Say:

> This is the bench calibration: the five gates are the first thing the app shows, because in this lab correctness comes before speed. Everything after this is measured evidence.

Press **Esc** or **Skip to workspace** if you are short on time. If the intro is not visible because the tab was already open, replay it from **Lab appearance → Replay calibration**, or open a fresh tab at `?splash=1`.

Then choose your audience:

- **Non-technical:** open **What is DARWIN?** (sidebar) and step through the six tour panels — Overview, Project Workspace, Architecture, Experiments, Evolution, Solution — about 90 seconds. Use arrow keys; close with **Done**.
- **Technical:** skip the tour. The **Overview** page carries the same story in one scroll.

---

## 5. Page-by-page script

### 5.1 Overview (home)

**What is on screen**

- Hero: **"Growth forces a decision. Evidence settles it."** with the *Illustrative decision* board — three configurations, **A Basic**, **B Cached** (choose), **C Distributed** (rejected), and the verdict *"C fails the duplicate-payment rule. The fastest configuration does not win."*
- **One server works. Then the traffic arrives.** The growth story, failure symptoms, and the question *"Which configuration should carry the next 10,000 users?"*
- The illustrative A/B/C table: shape, **hypothetical** monthly cost (₹10,000 / ₹20,000 / ₹35,000), response time, recovery, duplicate-payment pass/fail, and the decision. The footnote says it is an example of the decision rule, not a DARWIN result.
- **One project, from question to solution**: Overview → Project Workspace → Architecture → Experiments → Evolution → Solution. Each card links to the page that performs that stage.
- **Why not just AWS, Kubernetes and load tests?** A comparison table: what each existing tool gives you, what it does not decide, and DARWIN's row.
- **What this lab is today — and what it is not yet**: implemented versus roadmap, explicitly labelled.
- **The analogy**: you would not choose a racing engine by guessing; you would build a test bench.
- **What you can run right now**: the baseline checkout stack, execution environment, and **Machine readiness**.

**Clicks**

1. Press **Start in the Project Workspace** to enter the guided flow. (Alternatively, **See the six stages** scrolls to the stage cards.)
2. Scroll through the illustrative decision and read the footnote aloud. Use **C** to make the central point: fastest, rejected.
3. Scroll to the six stage cards and name the page that performs each stage.
4. Point at the scope cards: left is implemented, right is roadmap.
5. Finish on **Machine readiness** and the baseline stack.

**Say**

> The system under test is a working checkout backend: gateway, API, PostgreSQL, inventory, and a mock payment service. The four controls on the Architecture page are the only things that vary between candidates, so comparisons stay fair. The Overview page states the direction of the product: a lab that sits alongside AWS, Kubernetes and load tests, not a replacement for them. The costs in the table are hypothetical on purpose; the decision rule is the point. Readiness is checked before anything runs — a missing dependency disables the run instead of failing halfway through it.

**Do not claim** that the A/B/C monthly costs or response times are measured DARWIN results. They are illustrative. Readiness is a tool check, not a security check.

---

### 5.2 Architecture (the builder)

**What is on screen**

- **Configuration** with the four controls, **Reset to baseline**.
- **Service topology** preview with service and connection counts and a live graph.
- Buttons: **Use in experiment**, **Simulate performance**, **Download Compose file**.
- **Simulated performance** card after simulating: estimated p95, throughput, calibration status, any held-out error.

**Clicks (do this deliberately; each change redraws the topology)**

1. Set **API replicas** from 1 to 3.
2. Set **Catalog cache** to 10 seconds.
3. Set **Notifications** to Queued worker.
4. Point at the topology summary changing: services, connections, replicas, and the genome hash under the details row.
5. Press **Simulate performance**. Read the estimate and the calibration label. Point at "Correctness gate unchecked."
6. Press **Use in experiment**. This carries the configuration into Experiments as **Custom architecture**.

**Say**

> Each configuration is a typed genome, not a pile of YAML. The topology and the Compose file are generated from it, and the hash identifies exactly what will be deployed. The simulator is fast and useful for screening, but look at what it says itself: the correctness gate is unchecked. A simulation can tell me what might be fast; only a measured fault run can tell me whether it is safe. That is why the next page exists.

**Numbers you can use**

- The simulator's held-out p95 error is 27.0% mean absolute across nine repetitions, with one cached-normal holdout missing by 53.9%.
- Every configuration in the 1–3 replicas × 0/10/30 s cache × sync/queued × none/idempotent space is previewable and exportable.

**If the preview says "Updating your architecture"** wait a beat; the preview is debounced. If it errors, press **Retry preview**; if the API is offline, the page explains it.

---

### 5.3 Experiments (run and break it)

**What is on screen**

- The page is framed as **Stage 04 · Experiments**: measure under simulated traffic, then inject database delays, outages and duplicate requests. Timing only counts after the invariant gate.
- **Judge-ready scenarios**: Quick checkout smoke, Normal baseline vs candidate, Flash sale comparison, Payment timeout with unsafe retry. Each card shows its duration and whether the duration is recorded or estimated.
- **New experiment**: type selector (Compare performance, Verify failure recovery, Unsafe retry fixture, Checkout smoke check), configuration selector (preset, baseline, or custom architecture).
- **Validate request** and **Start**.
- **Run history** with a saved-run picker.
- A run card with status, attempts started, cleanup, and expandable events.
- Per-candidate cards with median (min–max) metrics, gate badges, and expandable repetitions containing gate reasons, invariant violations, recovery times, and evidence links.

**The honest framing**

> Three isolated repetitions per configuration. Every repetition is deployed into a fresh sandbox. The gate runs on recorded business state; performance only counts after the gate passes.

**Recommended live demonstration: Quick checkout smoke**

1. Under **Judge-ready scenarios**, press **Quick checkout smoke**.
2. While it runs, point at **Attempts started**, **Cleanup**, and **Experiment events**. The page polls; you do not need to refresh.
3. When it completes, expand a repetition and show the gate result and evidence links.

Native takes roughly 20–30 seconds. Docker takes roughly 2 minutes because each repetition deploys and tears down an isolated Compose project. Do not promise a number; say "about half a minute natively" and report what you see.

**The showpiece live demonstration: Unsafe retry fixture**

Use this only if you have 1–2 minutes and want the strongest correctness story.

1. Set **Experiment type** to **Unsafe retry fixture**.
2. Start it.
3. While it runs, explain the setup: lose the payment reply, retry without idempotency, then inspect the ledger.
4. On completion, show the gate rejection: **I-01**, three payment effects for one request key, all repetitions.

Recorded evidence: the unsafe fixture measured 408.4 ms median p95 versus 483.0 ms for the safe configuration, and was rejected anyway. A fresh dashboard rerun reproduced the rejection in all three repetitions.

**The saved-run demonstration: Normal baseline vs candidate**

If you pre-ran it, use the **Saved experiments** picker and select it instead of starting it live. Show:

- Both configurations, three repetitions each.
- Median and min–max spread for p95, requests/s, errors, CPU seconds, peak MiB.
- The gate badge on each candidate.
- One repetition's evidence links.

Recorded Docker result: baseline median p95 102.75 ms versus 77.65 ms for the three-replica cached candidate, zero measured errors. A live native comparison will produce different absolute numbers on this laptop; say that before you show it.

**Say, if a run fails or is slow**

> This is a real measurement, so it can fail for real reasons. The run keeps its events and artifacts, and I can rerun the configuration. I would rather show you a failed run than a fabricated number.

**Do not** cancel a run just because it is taking longer than expected. Report progress and keep narrating. Cancellation exists, but using it on stage undercuts the evidence story.

---

### 5.4 Evolution (search)

**What is on screen**

- The page is framed as **Stage 05 · Evolution**: NSGA-II, random search and hill climbing propose candidates; the simulator screens them; correctness failures never enter the ranking.
- **Evolution setup**: method (NSGA-II, Random search, Hill climbing), measured attempts (6, 12, 18), seed.
- **Start measured search**.
- **Evolution results**: saved-search picker, recorded-run buttons, run card, Pareto chart, candidate table, inspect dialog, lineage.

**This is the heart of the talk. Present it from saved evidence.**

**Clicks**

1. Press **Open recorded feasible run** (or pick the feasible search from **Saved searches**).
2. Point at the run cards: generation, runtime, workload, seed, measured attempts started, candidate count, feasible count, search overhead.
3. Point at the Pareto plot: p95 on the vertical axis, application CPU seconds on the horizontal. Filled points are the Pareto front.
4. Select a filled point, or press **Inspect** in the table. In the dialog, show the metrics, the service topology, the repetition details, and **Open in Architecture**.
5. Close the dialog. Change **Evidence** to **Screened** and back to **All**. Show that simulated candidates are labeled "Simulated · screened" and never appear as feasible winners.
6. Press **Open recorded rejection**.
7. Walk through the verdict panel: "No candidate passed all gates", the rejection reasons with counts, the rejected candidates, and the three safe next choices.

**Say**

> Search proposes candidates with NSGA-II, random search, or hill climbing. The simulator screens them cheaply; only promoted candidates get real runs. Notice the three evidence labels: simulated, measured, and rejected. A simulated number is never allowed to win. In this feasible run, six of twenty-four measured candidates passed every gate and form the Pareto front. This rejection is just as important: eight candidates were measured, none passed, so there is no honest winner. DARWIN says that instead of quietly showing a "best" bar. The safe next steps are more measured attempts, a different workload, or inspecting the rejection trace — none of them bypasses a gate.

**Recorded references**

- Feasible: random search, 24 candidates, 6 feasible, 6 on the Pareto front.
- Rejected: NSGA-II, 8 candidates, 0 feasible, rejections recorded as `recovery_not_observed`.
- Three-seed campaign: 11 of 12 searches completed, 68 measured attempts in about 1.3 hours. NSGA-II with simulation had the lowest median-of-best p95 at 357.2 ms, then hill climbing at 394.6 ms, random at 407.6 ms, NSGA-II without simulation at 445.1 ms. This is one host with varying seeds, not a general algorithm ranking.

**If you do run a live search** (only with a rehearsed slot): use 6 measured attempts natively and expect minutes, not seconds. Docker search has taken 12 minutes 52 seconds. Explain the progress counter while it runs, and use **Cancel search** only if you intend to talk about cancellation.

**If no candidate passes on a live search**, treat it as the intended verdict. Read the reasons, open a rejection trace, use a safe next choice. Do not retry repeatedly on stage hoping for a better result.

---

### 5.5 Solution (the decision record)

**What is on screen**

- The page is framed as **Stage 06 · Solution**: the outcome of one pinned project, ready for a team to act on.
- A **decision selector** listing recorded and live project evaluations (project, commit, verdict, date).
- A **decision card** with the verdict label and reason, the source repository and pinned commit, the challenge,
  the mode, the correctness checks (for example 3/3), the evidence kind and the recorded date.
- Measured panels: original versus recommended median, p95 and the percentage change; the cost of the change
  when a metric regressed.
- **Recommendation** and **evidence to keep**: the reviewable change with rollback notes, and the evidence files
  with their digest prefixes.
- A **truth boundary** panel: what the decision carries, and what it does not claim.
- When the page is connected to a live bench, **Download evidence bundle** is enabled. In the hosted showcase it
  reads the recorded evidence and keeps the download disabled rather than pretending.

**Clicks**

1. Open **Solution** from the sidebar. The newest recorded evaluation is selected.
2. Read the verdict label and reason aloud. Point at the correctness count and the evidence kind.
3. If the selector has a simulated screening entry, choose it and show the warning: **SIMULATED · NOT MEASURED**,
   no measured latency panels, and no promotion to a winner.
4. Choose a measured improvement or trade-off entry. Point at the original-versus-recommended numbers and any
   regressed metric — a win on latency never hides a cost.
5. Read the recommendation, then the truth-boundary column: one host, one workload window, reviewable change,
   no automatic edit.
6. Finish by pointing back to **Project Workspace** to run a fresh comparison.

**Say**

> The last stage is the one a team actually needs: not a chart, but a decision with its evidence and its way back.
> This verdict kept the original configuration because the improvement did not clear the policy threshold — and the
> page says so instead of inventing a winner. When there is a change, it is a reviewable diff with rollback notes;
> DARWIN never edits or pushes the repository. The numbers are measured on this host for this workload, and the
> page states that limit rather than turning one run into a production promise.

**Do not claim** that a recorded verdict is a fresh measurement, or that a simulated recommendation is deployable
evidence. The badge on the card is the authority; read it before the number.

---

### 5.6 Example lab (demo shop)

**What is on screen**

- The page is framed as **Example lab · Verify correctness**: the checkout walkthrough is the smallest reproduction of the invariant gate.
- Shop connection status and **Reset demo shop**.
- Three steps: Place a demo order, Resend the same request, Compare the results.
- **Checkout** with product, quantity, simulated credits, stock.
- **What the shop returned** with a comparison table, verdict, and payment ledger.
- An expandable "How this connects to DARWIN's architecture".

**Clicks (30–45 seconds)**

1. Press **Reset demo shop** if the previous run left data. This only resets demo tables and restores initial stock.
2. Choose a product and quantity, press **Place demo order**.
3. Read the receipt: order ID, simulated payment, remaining stock.
4. Press **Resend same request**.
5. Point at the comparison table: same order ID, same amount, unchanged stock.
6. Point at the verdict and the ledger: 1 order, 1 capture, 1 payment effect, and "The repeat added no second effect."
7. Optionally expand **Request details** to show the idempotency key.

**Say**

> This is a real checkout against a real PostgreSQL-backed shop with simulated payments — no payment provider is contacted. The request carries an idempotency key. When I resend the same request, the backend returns the original order instead of charging again. One order, one capture, one payment effect. That is I-01 and I-04 in miniature, and it is the behavior the unsafe fixture deliberately breaks.

**Do not claim** that this is a production payment flow. It is a test shop with synthetic products and simulated payments.

---

### 5.7 Closing (30 seconds)

> DARWIN is not a diagram tool and not a load-test dashboard. It closes the loop: design a real backend, measure it, break it, verify the business rules, and evolve the ones that survive. Simulation only screens. Rejected candidates keep their evidence. The system runs locally on loopback with an optional shared token; it is not a hosted service, and it does not handle real payments.

If asked about readiness: MVP complete, about 82% of production readiness. The remaining gaps are per-user security and isolation, release automation, cross-platform native fault injection, multi-host validation, packaging, and an updated walkthrough video.

---

## 6. Presenting when processing takes time

This is the part that decides whether the demo feels professional. Never let the audience watch an empty progress bar in silence.

### Rule 1: pre-run the slow evidence

Run the benchmark, the fault verification, and any search **before** the talk. Present those results from **Saved experiments** and **Saved searches**. The audience sees the evidence, not the wait.

### Rule 2: keep exactly one live run in flight

Choose one live measurement for credibility — usually **Quick checkout smoke** (about 20–30 seconds). Start it, then immediately move to another page while it runs. The Experiments page keeps polling in the background; when you return, the result is there.

### Rule 3: choreograph the wait

Start the run, then use the time for content that does not depend on it:

| Start this | While it runs, show | Return to |
| --- | --- | --- |
| Quick checkout smoke | Architecture controls and topology, then the readiness panel | Experiments result and gate |
| Normal comparison (pre-run preferred) | Evolution recorded feasible run | Experiments metrics |
| Fault verification (pre-run preferred) | Example lab idempotency | Experiments gate rejection |
| Live search (only if rehearsed) | Example lab, then Architecture export | Evolution Pareto and candidates |

The transition sentence matters:

> I have just started a real measurement. While the sandbox deploys, let me show you the part that decides which candidates are even allowed to compete.

That is honest, it explains the wait, and it gives the audience a reason to follow you to the next page.

### Rule 4: report progress, do not invent it

The run card shows attempts started and expandable events. Quote those. If you do not know the remaining time, say:

> It is still on repetition two of three. The duration depends on the machine; I will report the measured number when it finishes.

Never promise "about ten more seconds" unless you know.

### Rule 5: plan for a slow or failed run

If a run exceeds your comfortable window, keep talking and check back once. If it fails, open the events, explain the failure, and show the rerun action. A failed run is still evidence. Have the recorded feasible and rejection search examples ready as the no-wait fallback.

### Realistic durations on this machine

| Run | Observed / recorded | Present it how |
| --- | --- | --- |
| Quick smoke, Native | 18–30 s | Live is fine |
| Quick smoke, Docker | about 114 s | Live only if you have a Docker story |
| Normal comparison, Native | about 154–184 s | Pre-run, present saved |
| Flash sale, Native | about 88 s recorded | Pre-run, present saved |
| Fault verification, Native | about 66–98 s | Pre-run, or live with narration |
| Unsafe fixture, Native | about 66–98 s | Live is the strongest 90-second moment |
| Normal comparison, Docker | about 328–446 s | Pre-run only |
| Measured search, 6 attempts | minutes; Docker search reached 12 min 52 s | Pre-run only |

These are this project's observed numbers, not guarantees. State them as recorded values and report live results as they are.

---

## 7. The 10-minute script

| Time | Page | Action | Point |
| --- | --- | --- | --- |
| 0:00 | Splash | Let it play, or skip | Gates before speed |
| 0:20 | Overview | Decision board, six stages, scope cards | Lab alongside your stack; fastest can lose |
| 1:30 | Architecture | Change replicas, cache, notifications; simulate | Four controls; simulation is screening only |
| 3:00 | Experiments | Start **Quick checkout smoke**; leave it running | One live measurement, started early |
| 3:20 | Evolution | **Open recorded feasible run**; inspect a Pareto point | Measured vs simulated; the Pareto front |
| 5:40 | Evolution | **Open recorded rejection** | No honest winner; gates are hard |
| 6:15 | Solution | Latest verdict, correctness count, change and rollback, evidence files | The last stage is a decision, not a chart |
| 7:00 | Experiments | Return; show smoke result, repetitions, gate, evidence | The live run finished while we talked |
| 8:00 | Example lab | Reset, order, resend, compare, ledger | Idempotency in one request key |
| 9:20 | Any | Closing boundary | Local, honest, negative results retained |

If the smoke is still running at 7:00, show the progress and events, then continue to the shop. Do not stall.

---

## 8. The six-minute version

1. **Overview** (40 s): the decision board, the six stages, and the scope line — "this is the lab today, that is the roadmap".
2. **Architecture** (45 s): change three controls, simulate, point at "Correctness gate unchecked."
3. **Evolution** (2 min): recorded feasible run, one Pareto point, then recorded rejection.
4. **Solution** (45 s): the latest verdict, correctness checks, change and rollback, evidence bundle.
5. **Example lab** (1 min): order, resend, ledger.
6. **Close** (30 s): measured evidence, correctness before speed, local-only.

Skip the live experiment entirely. Show the pre-run smoke from **Saved experiments** if you need a completed run.

---

## 9. Cue card (keep this open)

```
OPEN      http://127.0.0.1:5173   (bench: scripts\demo.py start)

1. Overview      decision board + six stages + scope cards
2. Architecture  3 replicas, 10s cache, queued -> simulate
                 "Correctness gate unchecked" -> Use in experiment
3. Experiments   Quick checkout smoke (start, LEAVE IT RUNNING)
4. Evolution     Open recorded feasible run -> inspect a filled point
                 -> filter "Screened" -> Open recorded rejection
5. Experiments   back to results -> repetitions -> gate -> evidence
6. Solution      latest verdict -> correctness -> change/rollback -> evidence
7. Example lab   Reset -> Place order -> Resend -> 1/1/1 ledger
8. Close         local-only, gates before speed, negative results kept

WAIT PHRASE  "While that measures, here is what decides who competes."
FALLBACK     hosted showcase in recorded mode; saved experiments/searches
NEVER        promise exact duration; claim production SaaS; expose 127.0.0.1
```

---

## 10. Questions you should expect

**"Is any of this mocked?"**
The checkout backend, database, cache, gateway, fault proxy, and measurements are real. Payment is a simulated provider by design, products are synthetic, and the shop is a test shop. Every result is labelled recorded or live, and artifacts carry hashes.

**"Why only four controls? Why not let me change everything?"**
A typed, hashed genome keeps comparisons fair and the search space tractable. Request timeout is intentionally fixed rather than becoming a fifth control. Unsupported combinations are rejected before deployment.

**"Why did you reject the faster configuration?"**
Because it produced three payment effects for one key. The unsafe fixture measured 408.4 ms median p95 versus 483.0 ms for the safe path and was still rejected under I-01. Correctness is a gate, not a weight.

**"Your simulator is 27% off. Why use it at all?"**
As a screening tool, to spend the real-run budget where it matters. It never produces a winner. Measured runs decide.

**"Why does search sometimes find nothing?"**
Because the gates are hard and search is stochastic. The project keeps the zero-feasible result, shows the rejection reasons, and offers safe next steps: more measured attempts, a different workload, or inspecting the trace. It does not lower a threshold to manufacture a winner.

**"How is this different from a load test or a chaos tool?"**
It does not replace them. AWS, Kubernetes, Redis, Locust, Prometheus and chaos tools supply infrastructure and raw signals. DARWIN closes the loop around one decision: it proposes architectures, screens them, deploys them, measures them, injects faults, verifies business invariants, and evolves the next generation. The gate and the evidence record are the point.

**"Why not just use AWS, Kubernetes, Redis, Locust and Prometheus?"**
Each answers a different question: capacity, orchestration, caching, load, observability, failure injection. None of them decides which configuration is correct and fast for your workload. That coordination, the correctness gate, and the retained evidence are what DARWIN adds. It is a lab next to those tools, not a competitor.

**"Can it run on Kubernetes or in the cloud?"**
Not yet. Docker Compose is the current deployment target, and Compose export is built in. Cloud adapters are a later extension.

**"Is this production-ready?"**
MVP complete, about 82% of production readiness. No per-user accounts, quotas, or project isolation; local trusted-operator tool; API and shop on loopback; optional shared token. Do not present it as a multi-tenant service.

**"Are those search rankings a general claim about algorithms?"**
No. They are one host with three seeds on the normal workload. Seeds vary schedules, not hardware. The report says so explicitly.

**"What happens if the audience machine has no Docker?"**
Native smoke, benchmarks, and faults run on Windows. Docker is optional and preflight disables what is unavailable. On Linux, use Docker for measured and fault runs.

---

## 11. Failure playbook

| Symptom | What to do | What to say |
| --- | --- | --- |
| Hosted page notes that no local bench answered | Nothing is broken: the page keeps working on recorded evidence. For live runs, start `scripts/demo.py start`, allow the local-network prompt, press **Try again** | "The hosted copy runs on recorded evidence; connecting the laptop's bench is optional for live runs." |
| API offline banner | `scripts/demo.py status`, restart if needed, **Refresh runtimes** | "The control plane is not answering; the dashboard will reconnect." |
| Docker options disabled | Use Native; do not switch runtimes mid-run | "Docker is optional on this machine; Native measurements are available." |
| Scenario card disabled | Preflight says the runtime is unavailable | "The preset is disabled rather than failing halfway." |
| Run fails | Open events; show the failure; rerun or use a saved run | "That is a real failure with retained evidence, not a hidden one." |
| Search stuck on progress | Read generation and attempts; cancel only if intended | "Search is still measuring; the budget is six real attempts." |
| No feasible candidates | Show the verdict and reasons; use a safe next choice | "No honest winner exists in this run." |
| Shop catalog offline | `demo.py status`, shop restart, **Refresh catalog** | "The shop is a separate local service; the rest of the lab is unaffected." |
| Projector crops the UI | Zoom out one step; the layout is responsive to 360 px | "The workspace reflows; here is the same content at a smaller width." |
| Intro replays unexpectedly | It runs once per session; `?nosplash=1` suppresses it | "That is the calibration intro; it only runs once per session." |

---

## 12. Boundaries to state out loud

- Local trusted-operator tool, not a hosted multi-tenant product.
- Loopback-only API and shop; optional shared token; no accounts or quotas.
- Simulated payments and synthetic products; never real customer data.
- The simulator screens; it does not prove.
- The A/B/C costs and response times on the home page are hypothetical illustrations of the decision rule, not measurements.
- The "what is next" column is the roadmap; do not describe general-purpose repository optimization as shipped.
- Search rankings are bounded to one host and the recorded seeds.
- Docker timings depend on the engine and host.
- Historical artifacts are evidence; do not delete or overwrite them while troubleshooting.
