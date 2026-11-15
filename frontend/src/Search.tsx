import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {Action, Icon} from './Action';
import {EvidenceLinks} from './EvidenceLinks';
import {Graph, Topology} from './Graph';
import {Status} from './Status';
import {rememberRunInUrl} from './runLink';
import {describeGenome, type Genome} from './genome';
import {isLive, localOnly, showcase} from './showcase';

type Evaluation = {
  evaluation_id: string; status: string; gate: string;
  gate_reasons?: string[]; violations?: {invariant_id: string; detail: string}[];
  artifacts: {name: string}[];
};
type Candidate = {
  genome_hash: string; genome: Genome; parent_ids: string[]; generation: number;
  status: string; objectives: number[] | null; experiment_id?: string; candidate_id?: string;
  summary?: {gate?: string; spread?: Record<string, {median: number}>} | null;
  evaluations: Evaluation[]; simulation?: {metrics: {p95_ms: number}; calibration_status: string};
};
type SearchRecord = {
  search_id: string; status: string; generation: number; attempts_used: number;
  search_overhead_s: number; finished_at?: string; recorded?: boolean;
  request: {algorithm: string; seed: number; workload_profile: string; runtime?: 'native' | 'docker'; budget?: {real_test_budget: number}};
  candidates: Candidate[]; pareto_ids: string[]; experiment_ids: string[]; error?: string;
};
type RecordedBundle = {label: string; generated_at: string; note: string; default: string; searches: SearchRecord[]};
type Event = {sequence: number; message: string};
type TopologyPreview = Parameters<typeof Topology>[0] & {genome_hash: string};
type CandidateFilter = 'all' | 'measured' | 'pareto' | 'screened';
type CandidateSort = 'search' | 'latency' | 'cpu' | 'recovery';
const terminal = (run: SearchRecord | null) => !run || ['completed', 'failed', 'cancelled'].includes(run.status);
const algorithms: Record<string, string> = {nsga2: 'NSGA-II', random: 'Random search', hill_climbing: 'Hill climbing'};
function EvidenceStatus({candidate}: {candidate: Candidate}) {
  if (candidate.objectives) return <Status value="passed" label="Measured · feasible"/>;
  if (candidate.status === 'promoted') return <Status value="queued" label="Promoted · measuring"/>;
  if (candidate.status !== 'measured') return <Status value="neutral" label="Simulated · screened"/>;
  if (!candidate.summary) return <Status value="requires_review" label="Measured · incomplete"/>;
  return candidate.summary.gate === 'passed'
    ? <Status value="requires_review" label="Measured · recovery unavailable"/>
    : <Status value="rejected" label="Measured · rejected"/>;
}

function measuredValue(candidate: Candidate, metric: Exclude<CandidateSort, 'search'>) {
  if (metric === 'latency') return candidate.objectives?.[0] ?? candidate.summary?.spread?.p95_ms?.median;
  if (metric === 'cpu') return candidate.objectives?.[1] ?? candidate.summary?.spread?.cpu_seconds?.median;
  return candidate.objectives?.[2];
}

function latencyLabel(candidate: Candidate) {
  const measured = measuredValue(candidate, 'latency');
  if (measured !== undefined) return measured.toFixed(1);
  return candidate.simulation ? `Simulated ${candidate.simulation.metrics.p95_ms.toFixed(1)}` : '—';
}

