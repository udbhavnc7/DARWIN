import {useState} from 'react';
import {Action, Icon} from './Action';
import {
  api, artifactUrl, bundleUrl, changeLabel, controlLabel, formatDate, formatDuration, formatMs,
  formatRows, tone, type Evaluation, type EvidenceFile, type Measurement, type ScreeningChange,
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
          <span className="section-kicker">Step 4 · Simulated screening</span>
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
        <span className="section-kicker">Step 4 · Simulated recommendation</span>
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

  if (!verdict) {
    return <section className="project-panel project-verdict">
      <span className="section-kicker">Step 4 · Verdict</span>
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
        <span className="section-kicker">Step 4 · Verdict</span>
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
