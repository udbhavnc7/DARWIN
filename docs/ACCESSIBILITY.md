# Accessibility

The dashboard is the only surface a judge or operator touches, so it has to work
with a keyboard, a screen reader, and a small screen. This document records what
was checked, how, what it found, and what remains unverified.

## What is covered

| Area | Result |
| --- | --- |
| WCAG 2.1 A/AA automated rules (axe-core 4.10.2) | 0 violations across 162 page/theme/viewport states |
| Palette token contrast (`python scripts/check_contrast.py`) | 23 colour pairs per palette meet AA in all six themes |
| Horizontal overflow at 320 CSS px (WCAG 1.4.10 reflow) | No page scrolls sideways in any theme or page |
| Keyboard path | 9 of 9 scripted checks pass (skip link, focus order, focus rings, dialog focus, Escape) |

"Page/theme/viewport state" means one rendered surface: the seven workspace pages
(Overview, Project Workspace, Architecture, Experiments, Evolution, Solution,
Demo shop), the palette dialog, and the calibration intro, each in all six
palettes at three viewport widths. That is 7 + 1 + 1 surfaces × 6 themes × 3
viewports = 162.

## Method

### Automated rules

`frontend/scripts/a11y-audit.mjs` drives Chromium through Playwright, injects
axe-core, and runs the `wcag2a`, `wcag2aa`, `wcag21a`, and `wcag21aa` rule sets
on every state. It also flags any state where
`documentElement.scrollWidth` exceeds `clientWidth` by more than one pixel.

```powershell
# Build and serve the static showcase the way it is published
npm --prefix frontend run build:showcase
npm --prefix frontend run preview:showcase

# One-off tool install; it does not touch package.json
npm --prefix frontend i --no-save playwright axe-core
npx --prefix frontend playwright install chromium

npm --prefix frontend run audit:a11y
```

The report lands in `frontend/artifacts/a11y/axe-report.json` (gitignored). The
script exits non-zero on any violation, overflow, or failed keyboard check, so
it can gate a release. If axe-core is not resolvable as a module, pass
`--axe <path to axe.min.js>`; `--base`, `--themes`, and `--pages` narrow a run.

Viewports: 1440×900 desktop, 390×844 phone, 320×640 (the WCAG 1.4.10 reflow
width).

### Palette contrast

The six palettes are fixed sets of CSS custom properties, so contrast is
computed rather than sampled. `scripts/check_contrast.py` parses
`frontend/src/style.css`, pairs every foreground token with the surfaces it is
drawn on, and applies the WCAG 2.1 relative-luminance formula.

```powershell
.\.venv\Scripts\python.exe scripts/check_contrast.py
```

Text pairs must reach 4.5:1; the control and input outline (`--control-line`)
must reach 3:1 as non-text UI. The script runs in the dashboard CI job, so a
palette edit that harms readability fails before merge.

### Keyboard path

The same audit script walks the keyboard path and asserts:

1. The first Tab stop is the skip link, and it becomes visible.
2. The skip link targets a real `#workspace` region.
3. Sidebar page links take focus and draw a 2px focus ring.
4. Enter on a focused page link changes the route.
5. Exactly one navigation item carries `aria-current="page"`.
6. No element uses a positive `tabindex`.
7. Opening the palette dialog moves focus inside it.
8. The dialog's controls are focusable and reachable.
9. Escape closes the dialog and returns focus to its trigger.

## Findings and fixes

The first full run found three problems, all now fixed:

| Finding | Where | Fix |
| --- | --- | --- |
| `color-contrast` on the sidebar page numbers (3.80–3.98:1, AA needs 4.5:1) | `frontend/src/style.css`, `.nav-index` | Dropped `opacity: .8`, so the index uses `--muted` (5.93:1) and the current page uses `--accent` |
| `button-name` on the palette trigger below 560px, where the theme name is hidden | `frontend/src/ThemePicker.tsx` | Added `aria-label={\`Theme: ${name}\`}` so the icon-only button keeps its name |
| The Evolution page scrolled sideways: a nowrap candidate summary forced its grid row to 462px | `frontend/src/style.css`, `.verdict-grid`, `.verdict-candidates li`, `.search-grid` | `minmax(0, 1fr)` columns plus `min-width: 0` on the grid items, so the summary ellipsizes instead of widening the page |

The project-evaluation form's placeholder text had no explicit colour, so it
fell back to the browser default. Every `::placeholder` is now `--muted` at full
opacity, which stays above 4.5:1 on the field background in all six palettes.

Adding the Solution page raised the run to 162 states. That pass found four more
problems, fixed before the page shipped:

| Finding | Where | Fix |
| --- | --- | --- |
| `definition-list` on the Solution and project-verdict metric grids: a `<span class="metric-range">` sat beside the `<dd>` inside `<dl><div>` | `frontend/src/Solution.tsx`, `frontend/src/ProjectVerdict.tsx` | Moved the range inside the `<dd>`, matching the Experiments page |
| `color-contrast` on the struck-through time of the failed option (2.62:1) | `frontend/src/story.css`, `.story-choice-fail .story-choice-stat` | Dropped `opacity: .65`; the line-through alone marks the rejected value |
| `scrollable-region-focusable` on the two Overview tables at 390px and 320px | `frontend/src/Story.tsx` | Both scroll containers are now labelled `role="region"` with `tabIndex={0}` |
| Project Workspace and Evolution scrolled sideways by 2–9px: `.header-tools` shrank while the fixed-width palette button could not | `frontend/src/style.css`, `.header-tools` | Added `flex: none` so the button keeps its width inside the header |

## What is not covered

- **Screen-reader testing.** No pass with NVDA, JAWS, VoiceOver, or TalkBack. The
  markup, names, landmarks, and live regions are exposed and pass the automated
  rules, but real assistive-technology output was not recorded.
- **People testing.** No session with a participant who uses assistive
  technology.
- **Zoom and text spacing.** The 320px reflow check covers layout width, but
  200% browser zoom and the WCAG 1.4.12 text-spacing overrides were not run as a
  separate pass.
- **Motion.** The calibration intro honours `prefers-reduced-motion` for its
  scene, but that was not audited as a state of its own.
- **Contrast inside the three.js scene and the React Flow graph.** These are
  decorative or labelled in the DOM; only the DOM text and controls are covered.

Treat the automated result as a floor, not a certificate. If a screen reader
review is added, record the tool, version, and browser here.
