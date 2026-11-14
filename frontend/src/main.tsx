import {useCallback, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {Shop} from './Shop';
import {Architecture} from './Architecture';
import {Experiments} from './Experiments';
import {Search} from './Search';
import {Status} from './Status';
import {BrandMark} from './Brand';
import {Tour} from './Demo';
import {ArchitectureArt} from './ArchitectureArt';
import {ThemePicker} from './ThemePicker';
import {Readiness, type Preflight} from './Preflight';
import {Action, Icon} from './Action';
import {applyTheme, onThemeStorage, readTheme, saveTheme, themes, type ThemeId} from './themes';
import {baseline, readDraft, saveDraft, type Genome} from './genome';

type Project = {execution_modes: string[]; baseline: Genome};
type Runtime = 'native' | 'docker';
const pages = {
  overview: {label: 'Overview', title: 'Overview'},
  configuration: {label: 'Architecture', title: 'Architecture builder'},
  experiments: {label: 'Experiments', title: 'Experiments'},
  search: {label: 'Search', title: 'Architecture search'},
  shop: {label: 'Demo shop', title: 'Demo shop'},
};
type Page = keyof typeof pages;
const pageOrder: Page[] = ['overview', 'configuration', 'experiments', 'search', 'shop'];
const workflow = [
  {page: 'configuration', title: 'Design your system', detail: 'Shape the services, caching, and retry behavior.', action: 'Open builder'},
  {page: 'experiments', title: 'Put it to the test', detail: 'Measure performance. Inject faults. Verify recovery.', action: 'Run an experiment'},
  {page: 'search', title: 'Find a better fit', detail: 'Compare candidates with measured evidence.', action: 'Explore search'},
] as const;

function currentPage(): Page {
  const hash = location.hash.slice(1);
  if (Object.hasOwn(pages, hash)) return hash as Page;
  const params = new URLSearchParams(location.search);
  return params.has('experiment') ? 'experiments' : params.has('search') ? 'search' : 'overview';
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
  const [themeId, setThemeId] = useState(readTheme);
  const theme = themes[themeId];
  const [builderDraft, setBuilderDraft] = useState(() => readDraft('builder') ?? baseline);
  const [draft, setDraft] = useState<{genome: Genome} | null>(() => {
    const genome = readDraft('experiment');
    return genome ? {genome} : null;
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
    <div className="app-frame">
      <a className="skip-link" href="#workspace" onClick={event => {event.preventDefault(); title.current?.focus();}}>Skip to workspace</a>
      <aside className="app-sidebar">
        <a className="brand" href="#overview"><BrandMark/><span>DARWIN<small>Architecture lab</small></span></a>
        <nav className="section-nav" aria-label="Workspace">
          {pageOrder.map(id => <a key={id} href={`#${id}`} aria-current={page === id ? 'page' : undefined}>
            <Icon name={id}/><span>{pages[id].label}</span><span className="nav-current" aria-hidden="true">›</span>
          </a>)}
        </nav>
        <button type="button" className="sidebar-guide" aria-haspopup="dialog" onClick={() => setTourOpen(true)}>
          <span className="sidebar-guide-icon"><Icon name="play"/></span>
          <strong>What is DARWIN?</strong>
          <span>See the lab end to end in a one-minute product tour.</span>
          <span className="sidebar-guide-link">Take the tour <Icon name="arrow"/></span>
        </button>
        <div className="sidebar-status">
          <Status value={connecting ? 'running' : project ? 'connected' : 'offline'}
            label={connecting ? 'Checking API' : project ? 'API connected' : 'API offline'}/>
          <Action variant="quiet" className="mobile-tour" icon="play" aria-haspopup="dialog"
            onClick={() => setTourOpen(true)}>Tour</Action>
        </div>
      </aside>
      <main id="workspace">
        <header className="workspace-header">
          <div><p className="workspace-breadcrumb">Workspace <span aria-hidden="true">/</span> <span> {pages[page].label}</span></p><h1 ref={title} tabIndex={-1}>{pages[page].title}</h1></div>
          <ThemePicker theme={themeId} onChange={changeTheme}/>
        </header>
        {page !== 'shop' && page !== 'overview' && <div className="context-bar" role="group" aria-label="Run settings">
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
        {!connecting && !project && <p className="notice" role="alert">The API is offline. Start the backend and refresh runtimes to reconnect.</p>}
        <div hidden={page !== 'overview'}>
          <section className="overview" aria-labelledby="overview-title">
            <div className="hero-copy">
              <span className="section-kicker hero-kicker"><span/>The backend architecture lab</span>
              <h2 id="overview-title">Better backends.{' '}<br/><em>Built on evidence.</em></h2>
              <p>Design your system, see where it breaks, and discover architectures that recover.</p>
              <div className="shop-actions">
                <a className="primary action-link" href="#configuration">Open architecture builder <Icon name="arrow"/></a>
                <button type="button" className="hero-secondary" aria-haspopup="dialog" onClick={() => setTourOpen(true)}><Icon name="play"/>How DARWIN works</button>
              </div>
            </div>
            <div className="hero-visual"><ArchitectureArt theme={theme}/><div className="visual-caption"><span className="visual-caption-line"/>Design <span>→</span> Measure <span>→</span> Evolve</div></div>
          </section>
          <div className="workflow-heading"><div><span className="section-kicker">From idea to evidence</span><h2>Your next move</h2></div><span className="muted">One workspace. Three steps.</span></div>
          <nav className="workflow" aria-label="Architecture workflow">
            {workflow.map((step, index) => <a className="panel workflow-link" href={`#${step.page}`} key={step.page}>
              <span className="workflow-top"><span className="workflow-icon"><Icon name={step.page}/></span><span className="workflow-number">0{index + 1}</span></span>
              <span className="workflow-copy"><strong>{step.title}</strong><small>{step.detail}</small></span>
              <span className="workflow-cta">{step.action}<Icon className="workflow-arrow" name="arrow"/></span>
            </a>)}
          </nav>
          <div className="overview-cards">
            <article className="panel baseline-card">
              <div className="section-title"><div className="panel-heading"><span className="section-kicker">The starting point</span><h2>A working checkout system</h2></div><span className="baseline-badge">Baseline</span></div>
              <ol className="baseline-flow" aria-label="Request path">
                <li><Icon name="configuration"/><strong>Gateway</strong><small>Route requests</small></li><li><Icon name="server"/><strong>Checkout API</strong><small>{project?.baseline.app_replicas ?? baseline.app_replicas} API replica</small></li><li><Icon name="database"/><strong>PostgreSQL</strong><small>Persist orders</small></li>
              </ol>
              <p className="muted">The API also calls inventory and mock payment services.</p>
              <a href="#configuration">Open architecture builder <span aria-hidden="true">→</span></a>
            </article>
            <article className="panel runtime-card">
              <div className="section-title"><div className="panel-heading"><span className="section-kicker">Ready for your next run</span><h2>Execution environment</h2></div><Status value={connecting ? 'running' : project ? 'connected' : 'offline'}/></div>
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
    <Tour open={tourOpen} onClose={() => setTourOpen(false)}/>
  </>;
}

applyTheme(readTheme());
createRoot(document.getElementById('root')!).render(<App/>);
