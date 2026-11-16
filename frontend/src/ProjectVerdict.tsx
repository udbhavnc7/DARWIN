import {useState} from 'react';
import {Action, Icon} from './Action';
import {
  api, artifactUrl, bundleUrl, changeLabel, controlLabel, formatDate, formatDuration, formatMs,
  formatRows, tone, type ArchitectureRun, type Evaluation, type EvidenceFile, type Measurement,
  type ScreeningChange,
} from './projectApi';

type Props = {
  evaluation: Evaluation;
  onRerun: () => void;
  onChooseAnother: () => void;
  downloadsAvailable: boolean;
  recordedView: boolean;
};

type ArtifactState = {
  artifact: {name: string; text: string} | null;
  busy: string;
  error: string;
  open: (name: string) => Promise<void>;
};

function speedLabel(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value > 0) return `${value.toFixed(1)}% faster`;
  if (value < 0) return `${Math.abs(value).toFixed(1)}% slower`;
  return 'No measured change';
}

function checkLabel(test?: Evaluation['source_tests']): {text: string; tone: 'good' | 'bad' | 'warn' | 'muted'} {
  if (!test) return {text: 'Not run', tone: 'muted'};
  const counts = test.tests_total
    ? ` (${test.tests_passed ?? 0}/${test.tests_total})`
    : '';
  if (test.status === 'passed') return {text: `Source tests passed${counts}`, tone: 'good'};
  if (test.status === 'failed') return {text: `Source tests failed${counts}`, tone: 'bad'};
  if (test.status === 'skipped') return {text: 'Source tests skipped', tone: 'warn'};
  return {text: 'Not run in this mode', tone: 'muted'};
}

function modelledLabel(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value > 0) return `${value.toFixed(1)}% lower`;
  if (value < 0) return `${Math.abs(value).toFixed(1)}% higher`;
  return 'No modelled change';
}

function setting(change: ScreeningChange, value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Enabled' : 'Off';
  if (value === 0 && (change.control === 'cache_ttl_s' || change.control === 'rate_limit')) return 'Off';
  if (value === 0 && change.control === 'replicas') return 'None';
  return change.unit && change.unit !== 'enabled' ? `${value} ${change.unit}` : String(value);
}

function MeasurementRow({item, primary}: {item: Measurement; primary: boolean}) {
  return <tr className={primary ? 'project-primary-row' : undefined}>
    <th scope="row">{formatRows(item.size)} rows {primary && <span className="project-primary-mark">primary</span>}</th>
    <td>{formatMs(item.baseline_median_ms)}</td>
    <td>{formatMs(item.candidate_median_ms)}</td>
    <td className={item.change_pct > 0 ? 'project-good' : item.change_pct < 0 ? 'project-bad' : ''}>{speedLabel(item.change_pct)}</td>
    <td>{Math.round(item.paired_win_rate * 100)}%</td>
    <td>{item.samples}</td>
  </tr>;
}

function EvidenceFiles({files, files_open, downloadsAvailable, evaluation, artifact}
  : {files: EvidenceFile[]; files_open: ArtifactState['open']; downloadsAvailable: boolean;
    evaluation: Evaluation; artifact: ArtifactState}) {
  return <>
    <ul className="project-evidence-links">
      {files.map(file => <li key={file.name}>
        {downloadsAvailable
          ? <a className="artifact-link" href={artifactUrl(evaluation.evaluation_id, file.name)}>
            <Icon name="download"/>{file.name}<span className="project-digest">{file.sha256.slice(0, 10)}</span>
          </a>
          : <button type="button" className="artifact-link artifact-recorded"
            aria-busy={artifact.busy === file.name}
            title={`Open the recorded ${file.name}`} onClick={() => void files_open(file.name)}>
            <Icon name="book"/>{file.name}<span className="project-digest">{file.sha256.slice(0, 10)}</span>
          </button>}
      </li>)}
    </ul>
    {artifact.artifact && <details open className="project-artifact-view">
      <summary>Recorded artifact · {artifact.artifact.name}</summary>
      <pre className="project-pre">{artifact.artifact.text}</pre>
    </details>}
    {artifact.error && <p className="notice" role="alert">{artifact.error}</p>}
  </>;
}

