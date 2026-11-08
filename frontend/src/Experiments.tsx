import {useEffect,useState} from 'react';

type Artifact={name:string;sha256:string};
type Evaluation={evaluation_id:string;status:string;repetition:number;artifacts:Artifact[]};
type Spread={min:number;median:number;max:number};
type Summary={repetitions:number;performance_constraints_met:boolean;spread:Record<string,Spread>};
type Run={experiment_id:string;status:string;attempts_used:number;error?:string;cleanup_status:string;measurement_kind:string;request:{workload_profile:string};candidates:{candidate_id:string;genome:{app_replicas:number;catalog_cache_ttl_s:number;notification_mode:string};summary?:Summary;evaluations:Evaluation[]}[]};
const terminal=(run:Run|null)=>!run||['completed','failed','cancelled'].includes(run.status);
const measures = [['p95_ms','p95 (ms)'], ['requests_per_s','Requests/s'], ['error_rate','Errors (%)'], ['cpu_seconds','CPU (s)'], ['memory_peak_mb','Peak MiB']];
function range(value:Spread, field:string){
  const fmt=(n:number)=>(field==='error_rate'?100*n:n).toFixed(2);
  return `${fmt(value.median)} (${fmt(value.min)}–${fmt(value.max)})`;
}
export function Experiments({workload,canMeasure}:{workload:string;canMeasure:boolean}){
  const [history,setHistory]=useState<Run[]>([]);
  const [run,setRun]=useState<Run|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [mode,setMode]=useState('benchmark');
  const measure=mode==='benchmark' && canMeasure;
  const activeWorkload=run&&!terminal(run)?run.request.workload_profile:workload;
  const [candidate,setCandidate]=useState('baseline');
  function remember(record:Run) {
    setRun(record);
    setHistory(rows=>[record,...rows.filter(row=>row.experiment_id!==record.experiment_id)]);
  }
  useEffect(()=>{
    fetch('/api/experiments').then(response=>{
      if(!response.ok) throw Error();
      return response.json();
    }).then((rows:Run[])=>{setHistory(rows);setRun(rows[0]??null)})
      .catch(()=>setError('Experiment worker unavailable.'));
  },[]);
  useEffect(()=>{
    if(!run||terminal(run)) return;
    let alive=true;
    const timer=setInterval(()=>{
      fetch(`/api/experiments/${run.experiment_id}`).then(response=>{
        if(!response.ok) throw Error();
        return response.json();
      }).then(value=>{if(alive){remember(value);setError('')}})
        .catch(()=>{if(alive)setError('Status connection lost. DARWIN will retry.')});
    },700);
    return ()=>{alive=false;clearInterval(timer)};
  },[run?.experiment_id,run?.status]);
  async function start(){
    setBusy(true);
    setError('');
    const cached={app_replicas:3,catalog_cache_ttl_s:10,notification_mode:'queued'};
    const payload=measure
      ? {mode:'native_benchmark',workload_profile:workload,genomes:[{},cached]}
      : {mode:'native_smoke',genomes:[candidate==='baseline'?{}:cached]};
    try {
      const response=await fetch('/api/experiments',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
      });
      const data=await response.json();
      if(!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Request was rejected');
      remember(data);
    } catch(error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }
  async function cancel(){
    if(!run) return;
    setBusy(true);
    try {
      const response=await fetch(`/api/experiments/${run.experiment_id}/cancel`,{method:'POST'});
      if(!response.ok) throw Error();
      remember(await response.json());
    } catch {
      setError('Cancellation could not be confirmed.');
    } finally {
      setBusy(false);
    }
  }
  return <section className="panel shop-panel"><div className="section-title"><h2>Run an experiment</h2></div>
    <label htmlFor="experiment-mode">Experiment type</label><select id="experiment-mode" value={measure?'benchmark':'smoke'} disabled={busy||!terminal(run)} onChange={e=>setMode(e.target.value)}>
      {canMeasure&&<option value="benchmark">Compare performance</option>}<option value="smoke">Checkout smoke check</option></select>
    {measure?<p className="muted">Compare the baseline with 3 replicas, a 10-second catalog cache and queued notifications. Each configuration runs three times under the {activeWorkload.replace('_',' ')} workload.</p>:<>
      <label htmlFor="smoke-candidate">Configuration</label><select id="smoke-candidate" disabled={busy||!terminal(run)} value={candidate} onChange={e=>setCandidate(e.target.value)}><option value="baseline">Baseline · 1 replica · cache off · sync</option><option value="cached">3 replicas · 10s cache · queued notifications</option></select></>}
    <div className="shop-actions"><button className="primary" disabled={busy||!terminal(run)} onClick={start}>{measure?'Start performance comparison':'Start smoke experiment'}</button>{!terminal(run)&&<button disabled={busy} onClick={cancel}>Cancel experiment</button>}</div>
    {error&&<p role="alert">{error}</p>}
    {history.length>1&&<><label htmlFor="saved-run">Saved experiments</label>
      <select id="saved-run" disabled={busy} value={run?.experiment_id??''} onChange={e=>{setError('');setRun(history.find(row=>row.experiment_id===e.target.value)??null)}}>
        {history.map(row=><option key={row.experiment_id} value={row.experiment_id}>
          {row.measurement_kind==='measured'?row.request.workload_profile.replace('_',' '):'Smoke'} · {row.status} · {row.experiment_id.slice(0,8)}
        </option>)}
      </select></>}
    {run&&<div><p role="status">{run.status.toUpperCase()} · {run.attempts_used} {run.attempts_used===1?'attempt':'attempts'} · cleanup: {run.cleanup_status}</p>
      <p className="muted">{run.measurement_kind==='measured'?`Measured · ${run.request.workload_profile.replace('_',' ')}`:'Smoke check'} · Run {run.experiment_id}</p>
      {run.error&&<p role="alert">{run.error}</p>}
      {run.candidates.map(c=><div key={c.candidate_id}>
        <h3>{c.genome.app_replicas} API {c.genome.app_replicas===1?'replica':'replicas'} · {c.genome.catalog_cache_ttl_s?`cache ${c.genome.catalog_cache_ttl_s}s`:'cache off'} · {c.genome.notification_mode}</h3>
        {c.summary&&<><p className="muted">Median (min–max) across {c.summary.repetitions} repetitions. Performance thresholds {c.summary.performance_constraints_met?'met':'exceeded'}.</p>
          <dl>{measures.map(([key,title])=><div key={key}><dt>{title}</dt><dd>{range(c.summary!.spread[key],key)}</dd></div>)}</dl></>}
        {c.evaluations.map(e=><details key={e.evaluation_id}><summary>Repetition {e.repetition+1} · {e.status}</summary><ul>{e.artifacts.map(a=><li key={a.name}><a className="artifact-link" href={`/api/experiments/${run.experiment_id}/artifacts/${e.evaluation_id}/${encodeURIComponent(a.name)}`}>{a.name}</a></li>)}</ul></details>)}
      </div>)}</div>}
  </section>;
}
