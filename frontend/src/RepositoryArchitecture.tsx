import {Icon, type IconName} from './Action';
import type {
  Architecture, Guess, Hotspot, Inspection, ProjectFact, ScreeningSupport, UnsupportedCapability,
} from './projectApi';
import {controlLabel} from './projectApi';

type Props = {
  project: Inspection['project'];
  facts: ProjectFact[];
  notSupported: UnsupportedCapability[];
  guesses: Guess[];
  architecture?: Architecture | null;
  hotspots?: Hotspot[];
  screening?: ScreeningSupport | null;
};

type Stage = {title: string; detail: string; evidence: string; icon: IconName};

const nodeIcons: Record<string, IconName> = {
  client: 'configuration', gateway: 'shield', service: 'server', cache: 'database',
  database: 'database', queue: 'refresh', worker: 'settings', external: 'arrow',
  storage: 'database', auth: 'shield',
};

function stages(project: Inspection['project']): Stage[] {
  if (project.type === 'react_webview_local_app') {
    return [
      {title: 'React UI', detail: 'Visible application', evidence: 'web/package.json', icon: 'configuration'},
      {title: 'Finance logic', detail: 'Reports, totals, budgets', evidence: 'web/src/utils/reporting.ts', icon: 'experiments'},
      {title: 'Browser storage', detail: project.persistence, evidence: 'web/src/data/persistence.ts', icon: 'database'},
      {title: 'Android WebView', detail: 'Host shell', evidence: 'app/src/main/java/…/SanchayModernUI.kt', icon: 'phone'},
    ];
  }
  if (project.type === 'client_web_app') {
    return [
      {title: 'Browser UI', detail: 'React application', evidence: 'web/package.json', icon: 'configuration'},
      {title: 'Application logic', detail: 'Client-side processing', evidence: 'source tree', icon: 'code'},
      {title: 'Persistence', detail: project.persistence, evidence: 'source tree', icon: 'database'},
    ];
  }
  if (project.type === 'node_service') {
    return [
      {title: 'Node process', detail: 'Server entry point found', evidence: 'package.json', icon: 'server'},
      {title: 'Service code', detail: project.application_host, evidence: 'source tree', icon: 'code'},
      {title: 'Persistence', detail: project.persistence, evidence: 'source tree', icon: 'database'},
    ];
  }
  return [
    {title: 'Source checkout', detail: 'Repository inspected read-only', evidence: 'pinned commit', icon: 'book'},
    {title: 'Application shape', detail: project.display_type, evidence: 'source tree', icon: 'search'},
  ];
}

function signalNames(items?: {name: string}[]): string {
  if (!items || items.length === 0) return 'None detected';
  return items.map(item => item.name).join(' · ');
}

function backendRows(project: Inspection['project']): {label: string; value: string}[] {
  const backend = project.backend;
  if (!backend?.detected) return [];
  return [
    {label: 'Services', value: backend.services?.length
      ? backend.services.map(service => `${service.name} (${service.framework})`).join(' · ')
      : 'None detected'},
    {label: 'HTTP routes', value: String(backend.route_count ?? 0)},
    {label: 'Data stores', value: signalNames(backend.datastores)},
    {label: 'Queues', value: signalNames(backend.queues)},
    {label: 'Authentication', value: signalNames(backend.auth)},
    {label: 'External calls', value: signalNames(backend.external_services)},
    {label: 'Background work', value: signalNames(backend.background_jobs)},
    {label: 'Tests', value: backend.tests?.file_count
      ? `${backend.tests.file_count} file(s)${backend.tests.frameworks?.length
        ? ` · ${backend.tests.frameworks.join(', ')}` : ''}`
      : 'None detected'},
    {label: 'Deployment', value: backend.deployment?.length
      ? backend.deployment.map(item => item.name).join(' · ') : 'None detected'},
    {label: 'Confidence', value: backend.confidence ?? '—'},
  ];
}

