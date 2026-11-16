import {useState} from 'react';
import {Action, Icon} from './Action';
import {
  api, artifactUrl, bundleUrl, changeLabel, formatDate, formatDuration, formatMs, formatRows,
  tone, type Evaluation, type Measurement,
} from './projectApi';

type Props = {
  evaluation: Evaluation;
  onRerun: () => void;
  onChooseAnother: () => void;
  downloadsAvailable: boolean;
  recordedView: boolean;
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
  if (test.status === 'passed') return {text: `Sanchay reporting tests passed${counts}`, tone: 'good'};
  if (test.status === 'failed') return {text: `Source tests failed${counts}`, tone: 'bad'};
  if (test.status === 'skipped') return {text: 'Source tests skipped', tone: 'warn'};
  return {text: 'Not run in this mode', tone: 'muted'};
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

export function ProjectVerdict({evaluation, onRerun, onChooseAnother, downloadsAvailable, recordedView}: Props) {
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
          <summary>Sanchay source-test output</summary>
          <pre className="project-pre">{evaluation.source_tests.output_tail}</pre>
        </details>}
        <h3>Evidence files</h3>
        <ul className="project-evidence-links">
          {evaluation.evidence.files.map(file => <li key={file.name}>
            {downloadsAvailable
              ? <a className="artifact-link" href={artifactUrl(evaluation.evaluation_id, file.name)}>
                <Icon name="download"/>{file.name}<span className="project-digest">{file.sha256.slice(0, 10)}</span>
              </a>
              : <button type="button" className="artifact-link artifact-recorded" aria-busy={artifactBusy === file.name}
                title={`Open the recorded ${file.name}`} onClick={() => void openArtifact(file.name)}>
                <Icon name="book"/>{file.name}<span className="project-digest">{file.sha256.slice(0, 10)}</span>
              </button>}
          </li>)}
        </ul>
        {artifact && <details open className="project-artifact-view">
          <summary>Recorded artifact · {artifact.name}</summary>
          <pre className="project-pre">{artifact.text}</pre>
        </details>}
        {artifactError && <p className="notice" role="alert">{artifactError}</p>}
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
