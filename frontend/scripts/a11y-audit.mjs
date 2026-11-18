#!/usr/bin/env node
/**
 * Accessibility audit for the dashboard.
 *
 * Runs axe-core (WCAG 2.1 A/AA) against every page in every theme, at a
 * desktop and a narrow viewport, and fails if any violation is reported.
 *
 * Usage:
 *   node scripts/a11y-audit.mjs                       # against the showcase preview
 *   node scripts/a11y-audit.mjs --base http://127.0.0.1:5173/
 *
 * The script needs `playwright` (Chromium) and axe-core. Install them without
 * touching package.json, then download the browser once:
 *   npm --prefix frontend i --no-save playwright axe-core
 *   npx --prefix frontend playwright install chromium
 * If neither module can be resolved, point A11Y_MODULES at a directory that has
 * them, or pass --axe <path to axe.min.js>.
 *
 * Output: a per-run summary on stdout and a JSON report in artifacts/a11y/.
 */
import {createRequire} from 'node:module';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const require = createRequire(import.meta.url);
const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

const base = opt('base', 'http://127.0.0.1:4173/DARWIN/');
const themes = opt('themes', 'texture,leather,carbon,blueprint,amethyst,midnight').split(',');
const pages = opt('pages', 'overview,project,configuration,experiments,search,solution,shop').split(',');
const viewports = [
  {name: 'desktop', width: 1440, height: 900},
  {name: 'narrow', width: 390, height: 844},
  // WCAG 1.4.10 reflow: content must work at 320 CSS pixels without loss.
  {name: 'reflow', width: 320, height: 640},
];
const tags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

function resolve(name) {
  const paths = [join(root, 'frontend'), root, process.env.A11Y_MODULES].filter(Boolean);
  for (const path of paths) {
    try {return require.resolve(name, {paths: [path]});} catch { /* try next */ }
  }
  return null;
}

function load(name) {
  const path = resolve(name);
  if (!path) {
    console.error(
      `Cannot resolve "${name}". Install the audit tools without changing package.json:\n` +
      '  npm --prefix frontend i --no-save playwright axe-core\n' +
      '  npx --prefix frontend playwright install chromium\n' +
      'or set A11Y_MODULES to a directory that contains them, or pass --axe <path>.',
    );
    process.exit(2);
  }
  return require(path);
}

async function loadAxe() {
  const module = resolve('axe-core');
  if (module) return require(module).source;
  const file = opt('axe', null);
  if (file) return readFile(file, 'utf8');
  console.error(
    'Cannot resolve "axe-core". Install it with\n' +
    '  npm --prefix frontend i --no-save axe-core\n' +
    'or pass --axe <path to axe.min.js> (for example from\n' +
    'https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js).',
  );
  process.exit(2);
}

const {chromium} = load('playwright');
const axeSource = await loadAxe();

const browser = await chromium.launch();
const results = [];
let violations = 0;

const settle = page =>
  page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))))
    .then(() => page.waitForTimeout(250));

async function audit(page, viewport, theme, name) {
  const report = await page.evaluate(async tags => {
    const r = await window.axe.run(document, {runOnly: {type: 'tag', values: tags}});
    const root = document.documentElement;
    return {
      violations: r.violations.map(v => ({
        id: v.id, impact: v.impact,
        nodes: v.nodes.map(n => ({target: n.target, html: n.html.slice(0, 160), summary: n.failureSummary})),
      })),
      passes: r.passes.length,
      incomplete: r.incomplete.map(v => v.id),
      // 1.4.10: nothing may require scrolling the page sideways.
      horizontalOverflow: Math.max(0, root.scrollWidth - root.clientWidth),
    };
  }, tags);

  violations += report.violations.length + (report.horizontalOverflow > 1 ? 1 : 0);
  results.push({viewport: viewport.name, theme, page: name, ...report});
  const problems = [
    ...report.violations.map(v => `${v.id}(${v.nodes.length})`),
    ...(report.horizontalOverflow > 1 ? [`overflow:${report.horizontalOverflow}px`] : []),
  ];
  console.log(problems.length
    ? `FAIL ${viewport.name} ${theme}/${name}: ${problems.join(', ')}`
    : `ok   ${viewport.name} ${theme}/${name} (${report.passes} rules passed)`);
}

