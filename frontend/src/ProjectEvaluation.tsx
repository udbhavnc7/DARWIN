import {useEffect, useState} from 'react';
import {Action, Icon} from './Action';
import {ProjectVerdict} from './ProjectVerdict';
import {RepositoryArchitecture} from './RepositoryArchitecture';
import {isLive, showcase} from './showcase';
import {useProjectWorkspace} from './ProjectContext';
import {
  api, controlLabel, formatDate, formatDuration, formatRows, isRunning, isTerminal, stageLabel,
  stageState, tone, type Catalog, type Evaluation,
} from './projectApi';

const steps = [
  {number: 1, label: 'Connect'},
  {number: 2, label: 'Understand'},
  {number: 3, label: 'Challenge'},
  {number: 4, label: 'Evolve'},
  {number: 5, label: 'Prove'},
] as const;

const challenges = [
  {id: 'faster', label: 'Faster under traffic', detail: 'Find a deployable change that lowers latency for the reviewed workload.'},
  {id: 'recover', label: 'Recover more reliably', detail: 'Restart a web replica and measure the outage the gateway exposes.'},
  {id: 'resources', label: 'Use fewer resources', detail: 'Compare CPU seconds and peak memory for the same workload.'},
  {id: 'spike', label: 'Handle a traffic spike', detail: 'Compare behaviour when the seeded load is pushed beyond steady state.'},
] as const;

const measuredStages = [
  {id: 'preparing', label: 'Prepare pinned source', detail: 'Copy only the reviewed source files into a DARWIN-owned overlay.'},
  {id: 'checking_correctness', label: 'Deploy and check correctness', detail: 'Start the isolated stack and verify the behaviour oracle.'},
  {id: 'measuring', label: 'Measure the challenge', detail: 'Run the seeded workload and the fault probe on this computer.'},
  {id: 'verdict', label: 'Derive the verdict', detail: 'Correctness gates first; regressions are never hidden.'},
] as const;

const screeningStages = [
  {id: 'preparing', label: 'Load the architecture', detail: 'Read the file-backed service, route and integration model.'},
  {id: 'simulating', label: 'Simulate variants', detail: 'Compare deployment controls with the deterministic model.'},
  {id: 'evaluating', label: 'Apply the policy', detail: 'Gate the recommendation on modelled error rate and cost.'},
  {id: 'verdict', label: 'Record the recommendation', detail: 'Store a SIMULATED, NOT_MEASURED candidate.'},
] as const;

function message(reason: unknown): string {
  return reason instanceof Error ? reason.message : 'The request failed.';
}

function stageProgress(evaluation: Evaluation): number {
  if (evaluation.status === 'queued') return 0;
  return evaluation.progress?.percent ?? 0;
}

function resultLabel(item: Evaluation): string {
  if (item.evaluation_type === 'architecture_screening' || item.evidence_kind === 'simulated') {
    const change = item.recommendation?.modelled_change_pct;
    return Number.isFinite(change)
      ? `SIMULATED · ${Math.abs(change as number).toFixed(1)}% modelled`
      : 'SIMULATED · no measured runtime';
  }
  if (item.verdict?.change_pct !== undefined) {
    return `${item.verdict.change_pct > 0 ? '−' : '+'}${Math.abs(item.verdict.change_pct).toFixed(1)}% measured`;
  }
  return 'No measured change';
}