function ScreeningVerdict({evaluation, onRerun, onChooseAnother, downloadsAvailable, recordedView, artifact}
  : Props & {artifact: ArtifactState}) {
  const verdict = evaluation.verdict;
  const screening = evaluation.screening;
  const recommendation = screening?.recommendation ?? evaluation.recommendation;

  if (!verdict) return null;

  if (!screening || !recommendation) {
    return <section className="project-panel project-verdict">
      <div className="section-title">
        <div className="panel-heading">
          <span className="section-kicker">Step 5 · Prove · Simulated screening</span>
          <h2>No screening result was produced.</h2>
        </div>
        <span className="status-chip warn">SIMULATED · NOT MEASURED</span>
      </div>
      <div className="project-verdict-callout warn" role="status">
        <strong>{verdict.label}</strong>
        <p>{verdict.reason}</p>
      </div>
      <p className="project-lede">
        This run ended before a recommendation. DARWIN does not retain a candidate, a winner or a
        performance claim from an incomplete screening.
      </p>
      {evaluation.error && <p className="notice" role="alert">{evaluation.error}</p>}
      <div className="project-actions">
        <Action variant="secondary" icon="refresh" onClick={onRerun}>Run a fresh screening</Action>
        <Action variant="quiet" onClick={onChooseAnother}>Choose another project</Action>
      </div>
    </section>;
  }

  const policy = screening.policy;
  const sensitivity = recommendation.seed_sensitivity;
  const hotspotCoverage = screening.hotspots_addressed;
  const candidate = screening.variants.find(variant =>
    variant.id === recommendation.candidate_id && variant.label !== 'Detected baseline');
  const changes = recommendation.changes;

  return <section className="project-panel project-verdict project-sim-verdict" aria-labelledby="project-verdict-title">
    <div className="section-title">
      <div className="panel-heading">
        <span className="section-kicker">Step 5 · Prove · Simulated recommendation</span>
        <h2 id="project-verdict-title">{recommendation.label}</h2>
      </div>
      <span className="status-chip warn"
        title={recordedView
          ? 'This recommendation comes from a saved recorded screening, not a live measurement.'
          : 'This recommendation was generated by the deterministic screening model on this computer. It is not a runtime measurement.'}>
        {recordedView ? 'Recorded simulation' : 'SIMULATED · NOT MEASURED'}
      </span>
    </div>

    <div className="project-sim-banner" role="note">
      <Icon name="shield"/>
      <span><strong>SIMULATED.</strong> No repository code, dependency, container or service was executed.
        Every number below is a model output and must be validated on a real deployment before it is
        described as an improvement.</span>
    </div>

    <div className={`project-verdict-callout ${recommendation.status === 'IMPROVEMENT_CANDIDATE' ? 'good'
      : recommendation.status === 'INCONCLUSIVE' ? 'warn' : 'active'}`} role="status">
      <strong>{recommendation.status.replaceAll('_', ' ')} · {verdict.status.replaceAll('_', ' ')}</strong>
      <p>{recommendation.summary}</p>
    </div>

    <dl className="metrics-grid project-metrics">
      <div><dt>Modelled baseline p95</dt><dd>{formatMs(recommendation.baseline_p95_ms)}</dd>
        <span className="metric-range">synthetic workload</span></div>
      <div><dt>Modelled candidate p95</dt><dd>{formatMs(recommendation.candidate_p95_ms)}</dd>
        <span className="metric-range">same seeds</span></div>
      <div><dt>Modelled change</dt>
        <dd className={(recommendation.modelled_change_pct ?? 0) > 0 ? 'project-good'
          : (recommendation.modelled_change_pct ?? 0) < 0 ? 'project-bad' : ''}>
          {modelledLabel(recommendation.modelled_change_pct)}
        </dd>
        <span className="metric-range">not measured</span></div>
      <div><dt>Cost index</dt><dd>{recommendation.cost_multiplier?.toFixed(2) ?? '—'}×</dd>
        <span className="metric-range">baseline = 1.00×</span></div>
      <div><dt>Modelled error rate</dt><dd>{recommendation.error_rate_pct?.toFixed(2) ?? '—'}%</dd>
        <span className="metric-range">policy limit {policy.maximum_error_rate_pct ?? '—'}%</span></div>
      <div><dt>Candidate state</dt>
        <dd><span className={`status-chip ${candidate?.qualifies ? 'good' : 'warn'}`}>
          {candidate?.qualifies ? 'Clears policy' : 'Does not clear policy'}</span></dd>
        <span className="metric-range">{recommendation.measured ? '' : 'unmeasured'}</span></div>
    </dl>

    <div className="project-sim-grid">
      <div>
        <h3>Recommended control changes</h3>
        {changes.length > 0 ? <div className="table-scroll project-table">
          <table>
            <thead><tr><th scope="col">Control</th><th scope="col">Detected</th><th scope="col">Candidate</th></tr></thead>
            <tbody>{changes.map(change => <tr key={change.control}>
              <th scope="row">{controlLabel(change.control)}</th>
              <td>{setting(change, change.from)}</td>
              <td>{setting(change, change.to)}</td>
            </tr>)}</tbody>
          </table>
        </div> : <p className="muted">
          No control change cleared the policy. The detected baseline is retained as the safer modelled choice.
        </p>}
        <p className="project-footnote">
          Only deployment-level controls supported by inspected source evidence are varied. Application code,
          schemas and business logic are unchanged.
        </p>

        {sensitivity && <div className="project-sim-sensitivity">
          <span className="section-kicker">Seed sensitivity</span>
          <p>
            {sensitivity.min_change_pct >= 0 && sensitivity.max_change_pct >= 0
              ? `Modelled change stays between ${sensitivity.min_change_pct.toFixed(1)}% and ${sensitivity.max_change_pct.toFixed(1)}% lower`
              : sensitivity.min_change_pct <= 0 && sensitivity.max_change_pct <= 0
                ? `Modelled change stays between ${Math.abs(sensitivity.max_change_pct).toFixed(1)}% and ${Math.abs(sensitivity.min_change_pct).toFixed(1)}% higher`
                : `Modelled change spans ${sensitivity.min_change_pct.toFixed(1)}% to ${sensitivity.max_change_pct.toFixed(1)}%`}
            {' '}across seeds {sensitivity.seeds.join(', ')}.
          </p>
        </div>}
      </div>

      <div>
        <h3>Policy applied</h3>
        <dl className="project-sim-policy">
          <div><dt>Primary metric</dt><dd>{String(policy.primary_metric ?? 'modelled p95 latency')}</dd></div>
          <div><dt>Minimum improvement</dt><dd>{policy.minimum_improvement_pct ?? '—'}%</dd></div>
          <div><dt>Regression limit</dt><dd>{policy.regression_limit_pct ?? '—'}%</dd></div>
          <div><dt>Max error rate</dt><dd>{policy.maximum_error_rate_pct ?? '—'}%</dd></div>
          <div><dt>Max cost index</dt><dd>{policy.maximum_cost_multiplier ?? '—'}×</dd></div>
        </dl>
        <p className="project-footnote">
          A candidate is reported only when the modelled p95 improvement clears the minimum and the modelled
          error rate and cost index stay within policy.
        </p>
      </div>
    </div>

    <div className="project-sim-variants">
      <h3>Screened variants <span className="status-chip">{screening.variants.length}</span></h3>
      <div className="table-scroll project-table">
        <table>
          <thead><tr>
            <th scope="col">Variant</th><th scope="col">Modelled p95</th><th scope="col">Change</th>
            <th scope="col">Error rate</th><th scope="col">Cost</th><th scope="col">Policy</th>
          </tr></thead>
          <tbody>{screening.variants.map(variant => <tr key={variant.id}
            className={variant.id === recommendation.candidate_id && variant.label !== 'Detected baseline'
              ? 'project-primary-row' : undefined}>
            <th scope="row">{variant.label}
              {variant.id === recommendation.candidate_id && variant.label !== 'Detected baseline'
                && <span className="project-primary-mark">recommended</span>}</th>
            <td>{formatMs(variant.metrics.p95_ms)}</td>
            <td className={variant.change_pct > 0 ? 'project-good' : variant.change_pct < 0 ? 'project-bad' : ''}>
              {modelledLabel(variant.change_pct)}
            </td>
            <td>{variant.metrics.error_rate_pct.toFixed(2)}%</td>
            <td>{variant.cost_multiplier.toFixed(2)}×</td>
            <td><span className={`status-chip ${variant.qualifies ? 'good' : 'warn'}`}>
              {variant.qualifies ? 'Clears' : 'Below policy'}</span></td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="project-footnote">
        “Detected baseline” is the architecture found in source. Every other row is a hypothetical deployment
        configuration, not a deployed or benchmarked system.
      </p>
    </div>

    {hotspotCoverage.length > 0 && <div className="project-sim-hotspots">
      <h3>Hotspot coverage</h3>
      <ul>{hotspotCoverage.map(item => <li key={item.hotspot}>
        <span className={`status-chip ${item.addressed ? 'good' : 'muted'}`}>
          {item.addressed ? 'Addressed' : 'Not addressed'}
        </span>
        <span>{item.title}<small>Control: {controlLabel(item.control)}</small></span>
      </li>)}</ul>
    </div>}

    <div className="project-sim-grid project-sim-notes">
      <div>
        <h3>Model assumptions</h3>
        <ul className="project-sim-list">{screening.assumptions.map(item => <li key={item}>{item}</li>)}</ul>
      </div>
      <div>
        <h3>Limitations</h3>
        <ul className="project-sim-list">{screening.limitations.map(item => <li key={item}>{item}</li>)}</ul>
      </div>
    </div>

    <div className="project-verdict-grid">
      <div>
        <h3>How this was produced</h3>
        <p className="muted">{screening.workload.note}</p>
        <dl className="project-sim-workload">
          <div><dt>Workload</dt><dd>{screening.workload.name}</dd></div>
          <div><dt>Arrival rate</dt><dd>{screening.workload.arrival_rate_rps} req/s · burst ×{screening.workload.burst_factor}</dd></div>
          <div><dt>Route mix</dt><dd>{screening.workload.routes} route(s) · read {(screening.workload.read_ratio * 100).toFixed(0)}%</dd></div>
          <div><dt>Services / stores</dt><dd>{screening.workload.services} / {screening.workload.datastores}</dd></div>
          <div><dt>Seeds</dt><dd>{screening.seeds.join(', ')}</dd></div>
          <div><dt>Model</dt><dd>{screening.model_version}</dd></div>
        </dl>
      </div>
      <div className="project-verdict-side">
        <h3>Simulation provenance</h3>
        <dl>
          <div><dt>Repository</dt><dd><a href={evaluation.source.url} target="_blank" rel="noreferrer">{evaluation.source.owner}/{evaluation.source.repo}</a></dd></div>
          <div><dt>Pinned commit</dt><dd><code>{evaluation.source.short_sha}</code></dd></div>
          <div><dt>Adapter</dt><dd>{screening.adapter_id} · v{screening.adapter_version}</dd></div>
          <div><dt>Mode</dt><dd>{screening.mode} · {screening.seeds.length} seed(s)</dd></div>
          <div><dt>Evidence kind</dt><dd><span className="status-chip warn">simulated</span></dd></div>
          <div><dt>Execution</dt><dd>None</dd></div>
          <div><dt>Recorded</dt><dd>{formatDate(evaluation.finished_at)}</dd></div>
          <div><dt>Run time</dt><dd>{formatDuration(evaluation.duration_s)}</dd></div>
        </dl>
      </div>
    </div>

    <div className="project-sim-correctness">
      <h3>Correctness scope</h3>
      <p>{verdict.correctness.note ?? 'No repository code was executed.'}</p>
      <p className="project-footnote">
        {verdict.correctness.checks_total} runtime correctness checks were executed. The screening policy gates
        the recommendation on modelled error rate and cost; it does not verify application behaviour.
      </p>
    </div>

    <details className="project-proof">
      <summary>Inspect evidence <span className="status-chip warn">SIMULATED</span></summary>
      <div className="project-proof-body">
        <p className="muted">
          This run stores its architecture model, screening inputs and recommendation as evidence. No runtime
          samples, candidate patch or source execution exist for a simulated screening.
        </p>
        <h3>Evidence files</h3>
        <EvidenceFiles files={evaluation.evidence.files} files_open={artifact.open}
          downloadsAvailable={downloadsAvailable} evaluation={evaluation} artifact={artifact}/>
        <p className="project-footnote">
          Verify every file against <code>manifest.json</code>. Re-running the same pinned source and mode
          reproduces the same deterministic recommendation.
        </p>
      </div>
    </details>

    <div className="project-actions">
      <Action variant="secondary" icon="download" disabled={!downloadsAvailable}
        title={downloadsAvailable ? undefined : 'The evidence archive is available when this page is connected to a live DARWIN bench.'}
        onClick={() => { if (downloadsAvailable) window.location.assign(bundleUrl(evaluation.evaluation_id)); }}>
        Download evidence bundle
      </Action>
      <Action variant="primary" icon="refresh" onClick={onRerun}>Run a fresh screening</Action>
      <Action variant="quiet" onClick={onChooseAnother}>Choose another project</Action>
    </div>
  </section>;
}

function rateLabel(value?: number | null): string {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : `${value.toFixed(2)}/s`;
}

function mbLabel(value?: number | null): string {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : `${value.toFixed(1)} MB`;
}

function cpuLabel(value?: number | null): string {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : `${value.toFixed(3)} s`;
}

function ArchitectureVerdict({evaluation, onRerun, onChooseAnother, downloadsAvailable, recordedView, artifact}
  : Props & {artifact: ArtifactState}) {
  const verdict = evaluation.verdict;
  const measurement = evaluation.architecture;
  const [change, setChange] = useState<string | null>(null);
  const [changeState, setChangeState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [changeError, setChangeError] = useState('');

  if (!verdict) return null;

  const runs: ArchitectureRun[] = measurement?.runs?.length
    ? measurement.runs.map(run => (run.metrics ? {...run, ...run.metrics} : run))
    : verdict.comparison ?? [];
  const baseline = runs.find(item => item.candidate_id === verdict.baseline_id)
    ?? runs.find(item => item.baseline) ?? runs[0];
  const winner = runs.find(item => item.candidate_id === verdict.winner_id);
  const challenge = measurement?.challenge ?? evaluation.workload?.challenge;
  const env = measurement?.environment;
  const regressions = verdict.regressions ?? [];
  const live = !recordedView && evaluation.evidence_kind === 'live';
  const changes = winner && baseline
    ? [
      {label: 'Service replicas', from: baseline.replicas, to: winner.replicas},
      {label: 'Gunicorn workers', from: baseline.workers, to: winner.workers},
    ].filter(item => item.from !== item.to)
    : [];

  async function loadChange() {
    if (change !== null) return;
    setChangeState('loading');
    try {
      setChange(await api.change(evaluation.evaluation_id));
      setChangeState('idle');
    } catch (reason) {
      setChangeState('error');
      setChangeError(reason instanceof Error ? reason.message : 'The change document could not be loaded.');
    }
  }

  return <section className="project-panel project-verdict" aria-labelledby="project-verdict-title">
    <div className="section-title">
      <div className="panel-heading">
        <span className="section-kicker">Step 5 · Prove</span>
        <h2 id="project-verdict-title">{verdict.label}</h2>
      </div>
      <span className={`status-chip ${live ? 'good' : 'warn'}`}
        title={live
          ? 'Measured on this computer in an isolated loopback stack and stored as evidence.'
          : 'This verdict is a saved run, not a live measurement.'}>
        {live ? 'LIVE · this computer' : 'RECORDED evidence'}
      </span>
    </div>

    <div className={`project-verdict-callout ${tone(verdict.status)}`} role="status">
      <strong>{verdict.status.replaceAll('_', ' ')}</strong>
      <p>{verdict.reason}</p>
    </div>

    <div className="project-decision">
      <div className="project-decision-main">
        <span className="section-kicker">Decision card</span>
        <h3>{winner ? winner.label : 'Original architecture retained'}</h3>
        <dl className="project-decision-facts">
          <div><dt>Challenge</dt><dd>{challenge ? challenge.replaceAll('_', ' ') : '—'}</dd></div>
          <div><dt>Original</dt><dd>{baseline ? `${baseline.replicas} replica(s) × ${baseline.workers} worker(s)` : '—'}</dd></div>
          <div><dt>Recommended</dt><dd>{winner ? `${winner.replicas} replica(s) × ${winner.workers} worker(s)` : 'No change'}</dd></div>
          <div><dt>Correctness</dt>
            <dd>{verdict.correctness.checks_passed}/{verdict.correctness.checks_total} checks</dd></div>
          <div><dt>Evidence</dt><dd><span className={`status-chip ${live ? 'good' : 'warn'}`}>
            {live ? 'LIVE' : 'RECORDED'}</span></dd></div>
          <div><dt>Confidence limits</dt><dd>One host, one workload window</dd></div>
        </dl>
        {changes.length > 0 ? <div className="table-scroll project-table">
          <table>
            <thead><tr><th scope="col">Deployable change</th><th scope="col">Original</th><th scope="col">Recommended</th></tr></thead>
            <tbody>{changes.map(item => <tr key={item.label}>
              <th scope="row">{item.label}</th>
              <td>{item.from}</td>
              <td>{item.to}</td>
            </tr>)}</tbody>
          </table>
        </div> : <p className="muted">The measured evidence does not support a deployment change.</p>}
        <p className="project-footnote">
          Thresholds: at least {verdict.policy.minimum_improvement_pct ?? 8}% better on the challenge metric,
          error rate at most {((verdict.policy.maximum_error_rate ?? 0.05) * 100).toFixed(0)}%, and no regression
          above {verdict.policy.regression_limit_pct ?? 5}% on latency, CPU, memory or throughput.
        </p>
      </div>
      <div className="project-decision-side">
        <span className="section-kicker">What this is not</span>
        <ul className="project-decision-limits">
          <li>Not a production benchmark: the load generator and the service share one host.</li>
          <li>Not the repository's own Compose file or Dockerfile; DARWIN deploys a reviewed stack.</li>
          <li>Not a business-correctness proof: the oracle checks HTTP health and counter monotonicity.</li>
          <li>No number here is simulated or estimated.</li>
        </ul>
        {measurement && !measurement.complete && <p className="notice" role="alert">
          This run was incomplete. {measurement.skipped?.length ?? 0} candidate(s) did not run inside the
          bounded budget. No missing number was filled in.
        </p>}
      </div>
    </div>

    {regressions.length > 0 && <div className="project-regressions" role="alert">
      <h3>Cost of this change</h3>
      <ul>{regressions.map(item => <li key={item.metric}>
        <span className="status-chip warn">Regressed</span>
        <span>{item.label}: {typeof item.baseline === 'number' ? item.baseline.toFixed(3) : item.baseline}
          {' → '}{typeof item.candidate === 'number' ? item.candidate.toFixed(3) : item.candidate}
          <small>{item.change_pct > 0 ? '+' : ''}{item.change_pct.toFixed(1)}%</small></span>
      </li>)}</ul>
      <p className="project-footnote">
        A win on the challenge metric never erases a regression elsewhere. DARWIN reports the tradeoff
        instead of a single winner score.
      </p>
    </div>}

    {challenge === 'recover' && <div className="project-recovery">
      <h3>Recovery measured during a web-replica restart</h3>
      <dl className="project-recovery-grid">
        <div><dt>Original</dt><dd>{formatMs((verdict.baseline_recovery_s ?? 0) * 1000)}</dd></div>
        <div><dt>Recommended</dt><dd>{formatMs((verdict.candidate_recovery_s ?? 0) * 1000)}</dd></div>
      </dl>
      <p className="muted">{(verdict.recovery_notes ?? []).join(' ')}</p>
    </div>}

    <div className="project-verdict-grid project-comparison">
      <div>
        <h3>Measured comparison</h3>
        {runs.length > 0 ? <div className="table-scroll project-table">
          <table>
            <thead><tr>
              <th scope="col">Configuration</th>
              <th scope="col">p95</th><th scope="col">Throughput</th><th scope="col">Errors</th>
              <th scope="col">CPU</th><th scope="col">Peak memory</th>
              {challenge === 'recover' && <th scope="col">Recovery</th>}
            </tr></thead>
            <tbody>{runs.map(item => <tr key={item.candidate_id}
              className={item.candidate_id === verdict.winner_id ? 'project-primary-row' : undefined}>
              <th scope="row">{item.label}
                <span className="project-run-shape">{item.replicas} × {item.workers}</span>
                {item.candidate_id === verdict.winner_id && <span className="project-primary-mark">recommended</span>}
                {item.candidate_id === verdict.baseline_id && <span className="project-primary-mark">original</span>}
              </th>
              <td>{formatMs(item.p95_ms)}</td>
              <td>{rateLabel(item.requests_per_s)}</td>
              <td>{item.error_rate === null || item.error_rate === undefined
                ? '—' : `${(item.error_rate * 100).toFixed(2)}%`}</td>
              <td>{cpuLabel(item.cpu_seconds)}</td>
              <td>{mbLabel(item.memory_peak_mb)}</td>
              {challenge === 'recover' && <td>{item.recovery_s == null ? '—' : formatMs(item.recovery_s * 1000)}</td>}
            </tr>)}</tbody>
          </table>
        </div> : <p className="muted">No measured run was retained. There is no performance claim to make.</p>}
        <p className="project-footnote">
          Median across repeated runs for latency, throughput, CPU and memory; the worst error rate is kept.
          Recovery is the user-visible outage at the gateway after a restart.
        </p>
      </div>
      <div className="project-verdict-side">
        <h3>Provenance</h3>
        <dl>
          <div><dt>Repository</dt><dd><a href={evaluation.source.url} target="_blank" rel="noreferrer">{evaluation.source.owner}/{evaluation.source.repo}</a></dd></div>
          <div><dt>Pinned commit</dt><dd><code>{evaluation.source.short_sha}</code></dd></div>
          <div><dt>Adapter</dt><dd>{evaluation.adapter_id} · v{evaluation.adapter_version}</dd></div>
          <div><dt>Challenge</dt><dd>{challenge ?? '—'}</dd></div>
          <div><dt>Mode</dt><dd>{evaluation.mode} · {measurement?.repetitions_requested ?? 1} repetition(s)</dd></div>
          <div><dt>Isolation</dt><dd>{env?.isolation ?? '—'} · loopback only</dd></div>
          <div><dt>Load window</dt><dd>{env?.load_window_s ?? '—'} s · {env?.load_rate_per_s ?? '—'} req/s</dd></div>
          <div><dt>Repository Compose</dt><dd>{env?.repository_compose_used ? 'used' : 'not used'}</dd></div>
          <div><dt>Recorded</dt><dd>{formatDate(evaluation.finished_at)}</dd></div>
          <div><dt>Run time</dt><dd>{formatDuration(evaluation.duration_s)}</dd></div>
        </dl>
      </div>
    </div>

    <details className="project-proof">
      <summary>Advanced evidence <span className="status-chip">{evaluation.evidence.files.length} files</span></summary>
      <div className="project-proof-body">
        <h3>Correctness gates</h3>
        <ul className="project-check-list">
          {(evaluation.correctness?.checks ?? []).map(check => <li key={check.name}
            className={check.passed ? 'passed' : 'failed'}>
            <span className={`status-chip ${check.passed ? 'good' : 'bad'}`}>{check.passed ? 'Pass' : 'Fail'}</span>
            <span>{check.name}{check.detail && <small>{check.detail}</small>}</span>
          </li>)}
        </ul>
        <p className="muted">{verdict.correctness.note}</p>

        {runs.length > 0 && <details>
          <summary>Repeated live runs</summary>
          <div className="table-scroll project-table">
            <table>
              <thead><tr><th scope="col">Configuration</th><th scope="col">Rep</th><th scope="col">p95</th>
                <th scope="col">Throughput</th><th scope="col">Errors</th></tr></thead>
              <tbody>{runs.flatMap(run => (run.repetitions ?? []).map(rep => <tr key={`${run.candidate_id}-${rep.repetition}`}>
                <th scope="row">{run.label}</th><td>{rep.repetition}</td>
                <td>{formatMs(rep.metrics.p95_ms)}</td><td>{rateLabel(rep.metrics.requests_per_s)}</td>
                <td>{(rep.metrics.error_rate * 100).toFixed(2)}%</td>
              </tr>))}</tbody>
            </table>
          </div>
        </details>}

        {measurement?.pareto && measurement.pareto.length > 0 && <p className="project-footnote">
          Non-dominated configurations on p95, error rate and replica count:{' '}
          {measurement.pareto.map(item => item.candidate_id).join(', ')}.
        </p>}

        <h3>Evidence files</h3>
        <EvidenceFiles files={evaluation.evidence.files} files_open={artifact.open}
          downloadsAvailable={downloadsAvailable} evaluation={evaluation} artifact={artifact}/>
        <p className="project-footnote">
          Verify every file against <code>manifest.json</code>. Raw samples live in <code>benchmark.json</code>;
          <code>change.md</code> records the decision, the measured comparison and any deployment change.
        </p>
      </div>
    </details>

    {changes.length === 0 && <p className="project-footnote project-no-change">
      No deployment change is exported for this verdict. <code>change.md</code> in the evidence bundle
      still records the measured comparison, the apply and rollback notes, and the limits of the run.
    </p>}

    <div className="project-actions">
      {changes.length > 0 && <Action variant="secondary" icon="code" pending={changeState === 'loading'} onClick={() => void loadChange()}>
        Open deployment change
      </Action>}
      <Action variant="secondary" icon="download" disabled={!downloadsAvailable}
        title={downloadsAvailable ? undefined : 'The evidence archive is available when this page is connected to a live DARWIN bench.'}
        onClick={() => { if (downloadsAvailable) window.location.assign(bundleUrl(evaluation.evaluation_id)); }}>
        Download evidence bundle
      </Action>
      <Action variant="primary" icon="refresh" onClick={onRerun}>Run a fresh comparison</Action>
      <Action variant="quiet" onClick={onChooseAnother}>Choose another project</Action>
    </div>
    {changeState === 'error' && <p className="notice" role="alert">{changeError}</p>}
    {change !== null && <details open className="project-diff">
      <summary>Deployment change · review before applying</summary>
      <pre className="project-pre">{change}</pre>
      <p className="project-footnote">
        This is a reviewable change, not an automatic edit. DARWIN never edits, commits or pushes the
        project repository; rollback is described in the document.
      </p>
    </details>}
  </section>;
}

export function ProjectVerdict(props: Props) {
  const {evaluation, onRerun, onChooseAnother, downloadsAvailable, recordedView} = props;
  const verdict = evaluation.verdict;
  const [diff, setDiff] = useState<string | null>(null);
  const [diffState, setDiffState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [diffError, setDiffError] = useState('');
  const [artifact, setArtifact] = useState<{name: string; text: string} | null>(null);
  const [artifactBusy, setArtifactBusy] = useState('');
  const [artifactError, setArtifactError] = useState('');
  const primary = verdict?.primary_size;
  const tests = checkLabel(evaluation.source_tests);
  const checks = evaluation.correctness?.checks ?? [];
  const failures = verdict?.correctness.failures ?? [];
  const env = evaluation.environment;
  const liveEvidence = !recordedView && evaluation.evidence_kind === 'live';
  const simulated = evaluation.evaluation_type === 'architecture_screening'
    || evaluation.evidence_kind === 'simulated' || Boolean(evaluation.screening);

  async function loadDiff() {
    if (diff !== null) return;
    setDiffState('loading');
    try {
      setDiff(await api.diff(evaluation.evaluation_id));
      setDiffState('idle');
    } catch (reason) {
      setDiffState('error');
      setDiffError(reason instanceof Error ? reason.message : 'The diff could not be loaded.');
    }
  }

  async function openArtifact(name: string) {
    setArtifactBusy(name);
    setArtifactError('');
    try {
      const response = await fetch(artifactUrl(evaluation.evaluation_id, name));
      if (!response.ok) throw Error(`The recorded artifact could not be loaded (HTTP ${response.status}).`);
      setArtifact({name, text: await response.text()});
    } catch (reason) {
      setArtifact(null);
      setArtifactError(reason instanceof Error ? reason.message : 'The recorded artifact could not be loaded.');
    } finally {
      setArtifactBusy('');
    }
  }

  const artifactState: ArtifactState = {
    artifact, busy: artifactBusy, error: artifactError, open: openArtifact,
  };

  if (simulated) {
    return <ScreeningVerdict {...props} artifact={artifactState}/>;
  }

  if (evaluation.evaluation_type === 'backend_architecture') {
    return <ArchitectureVerdict {...props} artifact={artifactState}/>;
  }

  if (!verdict) {
    return <section className="project-panel project-verdict">
      <span className="section-kicker">Step 5 · Prove · Verdict</span>
      <h2>No verdict was recorded</h2>
      <p className="project-lede">This evaluation ended without a defensible result. DARWIN will not invent one.</p>
      {evaluation.error && <p className="notice" role="alert">{evaluation.error}</p>}
      <div className="project-actions">
        <Action variant="secondary" icon="refresh" onClick={onRerun}>Run again</Action>
        <Action variant="quiet" onClick={onChooseAnother}>Choose another project</Action>
      </div>
    </section>;
  }

  const verdictTone = tone(verdict.status);
  return <section className="project-panel project-verdict" aria-labelledby="project-verdict-title">
    <div className="section-title">
      <div className="panel-heading">
        <span className="section-kicker">Step 5 · Prove · Verdict</span>
        <h2 id="project-verdict-title">{verdict.label}</h2>
      </div>
      <span className={`status-chip ${liveEvidence ? 'good' : ''}`}
        title={liveEvidence
          ? 'Measured by the DARWIN bench on this computer and stored as evidence. It is not a continuously updating feed.'
          : 'This verdict comes from a saved recorded run, not a live measurement.'}>
        {liveEvidence ? 'Live measurement' : 'Recorded evidence'}
      </span>
    </div>

    <div className={`project-verdict-callout ${verdictTone}`} role="status">
      <strong>{verdict.status.replaceAll('_', ' ')}</strong>
      <p>{verdict.reason}</p>
    </div>

    <dl className="metrics-grid project-metrics">
      <div><dt>Original median</dt><dd>{formatMs(verdict.baseline_median_ms)}</dd><span className="metric-range">{primary ? `${formatRows(primary)} rows` : ''}</span></div>
      <div><dt>Candidate median</dt><dd>{formatMs(verdict.candidate_median_ms)}</dd><span className="metric-range">{primary ? `${formatRows(primary)} rows` : ''}</span></div>
      <div><dt>Time change</dt><dd>{changeLabel(verdict.change_pct)}</dd><span className="metric-range">{speedLabel(verdict.change_pct)}</span></div>
      <div><dt>Correctness</dt><dd>{verdict.correctness.checks_passed}/{verdict.correctness.checks_total}</dd><span className="metric-range">{verdict.correctness.passed ? 'all checks passed' : 'failed'}</span></div>
    </dl>

    <div className="project-verdict-grid">
      <div>
        <h3>Measured workloads</h3>
        {verdict.per_size.length > 0 ? <div className="table-scroll project-table">
          <table>
            <thead><tr><th scope="col">Ledger</th><th scope="col">Original</th><th scope="col">Candidate</th><th scope="col">Time change</th><th scope="col">Paired wins</th><th scope="col">Samples</th></tr></thead>
            <tbody>{verdict.per_size.map(item => <MeasurementRow key={item.size}
              item={item} primary={item.size === primary}/>)}</tbody>
          </table>
        </div> : <p className="muted">No timed samples were retained. There is no performance claim to make.</p>}
        <p className="project-footnote">
          Pure report-calculation timing, measured after warm-up on the same host.
          Currency scoping and React rendering sit outside the timed region.
          “Primary” is the largest measured ledger and drives the verdict.
        </p>
      </div>
      <div className="project-verdict-side">
        <h3>Correctness and provenance</h3>
        <dl>
          <div><dt>Repository</dt><dd><a href={evaluation.source.url} target="_blank" rel="noreferrer">{evaluation.source.owner}/{evaluation.source.repo}</a></dd></div>
          <div><dt>Commit</dt><dd><code>{evaluation.source.short_sha}</code></dd></div>
          <div><dt>Adapter</dt><dd>{evaluation.adapter_id} · v{evaluation.adapter_version}</dd></div>
          <div><dt>Mode</dt><dd>{evaluation.mode} · {evaluation.workload.seeds.length} seed(s)</dd></div>
          <div><dt>Recorded</dt><dd>{formatDate(evaluation.finished_at)}</dd></div>
          <div><dt>Run time</dt><dd>{formatDuration(evaluation.duration_s)}</dd></div>
          <div><dt>Source tests</dt><dd><span className={`status-chip ${tests.tone}`}>{tests.text}</span></dd></div>
          {evaluation.source_tests?.status === 'skipped' && evaluation.source_tests.reason &&
            <div><dt>Why skipped</dt><dd>{evaluation.source_tests.reason}</dd></div>}
        </dl>
        {env && <details>
          <summary>Runtime and hardware</summary>
          <dl>
            <div><dt>Node</dt><dd>{env.node_version ?? '—'}</dd></div>
            <div><dt>Platform</dt><dd>{env.platform ?? '—'} · {env.arch ?? '—'}</dd></div>
            <div><dt>CPU</dt><dd>{env.cpu_model ?? '—'}</dd></div>
            <div><dt>Memory</dt><dd>{env.total_memory_bytes ? `${(env.total_memory_bytes / 1024 ** 3).toFixed(1)} GB` : '—'}</dd></div>
          </dl>
        </details>}
      </div>
    </div>

    {failures.length > 0 && <div className="project-failures" role="alert">
      <h3>Correctness failures</h3>
      <ul>{failures.map(failure => <li key={failure.name}><strong>{failure.name}</strong>{failure.detail}</li>)}</ul>
    </div>}

    <details className="project-proof">
      <summary>Inspect proof <span className={`status-chip ${checks.every(check => check.passed) ? 'good' : 'bad'}`}>{checks.filter(check => check.passed).length}/{checks.length} checks</span></summary>
      <div className="project-proof-body">
        <p className="muted">
          Exact checks executed against the real reporting functions and the isolated candidate overlay.
          Every check below is a hard gate: a faster candidate that changes a report is rejected.
        </p>
        <ul className="project-check-list">
          {checks.map(check => <li key={check.name} className={check.passed ? 'passed' : 'failed'}>
            <span className={`status-chip ${check.passed ? 'good' : 'bad'}`}>{check.passed ? 'Pass' : 'Fail'}</span>
            <span>{check.name}{check.detail && <small>{check.detail}</small>}</span>
          </li>)}
        </ul>
        {evaluation.source_tests?.output_tail && <details>
          <summary>Source-test output</summary>
          <pre className="project-pre">{evaluation.source_tests.output_tail}</pre>
        </details>}
        <h3>Evidence files</h3>
        <EvidenceFiles files={evaluation.evidence.files} files_open={artifactState.open}
          downloadsAvailable={downloadsAvailable} evaluation={evaluation} artifact={artifactState}/>
        <p className="project-footnote">Verify every file against <code>manifest.json</code>. Raw samples live in <code>benchmark.json</code>.</p>
      </div>
    </details>

    <div className="project-actions">
      <Action variant="secondary" icon="download" disabled={!downloadsAvailable}
        title={downloadsAvailable ? undefined : 'The evidence archive is available when this page is connected to a live DARWIN bench.'}
        onClick={() => { if (downloadsAvailable) window.location.assign(bundleUrl(evaluation.evaluation_id)); }}>
        Download evidence bundle
      </Action>
      <Action variant="secondary" icon="code" pending={diffState === 'loading'} onClick={() => void loadDiff()}>View code diff</Action>
      <Action variant="primary" icon="play" onClick={onRerun}>Run a fresh comparison</Action>
      <Action variant="quiet" onClick={onChooseAnother}>Choose another project</Action>
    </div>
    {diffState === 'error' && <p className="notice" role="alert">{diffError}</p>}
    {diff !== null && <details open className="project-diff">
      <summary>Candidate diff · read-only source overlay</summary>
      <pre className="project-pre">{diff || 'The recorded diff is empty.'}</pre>
      <p className="project-footnote">
        This patch is evidence, not an automatic change. DARWIN never edits, commits or pushes the project repository.
      </p>
    </details>}
  </section>;
}
