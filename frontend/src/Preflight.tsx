import {Action, Icon} from './Action';
import {Status} from './Status';
import {isLive, showcase} from './showcase';

const recorded = () => showcase && !isLive();

export type PreflightCheck = {
  id: string; label: string; required: boolean; status: string;
  version: string | null; detail: string; remedy: string | null;
};
export type Preflight = {
  generated_at: string; ready: boolean;
  platform: {system: string; release: string; cpu_count: number | null; memory_mb: number | null};
  checks: PreflightCheck[];
  capabilities: {smoke: boolean; benchmark: boolean; faults: boolean; docker: boolean};
};

const tone = (status: string) => status === 'ready' ? 'ready' : status === 'optional_missing' ? 'optional' : 'missing';

export function Readiness({preflight, loading, onRefresh}: {
  preflight: Preflight | null; loading: boolean; onRefresh: () => void;
}) {
  const blockers = preflight?.checks.filter(check => check.required && check.status !== 'ready') ?? [];
  const optionalMissing = preflight?.checks.filter(check => !check.required && check.status !== 'ready') ?? [];
  return <section className="panel readiness" aria-labelledby="readiness-title">
    <div className="section-title">
      <div className="panel-heading">
        <span className="section-kicker">{recorded() ? 'Recorded on the capture machine' : 'Before you present'}</span>
        <h2 id="readiness-title">Machine readiness</h2>
      </div>
      <Status value={loading ? 'running' : !preflight ? 'offline' : blockers.length ? 'failed' : 'connected'}
        label={loading ? 'Checking' : !preflight ? 'Unavailable' : blockers.length ? 'Needs attention' : 'Ready'}/>
    </div>
    {!preflight && <p className="muted">{loading ? 'Checking this machine for the tools DARWIN uses.' : 'The API did not return a readiness report. Start the backend and check again.'}</p>}
    {preflight && <>
      <p className="muted readiness-summary">
        {preflight.platform.system} · {preflight.platform.cpu_count ?? '—'} logical CPUs · {preflight.platform.memory_mb ? `${Math.round(preflight.platform.memory_mb / 1024)} GiB memory` : 'memory unknown'}
        <span aria-hidden="true"> · </span>
        {preflight.capabilities.faults ? 'smoke, performance and fault tests available'
          : preflight.capabilities.benchmark ? 'smoke and performance tests available' : 'smoke checks only'}
      </p>
      <ul className="readiness-checks" aria-label="Readiness checks">
        {preflight.checks.map(check => <li key={check.id} className={`readiness-check ${tone(check.status)}`}>
          <span className="readiness-mark" aria-hidden="true">{check.status === 'ready' ? <Icon name="check"/> : <Icon name="shield"/>}</span>
          <span className="readiness-copy"><strong>{check.label}</strong>
            <small>{check.version ?? check.detail}{check.version && check.status !== 'ready' ? ` · ${check.detail}` : ''}</small>
          </span>
          <span className="readiness-state">{check.status === 'ready' ? 'Ready' : check.required ? 'Missing' : 'Optional'}</span>
        </li>)}
      </ul>
      {blockers.length > 0 && <div className="readiness-remedy" role="alert">
        <strong>Some checks need attention.</strong>
        <ul>{blockers.map(check => <li key={check.id}>{check.label}: {check.remedy ?? 'Install this dependency.'}</li>)}</ul>
      </div>}
      {optionalMissing.length > 0 && <p className="muted readiness-optional">
        Optional on this machine: {optionalMissing.map(check => check.label).join(', ')}. Runs that need them stay disabled instead of failing halfway.
      </p>}
      <div className="readiness-footer">
        <span className="muted">Checked {recorded() ? new Date(preflight.generated_at).toLocaleString() : new Date(preflight.generated_at).toLocaleTimeString()}</span>
        {!recorded() && <Action variant="quiet" icon="refresh" pending={loading} onClick={onRefresh}>{loading ? 'Checking…' : 'Run preflight again'}</Action>}
      </div>
    </>}
  </section>;
}
