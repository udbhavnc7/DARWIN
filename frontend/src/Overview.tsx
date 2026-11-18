import {Icon} from './Action';
import {Readiness, type Preflight} from './Preflight';
import {Status} from './Status';

const stages = [
  {page: 'project', icon: 'project', title: 'Connect', detail: 'Pin a repository and check support.'},
  {page: 'configuration', icon: 'configuration', title: 'Compare designs', detail: 'Inspect the supported alternatives.'},
  {page: 'experiments', icon: 'experiments', title: 'Test', detail: 'Measure traffic, failures and correctness.'},
  {page: 'search', icon: 'search', title: 'Evaluate', detail: 'Compare the feasible trade-offs.'},
  {page: 'solution', icon: 'solution', title: 'Decide', detail: 'Review the change and its evidence.'},
] as const;

export function Overview({preflight, loading, onRefresh, recorded, connected, runtime, canMeasure}: {
  preflight: Preflight | null; loading: boolean; onRefresh: () => void;
  recorded: boolean; connected: boolean; runtime: string; canMeasure: boolean;
}) {
  return <div className="overview-page">
    <section className="overview overview-compact" aria-labelledby="overview-title">
      <div className="hero-copy">
        <span className="section-kicker hero-kicker"><span/>Backend architecture decisions</span>
        <h2 id="overview-title">Better backends.<br/><em>Built on evidence.</em></h2>
        <p>Compare supported ways to run your backend. Test performance and correctness,
          then choose a change, review a trade-off or keep what works.</p>
        <div className="shop-actions">
          <a className="primary action-link" href="#project">Open a project <Icon name="arrow"/></a>
          <a className="hero-secondary" href="#solution">View decisions <Icon name="arrow"/></a>
        </div>
        <span className="overview-audience">For startups, growing teams and software agencies.</span>
      </div>
      <figure className="overview-proof" aria-labelledby="overview-proof-title">
        <div className="overview-proof-header"><Status value="showcase" label="Recorded measurement"/><span>Flask + Redis</span></div>
        <h3 id="overview-proof-title">A second replica was faster.<br/>It also used more resources.</h3>
        <dl className="overview-proof-metrics">
          <div><dt>p95 latency</dt><dd className="overview-metric-good">−29.9%</dd></div>
          <div><dt>CPU</dt><dd>+39.0%</dd></div>
          <div><dt>Peak memory</dt><dd>+82.7%</dd></div>
        </dl>
        <div className="overview-proof-verdict"><Icon name="shield"/><span><strong>Trade-off requires a choice</strong><small>3/3 correctness checks passed.</small></span></div>
        <figcaption>One recorded full comparison on a local Docker bench. Results apply to that workload and host.</figcaption>
      </figure>
    </section>

    <section className="overview-workflow" aria-labelledby="overview-workflow-title">
      <div className="workflow-heading"><h2 id="overview-workflow-title">From repository to decision</h2><span className="muted">One pinned project</span></div>
      <nav className="overview-steps" aria-label="Project workflow">
        {stages.map((stage, index) => <a href={`#${stage.page}`} key={stage.page}>
          <span className="overview-step-number">0{index + 1}</span><Icon name={stage.icon}/>
          <strong>{stage.title}</strong><small>{stage.detail}</small>
        </a>)}
      </nav>
      <p className="overview-rule"><Icon name="shield"/><span>A candidate that fails a required correctness check cannot be recommended.</span></p>
    </section>

    <div className="overview-details">
      <details className="panel overview-disclosure">
        <summary>Supported scope and limits</summary>
        <div className="overview-scope-grid">
          <div><h3>Available today</h3><p>Public repository inspection, reviewed Flask + Redis and Node + Redis backend comparisons,
            a Sanchay report-processing adapter, and a separate checkout lab.</p>
            <p>External backend measurements require a local Linux Docker engine. Unknown repositories can be inspected;
              execution requires a supported adapter.</p></div>
          <div><h3>What the result means</h3><p>Measurements apply to the tested workload. Simulated screening is labelled separately.
            Correctness coverage depends on the adapter; counter checks do not establish payment safety.</p>
            <p>DARWIN provides reviewable guidance. Broader adapter support and a hosted multi-user service remain future work.</p></div>
        </div>
        <a href="#shop" className="action-link">Explore the checkout example <Icon name="arrow"/></a>
      </details>
      <details className="panel overview-disclosure">
        <summary>{recorded ? 'Recorded bench details' : 'Local bench readiness'}
          <Status value={recorded ? 'showcase' : loading ? 'running' : connected ? 'connected' : 'offline'}
            label={recorded ? 'Recorded' : loading ? 'Checking' : connected ? 'Connected' : 'Offline'}/></summary>
        <p className="muted overview-runtime">{recorded ? 'Capture environment' : 'Checkout lab runtime'}: {connected ? runtime : 'unavailable'}
          {connected && ` · ${canMeasure ? 'Smoke, benchmark and fault tests' : 'Smoke checks'}`}</p>
        <Readiness preflight={preflight} loading={loading} onRefresh={onRefresh}/>
      </details>
    </div>
  </div>;
}
