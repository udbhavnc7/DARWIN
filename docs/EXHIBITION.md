# Exhibition readiness and demo runbook

This document is the pre-flight and presentation record for the DARWIN demo. It captures the machine used, the exact commands run, the results observed, and the limits that must be stated honestly to an audience. It does not change the measurement engine or acceptance criteria.

Captured **2026-11-14** on branch `exhibition-readiness` (base `d486677`). Re-run the commands below on the presentation machine; recorded durations and readiness can differ.

---

## 1. Machine baseline

| Item | Value at capture |
| --- | --- |
| OS | Windows 10 (10.0.26300), x86-64 |
| CPUs / memory | 16 logical CPUs, 24,283 MiB |
| Python | 3.11.15 (`.venv`) |
| Node / npm | 20.20.1 / 10.8.2 |
| PostgreSQL | 18.4 (`initdb`, `pg_ctl` on `PATH`) |
| Redis | 8.8.0 |
| Toxiproxy | 2.13.0 (bundled at `.runtime/tools/toxiproxy-server.exe`) |
| Docker engine | **not running** (Linux engine pipe unavailable) |

Docker measurements and the containerized shop are therefore unavailable on this machine. Native smoke, benchmark, and fault runs are available. The UI disables Docker-only options instead of failing part-way.

### Readiness snapshot

```powershell
curl.exe http://127.0.0.1:8000/api/preflight?refresh=true
```

Observed summary:

```text
ready true
execution_modes native_smoke, native_benchmark, native_faults
capabilities     smoke=true benchmark=true faults=true docker=false

python          ready  3.11.15
node            ready  v20.20.1
postgres        ready  initdb (PostgreSQL) 18.4
redis           ready  Redis server v=8.8.0
demo_database   ready  The demo shop cluster is running.
demo_shop       ready  The interactive checkout shop is running.
docker          optional_missing  Docker measurements are disabled.
toxiproxy       ready  toxiproxy-server version 2.13.0
disk            ready  (free space at capture; value varies)
memory          ready  24283 MiB
```

The Overview page renders the same data as the **Machine readiness** panel. A missing optional tool is shown with a remedy; a missing required tool flips the panel to **Needs attention**.

---

## 2. Scenario catalog and observed durations

The four judge-facing presets are ordinary experiment requests. They use the same isolated sandboxes, repetitions, fault injection, and invariant gates as a manual run.

| Preset | Mode | Workload | What it proves | Duration source at capture |
| --- | --- | --- | --- | --- |
| Quick checkout smoke | `native_smoke` | normal | One order, one payment effect after a repeated request | 29 s recorded; **18 s live** |
| Normal baseline vs candidate | `native_benchmark` | normal | Measured latency, CPU, and recovery for two configurations | 184 s recorded |
| Flash sale comparison | `native_benchmark` | flash sale | Behavior under sustained concurrent checkout traffic | 88 s recorded; 180 s estimate |
| Payment timeout with unsafe retry | `native_faults` | normal | I-01 rejection and three payment effects for one key | 100 s recorded |

Durations come from matching completed records in the local experiment store; otherwise the UI says "estimated". A live run is always labelled as live evidence and can differ from these values.

```powershell
curl.exe "http://127.0.0.1:8000/api/exhibition/scenarios?runtime=native"
curl.exe -X POST "http://127.0.0.1:8000/api/exhibition/scenarios/quick_smoke?runtime=native"
```

Live validation on 2026-11-14:

- `quick_smoke` (`0054ab6c-7eac-436f-b6ec-885b25974084`) completed in **18 s** with 3 measured attempts and `cleanup_status: completed`.
- `unsafe_payment` (`ba096ae7-89d1-48e7-9dfb-6c141c06b820`) completed in **66 s**; all three repetitions were rejected by the gate with `business_invariant_failed`. The candidate has no objectives and is not ranked — the same honest rejection path used for the saved rejected example.

---

## 3. Saved-run fallback

The Search page can show a recorded example when the API or a live run is unavailable. The bundle is a compact export of real completed searches; it is not a mock and is never promoted as a new result.

- Bundle: `frontend/public/recorded-example.json` (~70 KiB), generated 2026-11-13.
- Feasible example: random search `fe3386fb…`, normal workload, 6 of 24 candidates measured feasible, 6 on the Pareto front.
- Rejected example: NSGA-II `e54c8fca…`, normal workload, 0 of 8 candidates feasible, rejections recorded as `recovery_not_observed`.
- The UI shows a **Recorded run** badge and a banner stating that these are saved measurements, not a live execution. Live-only links are hidden.
- **Open recorded feasible run** and **Open recorded rejection** are available above the results; the rejection view renders the same "No candidate passed all gates" panel used for a live empty search.

Regenerate the bundle from the local store (it performs no new experiments):

```powershell
.\.venv\Scripts\python.exe scripts/record_exhibition.py
```

The script prints the two selected search IDs. Confirm the frontend still builds after replacing the bundle.

---

## 4. No-feasible-candidate behavior

When a live search completes with measured candidates but none feasible, DARWIN shows an explicit verdict instead of an empty chart:

