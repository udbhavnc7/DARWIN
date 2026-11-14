import {Icon} from './Action';

const primaryReports = new Set(['fault-report.json', 'measurement.json', 'smoke.json', 'manifest.json']);

export function EvidenceLinks({experimentId, evaluationId, artifacts}: {
  experimentId: string;
  evaluationId: string;
  artifacts: {name: string}[];
}) {
  const primary = artifacts.filter(({name}) => primaryReports.has(name));
  const other = artifacts.filter(({name}) => !primaryReports.has(name));
  function links(files: {name: string}[]) {
    return <ul className="evidence-links">{files.map(({name}) => <li key={name}>
      <a className="artifact-link" href={`/api/experiments/${experimentId}/artifacts/${evaluationId}/${encodeURIComponent(name)}`}><Icon name="download"/>{name}</a>
    </li>)}</ul>;
  }

  return <>
    {primary.length > 0 && links(primary)}
    {other.length > 0 && <details><summary>Supporting artifacts ({other.length})</summary>{links(other)}</details>}
  </>;
}
