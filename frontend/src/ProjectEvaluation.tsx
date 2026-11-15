import {useEffect, useRef, useState} from 'react';
import {Action, Icon} from './Action';
import {ProjectVerdict} from './ProjectVerdict';
import {RepositoryArchitecture} from './RepositoryArchitecture';
import {isLive, showcase} from './showcase';
import {
  api, formatDate, formatDuration, formatRows, isRunning, isTerminal, stageLabel, stageState,
  tone, type Catalog, type Evaluation, type Inspection, type ProjectEvent,
} from './projectApi';

const steps = [
  {number: 1, label: 'Choose a project'},
  {number: 2, label: 'Understand it'},
  {number: 3, label: 'Test the change'},
  {number: 4, label: 'Read the verdict'},
] as const;

const runStages = [
  {id: 'preparing', label: 'Prepare pinned source', detail: 'Copy the real report modules into a temporary overlay.'},
  {id: 'checking_correctness', label: 'Check correctness', detail: 'Compare every report result on timed and edge-case ledgers.'},
  {id: 'measuring', label: 'Measure report time', detail: 'Paired repetitions after warm-up on this computer.'},
  {id: 'verdict', label: 'Derive the verdict', detail: 'Correctness gates first; speed only decides afterwards.'},
] as const;

function message(reason: unknown): string {
  return reason instanceof Error ? reason.message : 'The request failed.';
}

function stageProgress(evaluation: Evaluation): number {
  if (evaluation.status === 'queued') return 0;
  return evaluation.progress?.percent ?? 0;
}