for (const viewport of viewports) {
  const context = await browser.newContext({viewport: {width: viewport.width, height: viewport.height}});
  const page = await context.newPage();

  // The seven workspace pages in every theme.
  await page.goto(`${base}?nosplash=1`, {waitUntil: 'networkidle'});
  await page.addScriptTag({content: axeSource});
  for (const theme of themes) {
    for (const name of pages) {
      await page.evaluate(([theme, name]) => {
        document.documentElement.dataset.theme = theme;
        location.hash = name;
      }, [theme, name]);
      await settle(page);
      await audit(page, viewport, theme, name);
    }
  }

  // The palette dialog: it lists all six finishes, so check it in every theme.
  await page.evaluate(() => { location.hash = 'overview'; });
  await settle(page);
  for (const theme of themes) {
    await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
    await page.click('.theme-trigger');
    await page.waitForSelector('.theme-dialog[open]');
    await settle(page);
    await audit(page, viewport, theme, 'dialog:palette');
    await page.keyboard.press('Escape');
    await page.waitForSelector('.theme-dialog', {state: 'hidden'});
  }

  // The calibration intro owns its own overlay and skip control.
  for (const theme of themes) {
    await page.goto(`${base}?splash=1`, {waitUntil: 'networkidle'});
    await page.addScriptTag({content: axeSource});
    await page.waitForSelector('.splash');
    await page.evaluate(theme => {
      document.documentElement.dataset.theme = theme;
      localStorage.setItem('darwin-theme', theme);
    }, theme);
    await settle(page);
    await audit(page, viewport, theme, 'overlay:intro');
  }

  await context.close();
}

// Keyboard and focus behaviour is not something axe can assert, so walk the
// paths a keyboard user actually takes.
const focusChecks = [];
function record(name, pass, detail = '') {
  focusChecks.push({name, pass, detail});
  console.log(`${pass ? 'ok  ' : 'FAIL'} keyboard: ${name}${detail ? ` (${detail})` : ''}`);
}

{
  const context = await browser.newContext({viewport: {width: 1440, height: 900}});
  const page = await context.newPage();
  await page.goto(`${base}?nosplash=1`, {waitUntil: 'networkidle'});

  await page.keyboard.press('Tab');
  const skip = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active) return null;
    const rect = active.getBoundingClientRect();
    return {cls: active.className, href: active.getAttribute('href'), top: Math.round(rect.top)};
  });
  record('skip link is the first tab stop and becomes visible',
    skip?.cls === 'skip-link' && skip.top >= 0, JSON.stringify(skip));

  record('skip link targets the workspace region',
    !!skip && skip.href === '#workspace' &&
    await page.evaluate(() => !!document.getElementById('workspace')), skip?.href ?? '');

  // Tab until a sidebar page link owns focus, then confirm its focus ring and
  // that Enter activates it.
  let focusedNav = false;
  for (let i = 0; i < 12 && !focusedNav; i += 1) {
    await page.keyboard.press('Tab');
    focusedNav = await page.evaluate(() => document.activeElement?.matches('.section-nav a') ?? false);
  }
  const ring = focusedNav && await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement);
    return {style: style.outlineStyle, width: parseFloat(style.outlineWidth)};
  });
  record('sidebar links take keyboard focus and draw a visible ring',
    !!ring && ring.style !== 'none' && ring.width >= 2, JSON.stringify(ring));

  const before = await page.evaluate(() => location.hash);
  if (focusedNav) await page.keyboard.press('Enter');
  await settle(page);
  const after = await page.evaluate(() => ({hash: location.hash, current: document.querySelectorAll('.section-nav a[aria-current="page"]').length}));
  record('Enter activates the focused page link', focusedNav && after.hash !== before && after.hash.length > 1,
    `${before} -> ${after.hash}`);
  record('exactly one nav item is marked aria-current="page"', after.current === 1, String(after.current));

  record('no positive tabindex values', await page.evaluate(() =>
    [...document.querySelectorAll('[tabindex]')].every(el => Number(el.getAttribute('tabindex')) <= 0)));

  // Palette dialog focus management.
  await page.click('.theme-trigger');
  await page.waitForSelector('.theme-dialog[open]');
  record('palette dialog moves focus inside itself',
    await page.evaluate(() => document.querySelector('.theme-dialog[open]').contains(document.activeElement)));
  const traps = await page.evaluate(async () => {
    const dialog = document.querySelector('.theme-dialog[open]');
    const focusables = [...dialog.querySelectorAll('button, input, select, a[href], [tabindex]:not([tabindex="-1"])')];
    return focusables.length > 0 && focusables.every(el => el.offsetParent !== null || el.getClientRects().length > 0);
  });
  record('palette dialog exposes focusable controls', traps);
  await page.keyboard.press('Escape');
  await page.waitForSelector('.theme-dialog', {state: 'hidden'});
  record('Escape closes the palette dialog and returns focus to its trigger',
    await page.evaluate(() => document.activeElement?.classList.contains('theme-trigger') ?? false));

  await context.close();
}

await browser.close();

const outDir = join(root, 'artifacts', 'a11y');
await mkdir(outDir, {recursive: true});
const file = join(outDir, 'axe-report.json');
await writeFile(file, JSON.stringify({base, tags, viewports: viewports.map(v => v.name), results, focusChecks}, null, 2));

const failedChecks = focusChecks.filter(check => !check.pass).length;
console.log(`\n${results.length} page/theme/viewport combinations, ${violations} violation(s)`);
console.log(`${focusChecks.length - failedChecks}/${focusChecks.length} keyboard checks passed`);
console.log(`report: ${file}`);
process.exit(violations || failedChecks ? 1 : 0);
