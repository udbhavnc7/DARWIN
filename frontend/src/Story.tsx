import {Icon} from './Action';

const workflow = [
  {
    step: '01',
    page: 'overview',
    icon: 'overview',
    title: 'Overview',
    detail: 'Name the decision: when traffic outgrows one server, which configuration should carry the next 10,000 customers?',
    action: 'Read the overview',
  },
  {
    step: '02',
    page: 'project',
    icon: 'project',
    title: 'Project Workspace',
    detail: 'Pin one exact commit. Map the API, database, cache and workers. Keep proven facts separate from guesses.',
    action: 'Open the workspace',
  },
  {
    step: '03',
    page: 'configuration',
    icon: 'configuration',
    title: 'Architecture',
    detail: 'Turn supported controls into deployable candidates: one to three replicas, cache TTL, notifications and retries.',
    action: 'Shape the architecture',
  },
  {
    step: '04',
    page: 'experiments',
    icon: 'experiments',
    title: 'Experiments',
    detail: 'Push seeded traffic through each candidate, inject failures and run the correctness gates before timing counts.',
    action: 'Run experiments',
  },
  {
    step: '05',
    page: 'search',
    icon: 'search',
    title: 'Evolution',
    detail: 'NSGA-II explores performance, resource use and recovery. Correctness failures never enter the ranking.',
    action: 'Evolve the search',
  },
  {
    step: '06',
    page: 'solution',
    icon: 'solution',
    title: 'Solution',
    detail: 'Deliver a verdict with measured trade-offs, a reviewable change, rollback notes and an evidence bundle.',
    action: 'Read the solution',
  },
] as const;

const tools = [
  {
    name: 'AWS',
    provides: 'Runs and rents the infrastructure: servers, storage, networking and databases.',
    decides: 'Which architecture should use it.',
  },
  {
    name: 'Kubernetes',
    provides: 'Deploys, manages and scales application instances.',
    decides: 'Whether a configuration is worth running.',
  },
  {
    name: 'Redis',
    provides: 'Keeps frequently read data in memory.',
    decides: 'Whether caching helps enough in this workload.',
  },
  {
    name: 'Locust',
    provides: 'Generates test traffic and reports response times and errors.',
    decides: 'Which measured trade-off is acceptable.',
  },
  {
    name: 'Prometheus · Grafana',
    provides: 'Shows what is happening inside a running system.',
    decides: 'Which alternative earns the next deployment.',
  },
  {
    name: 'Chaos tools',
    provides: 'Introduce failures on purpose.',
    decides: 'Whether the business rules survived them.',
  },
] as const;

const today = [
  'A controlled e-commerce checkout lab with four supported controls and five business invariants.',
  'Two genuine public backends (Flask + Redis, Node/Express + Redis) with reviewed adapters and measured comparisons when a Linux Docker engine is available.',
  'Any public repository can be inspected at a pinned commit; only catalogued adapters are allowed to execute.',
  'Simulated screening is labelled SIMULATED / NOT_MEASURED and can never be promoted to a winner.',
  'Every result keeps seeds, artifacts, hashes and a replay command.',
] as const;

const next = [
  'Connect arbitrary GitHub repositories and infer more backend architectures automatically.',
  'Support more frameworks, databases and service topologies.',
  'Execute experiments in isolated cloud environments.',
  'Compare infrastructure costs across candidates.',
  'Recommend and, where validated, deploy the improvement.',
] as const;

function DecisionBoard() {
  return <figure className="story-board" aria-labelledby="story-board-title">
    <div className="story-board-head">
      <span id="story-board-title">Illustrative decision</span>
      <span>Hypothetical numbers</span>
    </div>
    <div className="story-choice">
      <span className="story-choice-id">A</span>
      <span className="story-choice-name"><strong>Basic</strong><small>1 API · PostgreSQL · no cache</small></span>
      <span className="story-choice-stat">900 ms</span>
      <span className="story-choice-flag">Cheap, slow</span>
    </div>
    <div className="story-choice story-choice-best">
      <span className="story-choice-id">B</span>
      <span className="story-choice-name"><strong>Cached</strong><small>2 APIs · Redis · PostgreSQL</small></span>
      <span className="story-choice-stat">250 ms</span>
      <span className="story-choice-flag">Choose</span>
    </div>
    <div className="story-choice story-choice-fail">
      <span className="story-choice-id">C</span>
      <span className="story-choice-name"><strong>Distributed</strong><small>Services · queues · Redis · workers</small></span>
      <span className="story-choice-stat">180 ms</span>
      <span className="story-choice-flag">Rejected</span>
    </div>
    <div className="story-board-verdict">
      <Icon name="shield"/>
      <span>C fails the duplicate-payment rule. The fastest configuration does not win.</span>
    </div>
    <figcaption>
      Monthly costs in the example: ₹10,000 · ₹20,000 · ₹35,000. This is a teaching example, not a measured run.
    </figcaption>
  </figure>;
}