export function ProjectEvaluation() {
  const workspace = useProjectWorkspace();
  const {inspection, evaluation, preview, events, setEvaluation, setError: setWorkspaceError, clear: clearWorkspace} = workspace;
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState('');
  const [recent, setRecent] = useState<Evaluation[]>([]);
  const [recentError, setRecentError] = useState('');
  const [url, setUrl] = useState('');
  const [ref, setRef] = useState('main');
  const [consent, setConsent] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [inspectionError, setInspectionError] = useState('');
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [challenge, setChallenge] = useState('faster');
  const [mode, setMode] = useState<'quick' | 'full'>('quick');
  const [includeTests, setIncludeTests] = useState(false);
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [now, setNow] = useState(Date.now());

  const recordedShowcase = showcase && !isLive();
  const inspectionId = inspection?.inspection_id ?? evaluation?.inspection_id ?? null;
  const project = inspection?.project ?? evaluation?.inspection.project ?? null;
  const facts = inspection?.facts ?? evaluation?.inspection.facts ?? [];
  const notSupported = inspection?.not_supported ?? evaluation?.inspection.not_supported ?? [];
  const guesses = inspection?.guesses ?? evaluation?.inspection.guesses ?? [];
  const architecture = inspection?.architecture ?? evaluation?.inspection.architecture ?? null;
  const hotspots = inspection?.hotspots ?? evaluation?.inspection.hotspots ?? [];
  const screening = inspection?.screening ?? evaluation?.inspection.screening ?? null;
  const adapter = inspection?.supported_evaluations[0] ?? null;
  const isBackendArch = Boolean(adapter && adapter.evaluation_type === 'backend_architecture');
  const containerMissing = isBackendArch && inspection?.readiness.container_runner_available === false;
  const measuredReady = Boolean((inspection?.execution_allowed ?? true) && adapter);
  const screeningReady = Boolean(screening?.available) && !measuredReady;
  const canRun = Boolean(inspectionId && (screeningReady || measuredReady));
  const isScreening = evaluation?.evaluation_type === 'architecture_screening';
  const activeStages = isScreening ? screeningStages : measuredStages;
  const challengeOptions = isBackendArch
    ? challenges.filter(item => (adapter?.challenges ?? preview?.challenges ?? ['faster']).includes(item.id))
    : [];
  const canOpen = (number: number) =>
    number === 1 || (number === 2 && Boolean(project))
    || (number === 3 && Boolean(project))
    || (number === 4 && Boolean(evaluation))
    || (number === 5 && Boolean(evaluation?.verdict));

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
    if (inspection && step === 1 && !evaluation) setStep(2);
  }, [inspection?.inspection_id]);

  useEffect(() => {
    if (!evaluation) return;
    if (evaluation.status === 'completed' && evaluation.verdict) {
      setStep(5);
      void loadRecent();
      return;
    }
    if (isTerminal(evaluation)) {
      setStep(4);
      void loadRecent();
      return;
    }
    if (isRunning(evaluation)) setStep(4);
  }, [evaluation?.evaluation_id, evaluation?.status]);

  useEffect(() => {
    if (!evaluation || !isRunning(evaluation)) return;
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, [evaluation?.evaluation_id, evaluation?.status]);

  useEffect(() => {
    if (workspace.error) setRunError(workspace.error);
  }, [workspace.error]);

  useEffect(() => {
    if (preview?.challenges?.length && !preview.challenges.includes(challenge)) {
      setChallenge(preview.challenges[0]);
    }
  }, [preview?.challenges, challenge]);

  useEffect(() => {
    if (step > 1) {
      document.getElementById('project-stage-title')?.focus({preventScroll: true});
    }
  }, [step]);

  async function inspectProject() {
    if (!url.trim() || !consent) return;
    setInspecting(true);
    setInspectionError('');
    setWorkspaceError('');
    try {
      const value = await api.inspect(url.trim(), ref.trim() || 'main', consent);
      workspace.selectInspection(value);
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
    setIncludeTests(next === 'full' && !screeningReady);
  }

  async function startRun() {
    if (!inspectionId || !canRun) return;
    setStarting(true);
    setRunError('');
    setWorkspaceError('');
    try {
      const value = await api.start(inspectionId, mode, includeTests,
        screeningReady ? 'architecture-screening-v1' : undefined,
        isBackendArch ? challenge : 'faster');
      setEvaluation(value);
      setStep(4);
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
    setRunError('');
    setWorkspaceError('');
    await workspace.selectEvaluation(item);
    setStep(item.status === 'completed' && item.verdict ? 5 : 4);
  }

  function reset() {
    clearWorkspace();
    setRunError('');
    setInspectionError('');
    setStep(1);
    void loadCatalog();
    void loadRecent();
  }

  function rerun() {
    setRunError('');
    setWorkspaceError('');
    setStep(inspection ? 3 : 2);
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
          <span className="section-kicker">Stage 02 · Project Workspace · Connect</span>
          <h2 id="project-stage-title" tabIndex={-1}>Connect a public backend.</h2>
          <p className="project-lede">
            DARWIN pins one exact commit, reads the source and builds a file-backed picture of the project
            and its backend. A catalogued measured adapter can run a real scoped comparison; every other
            repository can receive a simulated architecture screening. Arbitrary repository code is never executed.
            This workspace carries one pinned project from Connect through Understand, Challenge, Evolve and Prove, then hands the outcome to the Solution stage.
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
              <span className="status-chip good">Optional measured example</span>
            </div>
            <h3>{item.name}</h3>
            <p>{item.subtitle}</p>
            <p className="muted">{item.summary}</p>
            <div className="project-tags">
              {item.evaluation_type === 'backend_architecture' ? <>
                <span className="status-chip">Flask + Redis</span>
                <span className="status-chip">Dockerised service</span>
                <span className="status-chip good">Measured backend</span>
              </> : <>
                <span className="status-chip">React + WebView</span>
                <span className="status-chip">localStorage</span>
                <span className="status-chip warn">Local app · not server</span>
              </>}
            </div>
            <dl>
              <div><dt>Evaluation</dt>
                <dd>{item.evaluation_type === 'backend_architecture'
                  ? 'Backend architecture' : 'Local report processing'}</dd></div>
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
          <span className="section-kicker">Inspect any public GitHub repository</span>
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
            Only repositories in DARWIN's audited adapter catalog can execute. Other repositories are
            read-only: DARWIN can model architecture variants, but it does not run their code or dependencies.
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
              <span>{resultLabel(item)}</span>
            </button>
          </li>)}
        </ul>
        {recentError && <p className="project-footnote">{recentError}</p>}
      </section>}
    </section>}

    {step === 2 && project && <div className="project-stage">
      <RepositoryArchitecture project={project} facts={facts} notSupported={notSupported}
        guesses={guesses} architecture={architecture} hotspots={hotspots} screening={screening}
        measuredChange={isBackendArch
          ? 'Measured deployment changes only: service replicas and gunicorn workers behind an nginx gateway. Application code stays identical, so a measured difference is attributable to topology.'
          : adapter?.evaluation_type === 'client_data_processing'
            ? 'A measured, audited code-path change: the pinned source runs the original implementation and the candidate side by side on the same inputs.'
            : undefined}/>

      <section className="project-panel project-understand" aria-labelledby="project-stage-title">
        <div className="section-title">
          <div className="panel-heading">
            <span className="section-kicker">Stage 02 · Project Workspace · Understand</span>
            <h2 id="project-stage-title" tabIndex={-1}>
              {measuredReady ? 'Pinned source, reviewed change, and an isolation boundary.'
                : screeningReady ? 'Read-only model, clearly labelled as simulated.'
                  : 'This repository can be read, but not executed.'}
            </h2>
          </div>
          <span className={`status-chip ${measuredReady ? 'good' : 'warn'}`}>
            {inspection?.support_level === 'READY_FOR_MEASURED_EVOLUTION' ? 'Ready for measured evolution'
              : inspection?.support_level === 'EVALUABLE_WITH_SETUP' ? 'Needs local setup'
                : 'Inspection only'}
          </span>
        </div>

        <div className="project-stage-note">
          <p><strong>Commit.</strong> <code>{inspection?.source.commit_sha.slice(0, 12)}</code> is the exact
            revision that was read. Nothing is fetched from a moving branch during a run.</p>
          <p><strong>Boundary.</strong> {adapter?.execution_note
            ?? 'No reviewed adapter matches this source. DARWIN will not run unrelated code as a substitute.'}</p>
        </div>

        {(inspection?.prerequisites?.length ?? 0) > 0 && <div className="project-sim-banner" role="note">
          <Icon name="shield"/>
          <span><strong>SETUP REQUIRED.</strong> {inspection?.prerequisites?.join(' ')}</span>
        </div>}

        {adapter && adapter.evaluation_type === 'backend_architecture' && <>
          <div className="project-candidate">
            <div className="project-candidate-side original">
              <span className="section-kicker">Original architecture</span>
              <strong>Single Flask replica behind a gateway</strong>
              <p>A hit counter lives in a shared Redis. The repository Compose file and Dockerfile are never
                executed; DARWIN deploys its own reviewed stack from <code>app.py</code> and
                <code>requirements.txt</code>.</p>
            </div>
            <span className="project-candidate-arrow" aria-hidden="true">→</span>
            <div className="project-candidate-side candidate">
              <span className="section-kicker">Reviewed change space</span>
              <strong>{preview?.candidates?.length ?? '—'} deployable configurations</strong>
              <p>Replica count and gunicorn workers vary. Application code stays identical, so any measured
                difference is attributable to deployment topology.</p>
            </div>
          </div>
          <details className="project-scope">
            <summary>Isolation guarantees <span className="status-chip good">LIVE · isolated</span></summary>
            <ul>{[
              'Loopback-only published port; no host Docker socket and no privileged containers.',
              'Internal sandbox network; the gateway is the only service with host access.',
              'Read-only root filesystems, dropped capabilities, CPU and memory caps.',
              'Only allowlisted source files are copied; path escapes and symlinks are rejected.',
              'The repository Compose file is not used. Generated Compose is validated before start.',
            ].map(item => <li key={item}>{item}</li>)}</ul>
            <p className="project-footnote">
              Absolute numbers are lab-only: the load generator and the service share one host.
            </p>
          </details>
        </>}

        <div className="project-actions">
          <Action variant="primary" icon="arrow" onClick={() => setStep(3)}>
            {canRun ? 'Choose a challenge' : 'Continue'}
          </Action>
          <Action variant="quiet" onClick={reset}>Choose another project</Action>
        </div>
      </section>
    </div>}

    {step === 3 && project && <div className="project-stage">
      <section className="project-panel project-run-setup" aria-labelledby="project-stage-title">
        <div className="section-title">
          <div className="panel-heading">
            <span className="section-kicker">
              {screeningReady || isBackendArch ? 'Stages 03–04 · Challenge the architecture'
                : 'Stages 03–04 · Challenge the implementation'}
            </span>
            <h2 id="project-stage-title" tabIndex={-1}>
              {screeningReady ? 'What should the backend get better at?'
                : measuredReady ? 'What should the architecture get better at?' : 'This project is read-only.'}
            </h2>
          </div>
          <span className={`status-chip ${screeningReady ? 'warn' : measuredReady ? 'good' : 'warn'}`}>
            {screeningReady ? 'SIMULATED · NOT MEASURED'
              : measuredReady ? (isBackendArch ? 'LIVE · isolated stack' : 'Measured adapter approved')
                : 'Inspection only'}
          </span>
        </div>

        {screeningReady ? <div className="project-stage-note">
          <p><strong>What is happening.</strong> DARWIN builds a deterministic queueing model from the inspected
            services, routes, data stores and integrations, then compares deployment-level variants.</p>
          <p><strong>Why it matters.</strong> The recommendation is an uncalibrated candidate for real deployment
            validation, not a measured winner. No repository code is executed.</p>
        </div> : <div className="project-stage-note">
          <p><strong>What is happening.</strong> DARWIN compares the pinned source with one scoped candidate on
            identical workloads.</p>
          <p><strong>Why it matters.</strong> A result that is fast but changes behaviour is not an improvement.</p>
        </div>}

        {!canRun && <div className="project-inspection-only">
          <span className="project-inspection-icon"><Icon name="shield"/></span>
          <div>
            <h3>No runnable adapter or screening path for this source.</h3>
            <p>{screening?.reason ?? inspection?.warnings?.[0]
              ?? 'This repository can be inspected, but DARWIN has no audited adapter or backend model for it and will not run the unrelated checkout demo as a substitute.'}</p>
            <Action variant="secondary" icon="arrow" onClick={reset}>Choose another project</Action>
          </div>
        </div>}

        {screeningReady && screening && <>
          <div className="project-candidate">
            <div className="project-candidate-side original">
              <span className="section-kicker">Detected baseline</span>
              <strong>{project.display_type}</strong>
              <p>{project.backend?.detected
                ? `${project.backend.services.length} service(s), ${project.backend.route_count} route(s), `
                  + `${project.backend.datastores.length} data store(s) and `
                  + `${project.backend.external_services.length} external integration(s).`
                : project.summary}</p>
            </div>
            <span className="project-candidate-arrow" aria-hidden="true">→</span>
            <div className="project-candidate-side candidate">
              <span className="section-kicker">Screening candidate</span>
              <strong>Deployment-level evolution</strong>
              <p>Vary only controls supported by the inspected source: {screening.controls.map(controlLabel).join(', ')}.
                Application code, schemas and business logic stay unchanged.</p>
            </div>
          </div>

          <details className="project-scope">
            <summary>What the model varies <span className="status-chip">{screening.adapter_id ?? 'architecture-screening-v1'}</span></summary>
            <p>{screening.mechanism}</p>
            <p className="muted">{screening.scope_note}</p>
            <h3>Controls supported by this source</h3>
            <ul>{screening.controls.map(control => <li key={control}>{controlLabel(control)}</li>)}</ul>
            <p className="project-footnote">{screening.execution_note}</p>
          </details>

          <div className="project-sim-banner" role="note">
            <Icon name="shield"/>
            <span><strong>SIMULATED</strong> This run does not execute repository code, install dependencies,
              start containers or measure a runtime. Every number is a model output.</span>
          </div>

          <fieldset className="project-mode-fieldset">
            <legend>Screening budget</legend>
            <div className="project-mode-grid">
              {(['quick', 'full'] as const).map(id => <label key={id} className={`project-mode${mode === id ? ' selected' : ''}`}>
                <input type="radio" name="project-mode" value={id} checked={mode === id} onChange={() => chooseMode(id)}/>
                <span>
                  <strong>{id === 'quick' ? 'Quick screening' : 'Full screening'}</strong>
                  <small>{id === 'quick'
                    ? 'One deterministic seed and a bounded variant set.'
                    : 'Three seeds, combined variants and seed-sensitivity reporting.'}</small>
                  <code>{id === 'quick'
                    ? `${catalog?.presets.quick.seeds.length ?? 1} seed · ${screening.controls.length} controls`
                    : `${catalog?.presets.full.seeds.length ?? 3} seeds · ${screening.controls.length} controls`}</code>
                </span>
              </label>)}
            </div>
          </fieldset>

          <dl className="project-workload">
            <div><dt>Seeds</dt><dd>{preset?.seeds.join(', ') ?? '—'}</dd></div>
            <div><dt>Controls</dt><dd>{screening.controls.length}</dd></div>
            <div><dt>Workload</dt><dd>Synthetic request mix</dd></div>
            <div><dt>Execution</dt><dd>None</dd></div>
            <div><dt>Evidence</dt><dd>Modelled</dd></div>
          </dl>

          <div className="project-actions">
            <Action variant="primary" icon="play" pending={starting} onClick={() => void startRun()}>
              {starting ? 'Starting the model…' : `Run ${mode} screening`}
            </Action>
            <Action variant="quiet" onClick={reset}>Choose another project</Action>
          </div>
          {runError && <p className="notice" role="alert">{runError}</p>}
        </>}

        {isBackendArch && canRun && <>
          <fieldset className="project-challenge-fieldset">
            <legend>Choose one challenge</legend>
            <div className="project-challenge-grid">
              {challengeOptions.map(item => <label key={item.id}
                className={`project-challenge${challenge === item.id ? ' selected' : ''}`}>
                <input type="radio" name="project-challenge" value={item.id}
                  checked={challenge === item.id} onChange={() => setChallenge(item.id)}/>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.detail}</small>
                </span>
              </label>)}
            </div>
          </fieldset>

          {preview && <div className="project-candidate-preview">
            <span className="section-kicker">Candidates DARWIN will deploy</span>
            <ul>{preview.candidates.map(item => <li key={item.candidate_id}>
              <span className="status-chip">{item.dimension.replicas}×{item.dimension.workers}</span>
              <span><strong>{item.label}</strong><small>{item.description}</small></span>
            </li>)}</ul>
            {(preview.unsupported?.length ?? 0) > 0 && <p className="project-footnote">
              Not evaluated: {preview.unsupported?.join(' ')}
            </p>}
          </div>}
        </>}

        {!screeningReady && measuredReady && adapter && <>
          <div className="project-candidate">
            <div className="project-candidate-side original">
              <span className="section-kicker">Original</span>
              <strong>{isBackendArch ? 'One replica × one gunicorn worker'
                : adapter.adapter_id === 'sanchay-reporting-v1'
                  ? 'Three independent report traversals' : 'Detected implementation'}</strong>
              <p>{isBackendArch
                ? 'The reviewed Flask app and Redis counter, deployed exactly as the pinned source describes.'
                : adapter.adapter_id === 'sanchay-reporting-v1'
                  ? 'Totals, category spending and payee totals each walk the same currency-scoped ledger.'
                  : 'The pinned source at its recorded commit.'}</p>
            </div>
            <span className="project-candidate-arrow" aria-hidden="true">→</span>
            <div className="project-candidate-side candidate">
              <span className="section-kicker">Candidate</span>
              <strong>{isBackendArch ? 'Reviewed replica and worker changes'
                : adapter.adapter_id === 'sanchay-reporting-v1'
                  ? 'Shared one-pass aggregation' : 'Scoped adapter change'}</strong>
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
              The candidate is placed in an isolated overlay. The original repository is never edited,
              committed or pushed.
            </p>
          </details>

          <fieldset className="project-mode-fieldset">
            <legend>{isBackendArch ? 'Run budget' : 'Comparison budget'}</legend>
            <div className="project-mode-grid">
              {(['quick', 'full'] as const).map(id => <label key={id} className={`project-mode${mode === id ? ' selected' : ''}`}>
                <input type="radio" name="project-mode" value={id} checked={mode === id} onChange={() => chooseMode(id)}/>
                <span>
                  <strong>{id === 'quick' ? 'Quick live comparison' : 'Full comparison'}</strong>
                  <small>{isBackendArch
                    ? (id === 'quick'
                      ? 'Deploy the baseline and the candidates for this challenge once each.'
                      : 'Up to three repetitions per configuration, all reviewed candidates, with spread retained.')
                    : (id === 'quick'
                      ? 'One seed, two ledgers, ten paired repetitions.'
                      : 'Three seeds, three ledgers, ten paired repetitions plus the optional source tests.')}</small>
                  <code>{isBackendArch
                    ? (id === 'quick' ? 'bounded · one repetition' : 'bounded · up to 3 repetitions')
                    : (catalog?.presets[id] ? `${catalog.presets[id].sizes.map(size => formatRows(size)).join(' / ')} rows` : '')}</code>
                </span>
              </label>)}
            </div>
            {!isBackendArch && <label className="project-consent project-test-toggle">
              <input type="checkbox" checked={includeTests} disabled={mode === 'quick'}
                onChange={event => setIncludeTests(event.target.checked)}/>
              <span>{mode === 'quick'
                ? 'Quick mode skips the adapter’s optional source tests.'
                : 'Run the adapter’s optional source tests against the candidate overlay.'}</span>
            </label>}
            {isBackendArch && <p className="project-footnote">
              The adapter verifies HTTP health and shared-counter monotonicity. It does not install the
              repository test runner, so no source-test result is claimed.
            </p>}
          </fieldset>

          <dl className="project-workload">
            {isBackendArch ? <>
              <div><dt>Challenge</dt><dd>{challenges.find(item => item.id === challenge)?.label ?? challenge}</dd></div>
              <div><dt>Load window</dt><dd>6 s steady state</dd></div>
              <div><dt>Correctness</dt><dd>Counter oracle</dd></div>
              <div><dt>Fault</dt><dd>{challenge === 'recover' ? 'Restart web replica' : 'Not injected'}</dd></div>
              <div><dt>Evidence</dt><dd>LIVE · cgroup v2</dd></div>
            </> : <>
              <div><dt>Seeds</dt><dd>{preset?.seeds.join(', ') ?? '—'}</dd></div>
              <div><dt>Ledgers</dt><dd>{preset ? preset.sizes.map(size => formatRows(size)).join(' / ') + ' rows' : '—'}</dd></div>
              <div><dt>Paired reps</dt><dd>{preset?.repetitions ?? '—'}</dd></div>
              <div><dt>Warm-ups</dt><dd>{preset?.warmups ?? '—'}</dd></div>
              <div><dt>Data</dt><dd>Fictional deterministic ledgers</dd></div>
            </>}
          </dl>

          <div className="project-actions">
            <Action variant="primary" icon="play" pending={starting} disabled={containerMissing} onClick={() => void startRun()}>
              {starting ? 'Starting…' : isBackendArch ? `Run ${mode} live comparison` : `Run ${mode} comparison`}
            </Action>
            <Action variant="quiet" onClick={reset}>Choose another project</Action>
          </div>
          {containerMissing && <p className="notice" role="alert">
            This live comparison needs a working Linux Docker engine. You can still inspect the project and read its
            recorded evidence; the native checkout lab does not require Docker.
          </p>}
          {!isBackendArch && !inspection?.readiness.node_available && <p className="notice" role="alert">
            Node.js was not found. The live comparison needs Node 22.18 or newer to execute the real source.
          </p>}
          {runError && <p className="notice" role="alert">{runError}</p>}
        </>}
      </section>
    </div>}

    {step === 4 && evaluation && <section className="project-panel project-run" aria-labelledby="project-stage-title">
      <div className="section-title">
        <div className="panel-heading">
          <span className="section-kicker">Stage 05 · Evolution · {isScreening ? 'Simulate the backend' : 'Test the change'}</span>
          <h2 id="project-stage-title" tabIndex={-1}>{isRunning(evaluation)
            ? (isScreening ? 'Modelling on this computer.' : 'Running on this computer.')
            : 'This run has ended.'}</h2>
        </div>
        <span className={`status-chip ${tone(evaluation.verdict?.status ?? evaluation.status)}`}>
          {isRunning(evaluation) ? (isScreening ? 'SIMULATED · modelling' : 'Live run')
            : (evaluation.verdict?.label ?? evaluation.status)}
        </span>
      </div>

      <div className="project-stage-note">
        {isScreening ? <>
          <p><strong>What is happening.</strong> DARWIN is evaluating deployment-level variants against the
            architecture it read from source.</p>
          <p><strong>Why it matters.</strong> No repository code is executed. The result is a model output,
            not a runtime measurement.</p>
        </> : <>
          <p><strong>What is happening.</strong> DARWIN is running the original and candidate paths over the same workload.</p>
          <p><strong>Why it matters.</strong> Numbers are not known until the correctness checks and paired timings finish.</p>
        </>}
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
          {activeStages.map(stage => {
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
          {isScreening
            ? 'Cancelling stops the local model. A cancelled screening never produces a recommendation.'
            : 'Cancelling stops the local worker. A cancelled run never produces a winner or a performance claim.'}
        </p>
      </>}

      {!isRunning(evaluation) && evaluation.status !== 'completed' && <div className="project-run-ended">
        <span className={`status-chip ${tone(evaluation.verdict?.status ?? evaluation.status)}`}>{evaluation.status}</span>
        <h3>{isScreening ? 'No recommendation was produced.' : 'No verified result was produced.'}</h3>
        <p>{evaluation.error ?? evaluation.verdict?.reason ?? 'The evaluation stopped before a result.'}</p>
        <p className="project-footnote">Nothing from this run is presented as an improvement or a measured winner.</p>
        <div className="project-actions">
          <Action variant="primary" icon="refresh" onClick={rerun}>Try again</Action>
          <Action variant="quiet" onClick={reset}>Choose another project</Action>
        </div>
      </div>}

      {!isRunning(evaluation) && evaluation.status === 'completed' && <div className="project-run-ended">
        <span className="status-chip good">{isScreening ? 'Screening complete' : 'Evaluation complete'}</span>
        <h3>{isScreening ? 'Evidence recorded. Opening the recommendation…' : 'Evidence recorded. Opening the verdict…'}</h3>
        <Action variant="primary" icon="arrow" onClick={() => setStep(5)}>
          {isScreening ? 'Read the recommendation' : 'Read the verdict'}
        </Action>
      </div>}

      {runError && <p className="notice" role="alert">{runError}</p>}
    </section>}

    {step === 5 && evaluation && (evaluation.verdict
      ? <ProjectVerdict evaluation={evaluation} onRerun={rerun} onChooseAnother={reset}
          downloadsAvailable={!recordedShowcase} recordedView={recordedShowcase}/>
      : <section className="project-panel">
        <h2 id="project-stage-title" tabIndex={-1}>No verdict</h2>
        <p className="project-lede">This evaluation has no recorded verdict.</p>
        <Action variant="secondary" onClick={() => setStep(4)}>Back to the run</Action>
      </section>)}
  </div>;
}
