# Phase 9 — Dashboard

The dashboard supports bounded measured search, saved search history, live event polling, cancellation and reruns. Each candidate shows its configuration and evidence status. Completed feasible candidates appear in a latency-versus-CPU chart, with Pareto membership determined using latency, CPU and recovery together. The table also exposes recovery time.

Candidate inspection renders the genome's generated service topology through React Flow. The lineage view links proposed candidates to their recorded parent hashes and organizes generations vertically. Rejected candidates expose gate reasons, invariant IDs and the original artifact downloads. The experiment panel can rerun individual configurations, display lifecycle events and refresh saved history.

Simulated values explicitly show their tier and calibration status. Pending or rejected candidates have no measured objective values in the tradeoff table. An empty feasible front displays a message explaining that no complete configuration has passed all measured gates.

The architecture builder updates the React Flow topology as the controls change. It can simulate the current configuration, download its Docker Compose file, or transfer the exact configuration into Experiments for checkout, performance, or recovery testing. Both drafts survive a refresh in the same browser tab. Downloaded Compose files build from the DARWIN checkout. Place the file at the repository root or supply the checkout path with `docker compose --project-directory`.

Overview, Architecture, Experiments, Search, and Demo shop each have a dedicated workspace view. A five-step product tour explains the lab end to end: the design-measure-verify-evolve loop, the shared checkout stack and its four controls, the correctness gate, how search screens and proves candidates, and where to start. It opens from the sidebar, from **How DARWIN works** on the overview, or from the compact **Tour** action on small screens, and `?tour=1` links straight to it. The tour is a modal dialog with labelled steps, arrow-key navigation, step dots, focus handling, and links into each workspace. Direct result links open without it.

The theme picker applies Greenhouse (white and green), Hazard (black and yellow), Rosewire (red and pink), Terracotta (brown and beige), or Ink & Paper (white and black) across the workspace. The browser remembers the selected palette. The overview uses a palette-aware Three.js server assembly, with a CSS illustration available when WebGL is unavailable.

The layout is responsive: below 800 px the navigation becomes a compact sticky header with a horizontally scrollable section bar, the theme picker stays on the title row, and the tour, builder, experiment, shop, and result tables stack into single-column layouts. Run settings appear only on Architecture, Experiments, and Search, and saved-run selectors sit inline with their panel headings.

Open a saved result directly with `?experiment=<experiment-id>`, `?search=<search-id>`, or both query parameters. These links support the recorded demonstration and preserve access to the exact run.

The frontend production build passed. Browser checks covered saved acceptance and rejection evidence, generated architecture, simulator output, search lineage and both measured Pareto points. The dashboard reran the unsafe fixture and downloaded the fresh fault report. The live shop replay returned the same confirmation and retained one payment effect.

The redesigned builder exported a two-replica configuration with a 30-second cache and queued notifications. Docker Compose validated the exported YAML. The same configuration completed all three dashboard-started Docker smoke repetitions and cleaned up in run `08f55991-7dbc-4ebd-b07f-151d00d5c351`.

Graph API reference: [React Flow controls](https://reactflow.dev/api-reference/components/controls).
