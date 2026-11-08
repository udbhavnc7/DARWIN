import { useState } from 'react';

type Genome={app_replicas:number;catalog_cache_ttl_s:number;notification_mode:string;retry_policy:string};
type Preview={genome_hash:string;topology:{nodes:{id:string;kind:string}[];edges:{source:string;target:string}[]}};
export function Architecture(){
  const [genome,setGenome]=useState<Genome>({app_replicas:1,catalog_cache_ttl_s:0,notification_mode:'sync',retry_policy:'idempotent_only'});
  const [preview,setPreview]=useState<Preview|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  function change(key:keyof Genome,value:number|string){setGenome({...genome,[key]:value});setPreview(null);setError('')}
  async function inspect(){setBusy(true);setError('');try{const r=await fetch('/api/genomes/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(genome)});if(!r.ok)throw Error();setPreview(await r.json());}catch{setError('Could not validate this architecture. Check the API connection.')}finally{setBusy(false)}}
  return <section className="panel shop-panel"><div className="section-title"><h2>Explore a configuration</h2><span>36 SUPPORTED COMBINATIONS</span></div><p className="muted">Preview the services required by these settings. Applying a configuration currently uses the local runner or generated Compose file.</p>
    <div className="genome-controls"><div><label htmlFor="replicas">API replicas</label><select disabled={busy} id="replicas" value={genome.app_replicas} onChange={e=>change('app_replicas',Number(e.target.value))}>{[1,2,3].map(v=><option key={v} value={v}>{v}</option>)}</select></div>
    <div><label htmlFor="ttl">Catalog cache</label><select disabled={busy} id="ttl" value={genome.catalog_cache_ttl_s} onChange={e=>change('catalog_cache_ttl_s',Number(e.target.value))}><option value={0}>Off</option><option value={10}>10 seconds</option><option value={30}>30 seconds</option></select></div>
    <div><label htmlFor="notification">Notifications</label><select disabled={busy} id="notification" value={genome.notification_mode} onChange={e=>change('notification_mode',e.target.value)}><option value="sync">Synchronous</option><option value="queued">Queued worker</option></select></div>
    <div><label htmlFor="retry">Retries</label><select disabled={busy} id="retry" value={genome.retry_policy} onChange={e=>change('retry_policy',e.target.value)}><option value="none">None</option><option value="idempotent_only">Idempotent only</option></select></div></div>
    <button className="primary preview-button" disabled={busy} onClick={inspect}>{busy?'Validating…':'Preview architecture'}</button>
    {error&&<p role="alert">{error}</p>}
    {preview&&<div><p role="status" className="muted">Configuration validated · preview only</p><div className="settings">{preview.topology.nodes.map(n=><span key={n.id}>{n.id}</span>)}</div><details><summary>Service connections and configuration hash</summary><ul>{preview.topology.edges.map(e=><li key={e.source+e.target}>{e.source} → {e.target}</li>)}</ul><code className="genome-hash">{preview.genome_hash}</code></details></div>}
  </section>;
}
