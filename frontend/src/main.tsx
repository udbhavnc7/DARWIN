import {lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import './story.css';
import {Shop} from './Shop';
import {Architecture} from './Architecture';
import {Experiments} from './Experiments';
import {Search} from './Search';
import {Status} from './Status';
import {BrandMark} from './Brand';
import {Tour} from './Demo';
import {ThemePicker} from './ThemePicker';
import {Readiness, type Preflight} from './Preflight';
import {ProjectEvaluation} from './ProjectEvaluation';
import {Story} from './Story';
import {Action, Icon} from './Action';
import {applyTheme, onThemeStorage, readTheme, saveTheme, themes, type ThemeId} from './themes';
import {baseline, readDraft, saveDraft, type Genome} from './genome';
import {installShowcase, isLive, manifest, probeLive, setLive, setupUrl, showcase} from './showcase';

// The calibration intro owns the three.js scene. Keep the renderer out of the
// initial bundle so the workspace paints before it is fetched.
const Splash = lazy(() => import('./Splash').then(module => ({default: module.Splash})));

type Project = {execution_modes: string[]; baseline: Genome};
type Runtime = 'native' | 'docker';
const pages = {
  overview: {label: 'The lab', title: 'Architecture, decided by evidence'},
  project: {label: 'Guided evaluation', title: 'Connect a real backend'},
  configuration: {label: 'Alternatives', title: 'Generate alternatives'},
  experiments: {label: 'Test & break', title: 'Run and break experiments'},
  search: {label: 'Evolve', title: 'Search for a better configuration'},
  shop: {label: 'Demo shop', title: 'Demo shop'},
};
type Page = keyof typeof pages;
const pageOrder: Page[] = ['overview', 'project', 'configuration', 'experiments', 'search', 'shop'];
const navGroups: {label: string; pages: Page[]}[] = [
  {label: 'Start here', pages: ['overview', 'project']},
  {label: 'Experiment lab', pages: ['configuration', 'experiments', 'search', 'shop']},
];

function currentPage(): Page {
  const hash = location.hash.slice(1);
  if (Object.hasOwn(pages, hash)) return hash as Page;
  const params = new URLSearchParams(location.search);
  return params.has('experiment') ? 'experiments' : params.has('search') ? 'search' : 'overview';
}

// The calibration intro runs once per browser session, so reconnecting the
// live bench (which reloads) does not replay it. ?splash=1 forces it back on.
function shouldShowSplash() {
  const params = new URLSearchParams(location.search);
  if (params.get('splash') === '1') return true;
  if (params.get('nosplash') === '1') return false;
  try {return sessionStorage.getItem('darwin-splash') !== 'seen';} catch {return true;}
}

function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(true);
  const [connecting, setConnecting] = useState(true);
  const [workload, setWorkload] = useState('normal');
  const [selectedRuntime, setSelectedRuntime] = useState<Runtime | null>(null);
  const [page, setPage] = useState<Page>(currentPage);
  const [tourOpen, setTourOpen] = useState(() => new URLSearchParams(location.search).has('tour'));
  const [intro, setIntro] = useState(shouldShowSplash);
  const [themeId, setThemeId] = useState(readTheme);
  const theme = themes[themeId];
  const [builderDraft, setBuilderDraft] = useState(() => readDraft('builder') ?? baseline);
  const [draft, setDraft] = useState<{genome: Genome} | null>(() => {
    const genome = readDraft('experiment');
    return genome ? {genome} : null;
  });
  const [capturedAt, setCapturedAt] = useState<string | null>(null);
  const live = isLive();
  const [liveProbe, setLiveProbe] = useState<'idle' | 'probing' | 'error'>('idle');
  const [liveError, setLiveError] = useState('');
  const [liveFellBack] = useState(() => {
    try {
      const fellBack = sessionStorage.getItem('darwin-live-fell-back') === '1';
      if (fellBack) sessionStorage.removeItem('darwin-live-fell-back');
      return fellBack;
    } catch { return false; }
  });
  const title = useRef<HTMLHeadingElement>(null);
  const modes = project?.execution_modes ?? [];
  const dockerAvailable = modes.includes('docker_smoke');
  const runtime = selectedRuntime === 'native' || !dockerAvailable ? 'native' : 'docker';
  const canMeasure = modes.includes(`${runtime}_benchmark`);

  useLayoutEffect(() => {applyTheme(themeId);}, [themeId]);
  useEffect(() => {
    const sync = (event: StorageEvent) => onThemeStorage(event, setThemeId);
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  function changeTheme(id: ThemeId) {
    setThemeId(id);
    saveTheme(id);
  }

  const dismissIntro = useCallback(() => {
    try {sessionStorage.setItem('darwin-splash', 'seen');} catch { /* Storage can be disabled. */ }
    setIntro(false);
    requestAnimationFrame(() => title.current?.focus({preventScroll: true}));
  }, []);

  const connect = useCallback(async () => {
    setConnecting(true);
    try {
      const response = await fetch('/api/project', {signal: AbortSignal.timeout(10000)});
      if (!response.ok) throw Error('API unavailable');
      setProject(await response.json());
    } catch {
      setProject(null);
    } finally {
      setConnecting(false);
    }
  }, []);

  const loadPreflight = useCallback(async (refresh = false) => {
    setPreflightLoading(true);
    try {
      const response = await fetch(`/api/preflight${refresh ? '?refresh=true' : ''}`, {signal: AbortSignal.timeout(15000)});
      if (!response.ok) throw Error();
      setPreflight(await response.json());
    } catch {
      setPreflight(null);
    } finally {
      setPreflightLoading(false);
    }
  }, []);

  useEffect(() => {void loadPreflight();}, [loadPreflight]);
  useEffect(() => {
    if (showcase && !live) manifest().then(value => setCapturedAt(value.captured_at)).catch(() => setCapturedAt(null));
  }, [live]);

  // Switches the published page from recorded evidence to the stack running on this
  // computer. A reload re-runs every request against 127.0.0.1 instead of the snapshot.
  async function connectBench() {
    setLiveProbe('probing'); setLiveError('');
    const problem = await probeLive();
    if (problem) {
      setLiveError('No local bench answered at 127.0.0.1:8000. This page keeps working on the recorded evidence, so nothing here is broken. To run live, start the bench with scripts/demo.py start and try again. If Chrome asks whether this site may access your local network, choose Allow.');
      setLiveProbe('error');
      return;
    }
    setLive(true);
    location.reload();
  }

  // A connected bench can stop later. Fall back to the recorded evidence instead of
  // leaving every page pointed at a dead port.
  useEffect(() => {
    if (!showcase || !isLive()) return;
    let cancelled = false;
    void probeLive(6000).then(problem => {
      if (cancelled || !problem) return;
      setLive(false);
      try { sessionStorage.setItem('darwin-live-fell-back', '1'); } catch { /* Storage can be disabled. */ }
      location.reload();
    });
    return () => { cancelled = true; };
  }, []);

  function disconnectBench() {
    setLive(false);
    location.reload();
  }

  useEffect(() => {
    void connect();
    const navigate = () => {
      setPage(currentPage());
      requestAnimationFrame(() => {
        window.scrollTo(0, 0);
        title.current?.focus({preventScroll: true});
      });
    };
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, [connect]);

  function useDraft(genome: Genome) {
    saveDraft('experiment', genome);
    setDraft({genome});
    location.hash = 'experiments';
  }

  function editCandidate(genome: Genome) {
    setBuilderDraft(genome);
    saveDraft('builder', genome);
    location.hash = 'configuration';
  }

  const runtimeLabel = runtime === 'docker' ? 'Docker' : 'Native';
  return <>
    <div className="app-frame" inert={intro}>
      <a className="skip-link" href="#workspace" onClick={event => {event.preventDefault(); title.current?.focus();}}>Skip to workspace</a>
      <aside className="app-sidebar">
        <a className="brand" href="#overview"><BrandMark/><span>DARWIN<small>Architecture lab</small></span></a>
        <nav className="section-nav" aria-label="Workspace">
          {navGroups.map(group => <div className="nav-cluster" key={group.label}>
            <span className="nav-group">{group.label}</span>
            {group.pages.map(id => <a key={id} href={`#${id}`} aria-current={page === id ? 'page' : undefined}>
              <span className="nav-index" aria-hidden="true">{String(pageOrder.indexOf(id) + 1).padStart(2, '0')}</span>
              <Icon name={id}/><span>{pages[id].label}</span><span className="nav-current" aria-hidden="true">›</span>
            </a>)}
          </div>)}
        </nav>
        <p className="sidebar-readout" aria-hidden="true"><span>{live ? 'LIVE BENCH' : showcase ? 'RECORDED BENCH' : 'LOCAL BENCH'}</span><span>v0.1.0</span></p>
        <button type="button" className="sidebar-guide" aria-haspopup="dialog" onClick={() => setTourOpen(true)}>
          <span className="sidebar-guide-icon"><Icon name="play"/></span>
          <strong>What is DARWIN?</strong>
          <span>See the lab end to end in a one-minute product tour.</span>
          <span className="sidebar-guide-link">Take the tour <Icon name="arrow"/></span>
        </button>
        <div className="sidebar-status">
          {showcase ? <Status value={live ? 'connected' : 'showcase'} label={live ? 'Live · this computer' : 'Showcase · recorded'}/>
            : <Status value={connecting ? 'running' : project ? 'connected' : 'offline'}
              label={connecting ? 'Checking API' : project ? 'API connected' : 'API offline'}/>}
          <Action variant="quiet" className="mobile-tour" icon="play" aria-haspopup="dialog"
            onClick={() => setTourOpen(true)}>Tour</Action>
        </div>
      </aside>
      <main id="workspace">
        <header className="workspace-header">
          <div><p className="workspace-breadcrumb"><span>Workspace</span> <span aria-hidden="true">/</span> <span> {pages[page].label}</span></p><h1 ref={title} tabIndex={-1}>{pages[page].title}</h1></div>
          <div className="header-tools"><span className="workspace-index" aria-hidden="true">{String(pageOrder.indexOf(page) + 1).padStart(2, '0')} <i>/</i> {String(pageOrder.length).padStart(2, '0')}</span><ThemePicker theme={themeId} onChange={changeTheme} onReplay={() => setIntro(true)}/></div>
        </header>
        {showcase && <aside className={`showcase-banner${live ? ' showcase-banner-live' : ''}`} aria-label={live ? 'Live bench connection' : 'About this showcase'}>
          <span className="showcase-banner-mark" aria-hidden="true"><Icon name={live ? 'play' : 'book'}/></span>
          {live ? <>
            <p><strong>Live bench: this page is driving the DARWIN stack on this computer.</strong>{' '}
              Experiments, searches and shop checkouts now run for real on this machine at 127.0.0.1 and nothing is exposed to the network. Keep <code>scripts/demo.py</code> running for the whole session; disconnect to go back to the recorded evidence.</p>
            <span className="showcase-banner-actions">
              <button type="button" className="action-link showcase-banner-link" onClick={disconnectBench}>Disconnect</button>
            </span>
          </> : <>
            <p><strong>Recorded evidence{capturedAt ? ` from ${new Date(capturedAt).toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'})}` : ''}, not a live run.</strong>{' '}
              This hosted copy is a complete walkthrough: no install, no Docker and no local server needed.
              Every result was produced on a local DARWIN bench and kept with its evidence label
              (measured or simulated). If you want to run experiments, searches or checkouts live on this
              computer, start the bench with <code>\.venv\Scripts\python.exe scripts/demo.py start</code> and connect it.</p>
            <span className="showcase-banner-actions">
              <button type="button" className="action-link showcase-banner-link" aria-busy={liveProbe === 'probing'}
                disabled={liveProbe === 'probing'} onClick={() => void connectBench()}>
                {liveProbe === 'probing' ? 'Looking for your bench…' : liveProbe === 'error' ? 'Try again' : 'Connect this computer'} <Icon name="arrow"/>
              </button>
              <a className="action-link showcase-banner-link" href={setupUrl} target="_blank" rel="noreferrer">How to run it <Icon name="arrow"/></a>
            </span>
          </>}
          {liveFellBack && <p className="showcase-banner-note" role="status">The connected bench could not be reached, so this page switched back to the recorded evidence. Everything shown here still works; reconnect whenever the bench is running.</p>}
          {liveError && <p className="showcase-banner-note" role="status">{liveError}</p>}
        </aside>}
        {page !== 'shop' && page !== 'overview' && page !== 'project' && <div className="context-bar" role="group" aria-label="Run settings">
          <div className="context-heading"><Icon name="settings"/><span>Run settings</span></div>
          <div className="header-controls">
            <div><label htmlFor="runtime">Runtime</label>
              <select id="runtime" value={runtime} disabled={!project || connecting}
                onChange={event => setSelectedRuntime(event.target.value as Runtime)}>
                <option value="native">Native</option>
                <option value="docker" disabled={!dockerAvailable}>Docker{dockerAvailable ? '' : ' (unavailable)'}</option>
              </select>
            </div>
            <div><label htmlFor="workload">Workload</label>
              <select id="workload" value={workload} onChange={event => setWorkload(event.target.value)}>
                <option value="normal">Normal traffic</option><option value="flash_sale">Flash sale</option><option value="checkout_heavy">Checkout heavy</option>
              </select>
            </div>
          </div>
          <Action variant="quiet" icon="refresh" pending={connecting} onClick={connect}>{connecting ? 'Checking runtimes…' : 'Refresh runtimes'}</Action>
        </div>}
        {!connecting && !project && <p className="notice" role="alert">{live ? 'This computer’s bench is not answering. Start it with scripts/demo.py start, then refresh runtimes.' : showcase ? 'The recorded snapshot could not be loaded. Reload the page to try again.' : 'The API is offline. Start the backend and refresh runtimes to reconnect.'}</p>}
        <div hidden={page !== 'project'}><ProjectEvaluation/></div>
        <div hidden={page !== 'overview'}>
          <Story baselineReplicas={project?.baseline.app_replicas ?? baseline.app_replicas}/>
          <div className="overview-cards">
            <article className="panel baseline-card">
              <div className="section-title"><div className="panel-heading"><span className="section-kicker">The system under test</span><h2>A working checkout backend</h2></div><span className="baseline-badge">Baseline</span></div>
              <ol className="baseline-flow" aria-label="Request path">
                <li><Icon name="configuration"/><strong>Gateway</strong><small>Route requests</small></li><li><Icon name="server"/><strong>Checkout API</strong><small>{project?.baseline.app_replicas ?? baseline.app_replicas} API {(project?.baseline.app_replicas ?? baseline.app_replicas) === 1 ? 'replica' : 'replicas'}</small></li><li><Icon name="database"/><strong>PostgreSQL</strong><small>Persist orders</small></li>
              </ol>
              <p className="muted">The API also calls inventory and mock payment services. The four supported controls are the only things that vary between candidates.</p>
              <a href="#configuration">Generate an alternative <span aria-hidden="true">→</span></a>
            </article>
            <article className="panel runtime-card">
              <div className="section-title"><div className="panel-heading"><span className="section-kicker">{showcase && !live ? 'Where this evidence was measured' : 'Ready for your next run'}</span><h2>Execution environment</h2></div>{showcase && !live ? <Status value="showcase" label="Recorded"/> : <Status value={connecting ? 'running' : project ? 'connected' : 'offline'}/>}</div>
              <dl><div><dt>Runtime</dt><dd>{project ? runtimeLabel : '—'}</dd></div>
                <div><dt>Capabilities</dt><dd>{connecting ? 'Checking' : canMeasure ? 'Smoke, benchmarks, fault tests' : project ? 'Smoke checks' : 'Unavailable'}</dd></div></dl>
              <a href="#search">Explore measured search <span aria-hidden="true">→</span></a>
            </article>
          </div>
          <Readiness preflight={preflight} loading={preflightLoading} onRefresh={() => void loadPreflight(true)}/>
        </div>
        <div hidden={page !== 'configuration'}><Architecture genome={builderDraft} onEdit={setBuilderDraft} workload={workload} connected={!!project} active={page === 'configuration'} onUse={useDraft}/></div>
        <div hidden={page !== 'experiments'}><Experiments workload={workload} canMeasure={canMeasure} runtime={runtime}
          canStart={modes.includes(`${runtime}_smoke`)} draft={draft}/></div>
        <div hidden={page !== 'search'}><Search workload={workload} runtime={runtime} canMeasure={canMeasure} onEditCandidate={editCandidate} onWorkloadChange={setWorkload}/></div>
        <div hidden={page !== 'shop'}><Shop/></div>
      </main>
    </div>
    <Tour open={tourOpen && !intro} onClose={() => setTourOpen(false)}/>
    {intro && <Suspense fallback={<div className="splash" aria-hidden="true"/>}>
      <Splash theme={theme} onDone={dismissIntro}/>
    </Suspense>}
  </>;
}

if (showcase) installShowcase();
applyTheme(readTheme());
createRoot(document.getElementById('root')!).render(<App/>);