export function Story({baselineReplicas}: {baselineReplicas: number}) {
  return <>
    <section className="overview story-hero" aria-labelledby="overview-title">
      <div className="hero-copy">
        <span className="section-kicker hero-kicker"><span/>Architecture experimentation laboratory</span>
        <h2 id="overview-title">Growth forces a decision.{' '}<br/><em>Evidence settles it.</em></h2>
        <p>When 100 customers become 10,000, the next architecture becomes a judgment call. DARWIN builds
          deployable alternatives, runs them under simulated traffic and injected failures, rejects any that
          break the business rules, then searches for the best measured trade-off.</p>
        <div className="shop-actions">
          <a className="primary action-link" href="#project">Start in the Project Workspace <Icon name="arrow"/></a>
          <button type="button" className="hero-secondary" onClick={() => document.getElementById('lab-workflow')?.scrollIntoView({behavior: 'smooth', block: 'start'})}>
            See the six stages <Icon name="arrow"/>
          </button>
        </div>
      </div>
      <div className="hero-visual story-hero-visual">
        <DecisionBoard/>
      </div>
    </section>

    <section className="story-section" aria-labelledby="decision-title">
      <div className="story-section-head">
        <div><span className="section-kicker">Why this lab exists</span><h2 id="decision-title">One server works. Then the traffic arrives.</h2></div>
        <span className="story-readout">100 → 10,000 customers</span>
      </div>
      <div className="story-decision-grid">
        <div className="story-prose">
          <p>With 100 customers, one backend and one database are enough. An influencer mentions the shop,
            and suddenly 2,000 people are checking out at once. Pages slow down, requests time out, the
            database saturates, payments fail and the bill climbs.</p>
          <p>Scaling adds capacity: a bigger machine, or more machines behind a load balancer. But capacity is
            not a decision. One team may need a cache; another needs a queue; another should stay simple.
            The right answer depends on the workload, the budget and the reliability the business requires.</p>
          <div className="story-symptoms" aria-label="Symptoms of an architecture that no longer fits">
            <span>Slow pages</span><span>Timeouts</span><span>Database overload</span><span>Failed payments</span><span>Rising cost</span>
          </div>
        </div>
        <aside className="panel story-question">
          <span className="section-kicker">The real question</span>
          <h3>Which configuration should carry the next 10,000 users?</h3>
          <dl>
            <div><dt>Cheap</dt><dd>A basic stack is simple, but may buckle under a spike.</dd></div>
            <div><dt>Fast</dt><dd>A cached stack may win on latency and cost more to operate.</dd></div>
            <div><dt>Complex</dt><dd>A distributed stack may be overkill — or it may hide a correctness bug.</dd></div>
          </dl>
          <p>Load tests, dashboards and architecture reviews each show part of the picture. Nobody automatically
            compares the alternatives, breaks them and checks the business rules together.</p>
        </aside>
      </div>

      <div className="table-scroll story-table" tabIndex={0} role="region" aria-label="Illustrative architecture comparison">
        <table aria-label="Illustrative architecture comparison with hypothetical numbers">
          <thead><tr>
            <th>Configuration</th><th>Shape</th><th>Monthly cost*</th><th>Response</th><th>Recovery</th><th>Duplicate payment</th><th>Decision</th>
          </tr></thead>
          <tbody>
            <tr>
              <td><strong>A · Basic</strong></td><td>1 API · PostgreSQL · no cache</td><td>₹10,000</td><td>900 ms</td><td>30 s</td><td>Pass</td><td>Cheap, slow</td>
            </tr>
            <tr className="story-table-best">
              <td><strong>B · Cached</strong></td><td>2 APIs · Redis · PostgreSQL</td><td>₹20,000</td><td>250 ms</td><td>10 s</td><td>Pass</td><td>Balanced — choose</td>
            </tr>
            <tr className="story-table-fail">
              <td><strong>C · Distributed</strong></td><td>Services · queues · Redis · workers</td><td>₹35,000</td><td>180 ms</td><td>5 s</td><td>Fail</td><td>Rejected</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="story-footnote">* Illustrative example with hypothetical numbers. Nothing in this table is a
        DARWIN result. The live lab reports only measured evidence and labels simulated screening separately.
        The point is the decision rule: a fast configuration that double-charges a customer is rejected.</p>
    </section>

    <section className="story-section" id="lab-workflow" aria-labelledby="workflow-title">
      <div className="story-section-head">
        <div><span className="section-kicker">The six stages</span><h2 id="workflow-title">One project, from question to solution</h2></div>
        <span className="story-readout">Overview → Solution</span>
      </div>
      <nav className="workflow story-workflow" aria-label="DARWIN lab workflow">
        {workflow.map(item => <a className="panel workflow-link" href={`#${item.page}`} key={item.step}>
          <span className="workflow-top"><span className="workflow-icon"><Icon name={item.icon}/></span><span className="workflow-number">{item.step}</span></span>
          <span className="workflow-copy"><strong>{item.title}</strong><small>{item.detail}</small></span>
          <span className="workflow-cta">{item.action}<Icon className="workflow-arrow" name="arrow"/></span>
        </a>)}
      </nav>
      <div className="story-outcome">
        <Icon name="book"/>
        <span><strong>Output: evidence-backed architecture recommendations.</strong>
          Every stage works on the same pinned commit, reviewed adapter and candidate IDs; a lab result is never presented as an imported-repo measurement.</span>
        <a href="#project">Start in the workspace <Icon name="arrow"/></a>
      </div>
    </section>

    <section className="story-section" aria-labelledby="compare-title">
      <div className="story-section-head">
        <div><span className="section-kicker">Positioning</span><h2 id="compare-title">Why not just AWS, Kubernetes and load tests?</h2></div>
        <span className="story-readout">Coordinate, don’t replace</span>
      </div>
      <div className="story-decision-grid story-compare-grid">
        <div className="table-scroll story-table story-compare" tabIndex={0} role="region" aria-label="Existing tools compared with DARWIN">
          <table aria-label="What existing tools do and what DARWIN adds">
            <thead><tr><th>Existing tool</th><th>What it gives you</th><th>What it does not decide</th></tr></thead>
            <tbody>
              {tools.map(tool => <tr key={tool.name}>
                <td><strong>{tool.name}</strong></td><td>{tool.provides}</td><td>{tool.decides}</td>
              </tr>)}
              <tr className="story-table-best">
                <td><strong>DARWIN</strong></td>
                <td>Coordinates alternatives, traffic, failures, correctness gates and evolutionary search into one experiment.</td>
                <td>—</td>
              </tr>
            </tbody>
          </table>
        </div>
        <aside className="story-prose story-position">
          <p>DARWIN does not replace these tools, and it did not invent load testing, fault injection or
            architecture optimization. It coordinates capabilities like these into one decision workflow.</p>
          <p>The difference is the combination: <strong>deployable alternatives + measured traffic + injected
            failures + business-correctness gates + NSGA-II search</strong>. The output is not a prettier diagram.
            It is a recommendation with an evidence trail.</p>
          <p className="story-callout">A fast configuration that double-charges a customer is not a winner.
            It is a rejected candidate with evidence.</p>
        </aside>
      </div>
    </section>

    <section className="story-section" aria-labelledby="scope-title">
      <div className="story-section-head">
        <div><span className="section-kicker">Scope, honestly</span><h2 id="scope-title">What this lab is today — and what it is not yet</h2></div>
        <span className="story-readout">Roadmap ≠ shipped</span>
      </div>
      <div className="story-scope">
        <article className="panel story-scope-card">
          <div className="section-title"><div className="panel-heading"><span className="section-kicker">Runs today</span><h3>Controlled backend laboratory</h3></div><span className="baseline-badge">Implemented</span></div>
          <ul>{today.map(item => <li key={item}><Icon name="check"/><span>{item}</span></li>)}</ul>
        </article>
        <article className="panel story-scope-card story-scope-next">
          <div className="section-title"><div className="panel-heading"><span className="section-kicker">Product direction</span><h3>General-purpose optimization</h3></div><span className="baseline-badge">Not shipped</span></div>
          <ul>{next.map(item => <li key={item}><Icon name="arrow"/><span>{item}</span></li>)}</ul>
          <p className="story-footnote">The right-hand column is the roadmap, not current functionality. The controlled
            lab is the foundation; optimizing arbitrary production systems is a much larger engineering problem.</p>
        </article>
      </div>
      <blockquote className="story-analogy">
        <span className="section-kicker">The analogy</span>
        <p>You would not choose a racing engine, tyres and suspension by guessing. You would build a test bench,
          measure each combination, reject the ones that fail safety, and keep the best overall trade-off.</p>
        <footer>DARWIN is that bench for backend architecture.</footer>
      </blockquote>
    </section>

    <div className="workflow-heading story-bench-heading">
      <div><span className="section-kicker">The bench today</span><h2>What you can run right now</h2></div>
      <span className="muted">Baseline: {baselineReplicas} API {baselineReplicas === 1 ? 'replica' : 'replicas'} · checkout lab</span>
    </div>
  </>;
}