export function Search({workload, runtime, canMeasure, onEditCandidate, onWorkloadChange}: {
  workload: string; runtime: 'native' | 'docker'; canMeasure: boolean; onEditCandidate: (genome: Genome) => void;
  onWorkloadChange: (workload: string) => void;
}) {
  const [algorithm, setAlgorithm] = useState('nsga2');
  const [budget, setBudget] = useState(6);
  const [seed, setSeed] = useState(42);
  const [history, setHistory] = useState<SearchRecord[]>([]);
  const [historyState, setHistoryState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [run, setRun] = useState<SearchRecord | null>(null);
  const [recordedMode, setRecordedMode] = useState(false);
  const [recordedBundle, setRecordedBundle] = useState<RecordedBundle | null>(null);
  const [recordedState, setRecordedState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [events, setEvents] = useState<Event[]>([]);
  const [activeAttemptCount, setActiveAttemptCount] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<'start' | 'rerun' | 'cancel' | null>(null);
  const [filter, setFilter] = useState<CandidateFilter>('all');
  const [sort, setSort] = useState<CandidateSort>('search');
  const [selectedHash, setSelectedHash] = useState<string | null>(null);
  const selected = run?.candidates.find(candidate => candidate.genome_hash === selectedHash);
  const dialog = useRef<HTMLDialogElement>(null);
  const inspectTrigger = useRef<HTMLButtonElement | SVGCircleElement>(null);
  const [preview, setPreview] = useState<{hash: string; topology: TopologyPreview | null} | null>(null);
  const recorded = showcase && !isLive();
  function remember(value: SearchRecord) {
    setRun(value);
    setHistory(rows => [value, ...rows.filter(row => row.search_id !== value.search_id)]);
  }
  async function loadRecorded(prefer: 'default' | 'feasible' | 'rejected' = 'default') {
    setRecordedState('loading'); setError('');
    try {
      const bundle: RecordedBundle = recordedBundle ?? await fetch('/recorded-example.json', {cache: 'no-store', signal: AbortSignal.timeout(8000)})
        .then(async response => {if (!response.ok) throw Error(); return response.json();});
      setRecordedBundle(bundle);
      const feasible = bundle.searches.filter(record => record.candidates.some(candidate => candidate.objectives));
      const rejected = bundle.searches.filter(record => !record.candidates.some(candidate => candidate.objectives));
      const record = (prefer === 'feasible' ? feasible[0] : prefer === 'rejected' ? rejected[0] : null)
        ?? bundle.searches.find(entry => entry.search_id === bundle.default) ?? feasible[0] ?? bundle.searches[0];
      if (!record) throw Error('No recorded searches');
      setRun({...record, recorded: true});
      setRecordedMode(true); setHistoryState('ready'); setRecordedState('idle');
      setEvents([]); setSelectedHash(null); setFilter('all'); setSort('search');
    } catch {
      setRecordedState('error');
      setError('Recorded evidence could not be loaded on this machine.');
    }
  }
  useEffect(() => {
    let alive = true;
    setHistoryState('loading');
    setError('');
    fetch('/api/searches', {signal: AbortSignal.timeout(10000)}).then(async response => {
      if (!response.ok) throw Error('Search service unavailable');
      const rows: SearchRecord[] = await response.json();
      const selected = new URLSearchParams(window.location.search).get('search');
      if (alive) {setHistory(rows); setRecordedMode(false); setRun(rows.find(row => row.search_id === selected) ?? rows[0] ?? null); setHistoryState('ready');}
    }).catch(() => {if (alive) {setHistoryState('error'); setError('Saved searches could not be loaded. Check the API connection and try again.'); void loadRecorded();}});
    return () => {alive = false;};
  }, [historyRefresh]);
  useEffect(() => {
    if (!run || recordedMode) return;
    let alive = true;
    async function refresh() {
      try {
        const [status, messages] = await Promise.all([
          fetch(`/api/searches/${run!.search_id}`),
          fetch(`/api/searches/${run!.search_id}/events`),
        ]);
        if (!status.ok || !messages.ok) throw Error('Search status connection lost');
        const value: SearchRecord = await status.json();
        const updates: Event[] = await messages.json();
        const activeChild = value.experiment_ids.at(-1);
        let attempts = 0;
        if (!terminal(value) && activeChild && value.candidates.some(candidate =>
          candidate.experiment_id === activeChild && candidate.status === 'promoted')) {
          const child = await fetch(`/api/experiments/${activeChild}`);
          if (child.ok) attempts = (await child.json()).attempts_used;
        }
        if (alive) {remember(value); setEvents(updates); setActiveAttemptCount(attempts); setError('');}
      } catch (reason) {if (alive) setError(String(reason));}
    }
    void refresh();
    const timer = terminal(run) ? undefined : setInterval(refresh, 1500);
    return () => {alive = false; clearInterval(timer);};
  }, [run?.search_id, run?.status]);
  async function action(url: string, body?: object, kind: 'start' | 'rerun' | 'cancel' = 'start') {
    setBusy(true); setPendingAction(kind); setError('');
    try {
      const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
      const result = await response.json();
      if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Request was rejected');
      rememberRunInUrl('search', result.search_id);
      setRecordedMode(false);
      remember(result); setSelectedHash(null); setFilter('all'); setSort('search');
    } catch (reason) {setError(String(reason));} finally {setBusy(false); setPendingAction(null);}
  }
  const previewBody = selected && JSON.stringify(selected.genome);
  useLayoutEffect(() => {
    if (selectedHash && !dialog.current?.open) dialog.current?.showModal();
  }, [selectedHash]);

  useEffect(() => {
    if (!selectedHash || !previewBody) return;
    const request = new AbortController();
    const hash = selectedHash;
    setPreview(null);
    fetch('/api/genomes/preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: previewBody,
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(8000)]),
    }).then(async response => {
      if (!response.ok) throw Error('Architecture unavailable');
      const {topology} = await response.json();
      if (!request.signal.aborted) setPreview({hash, topology});
    }).catch(() => {
      if (!request.signal.aborted) setPreview({hash, topology: null});
    });
    return () => request.abort();
  }, [selectedHash, previewBody]);

  function inspect(candidate: Candidate, trigger: HTMLButtonElement | SVGCircleElement) {
    inspectTrigger.current = trigger;
    setSelectedHash(candidate.genome_hash);
  }
  const feasible = run?.candidates.filter(row => row.objectives !== null) ?? [];
  const pareto = new Set(run?.pareto_ids);
  const candidates = run?.candidates.filter(row => {
    if (filter === 'measured') return row.status === 'measured';
    if (filter === 'pareto') return pareto.has(row.genome_hash);
    if (filter === 'screened') return row.status === 'screened';
    return true;
  }) ?? [];
  if (sort !== 'search') {
    candidates.sort((left, right) => {
      const a = measuredValue(left, sort);
      const b = measuredValue(right, sort);
      if (a === undefined) return b === undefined ? 0 : 1;
      return b === undefined ? -1 : a - b;
    });
  }
  const attempts = (run?.attempts_used ?? 0) + (terminal(run) ? 0 : activeAttemptCount);
  const attemptBudget = run?.request.budget?.real_test_budget;
  const measured = run?.candidates.filter(row => row.status === 'measured') ?? [];
  const rejectedRows = measured.filter(row => !row.objectives);
  const reasons = new Map<string, number>();
  for (const row of rejectedRows) {
    for (const evaluation of row.evaluations) {
      if (evaluation.gate && evaluation.gate !== 'passed') {
        for (const reason of evaluation.gate_reasons ?? []) reasons.set(reason, (reasons.get(reason) ?? 0) + 1);
        for (const violation of evaluation.violations ?? []) {
          const reason = `${violation.invariant_id} · ${violation.detail}`;
          reasons.set(reason, (reasons.get(reason) ?? 0) + 1);
        }
      }
    }
    if (!row.evaluations.length) reasons.set('measurement_did_not_complete', (reasons.get('measurement_did_not_complete') ?? 0) + 1);
  }
  const noFeasible = terminal(run) && measured.length > 0 && feasible.length === 0;
  function retryWith(count: number) {
    if (!run) return;
    void action('/api/searches', {
      algorithm: run.request.algorithm, runtime: run.request.runtime ?? runtime,
      workload_profile: run.request.workload_profile, seed: run.request.seed,
      generations: Math.max(1, Math.round(count / 3)), promotions_per_generation: 1, population_size: 4,
      budget: {real_test_budget: count, max_candidates: Math.min(36, Math.round(count / 3) * 4), wall_clock_s: Math.min(14400, count * 240)},
    });
  }
  const maxLatency = Math.max(1, ...feasible.map(row => row.objectives![0]));
  const maxCpu = Math.max(1, ...feasible.map(row => row.objectives![1]));
  const positions: Record<number, number> = {};
  const lineage = run?.candidates.map(row => {
    const column = positions[row.generation] ?? 0;
    positions[row.generation] = column + 1;
    return {id: row.genome_hash, label: `${row.genome_hash.slice(0, 6)} · ${row.status}`, x: column * 220, y: row.generation * 120};
  }) ?? [];
  return <section aria-label="Architecture search workspace" className="page-content">
    <p className="page-intro">Screen candidate architectures, verify them under failures, and compare those that pass.</p>
    <div className={`search-grid${terminal(run) ? '' : ' search-running'}`}>
    <div className="panel search-setup" hidden={!terminal(run)}>
    <div className="section-title panel-heading"><div><p className="section-kicker">Search setup</p><h2>New search</h2></div></div>
    <div className="genome-controls search-controls">
      <div><label htmlFor="algorithm">Search method</label><select id="algorithm" value={algorithm} disabled={busy || !terminal(run)} onChange={event => setAlgorithm(event.target.value)}>
        <option value="nsga2">NSGA-II</option><option value="random">Random search</option><option value="hill_climbing">Hill climbing</option>
      </select></div>
      <div><label htmlFor="search-budget">Measured attempts</label><select id="search-budget" value={budget} disabled={busy || !terminal(run)} onChange={event => setBudget(Number(event.target.value))}>
        {[6, 12, 18].map(value => <option key={value}>{value}</option>)}
      </select></div>
      <div><label htmlFor="search-seed">Seed</label><input id="search-seed" type="number" min={0} max={4294967295} value={seed} disabled={busy || !terminal(run)} onChange={event => setSeed(Number(event.target.value))}/></div>
    </div>
    <p className="muted">Three repetitions per measured configuration. Each generation uses completed fault checks to select parents. The selected workload is {workload.replace('_', ' ')}.</p>
    <div className="shop-actions form-actions">
      <Action variant="primary" icon="play" pending={pendingAction === 'start'} disabled={recorded || !canMeasure || busy || historyState === 'loading' || !Number.isInteger(seed) || seed < 0 || seed > 4294967295} aria-describedby={recorded ? 'search-showcase-hint' : !canMeasure ? 'search-runtime-hint' : undefined} onClick={() => action('/api/searches', {
        algorithm, runtime, workload_profile: workload, seed, generations: budget / 3,
        promotions_per_generation: 1, population_size: 4,
        budget: {real_test_budget: budget, max_candidates: Math.min(36, budget / 3 * 4), wall_clock_s: Math.min(14400, budget * 240)},
      })}>{pendingAction === 'start' ? 'Starting search…' : 'Start measured search'}</Action>
    </div>
    {recorded && <p id="search-showcase-hint" className="field-help">{localOnly}</p>}
    {!recorded && !canMeasure && <p id="search-runtime-hint" className="field-help">Measured search is unavailable for the selected runtime. Refresh runtimes above to check availability.</p>}
    </div>
    <div className="panel search-results">
    <div className="section-title"><h2>Search results</h2>
      {run && terminal(run) && !recordedMode && !recorded && <Action variant="quiet" icon="refresh" pending={pendingAction === 'rerun'} disabled={busy} onClick={() => action(`/api/searches/${run.search_id}/rerun`, undefined, 'rerun')}>{pendingAction === 'rerun' ? 'Starting rerun…' : 'Rerun search'}</Action>}
      {run && !terminal(run) && <Action variant="danger" icon="stop" pending={pendingAction === 'cancel'} disabled={busy} onClick={() => action(`/api/searches/${run.search_id}/cancel`, undefined, 'cancel')}>{pendingAction === 'cancel' ? 'Cancelling…' : 'Cancel search'}</Action>}
    </div>
    {error && <p role="alert">{error}</p>}
    {!run && <div className="empty-state" role="status" aria-live="polite">
      <span className="empty-state-icon" aria-hidden="true">{historyState === 'loading' ? <span className="button-spinner"/> : <Icon name="search"/>}</span>
      <div className="empty-state-copy"><h3>{historyState === 'loading' ? 'Loading your searches' : historyState === 'error' ? 'Search history unavailable' : 'Find your next architecture'}</h3>
        <p>{historyState === 'loading' ? 'Retrieving saved runs and candidate evidence.' : historyState === 'error' ? 'Reconnect to the API, then retry loading your saved searches.' : 'Choose a search method and attempt budget, then start a measured search. Compare the resulting candidates here.'}</p>
        {historyState === 'error' && <Action icon="refresh" onClick={() => setHistoryRefresh(value => value + 1)}>Retry loading searches</Action>}
        {historyState !== 'loading' && <Action variant="quiet" icon="book" pending={recordedState === 'loading'} onClick={() => void loadRecorded('feasible')}>Open recorded example</Action>}
      </div>
    </div>}
    {history.length > 0 && <div className="run-picker"><label htmlFor="search-history">Saved searches</label><select id="search-history" disabled={busy || !terminal(run)} value={run?.search_id ?? ''} onChange={event => {
      setRecordedMode(false);
      setRun(history.find(row => row.search_id === event.target.value) ?? null);
      setSelectedHash(null); setEvents([]); setFilter('all'); setSort('search');
      rememberRunInUrl('search', event.target.value);
    }}>{history.map(row => <option key={row.search_id} value={row.search_id}>
      {algorithms[row.request.algorithm] ?? row.request.algorithm} · {row.request.runtime === 'docker' ? 'Docker' : 'Native'} · {row.status} · {row.search_id.slice(0, 8)}
    </option>)}</select></div>}
    {history.length > 0 && <div className="recorded-actions">
      <Action variant="quiet" icon="book" pending={recordedState === 'loading'} onClick={() => void loadRecorded('feasible')}>Open recorded feasible run</Action>
      <Action variant="quiet" icon="book" pending={recordedState === 'loading'} onClick={() => void loadRecorded('rejected')}>Open recorded rejection</Action>
    </div>}
    {run && <>
      <div className="run-card">
        <div className="section-title"><h3>{algorithms[run.request.algorithm] ?? run.request.algorithm}</h3>
          <span className="run-badges"><Status value={run.status}/>{recordedMode && <Status value="recorded" label="Recorded run"/>}</span></div>
        <p className="muted run-meta">Generation {run.generation} · {run.request.runtime === 'docker' ? 'Docker' : 'Native'} · {run.request.workload_profile.replace('_', ' ')} · seed {run.request.seed}</p>
        {recordedMode && <p className="recorded-banner" role="status"><strong>Recorded evidence</strong> · {recordedBundle?.note ?? 'Saved measurements, not a live execution.'} Re-run a search to produce new evidence.</p>}
        <div className="progress-caption" role="status"><span>Measured attempts started</span><span>{attempts}{attemptBudget ? ` / ${attemptBudget}` : ''}</span></div>
        {attemptBudget && <progress aria-label="Measured search attempts started" value={attempts} max={attemptBudget}/>}
        <p className="muted run-meta">{run.candidates.length} candidates · {feasible.length} measured feasible · {run.search_overhead_s.toFixed(2)} s search overhead</p>
        {run.error && <p role="alert">{run.error}</p>}
        <details><summary>Search events</summary><ol className="event-list">{events.map(event => <li key={event.sequence}>{event.message}</li>)}</ol></details>
        {lineage.length > 0 && <details><summary>Candidate lineage</summary><Graph nodes={lineage} edges={run.candidates.flatMap(row => row.parent_ids.map(source => ({source, target: row.genome_hash})))} label="Candidate lineage"/></details>}
      </div>
      {noFeasible ? <div className="verdict-panel" role="status">
        <div className="verdict-header">
          <span className="section-kicker">Verified outcome</span>
          <h3>No candidate passed all gates</h3>
          <p className="muted">The search finished, but every measured candidate was rejected by at least one hard gate. DARWIN does not rank or promote rejected candidates, so there is no honest winner to show.</p>
        </div>
        <div className="verdict-grid">
          <div><h4>Why candidates were rejected</h4>
            <ul className="verdict-reasons">{[...reasons.entries()].sort((left, right) => right[1] - left[1]).slice(0, 6).map(([reason, count]) =>
              <li key={reason}><span>{reason.replaceAll('_', ' ')}</span><strong>{count}×</strong></li>)}
              {!reasons.size && <li><span>No gate details were recorded for these attempts.</span></li>}
            </ul>
          </div>
          <div><h4>Rejected candidates</h4>
            <ul className="verdict-candidates">{rejectedRows.slice(0, 4).map(row => <li key={row.genome_hash}>
              <span>{describeGenome(row.genome)}</span>
              <Action className="compact-action" variant="quiet" icon="search" aria-haspopup="dialog"
                aria-label={`Inspect ${describeGenome(row.genome)}`} onClick={event => inspect(row, event.currentTarget)}>Inspect</Action>
            </li>)}</ul>
          </div>
        </div>
        <div className="verdict-actions">
          <Action icon="refresh" disabled={recorded || !canMeasure || busy} title={recorded ? localOnly : undefined} pending={pendingAction === 'start'} onClick={() => retryWith(12)}>Retry with 12 measured attempts</Action>
          {run.request.workload_profile !== 'flash_sale' && <Action disabled={!canMeasure || busy} onClick={() => onWorkloadChange('flash_sale')}>Try the flash-sale workload</Action>}
          <Action variant="quiet" icon="book" pending={recordedState === 'loading'} onClick={() => void loadRecorded('feasible')}>Open a recorded feasible run</Action>
        </div>
        <p className="muted">Safe next choices: change the workload, increase the measured attempt budget, or inspect each rejection trace before retrying. None of these bypasses a gate.</p>
      </div> : <div className="chart-card search-chart"><h3>Measured feasible tradeoffs</h3>
      {feasible.length ? <><p className="muted">Select a point to inspect its evidence. Filled points are on the Pareto front across latency, CPU time, and recovery.</p>
        <svg viewBox="0 0 660 300" role="group" aria-label="Measured latency versus application CPU time" className="pareto">
          {[0, .25, .5, .75, 1].map(fraction => {
            const y = 40 + (1 - fraction) * 200;
            return <g key={`y-${fraction}`}><line className="chart-grid" x1="52" x2="620" y1={y} y2={y}/>
              <text x="44" y={y + 4} textAnchor="end">{Math.round(maxLatency * fraction)}</text></g>;
          })}
          {[0, .25, .5, .75, 1].map(fraction => {
            const x = 52 + fraction * 568;
            return <g key={`x-${fraction}`}><line className="chart-grid" x1={x} x2={x} y1="40" y2="240"/>
              <text x={x} y="258" textAnchor="middle">{(maxCpu * fraction).toFixed(1)}</text></g>;
          })}
          <path className="chart-axis" d="M52 24V240H630" fill="none"/>
          <text x="335" y="284" textAnchor="middle">Application CPU seconds</text><text x="10" y="30">p95 ms</text>
          {feasible.map(row => {
            const [latency, cpu, recovery] = row.objectives!;
            const label = `${describeGenome(row.genome)} · p95 ${latency.toFixed(1)} ms · CPU ${cpu.toFixed(2)} s · recovery ${recovery.toFixed(2)} s`;
            return <circle key={row.genome_hash} cx={52 + cpu / maxCpu * 568} cy={240 - latency / maxLatency * 200}
              className="candidate-point" role="button" tabIndex={0} aria-label={label} aria-haspopup="dialog"
              onClick={event => inspect(row, event.currentTarget)} onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  inspect(row, event.currentTarget);
                }
              }} r={8} fill={pareto.has(row.genome_hash) ? 'var(--accent)' : 'var(--surface)'} stroke="var(--accent)">
              <title>{label}</title>
            </circle>;
          })}
        </svg>
        <div className="chart-legend">
          <span><i className="legend-dot on"/>Pareto front</span>
          <span><i className="legend-dot"/>Measured feasible</span>
        </div></> : <p className="muted">No complete configuration has passed every measured feasibility gate in this search.</p>}
      </div>}
      <section className="candidate-browser panel" aria-labelledby="candidates-title">
        <div className="section-title"><h3 id="candidates-title">Candidates</h3><span className="muted" role="status">{candidates.length} of {run.candidates.length} shown</span></div>
        <div className="candidate-filters">
          <div><label htmlFor="candidate-filter">Evidence</label><select id="candidate-filter" value={filter} onChange={event => setFilter(event.target.value as CandidateFilter)}>
            <option value="all">All candidates</option><option value="measured">Measured</option><option value="pareto">Pareto front</option><option value="screened">Screened</option>
          </select></div>
          <div><label htmlFor="candidate-sort">Sort by</label><select id="candidate-sort" value={sort} onChange={event => setSort(event.target.value as CandidateSort)}>
            <option value="search">Search order</option><option value="latency">Lowest measured p95</option><option value="cpu">Lowest measured CPU</option><option value="recovery">Fastest measured recovery</option>
          </select></div>
        </div>
      {!candidates.length ? <p className="muted">{run.candidates.length ? 'No candidates match this filter.' : 'Candidates appear as search generations begin.'}</p> :
      <div className="table-scroll candidate-table" tabIndex={0} role="region" aria-label="Candidate comparison"><table role="table"><thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">Configuration</th><th role="columnheader" scope="col">Evidence</th><th role="columnheader" scope="col">p95 ms</th><th role="columnheader" scope="col">CPU s</th><th role="columnheader" scope="col">Recovery s</th><th role="columnheader" scope="col">Details</th></tr></thead>
        <tbody role="rowgroup">{candidates.map(row => <tr role="row" key={row.genome_hash}>
          <td role="cell" className="candidate-config"><strong>{row.genome.app_replicas} {row.genome.app_replicas === 1 ? 'replica' : 'replicas'} · {row.genome.catalog_cache_ttl_s ? `${row.genome.catalog_cache_ttl_s}s cache` : 'cache off'}</strong>
            <small>{row.genome.notification_mode === 'queued' ? 'Queued' : 'Sync'} notifications · {row.genome.retry_policy === 'none' ? 'No retries' : 'Idempotent retries'}</small></td><td role="cell" className="candidate-evidence"><EvidenceStatus candidate={row}/></td>
          <td role="cell" className="candidate-metric"><span aria-hidden="true">p95 ms</span>{latencyLabel(row)}</td>
          <td role="cell" className="candidate-metric"><span aria-hidden="true">CPU s</span>{measuredValue(row, 'cpu')?.toFixed(2) ?? '—'}</td>
          <td role="cell" className="candidate-metric"><span aria-hidden="true">Recovery s</span>{measuredValue(row, 'recovery')?.toFixed(2) ?? '—'}</td>
          <td role="cell" className="candidate-inspect"><Action className="compact-action" variant="quiet" icon="search" aria-label={`Inspect ${describeGenome(row.genome)}`} aria-haspopup="dialog" onClick={event => inspect(row, event.currentTarget)}>Inspect</Action></td>
        </tr>)}</tbody></table></div>}
      </section>
    </>}
    </div>
    </div>
    <dialog ref={dialog} className="candidate-dialog" aria-label="Candidate details" onClose={() => {
      setSelectedHash(null);
      inspectTrigger.current?.focus();
    }}>
      {selected && <>
        <div className="candidate-dialog-header section-title"><h2>Candidate details</h2>
          <Action variant="quiet" icon="close" autoFocus onClick={() => dialog.current?.close()}>Close details</Action></div>
        <h3>{describeGenome(selected.genome)}</h3>
        <div className="candidate-dialog-meta"><EvidenceStatus candidate={selected}/>
          <span className="muted">Generation {selected.generation + 1}</span>
          {pareto.has(selected.genome_hash) && <Status value="passed" label="Pareto front"/>}
        </div>
        <div className="shop-actions">
          <Action variant="primary" icon="configuration" onClick={() => {inspectTrigger.current = null; dialog.current?.close(); onEditCandidate(selected.genome);}}>Open in Architecture</Action>
          {selected.experiment_id && !recordedMode && <a className="action-link" href={`?experiment=${encodeURIComponent(selected.experiment_id)}&search=${encodeURIComponent(run!.search_id)}#experiments`}>View experiment</a>}
        </div>
        <dl className="metrics-grid">
          <div><dt>p95 latency (ms)</dt><dd>{latencyLabel(selected)}</dd></div>
          <div><dt>CPU time (s)</dt><dd>{measuredValue(selected, 'cpu')?.toFixed(2) ?? '—'}</dd></div>
          <div><dt>Recovery (s)</dt><dd>{measuredValue(selected, 'recovery')?.toFixed(2) ?? '—'}</dd></div>
        </dl>
        {preview?.hash === selected.genome_hash ? (preview.topology ? <Topology key={preview.hash} {...preview.topology}/> : <p role="alert">The service topology could not be loaded.</p>)
          : <p className="muted" role="status">Loading service topology…</p>}
        {selected.simulation && <p className="muted">Simulation status · {selected.simulation.calibration_status.replaceAll('_', ' ')}</p>}
        {selected.evaluations.map((evaluation, index) => <details key={evaluation.evaluation_id}>
          <summary>Repetition {index + 1} · {evaluation.status} · gate {evaluation.gate}</summary>
          {evaluation.gate_reasons?.map(reason => <p key={reason}>{reason.replaceAll('_', ' ')}</p>)}
          {evaluation.violations?.map((violation, index) => <p key={index}>{violation.invariant_id} · {violation.detail}</p>)}
          {selected.experiment_id && !recordedMode && <EvidenceLinks experimentId={selected.experiment_id} evaluationId={evaluation.evaluation_id} artifacts={evaluation.artifacts}/>}
        </details>)}
      </>}
    </dialog>
  </section>;
}
