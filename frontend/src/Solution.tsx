import {useEffect, useState} from 'react';
import {Action, Icon} from './Action';
import {api, bundleUrl, changeLabel, formatDate, formatDuration, formatMs, tone, type Evaluation} from './projectApi';
import {isLive} from './showcase';

const stages = [
  {id: 'overview', label: 'Overview'},
  {id: 'project', label: 'Project Workspace'},
  {id: 'configuration', label: 'Architecture'},
  {id: 'experiments', label: 'Experiments'},
  {id: 'search', label: 'Evolution'},
  {id: 'solution', label: 'Solution'},
] as const;

function newestFirst(rows: Evaluation[]): Evaluation[] {
  const when = (item: Evaluation) => item.finished_at ?? item.started_at ?? item.created_at;
  return [...rows].sort((a, b) => when(b).localeCompare(when(a)));
}

function simulated(evaluation: Evaluation): boolean {
  return evaluation.evaluation_type === 'architecture_screening'
    || evaluation.evidence_kind === 'simulated' || Boolean(evaluation.screening);
}

export function Solution() {
  const live = isLive();
  const [rows, setRows] = useState<Evaluation[] | null>(null);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const list = newestFirst((await api.evaluations()).filter(item => item.verdict));
      setRows(list);
      setSelected(current => current || list[0]?.evaluation_id || '');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The recorded decisions could not be loaded.');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const evaluation = rows?.find(item => item.evaluation_id === selected) ?? null;
  const verdict = evaluation?.verdict ?? null;
  const screening = evaluation ? simulated(evaluation) : false;
  const change = verdict?.change_pct;
  const actionable = verdict?.status === 'VERIFIED_IMPROVEMENT' || verdict?.status === 'TRADEOFF_REQUIRES_CHOICE';
  const checks = verdict?.correctness;

  return <div className="solution-page">
    <section className="overview solution-hero" aria-labelledby="solution-title">
      <div className="hero-copy">
        <span className="section-kicker hero-kicker"><span/>Stage 06 · Solution</span>
        <h2 id="solution-title">A decision the team can act on.</h2>
        <p>A solution here is not a diagram or a slide. It is the recommended configuration, the measured
          trade-off it buys, the correctness checks it passed, the evidence behind it and the way back
          if it does not hold up in your own environment.</p>
        <div className="shop-actions">
          <a className="primary action-link" href="#project">Run a fresh evaluation <Icon name="arrow"/></a>
          <button type="button" className="hero-secondary" onClick={() => document.getElementById('decision-record')?.scrollIntoView({behavior: 'smooth', block: 'start'})}>
            Read the latest decision <Icon name="arrow"/>
          </button>
        </div>
      </div>
      <aside className="panel solution-hero-card" aria-label="The six stages">
        <span className="section-kicker">One project, end to end</span>
        <ol className="solution-stage-list">
          {stages.map((stage, index) => <li key={stage.id} className={stage.id === 'solution' ? 'current' : undefined}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <strong>{stage.label}</strong>
            {stage.id === 'solution' && <em>You are here</em>}
          </li>)}
        </ol>
      </aside>
    </section>

    <section className="solution-section" id="decision-record" aria-labelledby="decision-title">
      <div className="story-section-head">
        <div><span className="section-kicker">Recorded decisions</span><h2 id="decision-title">The latest evidence-backed outcome</h2></div>
        <span className="story-readout">{live ? 'Live bench' : 'Recorded evidence'}</span>
      </div>

      {error && <p className="notice" role="alert">{error}</p>}

      {loading && <p className="muted solution-loading">Loading recorded decisions…</p>}

      {!loading && rows && rows.length > 0 && evaluation && verdict && <>
        <div className="solution-selector">
          <label htmlFor="solution-decision">Decision</label>
          <select id="solution-decision" value={selected} onChange={event => setSelected(event.target.value)}>
            {rows.map(item => <option key={item.evaluation_id} value={item.evaluation_id}>
              {item.source.owner}/{item.source.repo} · {item.source.short_sha} · {item.verdict?.label ?? item.status} · {formatDate(item.finished_at)}
            </option>)}
          </select>
        </div>

        <article className="panel solution-card">
          <div className="section-title">
            <div className="panel-heading">
              <span className="section-kicker">{screening ? 'Simulated recommendation' : 'Measured verdict'}</span>
              <h3>{verdict.label}</h3>
            </div>
            <span className={`status-chip ${screening ? 'warn' : tone(verdict.status)}`}>
              {screening ? 'SIMULATED · NOT MEASURED' : live ? 'LIVE · this computer' : 'RECORDED · measured'}
            </span>
          </div>

          <div className={`project-verdict-callout ${screening ? 'warn' : tone(verdict.status)}`} role="status">
            <strong>{verdict.status.replaceAll('_', ' ')}</strong>
            <p>{verdict.reason}</p>
          </div>

          {screening && <p className="notice" role="note">
            This decision comes from the file-backed architecture model, not a runtime measurement.
            It is labelled SIMULATED / NOT_MEASURED and can never be promoted to a measured winner.
          </p>}

          <dl className="solution-facts">
            <div><dt>Project</dt><dd><a href={evaluation.source.url} target="_blank" rel="noreferrer">{evaluation.source.owner}/{evaluation.source.repo}</a></dd></div>
            <div><dt>Pinned commit</dt><dd><code>{evaluation.source.short_sha}</code></dd></div>
            <div><dt>Challenge</dt><dd>{evaluation.workload.challenge?.replaceAll('_', ' ') ?? '—'}</dd></div>
            <div><dt>Mode</dt><dd>{evaluation.mode} · {evaluation.workload.repetitions} repetition(s)</dd></div>
            <div><dt>Correctness</dt><dd>{checks ? `${checks.checks_passed}/${checks.checks_total} checks passed` : '—'}</dd></div>
            <div><dt>Evidence kind</dt><dd>{screening ? 'simulated' : evaluation.evidence_kind}</dd></div>
            <div><dt>Recorded</dt><dd>{formatDate(evaluation.finished_at)}</dd></div>
            <div><dt>Run time</dt><dd>{formatDuration(evaluation.duration_s)}</dd></div>
          </dl>

          {!screening && <dl className="metrics-grid solution-metrics">
            {(actionable ? verdict.candidate_median_ms : verdict.baseline_median_ms) !== undefined
              && <div><dt>{actionable ? 'Recommended median' : 'Original median'}</dt>
                <dd>{formatMs(actionable ? verdict.candidate_median_ms : verdict.baseline_median_ms)}
                  <span className="metric-range">{actionable ? `original ${formatMs(verdict.baseline_median_ms)}` : 'measured'}</span></dd></div>}
            {change !== undefined
              && <div><dt>Change</dt>
                <dd className={actionable && change > 0 ? 'project-good' : undefined}>{changeLabel(change)}
                  <span className="metric-range">{actionable ? 'positive is faster' : 'no deployment change'}</span></dd></div>}
            <div><dt>p95 original</dt><dd>{formatMs(verdict.baseline_p95_ms)}<span className="metric-range">measured</span></dd></div>
            <div><dt>p95 {actionable ? 'recommended' : 'candidate'}</dt><dd>{formatMs(verdict.candidate_p95_ms)}<span className="metric-range">measured</span></dd></div>
          </dl>}

          {!screening && (verdict.regressions?.length ?? 0) > 0 && <div className="project-regressions">
            <h3>Cost of the change</h3>
            <ul>{verdict.regressions?.map(item => <li key={item.metric}>
              <span className="status-chip warn">Regressed</span>
              <span>{item.label}: {item.baseline.toFixed(3)} → {item.candidate.toFixed(3)}
                <small>{item.change_pct > 0 ? '+' : ''}{item.change_pct.toFixed(1)}%</small></span>
            </li>)}</ul>
          </div>}

          <div className="solution-plan">
            <div>
              <span className="section-kicker">Recommendation</span>
              <p>{verdict.status === 'VERIFIED_IMPROVEMENT'
                ? 'The measured evidence supports the candidate above. Review the deployment change before applying it; the original configuration stays the fallback.'
                : verdict.status === 'TRADEOFF_REQUIRES_CHOICE'
                  ? 'The candidate buys the measured improvement at the cost shown above. DARWIN will not choose for you: adopt it only if those regressions are acceptable for this deployment.'
                  : 'The measured evidence does not justify a deployment change. Keep the current architecture and, if needed, rerun with a different challenge.'}</p>
              <p className="project-footnote">
                {screening
                  ? 'A simulated recommendation is a direction to test, not a deployment instruction.'
                  : 'The change document records the apply and rollback notes; DARWIN never edits, commits or pushes the project repository.'}
              </p>
            </div>
            <div>
              <span className="section-kicker">Evidence to keep</span>
              <ul className="solution-files">
                {evaluation.evidence.files.slice(0, 6).map(file => <li key={file.name}>
                  <code>{file.name}</code><span className="project-digest">{file.sha256.slice(0, 10)}</span>
                </li>)}
              </ul>
              <p className="project-footnote">{evaluation.evidence.files.length} file(s) in the bundle{evaluation.evidence.manifest_sha256 ? ' · manifest hash recorded' : ''}.</p>
            </div>
          </div>

          <div className="project-actions">
            <Action variant="secondary" icon="download" disabled={!live}
              title={live ? undefined : 'The evidence archive is available when this page is connected to a live DARWIN bench.'}
              onClick={() => { if (live) window.location.assign(bundleUrl(evaluation.evaluation_id)); }}>
              Download evidence bundle
            </Action>
            <a className="action-link" href="#project"><Icon name="refresh"/><span>Run a fresh comparison</span></a>
          </div>
        </article>
      </>}

      {!loading && rows && rows.length === 0 && <article className="panel solution-empty">
        <Icon name="project"/>
        <div>
          <h3>No decision has been recorded yet.</h3>
          <p className="muted">Start in the Project Workspace: pin one public backend commit, choose an adapter and a challenge,
            and let the Experiments and Evolution stages produce a measured verdict.</p>
          <a className="primary action-link" href="#project">Open the Project Workspace <Icon name="arrow"/></a>
        </div>
      </article>}
    </section>

    <section className="solution-section" aria-labelledby="boundary-title">
      <div className="story-section-head">
        <div><span className="section-kicker">Truth boundary</span><h2 id="boundary-title">What a solution here does and does not claim</h2></div>
        <span className="story-readout">Evidence over assertion</span>
      </div>
      <div className="solution-boundary">
        <article className="panel story-scope-card">
          <div className="section-title"><div className="panel-heading"><span className="section-kicker">Included</span><h3>What the decision carries</h3></div></div>
          <ul>
            <li><Icon name="check"/><span>The same pinned commit, reviewed adapter and candidate IDs across every stage.</span></li>
            <li><Icon name="check"/><span>Correctness gates before performance: an incorrect candidate is rejected, however fast.</span></li>
            <li><Icon name="check"/><span>Measured numbers kept with seeds, artifacts, hashes and a replay command.</span></li>
            <li><Icon name="check"/><span>A reviewable change and rollback notes, never an automatic repository edit.</span></li>
          </ul>
        </article>
        <article className="panel story-scope-card story-scope-next">
          <div className="section-title"><div className="panel-heading"><span className="section-kicker">Excluded</span><h3>What it does not claim</h3></div></div>
          <ul>
            <li><Icon name="close"/><span>Not a production benchmark: the load generator and the service share one host.</span></li>
            <li><Icon name="close"/><span>Not a proof for every workload; the measured window and scenario are stated.</span></li>
            <li><Icon name="close"/><span>Not a simulation promoted to a winner: simulated results stay labelled NOT_MEASURED.</span></li>
            <li><Icon name="close"/><span>Not an automatic deployment; applying and validating the change belongs to your team.</span></li>
          </ul>
        </article>
      </div>
      <p className="story-footnote">Recorded decisions come from a local DARWIN bench and are presented as saved evidence.
        When this page is connected to a live bench, the same panel reads the current run instead.</p>
    </section>
  </div>;
}
