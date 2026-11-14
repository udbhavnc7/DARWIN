import {useEffect, useState} from 'react';
import {Topology} from './Graph';
import {Action, Icon} from './Action';
import {baseline, isBaseline, saveDraft, type Genome} from './genome';

type Preview = {genome_hash: string; topology: {nodes: {id: string; kind: string}[]; edges: {source: string; target: string}[]}};
type Simulation = {
  workload_profile: string;
  calibration_status: 'uncalibrated' | 'fitted_limited_evidence';
  metrics: {p95_ms: number; requests_per_s: number};
  heldout_evidence?: {repetitions: number; absolute_percentage_errors: number[]};
};

export function Architecture({genome, onEdit, workload, connected, active, onUse}: {
  genome: Genome; onEdit: (genome: Genome) => void;
  workload: string; connected: boolean; active: boolean; onUse: (genome: Genome) => void;
}) {
  const [previewResult, setPreviewResult] = useState<{genome: Genome; value: Preview} | null>(null);
  const preview = previewResult?.genome === genome ? previewResult.value : null;
  const [previewError, setPreviewError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [simulating, setSimulating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [simulation, setSimulation] = useState<{genome: Genome; value: Simulation} | null>(null);
  const estimate = simulation?.genome === genome ? simulation.value : null;
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active || !connected) return;
    const request = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch('/api/genomes/preview', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(genome), signal: request.signal,
        });
        if (!response.ok) throw Error();
        const value: Preview = await response.json();
        if (!request.signal.aborted) setPreviewResult({genome, value});
      } catch {
        if (!request.signal.aborted) setPreviewError('Could not load the architecture preview.');
      }
    }, 140);
    return () => {clearTimeout(timer); request.abort();};
  }, [genome, active, connected, refresh]);

  function edit(next: Genome) {
    saveDraft('builder', next);
    onEdit(next); setPreviewError(''); setError('');
  }

  async function simulate() {
    setSimulating(true); setSimulation(null); setError('');
    try {
      const response = await fetch('/api/simulate', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({genome, workload_profile: workload, duration_s: 12}),
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) throw Error();
      setSimulation({genome, value: await response.json()});
    } catch {
      setError('Could not simulate this configuration. Check the API connection and retry.');
    } finally {
      setSimulating(false);
    }
  }

  async function exportCompose() {
    if (!preview) return;
    setExporting(true); setError('');
    try {
      const response = await fetch('/api/genomes/compose', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(genome),
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw Error();
      const url = URL.createObjectURL(await response.blob());
      const download = document.createElement('a');
      download.href = url;
      download.download = `darwin-${preview.genome_hash.slice(0, 12)}.compose.yaml`;
      download.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError('Could not download the Compose file. Check the API connection and retry.');
    } finally {setExporting(false);}
  }

  return <section aria-label="Architecture builder" className="page-content">
    <p className="page-intro">Choose how the checkout backend is assembled, then simulate or run the configuration.</p>
    <div className="builder-grid">
      <div className="panel builder-controls">
        <div className="section-title panel-heading">
          <div><p className="section-kicker">Architecture settings</p><h2>Configuration</h2></div>
          <Action variant="quiet" icon="refresh" disabled={simulating || exporting || isBaseline(genome)} onClick={() => edit(baseline)}>Reset to baseline</Action>
        </div>
        <fieldset disabled={simulating || exporting}>
          <legend className="visually-hidden">Backend configuration</legend>
          <section className="builder-section" aria-labelledby="capacity-title">
            <h3 className="builder-section-heading" id="capacity-title"><Icon name="configuration"/>Capacity &amp; caching</h3>
            <div className="builder-field">
              <label htmlFor="replicas">API replicas</label>
              <select id="replicas" aria-describedby="replicas-help" value={genome.app_replicas} onChange={event => edit({...genome, app_replicas: Number(event.target.value)})}>
                {[1, 2, 3].map(value => <option key={value} value={value}>{value} {value === 1 ? 'replica' : 'replicas'}</option>)}
              </select>
              <p className="field-help" id="replicas-help">Share incoming requests across API instances.</p>
            </div>
            <div className="builder-field">
              <label htmlFor="ttl">Catalog cache</label>
              <select id="ttl" aria-describedby="ttl-help" value={genome.catalog_cache_ttl_s} onChange={event => edit({...genome, catalog_cache_ttl_s: Number(event.target.value)})}>
                <option value={0}>Off</option><option value={10}>10 seconds</option><option value={30}>30 seconds</option>
              </select>
              <p className="field-help" id="ttl-help">Choose how long product responses stay cached.</p>
            </div>
          </section>
          <section className="builder-section" aria-labelledby="resilience-title">
            <h3 className="builder-section-heading" id="resilience-title"><Icon name="refresh"/>Delivery &amp; resilience</h3>
            <div className="builder-field">
              <label htmlFor="notification">Notifications</label>
              <select id="notification" aria-describedby="notification-help" value={genome.notification_mode} onChange={event => edit({...genome, notification_mode: event.target.value as Genome['notification_mode']})}>
                <option value="sync">Synchronous</option><option value="queued">Queued worker</option>
              </select>
              <p className="field-help" id="notification-help">Send during checkout or use a background worker.</p>
            </div>
            <div className="builder-field">
              <label htmlFor="retry">Retries</label>
              <select id="retry" aria-describedby="retry-help" value={genome.retry_policy} onChange={event => edit({...genome, retry_policy: event.target.value as Genome['retry_policy']})}>
                <option value="none">None</option><option value="idempotent_only">Idempotent only</option>
              </select>
              <p className="field-help" id="retry-help">Idempotent retries reuse the original request key.</p>
            </div>
          </section>
        </fieldset>
        <div className="shop-actions form-actions builder-actions">
          <Action variant="primary" icon="arrow" disabled={!preview || !connected || simulating || exporting} onClick={() => onUse(genome)}>Use in experiment</Action>
          <Action icon="experiments" disabled={!connected || exporting} pending={simulating} onClick={simulate}>{simulating ? 'Simulating…' : 'Simulate performance'}</Action>
          <Action variant="quiet" icon="download" disabled={!preview || !connected || simulating} pending={exporting} onClick={exportCompose}>{exporting ? 'Downloading…' : 'Download Compose file'}</Action>
        </div>
        {error && <p role="alert">{error}</p>}
      </div>
      <div className="panel topology-panel">
        <div className="section-title panel-heading">
          <div><p className="section-kicker">Live preview</p><h2>Service topology</h2></div>
          <span className="muted mono">{isBaseline(genome) ? 'Baseline' : 'Custom configuration'}</span>
        </div>
        {preview && connected && <div className="topology-summary" aria-label="Topology summary">
          <span><Icon name="configuration"/><strong>{preview.topology.nodes.length}</strong> services</span>
          <span><strong>{preview.topology.edges.length}</strong> connections</span>
          <span><strong>{genome.app_replicas}</strong> API {genome.app_replicas === 1 ? 'replica' : 'replicas'}</span>
        </div>}
        {active && connected && preview && <>
          <Topology key={preview.genome_hash} {...preview.topology}/>
          <details><summary>Service connections and configuration hash</summary>
            <ul>{preview.topology.edges.map(edge => <li key={`${edge.source}-${edge.target}`}>{edge.source} → {edge.target}</li>)}</ul>
            <code className="genome-hash">{preview.genome_hash}</code>
          </details>
        </>}
        {(!connected || !preview) && <div className="graph graph-placeholder topology-empty">
          {previewError && connected ? <><p role="alert">{previewError}</p><Action icon="refresh" onClick={() => {setPreviewError(''); setRefresh(value => value + 1);}}>Retry preview</Action></>
            : <><Icon name="configuration"/><h3>{connected ? 'Updating your architecture' : 'Your topology will appear here'}</h3>
              <p role="status">{connected ? 'Mapping services and connections for these settings…' : 'Connect the API to preview the services in your configuration.'}</p></>}
        </div>}
      </div>
    </div>
    {estimate?.workload_profile === workload && <div className="panel simulation-card" role="status">
      <div className="section-title"><h2>Simulated performance</h2><span className="muted">{estimate.calibration_status === 'uncalibrated' ? 'Uncalibrated' : 'Fitted with limited evidence'}</span></div>
      <dl className="metrics-grid">
        <div><dt>Estimated p95 latency</dt><dd>{estimate.metrics.p95_ms.toFixed(1)} ms</dd></div>
        <div><dt>Estimated throughput</dt><dd>{estimate.metrics.requests_per_s.toFixed(2)} requests/s</dd></div>
      </dl>
      {estimate.heldout_evidence && estimate.heldout_evidence.repetitions > 0 &&
        <p className="muted">Held-out p95 error: {estimate.heldout_evidence.absolute_percentage_errors.map(value => `${value.toFixed(1)}%`).join(', ')}.</p>}
      <p className="muted">Correctness gate unchecked. Use a fault experiment to verify recovery.</p>
    </div>}
  </section>;
}
