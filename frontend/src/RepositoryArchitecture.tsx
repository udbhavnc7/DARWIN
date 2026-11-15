import {Icon, type IconName} from './Action';
import type {Guess, Inspection, ProjectFact, UnsupportedCapability} from './projectApi';

type Props = {
  project: Inspection['project'];
  facts: ProjectFact[];
  notSupported: UnsupportedCapability[];
  guesses: Guess[];
};

type Stage = {title: string; detail: string; evidence: string; icon: IconName};

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

export function RepositoryArchitecture({project, facts, notSupported, guesses}: Props) {
  const map = stages(project);
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
    <p className="project-lede">{project.summary}</p>

    <ol className="repository-map" aria-label="Proven application path">
      {map.map((stage, index) => <li key={stage.title}>
        <span className="repository-map-icon"><Icon name={stage.icon}/></span>
        <span className="repository-map-copy">
          <strong>{stage.title}</strong>
          <small>{stage.detail}</small>
          <code>{stage.evidence}</code>
        </span>
        {index < map.length - 1 && <span className="repository-arrow" aria-hidden="true">→</span>}
      </li>)}
    </ol>

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
        <h3>Not claimed as server architecture</h3>
        <ul className="repository-unsupported">
          {notSupported.map(item => <li key={item.capability}>
            <Icon name="close"/>
            <span><strong>{item.capability}</strong>{item.reason}</span>
          </li>)}
        </ul>
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
