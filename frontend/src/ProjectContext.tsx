import {createContext, useContext, useEffect, useRef, useState, type ReactNode} from 'react';
import {api, isRunning, type CandidatePreview, type Evaluation, type Inspection, type ProjectEvent} from './projectApi';
import {isLive, showcase} from './showcase';

type Workspace = {
  inspection: Inspection | null;
  evaluation: Evaluation | null;
  preview: CandidatePreview | null;
  events: ProjectEvent[];
  loading: boolean;
  error: string;
  selectInspection: (value: Inspection) => void;
  selectEvaluation: (value: Evaluation) => Promise<void>;
  setEvaluation: (value: Evaluation | null) => void;
  setError: (value: string) => void;
  clear: () => void;
};
const Context = createContext<Workspace | null>(null);
const storageKey = () => `darwin-project-v1-${showcase && !isLive() ? 'recorded' : 'local'}`;

export function ProjectProvider({children}: {children: ReactNode}) {
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [evaluation, setEvaluationState] = useState<Evaluation | null>(null);
  const [preview, setPreview] = useState<CandidatePreview | null>(null);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const version = useRef(0);

  function remember(inspectionId: string, evaluationId?: string) {
    try {localStorage.setItem(storageKey(), JSON.stringify({inspectionId, evaluationId}));} catch { /* Optional persistence. */ }
  }

  function clear() {
    version.current++;
    setInspection(null); setEvaluationState(null); setPreview(null); setEvents([]); setError(''); setLoading(false);
    try {localStorage.removeItem(storageKey());} catch { /* Optional persistence. */ }
  }

  function selectInspection(value: Inspection) {
    version.current++;
    setInspection(value); setEvaluationState(null); setEvents([]); setPreview(null); setError(''); setLoading(false);
    remember(value.inspection_id);
  }

  function setEvaluation(value: Evaluation | null) {
    setEvaluationState(value);
    if (value) remember(value.inspection_id, value.evaluation_id);
  }

  async function selectEvaluation(value: Evaluation) {
    const request = ++version.current;
    // Clear the previous source immediately: a slow request must never mix projects.
    setInspection(null); setPreview(null); setEvents([]); setEvaluationState(value); setError(''); setLoading(true);
    remember(value.inspection_id, value.evaluation_id);
    try {
      const record = await api.inspection(value.inspection_id);
      if (request !== version.current) return;
      if (record.source.commit_sha !== value.source.commit_sha) throw Error('The inspection and evaluation commits do not match.');
      setInspection(record);
    } catch (reason) {
      if (request === version.current) setError(`Source inspection unavailable. The saved run still retains its provenance. ${reason instanceof Error ? reason.message : ''}`);
    } finally {if (request === version.current) setLoading(false);}
  }

  useEffect(() => {
    const request = version.current;
    async function restore() {
      try {
        const saved = JSON.parse(localStorage.getItem(storageKey()) ?? 'null');
        if (saved?.evaluationId) {
          const record = await api.evaluation(saved.evaluationId);
          if (request === version.current) await selectEvaluation(record);
        } else if (saved?.inspectionId) {
          const record = await api.inspection(saved.inspectionId);
          if (request === version.current) selectInspection(record);
        }
      } catch {if (request === version.current) {clear(); setError('The saved selection is unavailable. Choose a project to continue.');}}
      finally {if (request === version.current) setLoading(false);}
    }
    void restore();
  }, []);

  useEffect(() => {
    setPreview(null);
    if (!inspection) return;
    let stopped = false;
    void api.candidates(inspection.inspection_id).then(value => {if (!stopped) setPreview(value);})
      .catch(() => {if (!stopped) setPreview(null);});
    return () => {stopped = true;};
  }, [inspection?.inspection_id]);

  useEffect(() => {
    if (!evaluation) return;
    let stopped = false;
    let timer: number | undefined;
    const id = evaluation.evaluation_id;
    async function poll() {
      try {
        const [next, history] = await Promise.all([api.evaluation(id), api.events(id)]);
        if (stopped) return;
        setEvaluationState(next); setEvents(history); setError('');
        remember(next.inspection_id, next.evaluation_id);
        if (isRunning(next)) timer = window.setTimeout(poll, 1000);
      } catch {
        if (!stopped) {
          setError('Could not refresh this run. Its last recorded state is shown.');
          if (isRunning(evaluation)) timer = window.setTimeout(poll, 3000);
        }
      }
    }
    void poll();
    return () => {stopped = true; window.clearTimeout(timer);};
  }, [evaluation?.evaluation_id]);

  return <Context.Provider value={{
    inspection, evaluation, preview, events, loading, error,
    selectInspection, selectEvaluation, setEvaluation, setError, clear,
  }}>{children}</Context.Provider>;
}

export function useProjectWorkspace() {
  const context = useContext(Context);
  if (!context) throw Error('ProjectProvider is required');
  return context;
}

export function ProjectIdentity() {
  const {inspection, evaluation, loading, error} = useProjectWorkspace();
  const source = evaluation?.source ?? inspection?.source;
  if (!source) return error ? <p className="notice" role="alert">{error}</p> : null;
  const adapter = evaluation?.adapter_id ?? inspection?.supported_evaluations[0]?.adapter_id
    ?? inspection?.screening?.adapter_id ?? 'Inspection only';
  return <aside className="project-identity" aria-label="Selected project" data-inspection={evaluation?.inspection_id ?? inspection?.inspection_id}
    data-commit={source.commit_sha} data-evaluation={evaluation?.evaluation_id ?? ''}>
    <div><strong>{source.owner}/{source.repo}</strong><span><code title={source.commit_sha}>{source.short_sha}</code> · {adapter}</span></div>
    <div><span>{evaluation ? `Run ${evaluation.evaluation_id.slice(0, 8)}` : 'No evaluation yet'}{loading ? ' · Loading…' : ''}</span>
      <a href="#project">Project workspace</a></div>
    {error && <p className="notice" role="alert">{error}</p>}
  </aside>;
}