export function ProjectEvaluation() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState('');
  const [recent, setRecent] = useState<Evaluation[]>([]);
  const [recentError, setRecentError] = useState('');
  const [url, setUrl] = useState('');
  const [ref, setRef] = useState('main');
  const [consent, setConsent] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [inspectionError, setInspectionError] = useState('');
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [mode, setMode] = useState<'quick' | 'full'>('quick');
  const [includeTests, setIncludeTests] = useState(false);
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [now, setNow] = useState(Date.now());
  const lastSequence = useRef(0);

  const recordedShowcase = showcase && !isLive();
  const inspectionId = inspection?.inspection_id ?? evaluation?.inspection_id ?? null;
  const project = inspection?.project ?? evaluation?.inspection.project ?? null;
  const facts = inspection?.facts ?? evaluation?.inspection.facts ?? [];
  const notSupported = inspection?.not_supported ?? evaluation?.inspection.not_supported ?? [];
  const guesses = inspection?.guesses ?? evaluation?.inspection.guesses ?? [];
  const adapter = inspection?.supported_evaluations[0] ?? null;
  const canRun = Boolean(inspectionId && (inspection?.execution_allowed ?? true) && adapter);
  const canOpen = (number: number) =>
    number === 1 || (number >= 2 && Boolean(project)) || (number >= 3 && Boolean(evaluation))
    || (number === 4 && Boolean(evaluation?.verdict));

  async function loadCatalog() {
    try {
      const value = await api.catalog();
      setCatalog(value);
      setCatalogError('');
    } catch (reason) {
      setCatalogError(message(reason));
    }
  }

  async function loadRecent() {
    try {
      const value = await api.evaluations();
      setRecent(value);
      setRecentError('');
    } catch {
      setRecent([]);
      setRecentError(recordedShowcase
        ? 'No recorded project evaluation is bundled with this snapshot.'
        : 'Recent project evaluations could not be loaded.');
    }
  }

  useEffect(() => { void loadCatalog(); void loadRecent(); }, []);

  useEffect(() => {
    if (!evaluation || !isRunning(evaluation)) return;
    lastSequence.current = 0;
    setEvents([]);
    let stopped = false;
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    const id = evaluation.evaluation_id;

    const poll = async () => {
      try {
        const [next, fresh] = await Promise.all([api.evaluation(id), api.events(id, lastSequence.current)]);
        if (stopped) return;
        setEvents(current => {
          const seen = new Set(current.map(item => item.sequence));
          return [...current, ...fresh.filter(item => !seen.has(item.sequence))]
            .sort((a, b) => a.sequence - b.sequence);
        });
        lastSequence.current = Math.max(lastSequence.current, ...fresh.map(item => item.sequence), 0);
        setEvaluation(next);
        setRunError('');
        if (next.status === 'completed' && next.verdict) {
          setStep(4);
          void loadRecent();
          return;
        }
        if (isTerminal(next)) {
          void loadRecent();
          return;
        }
      } catch (reason) {
        if (!stopped) setRunError(message(reason));
      }
      if (!stopped) window.setTimeout(poll, 700);
    };
    const timer = window.setTimeout(poll, 350);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearInterval(tick);
    };
  }, [evaluation?.evaluation_id, evaluation?.status]);

  useEffect(() => {
    if (step === 2 || step === 3 || step === 4) {
      document.getElementById('project-stage-title')?.focus({preventScroll: true});
    }
  }, [step]);

  async function inspectProject() {
    if (!url.trim() || !consent) return;
    setInspecting(true);
    setInspectionError('');
    try {
      const value = await api.inspect(url.trim(), ref.trim() || 'main', consent);
      setInspection(value);
      setEvaluation(null);
      setEvents([]);
      setRunError('');
      setStep(2);
    } catch (reason) {
      setInspectionError(message(reason));
    } finally {
      setInspecting(false);
    }
  }

  function chooseMode(next: 'quick' | 'full') {
    setMode(next);
    setIncludeTests(next === 'full');
  }

  async function startRun() {
    if (!inspectionId || !canRun) return;
    setStarting(true);
    setRunError('');
    try {
      const value = await api.start(inspectionId, mode, includeTests);
      lastSequence.current = 0;
      setEvaluation(value);
      setEvents([]);
      setStep(3);
      void loadRecent();
    } catch (reason) {
      setRunError(message(reason));
    } finally {
      setStarting(false);
    }
  }

  async function cancelRun() {
    if (!evaluation) return;
    setCancelling(true);
    try {
      setEvaluation(await api.cancel(evaluation.evaluation_id));
    } catch (reason) {
      setRunError(message(reason));
    } finally {
      setCancelling(false);
    }
  }

  async function openEvaluation(item: Evaluation) {
    setEvaluation(item);
    setEvents([]);
    setRunError('');
    lastSequence.current = 0;
    try {
      const record = await api.inspection(item.inspection_id);
      setInspection(record);
    } catch {
      setInspection(null);
    }
    try {
      const history = await api.events(item.evaluation_id);
      setEvents(history);
      lastSequence.current = Math.max(0, ...history.map(event => event.sequence));
    } catch { /* A saved verdict can still be shown without its event log. */ }
    setStep(item.status === 'completed' && item.verdict ? 4 : 3);
  }

  function reset() {
    setInspection(null);
    setEvaluation(null);
    setEvents([]);
    setRunError('');
    setInspectionError('');
    setStep(1);
    void loadCatalog();
    void loadRecent();
  }

  function rerun() {
    setRunError('');
    if (!inspection && evaluation) {
      void api.inspection(evaluation.inspection_id).then(setInspection).catch(() => {});
    }
    setStep(2);
  }

  const example = catalog?.examples[0];
  const selectedExample = Boolean(example && url.trim().replace(/\.git$/, '').replace(/\/$/, '')
    === example.repository_url.replace(/\/$/, ''));
  const preset = catalog?.presets[mode];
  const elapsed = evaluation
    ? evaluation.duration_s ?? (evaluation.started_at && isRunning(evaluation)
      ? Math.max(0, (now - new Date(evaluation.started_at).valueOf()) / 1000) : 0)
    : 0;

  return <div className="project-workspace">
    <nav className="project-stepper" aria-label="Project evaluation steps">
      {steps.map(item => <button key={item.number} type="button" aria-current={step === item.number ? 'step' : undefined}
        disabled={!canOpen(item.number)} onClick={() => setStep(item.number as 1 | 2 | 3 | 4)}>
        <span className="project-step-number">0{item.number}</span>
        <span>{item.label}</span>
      </button>)}
      <span className={`status-chip ${recordedShowcase ? 'warn' : 'good'} project-bench-chip`}>
        {recordedShowcase ? 'Recorded snapshot' : 'Live · this computer'}
      </span>
    </nav>

    {step === 1 && <section className="project-panel project-choose" aria-labelledby="project-stage-title">
      <div className="project-intro">
        <div>
          <span className="section-kicker">Real Project Mode · step 1</span>
          <h2 id="project-stage-title" tabIndex={-1}>Choose a real project.</h2>
          <p className="project-lede">
            DARWIN pins one exact commit, reads the source and measures a narrowly scoped change.
            It never substitutes the checkout lab for a project it cannot actually run.
          </p>
        </div>
        <span className={`status-chip ${recordedShowcase ? 'warn' : 'active'}`}>
          {recordedShowcase ? 'Recorded evidence' : 'Live inspection'}
        </span>
      </div>

      <div className="project-stage-note">
        <p><strong>What is happening.</strong> DARWIN resolves a public GitHub URL to a commit SHA before it downloads anything.</p>
        <p><strong>Why it matters.</strong> A result can only be trusted if the exact source revision is recorded.</p>
      </div>

      {catalogError && <p className="notice" role="alert">{catalogError}</p>}

      <div className="project-choice-grid">
        <div className="project-choice-list" aria-label="Trusted examples">
          {catalog?.examples.map(item => <article key={item.id}
            className={`project-choice-card${selectedExample ? ' selected' : ''}`}>
            <div className="project-choice-top">
              <span className="project-choice-mark"><Icon name="project"/></span>
              <span className="status-chip good">Trusted adapter</span>
            </div>
            <h3>{item.name}</h3>
            <p>{item.subtitle}</p>
            <p className="muted">{item.summary}</p>
            <div className="project-tags">
              <span className="status-chip">React + WebView</span>
              <span className="status-chip">localStorage</span>
              <span className="status-chip warn">Local app · not server</span>
            </div>
            <dl>
              <div><dt>Evaluation</dt><dd>Local report processing</dd></div>
              <div><dt>Pinned commit</dt><dd><code>{item.pinned_commit.slice(0, 12)}</code></dd></div>
              <div><dt>Adapter</dt><dd>{item.adapter.adapter_id} · v{item.adapter.adapter_version}</dd></div>
            </dl>
            <button type="button" className="action-link project-use-example"
              onClick={() => { setUrl(item.repository_url); setRef(item.default_ref || 'main'); }}>
              Use this example <Icon name="arrow"/>
            </button>
          </article>)}
          {!catalog && !catalogError && <div className="project-loading">Loading trusted examples…</div>}
        </div>

        <form className="project-url-card" onSubmit={event => { event.preventDefault(); void inspectProject(); }}>
          <span className="section-kicker">Or inspect another public repository</span>
          <label htmlFor="project-url">Public GitHub URL</label>
          <input id="project-url" value={url} onChange={event => setUrl(event.target.value)}
            placeholder="https://github.com/owner/repo" autoComplete="off" spellCheck={false}/>
          <label htmlFor="project-ref">Branch, tag or commit</label>
          <input id="project-ref" value={ref} onChange={event => setRef(event.target.value)}
            placeholder="main" autoComplete="off" spellCheck={false}/>
          <label className="project-consent">
            <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)}/>
            <span>I allow DARWIN to download this public source read-only. Private repositories and credentials are not supported.</span>
          </label>
          <Action variant="primary" icon="search" type="submit" pending={inspecting}
            disabled={!url.trim() || !consent}>
            {inspecting ? 'Pinning the commit…' : 'Inspect this project'}
          </Action>
          <p className="project-footnote">
            Only repositories in DARWIN's audited adapter catalog can execute. Everything else is inspection-only.
          </p>
          {inspectionError && <p className="notice" role="alert">{inspectionError}</p>}
        </form>
      </div>

      {recent.length > 0 && <section className="project-recent" aria-labelledby="project-recent-title">
        <div className="section-title">
          <div className="panel-heading">
            <span className="section-kicker">Recorded evidence</span>
            <h3 id="project-recent-title">Saved project evaluations</h3>
          </div>
          <button type="button" className="action action-quiet compact-action" onClick={() => void loadRecent()}>
            <Icon name="refresh"/>Refresh
          </button>
        </div>
        <ul>
          {recent.slice(0, 4).map(item => <li key={item.evaluation_id}>
            <button type="button" onClick={() => void openEvaluation(item)}>
              <span className={`status-chip ${tone(item.verdict?.status ?? item.status)}`}>
                {item.verdict?.label ?? item.status}
              </span>
              <strong>{item.source.owner}/{item.source.repo}</strong>
              <small>{item.mode} · {formatDate(item.finished_at ?? item.created_at)}</small>
              <span>{item.verdict?.change_pct !== undefined
                ? `${item.verdict.change_pct > 0 ? '−' : '+'}${Math.abs(item.verdict.change_pct).toFixed(1)}%`
                : 'No measured change'}</span>
            </button>
          </li>)}
        </ul>
        {recentError && <p className="project-footnote">{recentError}</p>}
      </section>}
    </section>}

    {step === 2 && project && <div className="project-stage">
      <RepositoryArchitecture project={project} facts={facts} notSupported={notSupported} guesses={guesses}/>

      <section className="project-panel project-run-setup" aria-labelledby="project-stage-title">
        <div className="section-title">
          <div className="panel-heading">
            <span className="section-kicker">Step 2 · Choose the scoped change</span>
            <h2 id="project-stage-title" tabIndex={-1}>Test one measured change.</h2>
          </div>
          <span className={`status-chip ${canRun ? 'good' : 'warn'}`}>{canRun ? 'Adapter approved' : 'Inspection only'}</span>
        </div>

        <div className="project-stage-note">
          <p><strong>What is happening.</strong> DARWIN compares the original report functions with one candidate on identical fictional ledgers.</p>
          <p><strong>Why it matters.</strong> A report that is fast but changes a budget total is not an improvement.</p>
        </div>

        {!canRun && <div className="project-inspection-only">
          <span className="project-inspection-icon"><Icon name="shield"/></span>
          <div>
            <h3>No runnable optimization adapter for this source.</h3>
            <p>{inspection?.warnings?.[0] ?? 'This repository can be inspected, but DARWIN has no audited adapter for it and will not run the unrelated checkout demo as a substitute.'}</p>
            <Action variant="secondary" icon="arrow" onClick={reset}>Choose another project</Action>
          </div>
        </div>}

        {canRun && adapter && <>
          <div className="project-candidate">
            <div className="project-candidate-side original">
              <span className="section-kicker">Original</span>
              <strong>Three independent report traversals</strong>
              <p>Totals, category spending and payee totals each walk the same currency-scoped ledger.</p>
            </div>
            <span className="project-candidate-arrow" aria-hidden="true">→</span>
            <div className="project-candidate-side candidate">
              <span className="section-kicker">Candidate</span>
              <strong>Shared one-pass aggregation</strong>
              <p>{adapter.change_summary}</p>
            </div>
          </div>

          <details className="project-scope">
            <summary>What exactly changes <span className="status-chip">{adapter.adapter_id}</span></summary>
            <p>{adapter.mechanism}</p>
            <p className="muted">{adapter.scope_note}</p>
            <h3>Correctness rules</h3>
            <ul>{adapter.correctness_rules.map(rule => <li key={rule}>{rule}</li>)}</ul>
            <p className="project-footnote">
              The candidate is placed in an isolated overlay. It is re-exported through the real reporting module and called
              from the real Reports tab call site. The original repository is never edited.
            </p>
          </details>

          <fieldset className="project-mode-fieldset">
            <legend>Comparison budget</legend>
            <div className="project-mode-grid">
              {(['quick', 'full'] as const).map(id => <label key={id} className={`project-mode${mode === id ? ' selected' : ''}`}>
                <input type="radio" name="project-mode" value={id} checked={mode === id} onChange={() => chooseMode(id)}/>
                <span>
                  <strong>{id === 'quick' ? 'Quick live comparison' : 'Full comparison'}</strong>
                  <small>{id === 'quick'
                    ? 'One seed, two ledgers, ten paired repetitions.'
                    : 'Three seeds, three ledgers, ten paired repetitions plus the reporting test overlay.'}</small>
                  <code>{catalog?.presets[id] ? `${catalog.presets[id].sizes.map(size => formatRows(size)).join(' / ')} rows` : ''}</code>
                </span>
              </label>)}
            </div>
            <label className="project-consent project-test-toggle">
              <input type="checkbox" checked={includeTests} disabled={mode === 'quick'}
                onChange={event => setIncludeTests(event.target.checked)}/>
              <span>{mode === 'quick'
                ? 'Quick mode skips Sanchay’s existing source tests.'
                : 'Run Sanchay’s existing reporting tests against the candidate overlay.'}</span>
            </label>
          </fieldset>

          <dl className="project-workload">
            <div><dt>Seeds</dt><dd>{preset?.seeds.join(', ') ?? '—'}</dd></div>
            <div><dt>Ledgers</dt><dd>{preset ? preset.sizes.map(size => formatRows(size)).join(' / ') + ' rows' : '—'}</dd></div>
            <div><dt>Paired reps</dt><dd>{preset?.repetitions ?? '—'}</dd></div>
            <div><dt>Warm-ups</dt><dd>{preset?.warmups ?? '—'}</dd></div>
            <div><dt>Data</dt><dd>Fictional deterministic ledgers</dd></div>
          </dl>

          <div className="project-actions">
            <Action variant="primary" icon="play" pending={starting} onClick={() => void startRun()}>
              {starting ? 'Starting the local worker…' : `Run ${mode} comparison`}
            </Action>
            <Action variant="quiet" onClick={reset}>Choose another project</Action>
          </div>
          {!inspection?.readiness.node_available && <p className="notice" role="alert">
            Node.js was not found. The live comparison needs Node 22.18 or newer to execute the real TypeScript source.
          </p>}
          {runError && <p className="notice" role="alert">{runError}</p>}
        </>}
      </section>
    </div>}

    {step === 3 && evaluation && <section className="project-panel project-run" aria-labelledby="project-stage-title">
      <div className="section-title">
        <div className="panel-heading">
          <span className="section-kicker">Step 3 · Test the change</span>
          <h2 id="project-stage-title" tabIndex={-1}>{isRunning(evaluation) ? 'Running on this computer.' : 'This run has ended.'}</h2>
        </div>
        <span className={`status-chip ${tone(evaluation.verdict?.status ?? evaluation.status)}`}>
          {isRunning(evaluation) ? 'Live run' : (evaluation.verdict?.label ?? evaluation.status)}
        </span>
      </div>

      <div className="project-stage-note">
        <p><strong>What is happening.</strong> DARWIN is running the original and candidate report paths over the same ledgers.</p>
        <p><strong>Why it matters.</strong> Numbers are not known until the correctness checks and paired timings finish.</p>
      </div>

      {isRunning(evaluation) && <>
        <div className="project-progress-head">
          <span>{stageLabel(evaluation.stage)}</span>
          <span>{stageProgress(evaluation)}%</span>
        </div>
        <progress value={stageProgress(evaluation)} max={100} aria-label={`Evaluation progress: ${stageProgress(evaluation)}%`}/>
        <p className="project-run-label">{evaluation.progress?.label}</p>
        <div className="project-run-meta">
          <span>Elapsed <strong>{formatDuration(elapsed)}</strong></span>
          <span>Run <code>{evaluation.evaluation_id.slice(0, 8)}</code></span>
          <span>Commit <code>{evaluation.source.short_sha}</code></span>
          <span>Mode <strong>{evaluation.mode}</strong></span>
        </div>

        <ol className="project-run-stages">
          {runStages.map(stage => {
            const state = stageState(evaluation.stage === 'queued' ? 'queued' : evaluation.stage, stage.id);
            return <li key={stage.id} className={state}>
              <span className="project-run-stage-mark">
                {state === 'done' ? <Icon name="check"/> : state === 'current' ? <span className="project-pulse"/> : '·'}
              </span>
              <span><strong>{stage.label}</strong><small>{stage.detail}</small></span>
            </li>;
          })}
        </ol>

        {events.length > 0 && <details className="project-events" open>
          <summary>Live stage events</summary>
          <ol>
            {events.slice(-8).map(event => <li key={event.sequence}>
              <time>{new Date(event.occurred_at).toLocaleTimeString()}</time>
              <span>{event.message}</span>
            </li>)}
          </ol>
        </details>}

        <div className="project-actions">
          <Action variant="danger" icon="stop" pending={cancelling} onClick={() => void cancelRun()}>
            {cancelling ? 'Stopping…' : 'Cancel evaluation'}
          </Action>
          <Action variant="quiet" onClick={reset}>Choose another project</Action>
        </div>
        <p className="project-footnote">
          Cancelling stops the local worker. A cancelled run never produces a winner or a performance claim.
        </p>
      </>}

      {!isRunning(evaluation) && evaluation.status !== 'completed' && <div className="project-run-ended">
        <span className={`status-chip ${tone(evaluation.verdict?.status ?? evaluation.status)}`}>{evaluation.status}</span>
        <h3>No verified result was produced.</h3>
        <p>{evaluation.error ?? evaluation.verdict?.reason ?? 'The evaluation stopped before a verdict.'}</p>
        <p className="project-footnote">Nothing from this run is presented as an improvement.</p>
        <div className="project-actions">
          <Action variant="primary" icon="refresh" onClick={rerun}>Try again</Action>
          <Action variant="quiet" onClick={reset}>Choose another project</Action>
        </div>
      </div>}

      {!isRunning(evaluation) && evaluation.status === 'completed' && <div className="project-run-ended">
        <span className="status-chip good">Evaluation complete</span>
        <h3>Evidence recorded. Opening the verdict…</h3>
        <Action variant="primary" icon="arrow" onClick={() => setStep(4)}>Read the verdict</Action>
      </div>}

      {runError && <p className="notice" role="alert">{runError}</p>}
    </section>}

    {step === 4 && evaluation && (evaluation.verdict
      ? <ProjectVerdict evaluation={evaluation} onRerun={rerun} onChooseAnother={reset}
          downloadsAvailable={!recordedShowcase}/>
      : <section className="project-panel">
        <h2 id="project-stage-title" tabIndex={-1}>No verdict</h2>
        <p className="project-lede">This evaluation has no recorded verdict.</p>
        <Action variant="secondary" onClick={() => setStep(3)}>Back to the run</Action>
      </section>)}
  </div>;
}
