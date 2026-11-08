import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import { Shop } from './Shop';
import { Architecture } from './Architecture';
import { Experiments } from './Experiments';

type Project = {name:string; benchmarking_available:boolean; baseline:{app_replicas:number; catalog_cache_ttl_s:number; notification_mode:string; retry_policy:string}};
function App() {
  const [project,setProject] = useState<Project|null>(null);
  const [error,setError] = useState('');
  const [workload,setWorkload] = useState('normal');
  const [result,setResult] = useState('');
  const [busy,setBusy] = useState(false);
  async function connect() {
    setError('');
    try {const response=await fetch('/api/project'); if(!response.ok) throw Error('API unavailable'); setProject(await response.json());}
    catch {setProject(null);setError('Cannot reach the DARWIN API. Start the backend and retry.');}
  }
  useEffect(()=>{void connect()},[]);
  async function validate() {
    setBusy(true);setResult('');
    try {const response=await fetch('/api/experiments/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(project?.benchmarking_available?{mode:'native_benchmark',workload_profile:workload,genomes:[{},{app_replicas:3,catalog_cache_ttl_s:10,notification_mode:'queued'}]}:{workload_profile:workload})}); if(!response.ok) throw Error();setResult('Request format is valid.');}
    catch {setResult('Validation failed. Check the API connection and retry.');}
    finally {setBusy(false);}
  }
  return <main>
    <header><a className="brand" href="/">D<span> / </span>DARWIN</a><span className="pill">PHASE 05 · PERFORMANCE</span></header>
    <section className="hero"><p className="eyebrow">THE ARCHITECTURE LAB</p><h1>Evolution begins<br/>with evidence.</h1><p className="intro">Explore backend configurations, test their limits, and keep the improvements that hold up.</p></section>
    <div className="columns"><section className="panel"><div className="section-title"><h2>Starting architecture</h2><span>BASELINE</span></div>
      <p className="muted">Baseline topology · check the live shop below for availability</p>
      <div className="flow"><div>Gateway</div><span>↓</span><div>Catalog / Checkout API</div><span>↓</span><div className="branches"><div>Inventory</div><div>Mock payment</div></div><span>↓</span><div>PostgreSQL</div></div>
      {project && <div className="settings"><span>{project.baseline.app_replicas} API replica</span><span>Cache off</span><span>Synchronous notifications</span><span>Idempotent retries</span></div>}
    </section><section className="panel"><div className="section-title"><h2>Prepare an experiment</h2><span className={project?'online':'muted'}>{project?'API CONNECTED':'API OFFLINE'}</span></div>
      <p className="muted">Choose the workload for your performance comparison.</p>
      {error && <div role="alert">{error} <button onClick={connect}>Retry connection</button></div>}
      <label htmlFor="workload">Workload profile</label><select id="workload" value={workload} onChange={e=>{setWorkload(e.target.value);setResult('')}}><option value="normal">Normal traffic</option><option value="flash_sale">Flash sale</option><option value="checkout_heavy">Checkout heavy</option></select>
      <dl><div><dt>Candidate limit</dt><dd>12</dd></div><div><dt>Measured run budget</dt><dd>6 runs</dd></div><div><dt>Repeat each configuration</dt><dd>3 times</dd></div></dl>
      <button className="primary" disabled={!project||busy} onClick={validate}>{busy?'Validating…':'Validate configuration →'}</button><p role="status" className="result">{result}</p>
    </section></div>
    <Experiments workload={workload} canMeasure={project?.benchmarking_available??false}/>
    <Architecture/>
    <Shop/>
    <footer><span>05 Performance measurements → 06 Fault testing</span></footer>
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
