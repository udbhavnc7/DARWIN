#!/usr/bin/env node
// Real Sanchay report benchmark runner.
//
// It imports the pinned Sanchay reporting module for the baseline and the patched
// call-site module for the candidate. Correctness is compared before timing, but
// timings are still recorded for an incorrect candidate so DARWIN can demonstrate
// that speed never outranks a failed correctness gate.

import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { cpus, totalmem, platform, arch } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const configPath = process.argv[2];
if (!configPath) {
  console.error('usage: node runner.mjs <config.json>');
  process.exit(2);
}
const config = JSON.parse(readFileSync(configPath, 'utf8'));
const { runBaseline } = await import(new URL('./baseline-entry.ts', import.meta.url).href);
const { runCandidate } = await import(new URL('./candidate-entry.ts', import.meta.url).href);
const { reportsAccountMap, scopeToCurrency } = await import(
  new URL('./source/reporting.ts', import.meta.url).href
);

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  if (typeof value === 'number' && !Number.isFinite(value)) return JSON.stringify(String(value));
  return JSON.stringify(value);
}

const digest = (value) => createHash('sha256').update(value).digest('hex');

function timed(fn) {
  const started = process.hrtime.bigint();
  const output = fn();
  const finished = process.hrtime.bigint();
  return { ns: Number(finished - started), output };
}

function percentile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(fraction * sorted.length) - 1))];
}

const checks = [];
function check(name, passed, detail = '') {
  checks.push({ name, passed: Boolean(passed), detail });
  return passed;
}

const fixtures = [];
for (const item of config.fixtures) {
  const path = resolve(__dirname, item.path);
  const fixture = JSON.parse(readFileSync(path, 'utf8'));
  const rawTransactions = fixture.transactions;
  const expectedSize = fixture.size;
  if (!Array.isArray(rawTransactions) || rawTransactions.length !== expectedSize) {
    throw new Error(`Fixture ${item.id} has ${rawTransactions?.length} rows, expected ${expectedSize}`);
  }
  const currency = fixture.currency;
  // Edge fixtures exercise the real currency-scoping functions before aggregation.
  // Timed fixtures are already scoped exactly as ReportsTab prepares `inCurrency`.
  const transactions = fixture.scope
    ? scopeToCurrency(rawTransactions, reportsAccountMap(fixture.accounts ?? []), currency)
    : rawTransactions;
  if (fixture.scope) {
    check(`${item.id}: real currency scoping selected the expected rows`,
      transactions.length === fixture.scoped_rows,
      `selected ${transactions.length}, expected ${fixture.scoped_rows}`);
  }
  const before = canonical(transactions);
  const baseline = runBaseline(transactions, currency, config.payee_limit);
  const candidate = runCandidate(transactions, currency, config.payee_limit);
  const baselineText = canonical(baseline);
  const candidateText = canonical(candidate);
  const unchanged = canonical(transactions) === before;

  check(`${item.id}: baseline and candidate match`, baselineText === candidateText,
    baselineText === candidateText ? '' : 'candidate output differs from the original functions');
  check(`${item.id}: candidate is deterministic`,
    canonical(runCandidate(transactions, currency, config.payee_limit)) === candidateText);
  check(`${item.id}: ledger input is not mutated`, unchanged,
    unchanged ? '' : 'the candidate changed the transaction array');
  if (fixture.expected) {
    check(`${item.id}: baseline matches documented finance semantics`,
      canonical(fixture.expected) === baselineText,
      canonical(fixture.expected) === baselineText ? '' : 'baseline did not match the edge-case expectation');
  }

  fixtures.push({
    ...item,
    currency,
    baselineHash: digest(baselineText).slice(0, 16),
    candidateHash: digest(candidateText).slice(0, 16),
    baselineOutput: baseline,
    candidateOutput: candidate,
    transactions,
  });
}

const parityPassed = checks.every((item) => item.passed);
const runs = [];
const summaries = [];