- "No candidate passed all gates" and why DARWIN does not rank rejected candidates.
- Gate reasons with counts (for example `recovery_not_observed`, invariant violations).
- The rejected candidates, each with an evidence inspector.
- Safe next choices: retry with a larger measured budget, switch workload, or inspect rejection traces. **None bypasses a gate.**
- A link to the recorded feasible run for comparison.

This was verified both with a real rejected search (`e54c8fca…`) and through the saved-run rejection action.

---

## 5. Demo shop proof

The interactive shop uses a dedicated PostgreSQL cluster under `.runtime/shop/` on loopback, synthetic products, and simulated payments. It never contacts a payment provider.

Validation on 2026-11-14, through the gateway:

```text
POST /shop/reset                     -> {"status": "reset"}
POST /shop/checkout (key K)          -> confirmed, order 8257a834…
POST /shop/checkout (same key K)     -> same order ID, same amount, stock unchanged
GET  /shop/ledger?request_key=K      -> orders 1, captures 1, payment_effects 1
GET  /shop/ledger                    -> totals also 1/1/1 after the reset
```

The Shop page shows the same counters after a repeat and includes **Reset demo shop**. Resetting only truncates the demo tables and restores initial stock.

> Do not point `DARWIN_DATABASE_URL` at a personal or production database. Integration tests additionally refuse any database whose name does not end in `_test`.

---

## 6. Presentation script (about 10 minutes)

1. **Overview → Machine readiness.** Point out required checks, execution modes, and any optional tool that is disabled. Press **Run preflight again** if the shop was just started.
2. **Experiments → Quick checkout smoke.** Start it; (~30 s) show the completed run, three repetitions, and gate status.
3. **Search → Open recorded feasible run.** Show the Pareto plot, 6 of 24 measured feasible, and candidate evidence. Then **Open recorded rejection** to show the honest no-feasible verdict and its gate reasons.
4. **Optional:** run **Normal baseline vs candidate** or **Flash sale comparison** if time allows (2–3 minutes). Do not promise a specific ordering; report what the run produces.
5. **Demo shop.** Reset, place an order, resend the same request. Show the identical receipt, unchanged stock, and ledger at 1 order / 1 capture / 1 payment effect.
6. Close with the boundary: local trusted-operator tool, measured evidence separated from simulation, and negative results retained.

If a live result differs from a recorded number, say so and investigate. Do not adjust thresholds or hide the run.

---

## 7. Validation record

| Check | Command | Result |
| --- | --- | --- |
| Fast test suite | `.venv\Scripts\python.exe -m pytest -q -rs` | **104 passed, 14 skipped** |
| Shop integration | `DARWIN_TEST_DATABASE_URL=…/darwin_shop_test pytest tests/test_shop.py` | **14 passed** |
| Type-check + production build | `npm --prefix frontend run build` | **passed** (`tsc --noEmit` + Vite) |
| Preflight API | `GET /api/preflight?refresh=true` | **ready: true**, required checks green |
| Scenario API | `POST /api/exhibition/scenarios/quick_smoke` | completed, 3 attempts, cleanup completed |
| Shop idempotency + ledger | repeat checkout with one key | 1 order / 1 capture / 1 effect |

The 14 skips are PostgreSQL/Redis integration tests that require an explicit dedicated database. They are skipped, not passed. Run them against `darwin_shop_test` (or another disposable `*_test` database) as shown.

Build note: the lazy-loaded Three.js scene is a separate 528 kB chunk, so Vite warns about the 500 kB threshold. It does not affect initial dashboard load.

---

## 8. Known limits and risks

- **No authentication or isolation.** The API and shop bind to `127.0.0.1` and assume a trusted operator. Never expose them to a shared network or the internet.
- **Docker is optional here.** Docker measurements and the containerized shop stay disabled while the daemon is unavailable. The preflight panel says so rather than failing mid-run.
- **Native faults are Windows-specific.** On Linux, use the Docker runtime.
- **Single-seed search evidence.** Recorded comparisons use one seed per strategy; they support the demo, not a general algorithm ranking.
- **Recorded bundle timestamp.** It reflects the local store on 2026-11-13. Regenerate it if the store gains a better example.
- **No CI yet.** Tests and builds are run locally; CI and packaging are the next phase.
- **Historical artifacts are evidence.** Do not delete or overwrite `artifacts/` while troubleshooting.

---

## 9. Troubleshooting

| Symptom | Checks |
| --- | --- |
| New endpoints return 404 | Restart the control plane so it loads the current backend. |
| Scenario card disabled | Preflight shows the selected runtime as unavailable; switch runtime or install the missing tool. |
| Recorded example does not load | Build/serve the frontend so `/recorded-example.json` is reachable, then retry; regenerate with `scripts/record_exhibition.py`. |
| Demo shop disconnected | Start `scripts/run_shop.py`; confirm ports 8010/8011/8012/8013 and 55432 are free and loopback-only. |
| Ledger unavailable | The shop must be restarted on current code; confirm `GET /shop/ledger` returns JSON. |
| Docker options missing | Start Docker Desktop with a Linux engine and cgroup v2; press **Run preflight again**. |