export function RepositoryArchitecture({
  project, facts, notSupported, guesses, architecture, hotspots = [], screening,
}: Props) {
  const map = stages(project);
  const backend = project.backend;
  const note = project.note;
  const nodes = architecture?.nodes ?? [];
  const edges = architecture?.edges ?? [];
  const nodeById = new Map(nodes.map(node => [node.id, node]));
  const controls = new Set(screening?.controls ?? []);
  const rows = backendRows(project);

  return <section className="project-panel repository-panel" aria-labelledby="repository-title">
    <div className="section-title">
      <div className="panel-heading">
        <span className="section-kicker">Step 2 · Understand it</span>
        <h2 id="repository-title">{project.display_type}</h2>
      </div>
      <span className={`status-chip ${project.is_server_backend ? 'active' : 'good'}`}>
        {project.is_server_backend ? 'Server application' : 'Client application'}
      </span>
    </div>
    <p className="project-lede">{note?.what_it_is ?? project.summary}</p>

    {note && <div className="project-note-grid">
      <div>
        <span className="section-kicker">What it is</span>
        <p>{note.what_it_is}</p>
      </div>
      <div>
        <span className="section-kicker">How the backend works</span>
        <p>{note.backend}</p>
      </div>
      <div>
        <span className="section-kicker">Request path</span>
        <p>{note.how_it_works}</p>
      </div>
      <div>
        <span className="section-kicker">What can evolve</span>
        <p>{note.evolution}</p>
      </div>
    </div>}

    {nodes.length > 0 ? <div className="repository-architecture">
      <div className="repository-flow-head">
        <h3>Detected architecture</h3>
        <span className="status-chip active">File-backed</span>
      </div>
      <p className="project-footnote">{architecture?.summary}</p>
      <ol className="repository-graph" aria-label="Detected backend architecture">
        {nodes.map(node => <li key={node.id} className={`repository-node repository-node-${node.kind}`}>
          <span className="repository-node-icon"><Icon name={nodeIcons[node.kind] ?? 'project'}/></span>
          <span className="repository-node-copy">
            <strong>{node.label}</strong>
            <small>{node.detail}</small>
            {node.evidence.length > 0 && <code>{node.evidence.join(' · ')}</code>}
          </span>
        </li>)}
      </ol>

      {edges.length > 0 && <ul className="repository-edges" aria-label="Detected connections">
        {edges.map(edge => {
          const source = nodeById.get(edge.source);
          const target = nodeById.get(edge.target);
          if (!source || !target) return null;
          return <li key={`${edge.source}-${edge.target}-${edge.label}`}>
            <span>{source.label}</span>
            <span className="repository-edge-arrow" aria-hidden="true">→</span>
            <span>{target.label}</span>
            <small>{edge.label}</small>
          </li>;
        })}
      </ul>}

      {(architecture?.flow?.length ?? 0) > 0 && <div className="repository-flow">
        <h3>How a request moves</h3>
        <ol>{architecture?.flow.map(step => <li key={step}>{step}</li>)}</ol>
      </div>}
    </div> : <ol className="repository-map" aria-label="Proven application path">
      {map.map((stage, index) => <li key={stage.title}>
        <span className="repository-map-icon"><Icon name={stage.icon}/></span>
        <span className="repository-map-copy">
          <strong>{stage.title}</strong>
          <small>{stage.detail}</small>
          <code>{stage.evidence}</code>
        </span>
        {index < map.length - 1 && <span className="repository-arrow" aria-hidden="true">→</span>}
      </li>)}
    </ol>}

    {rows.length > 0 && <div className="repository-backend">
      <h3>Backend profile</h3>
      <dl className="repository-backend-grid">
        {rows.map(row => <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>)}
      </dl>
      {backend && backend.routes.length > 0 && <details className="repository-routes">
        <summary>Detected routes <span className="status-chip">{backend.routes.length}</span></summary>
        <div className="table-scroll project-table">
          <table>
            <thead><tr><th scope="col">Method</th><th scope="col">Path</th><th scope="col">Source</th></tr></thead>
            <tbody>{backend.routes.map(route => <tr key={`${route.file}-${route.line}-${route.method}-${route.path}`}>
              <td><code>{route.method}</code></td>
              <td><code>{route.path}</code></td>
              <td>{route.file}{route.line ? `:${route.line}` : ''}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <p className="project-footnote">
          Routes are read from source with static patterns. They are not probed, started or called.
        </p>
      </details>}
    </div>}

    {hotspots.length > 0 && <div className="repository-hotspots">
      <h3>Architecture hotspots <span className="status-chip warn">{hotspots.length}</span></h3>
      <ul className="repository-hotspot-list">
        {hotspots.map(hotspot => <li key={hotspot.id} className={`repository-hotspot severity-${hotspot.severity}`}>
          <div className="repository-hotspot-head">
            <span className={`status-chip ${hotspot.severity === 'high' ? 'bad'
              : hotspot.severity === 'medium' ? 'warn' : 'muted'}`}>{hotspot.severity}</span>
            <strong>{hotspot.title}</strong>
            <small>{hotspot.confidence} confidence</small>
          </div>
          <p>{hotspot.detail}</p>
          {hotspot.evidence.length > 0 && <ul className="repository-hotspot-evidence">
            {hotspot.evidence.map(item => <li key={`${item.file}-${item.line}-${item.snippet}`}>
              <code>{item.file}{item.line ? `:${item.line}` : ''}</code>
              <span>{item.snippet}</span>
            </li>)}
          </ul>}
          <p className="project-footnote">
            <strong>Suggested check:</strong> {hotspot.recommendation}
            {hotspot.control && <> · Screening control: {controls.has(hotspot.control)
              ? controlLabel(hotspot.control) : `${controlLabel(hotspot.control)} (not available)`}</>}
          </p>
        </li>)}
      </ul>
    </div>}

    <div className="repository-columns">
      <div>
        <h3>Proven from source</h3>
        <dl className="repository-facts">
          {facts.map(fact => <div key={fact.label}>
            <dt>{fact.label}</dt>
            <dd>{fact.value}<span>{fact.evidence.join(' · ')}</span></dd>
          </div>)}
        </dl>
      </div>
      <div>
        <h3>Not claimed</h3>
        <ul className="repository-unsupported">
          {notSupported.map(item => <li key={item.capability}>
            <Icon name="close"/>
            <span><strong>{item.capability}</strong>{item.reason}</span>
          </li>)}
        </ul>
        {notSupported.length === 0 && <p className="muted">No unsupported claim was recorded for this source.</p>}
      </div>
    </div>

    {guesses.length > 0 && <details className="repository-guesses">
      <summary>Unconfirmed observations <span className="status-chip warn">{guesses.length}</span></summary>
      <ul>{guesses.map(guess => <li key={guess.label}>
        <strong>{guess.label} · {guess.confidence} confidence.</strong> {guess.guess}
      </li>)}</ul>
    </details>}
  </section>;
}