for (const fixture of fixtures.filter((item) => item.timed !== false)) {
  const args = [fixture.transactions, fixture.currency, config.payee_limit];
  const reference = canonical(fixture.baselineOutput);
  for (let warmup = 0; warmup < config.warmups; warmup += 1) {
    if (warmup % 2 === 0) {
      runBaseline(...args);
      runCandidate(...args);
    } else {
      runCandidate(...args);
      runBaseline(...args);
    }
  }

  const baselineNs = [];
  const candidateNs = [];
  const orders = [];
  let outputsStable = true;
  for (let repetition = 0; repetition < config.repetitions; repetition += 1) {
    const candidateFirst = repetition % 2 === 1;
    orders.push(candidateFirst ? 'candidate-first' : 'baseline-first');
    let baseline;
    let candidate;
    if (candidateFirst) {
      candidate = timed(() => runCandidate(...args));
      baseline = timed(() => runBaseline(...args));
    } else {
      baseline = timed(() => runBaseline(...args));
      candidate = timed(() => runCandidate(...args));
    }
    baselineNs.push(baseline.ns);
    candidateNs.push(candidate.ns);
    if (canonical(baseline.output) !== reference || canonical(candidate.output) !== reference) {
      outputsStable = false;
    }
  }
  check(`${fixture.id}: every measured repetition returned the same result`, outputsStable);

  const baselineMedian = percentile(baselineNs, 0.5);
  const candidateMedian = percentile(candidateNs, 0.5);
  summaries.push({
    fixture_id: fixture.id,
    seed: fixture.seed,
    size: fixture.size,
    currency: fixture.currency,
    baseline_median_ns: baselineMedian,
    candidate_median_ns: candidateMedian,
    baseline_p95_ns: percentile(baselineNs, 0.95),
    candidate_p95_ns: percentile(candidateNs, 0.95),
    baseline_min_ns: Math.min(...baselineNs),
    baseline_max_ns: Math.max(...baselineNs),
    candidate_min_ns: Math.min(...candidateNs),
    candidate_max_ns: Math.max(...candidateNs),
    change_pct: baselineMedian > 0 ? ((baselineMedian - candidateMedian) / baselineMedian) * 100 : 0,
    paired_candidate_wins: baselineNs.filter((value, index) => candidateNs[index] < value).length,
    samples: baselineNs.length,
  });
  runs.push({
    fixture_id: fixture.id,
    seed: fixture.seed,
    size: fixture.size,
    currency: fixture.currency,
    orders,
    baseline_ns: baselineNs,
    candidate_ns: candidateNs,
    baseline_hash: fixture.baselineHash,
    candidate_hash: fixture.candidateHash,
  });
}

const output = {
  schema_version: 1,
  ok: true,
  measurement_scope: 'pure report aggregation functions; currency filtering and React rendering are outside the timed region',
  parity: { passed: parityPassed, checks, total: checks.length, passed_count: checks.filter((item) => item.passed).length },
  environment: {
    node_version: process.version,
    platform: platform(),
    arch: arch(),
    cpu_model: cpus()[0]?.model ?? 'unknown',
    total_memory_bytes: totalmem(),
    heap_limit_bytes: (await import('node:v8')).getHeapStatistics().heap_size_limit,
    forced_gc: false,
  },
  config: {
    sizes: config.sizes,
    seeds: config.seeds,
    repetitions: config.repetitions,
    warmups: config.warmups,
    payee_limit: config.payee_limit,
  },
  summaries,
  runs,
};
writeFileSync(resolve(__dirname, config.output || 'benchmark.json'), JSON.stringify(output, null, 2));

const passed = output.parity.passed_count;
const total = output.parity.total;
console.log(JSON.stringify({
  ok: true,
  parity: output.parity.passed,
  checks: `${passed}/${total}`,
  summaries,
  node: process.version,
}));
