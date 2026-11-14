import {useEffect,useState} from 'react';
import {EvidenceLinks} from './EvidenceLinks';
import {Action, Icon} from './Action';
import {Status} from './Status';
import {rememberRunInUrl} from './runLink';
import {baseline, cached, describeGenome, isBaseline, type Genome} from './genome';

type Artifact={name:string;sha256:string};
type Evaluation={evaluation_id:string;status:string;repetition:number;artifacts:Artifact[];gate?:string;gate_reasons?:string[];violations?:{invariant_id:string;detail:string;key?:string}[];recovery?:{scenario:string;recovery_s:number|null}[]};
type Spread={min:number;median:number;max:number};
type Summary={repetitions:number;performance_constraints_met:boolean;spread:Record<string,Spread>;gate?:string};
type Run={experiment_id:string;status:string;attempts_used:number;error?:string;cleanup_status:string;measurement_kind:string;request:{workload_profile:string;mode:string;fault_fixture?:string;budget?:{repetitions:number}};candidates:{candidate_id:string;genome:Genome;summary?:Summary;evaluations:Evaluation[]}[]};
const terminal=(run:Run|null)=>!run||['completed','failed','cancelled'].includes(run.status);
const measures = [['p95_ms','p95 (ms)'], ['requests_per_s','Requests/s'], ['error_rate','Errors (%)'], ['cpu_seconds','CPU (s)'], ['memory_peak_mb','Peak MiB']];
const formatMetric = (n:number, field:string) => (field==='error_rate'?100*n:n).toFixed(2);
export function Experiments({workload,canMeasure,runtime,canStart,draft}:{workload:string;canMeasure:boolean;runtime:'native'|'docker';canStart:boolean;draft:{genome:Genome}|null}){
  const [history,setHistory]=useState<Run[]>([]);
  const [historyState,setHistoryState]=useState<'loading'|'ready'|'error'>('loading');
  const [run,setRun]=useState<Run|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [refreshKey,setRefreshKey]=useState(0);
  const [events,setEvents]=useState<{sequence:number;message:string}[]>([]);
  const [mode,setMode]=useState('benchmark');
  const measure=mode==='benchmark' && canMeasure;
  const faults=(mode==='faults'||mode==='unsafe') && canMeasure;
  const [candidate,setCandidate]=useState('preset');
  const [validating,setValidating]=useState(false);
  const [validatedRequest,setValidatedRequest]=useState('');
  const selectedGenome = candidate==='custom' && draft ? draft.genome
    : candidate==='baseline' ? baseline : faults ? {...baseline, notification_mode: 'queued' as const} : cached;
  const duplicateBaseline = measure && isBaseline(selectedGenome);
  const locked = busy || validating || historyState==='loading' || !terminal(run);
  const payload = faults
    ? {mode:`${runtime}_faults`,workload_profile:workload,fault_fixture:mode==='unsafe'?'unsafe_retry':'safe',
       fault_scenarios:mode==='unsafe'?['timeout_retry_duplicate']:['db_delay','service_outage','timeout_retry_duplicate'],
       genomes:[mode==='unsafe' ? {...baseline, notification_mode:'queued'} : selectedGenome]}
    : measure ? {mode:`${runtime}_benchmark`,workload_profile:workload,genomes:[baseline,selectedGenome]}
    : {mode:`${runtime}_smoke`,genomes:[selectedGenome]};
  const requestBody = JSON.stringify(payload);

  useEffect(()=>{if(draft){setCandidate('custom');setMode('smoke');}},[draft]);
  function remember(record:Run) {
    setRun(record);
    setHistory(rows=>[record,...rows.filter(row=>row.experiment_id!==record.experiment_id)]);
  }
  useEffect(()=>{
    let alive=true;
    setHistoryState('loading');
    fetch('/api/experiments',{signal:AbortSignal.timeout(10000)}).then(response=>{
      if(!response.ok) throw Error();
      return response.json();
    }).then((rows:Run[])=>{
      if(!alive) return;
      const selected = new URLSearchParams(window.location.search).get('experiment');
      setHistory(rows);
      setRun(rows.find(row=>row.experiment_id===selected)??rows[0]??null);
      setHistoryState('ready');
      setError('');
    })
      .catch(()=>{if(alive){setHistoryState('error');setError('Saved experiments could not be loaded. Check the API connection and refresh the history.');}});
    return ()=>{alive=false};
  },[refreshKey]);
  useEffect(()=>{
    if(!run) return;
    let alive=true;
    const refresh=()=>fetch(`/api/experiments/${run.experiment_id}/events`)
      .then(response=>response.ok?response.json():[])
      .then(value=>{if(alive)setEvents(value)})
      .catch(()=>{});
    void refresh();
    const timer=terminal(run)?undefined:setInterval(refresh,1500);
    return ()=>{alive=false;clearInterval(timer)};
  },[run?.experiment_id,run?.status]);
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
    try {
      const response=await fetch('/api/experiments',{
        method:'POST',headers:{'Content-Type':'application/json'},body:requestBody
      });
      const data=await response.json();
      if(!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Request was rejected');
      rememberRunInUrl('experiment',data.experiment_id);
      remember(data);
    } catch(error) {
      setError(String(error));
    } finally {
      setBusy(false);
    }
  }
  async function validate() {
    setValidating(true); setValidatedRequest(''); setError('');
    try {
      const response = await fetch('/api/experiments/validate', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:requestBody, signal:AbortSignal.timeout(10000),
      });
      if (!response.ok) throw Error();
      setValidatedRequest(requestBody);
    } catch {
      setError('Could not validate this experiment. Check the settings and API connection.');
    } finally {setValidating(false);}
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
  async function rerun(candidateId:string){
    setBusy(true);setError('');
    try {
      const response=await fetch(`/api/candidates/${candidateId}/rerun`,{method:'POST'});
      const value=await response.json();
      if(!response.ok)throw Error(value.detail??'Rerun rejected');
      rememberRunInUrl('experiment',value.experiment_id);
      remember(value);
    }catch(reason){setError(String(reason))}
    finally{setBusy(false)}
  }
  const plannedAttempts=run ? run.candidates.length*(run.request.budget?.repetitions??3) : 0;
  return <section aria-label="Experiment workspace" className="page-content">
    <p className="page-intro">Run isolated checkout, load, and recovery tests. Compare measured results and inspect the evidence.</p>
    <div className="experiment-grid">
    <div className="panel experiment-controls">
    <div className="section-title panel-heading"><div><p className="section-kicker">Experiment setup</p><h2>New experiment</h2></div></div>
    <label htmlFor="experiment-mode">Experiment type</label><select id="experiment-mode" value={canMeasure?mode:'smoke'} disabled={locked} onChange={e=>setMode(e.target.value)}>
      {canMeasure&&<><option value="benchmark">Compare performance</option><option value="faults">Verify failure recovery</option><option value="unsafe">Unsafe retry fixture</option></>}<option value="smoke">Checkout smoke check</option></select>
    {!(faults && mode==='unsafe') && <>
      <label htmlFor="experiment-candidate">Configuration</label>
      <select id="experiment-candidate" disabled={locked} value={candidate} onChange={e=>setCandidate(e.target.value)}>
        <option value="preset">{faults?'Queued notifications':'Three replicas with cache'}</option>
        <option value="baseline" disabled={measure}>Baseline</option>
        {draft && <option value="custom">Custom architecture</option>}
      </select>
      <p className="configuration-summary">{describeGenome(selectedGenome)}</p>
    </>}
    <p className="muted">{faults ? mode==='unsafe'?'Reproduce a duplicate payment after a lost response in the test shop.':'Inject database delay, disconnection and an API outage, then verify checkout, retries and notification recovery.'
      : measure ? `Compare this configuration with the baseline using the ${workload.replaceAll('_',' ')} workload.`
      : 'Verify that the checkout stack starts and handles repeat orders correctly.'} Three isolated repetitions per configuration.</p>
    {duplicateBaseline && <p role="alert">Choose a configuration that differs from the baseline to compare performance.</p>}
    <div className="shop-actions form-actions">{!terminal(run)
      ? <Action variant="danger" icon="stop" pending={busy} onClick={cancel}>{busy?'Cancelling…':'Cancel experiment'}</Action>
      : <><Action variant="primary" icon="play" disabled={!canStart||validating||historyState==='loading'||duplicateBaseline} aria-describedby={!canStart?'experiment-runtime-hint':undefined} pending={busy} onClick={start}>{busy?'Submitting…':faults?(mode==='unsafe'?'Run unsafe retry fixture':'Start fault verification'):measure?'Start performance comparison':'Start smoke experiment'}</Action>
        <Action icon="check" disabled={!canStart||busy||historyState==='loading'||duplicateBaseline} pending={validating} onClick={validate}>{validating?'Validating…':'Validate request'}</Action></>}
    </div>
    {!canStart && <p id="experiment-runtime-hint" className="field-help">The selected runtime is unavailable. Refresh runtimes above before starting an experiment.</p>}
    {canStart && !canMeasure && <p className="field-help">This runtime currently supports smoke checks. Performance and recovery tests need a runtime with measurement support.</p>}
    {validatedRequest===requestBody && <p role="status" className="result">Experiment request validated.</p>}
    {error&&<p role="alert">{error}</p>}
    </div>
    <div className="panel experiment-results">
    <div className="section-title"><h2>Run history</h2>
      <Action variant="quiet" icon="refresh" pending={historyState==='loading'} disabled={locked} onClick={()=>setRefreshKey(value=>value+1)}>{historyState==='loading'?'Loading history…':'Refresh saved experiments'}</Action>
    </div>
    {!run && <div className="empty-state" role="status" aria-live="polite">
      <span className="empty-state-icon" aria-hidden="true">{historyState==='loading'?<span className="button-spinner"/>:<Icon name="experiments"/>}</span>
      <div className="empty-state-copy"><h3>{historyState==='loading'?'Loading your experiments':historyState==='error'?'Experiment history unavailable':'Put your architecture to the test'}</h3>
        <p>{historyState==='loading'?'Retrieving saved runs and their results.':historyState==='error'?'Reconnect to the API, then refresh the saved experiments above.':'Choose an experiment type and configuration, then start a run. Its measurements, recovery checks, and evidence will appear here.'}</p>
      </div>
    </div>}
    {history.length>0&&<div className="run-picker"><label htmlFor="saved-run">Saved experiments</label>
      <select id="saved-run" disabled={busy||historyState==='loading'||!terminal(run)} value={run?.experiment_id??''} onChange={e=>{
        setError(''); setEvents([]); setRun(history.find(row=>row.experiment_id===e.target.value)??null);
        rememberRunInUrl('experiment',e.target.value);
      }}>
        {history.map(row=><option key={row.experiment_id} value={row.experiment_id}>
          {row.request.mode.endsWith('_faults')?(row.request.fault_fixture==='unsafe_retry'?'Unsafe retry':'Fault verification'):row.measurement_kind==='measured'?row.request.workload_profile.replace('_',' '):'Smoke'} · {row.request.mode.startsWith('docker_')?'Docker':'Native'} · {row.status} · {row.experiment_id.slice(0,8)}
        </option>)}
      </select></div>}
    {run&&<div>
      <div className="run-card">
        <div className="section-title"><h3>{run.request.mode.endsWith('_faults')
          ? run.request.fault_fixture==='unsafe_retry'?'Unsafe payment fixture':'Fault verification'
          : run.measurement_kind==='measured'?'Performance comparison':'Checkout smoke check'}</h3><Status value={run.status}/></div>
        <p className="muted run-meta">{run.request.mode.startsWith('docker_')?'Docker':'Native'} · {run.request.workload_profile.replace('_',' ')} · {run.experiment_id}</p>
        <div className="progress-caption" role="status"><span>Attempts started</span><span>{run.attempts_used} / {plannedAttempts}</span></div>
        {plannedAttempts>0&&<progress aria-label="Experiment attempts started" value={run.attempts_used} max={plannedAttempts}/>}
        <p className="muted run-meta">Cleanup {run.cleanup_status.replaceAll('_',' ')}</p>
        {run.error&&<p role="alert">{run.error}</p>}
        <details><summary>Experiment events</summary><ol className="event-list">{events.map(event=><li key={event.sequence}>{event.message}</li>)}</ol></details>
      </div>
      {run.candidates.map(c=><div className="candidate-card" key={c.candidate_id}>
        <div className="section-title"><h3>{describeGenome(c.genome)}</h3>
          {c.summary?.gate&&c.summary.gate!=='not_checked'&&<Status value={c.summary.gate} label={`Feasibility gate ${c.summary.gate==='passed'?'passed':'rejected'}`}/>}
        </div>
        {c.summary&&<><p className="muted">Median (min–max) across {c.summary.repetitions} repetitions. Performance thresholds {c.summary.performance_constraints_met?'met':'exceeded'}.</p>
          <dl className="metrics-grid">{measures.map(([key,title])=>{
            const spread=c.summary?.spread[key];
            return spread&&<div key={key}><dt>{title}</dt><dd>{formatMetric(spread.median,key)}<span className="metric-range">{formatMetric(spread.min,key)}–{formatMetric(spread.max,key)}</span></dd></div>;
          })}</dl></>}
        {c.evaluations.map(e=><details key={e.evaluation_id}><summary>Repetition {e.repetition+1}<Status value={e.status}/>{e.gate&&e.gate!=='not_checked'&&<Status value={e.gate} label={`Gate ${e.gate}`}/>}</summary>
          {e.gate_reasons?.map(reason=><p key={reason}>{reason.replaceAll('_',' ')}</p>)}
          {e.violations?.map((violation,index)=><p className="invariant" key={index}><strong>{violation.invariant_id}</strong> · {violation.detail}{violation.key?` (${violation.key})`:''}</p>)}
          {e.recovery && e.recovery.length>0 && <dl>{e.recovery.map(row=><div key={row.scenario}>
            <dt>{row.scenario.replaceAll('_',' ')}</dt><dd>{row.recovery_s===null?'Recovery not observed':`${row.recovery_s.toFixed(2)} s recovery`}</dd>
          </div>)}</dl>}
          <EvidenceLinks experimentId={run.experiment_id} evaluationId={e.evaluation_id} artifacts={e.artifacts}/>
        </details>)}
        <div className="shop-actions"><Action variant="quiet" icon="refresh" disabled={locked} onClick={()=>rerun(c.candidate_id)}>Rerun this configuration</Action></div>
      </div>)}</div>}
    </div></div>
  </section>;
}
