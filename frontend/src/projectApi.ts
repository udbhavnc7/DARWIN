// Typed API client for Real Project Mode.
//
// Every numeric value comes from the backend record. This module never invents
// an estimate, a winner or a pass count.

export type ProjectFact = {label: string; value: string; evidence: string[]};
export type UnsupportedCapability = {capability: string; reason: string};
export type Guess = {label: string; guess: string; confidence: string};
export type AdapterMode = {id: 'quick' | 'full'; label: string; description: string; estimated_seconds?: number};

export type ProjectNote = {
  what_it_is: string;
  backend: string;
  how_it_works: string;
  evolution: string;
  readme_used?: boolean;
};

export type BackendService = {
  name: string;
  path: string;
  language: string;
  framework: string;
  kind: string;
  entry_points: string[];
  evidence: string[];
  route_count?: number;
  node_id?: string;
};

export type BackendRoute = {
  method: string;
  path: string;
  file: string;
  line: number;
  service_path: string;
  snippet: string;
};

export type BackendSignal = {name: string; evidence: string[]; role?: string; node_id?: string};

export type BackendProfile = {
  detected: boolean;
  services: BackendService[];
  routes: BackendRoute[];
  route_count: number;
  datastores: BackendSignal[];
  queues: BackendSignal[];
  auth: BackendSignal[];
  external_services: BackendSignal[];
  deployment: {name: string; evidence: string}[];
  tests: {frameworks: string[]; file_count: number; evidence: string[]};
  models: {name: string; framework: string; file: string; line: number}[];
  model_count: number;
  migrations: string[];
  background_jobs: BackendSignal[];
  gateway: string;
  confidence: string;
  evidence: string[];
  languages?: {language: string; files: number; evidence: string}[];
  primary_language?: string;
  frontend_detected?: boolean;
  frontend_evidence?: string[];
};

export type ArchitectureNode = {
  id: string;
  label: string;
  kind: string;
  detail: string;
  evidence: string[];
};

export type ArchitectureEdge = {source: string; target: string; label: string};

export type Architecture = {
  nodes: ArchitectureNode[];
  edges: ArchitectureEdge[];
  flow: string[];
  summary: string;
};

export type Hotspot = {
  id: string;
  title: string;
  detail: string;
  severity: string;
  confidence: string;
  evidence: {file: string; line?: number; snippet: string}[];
  recommendation: string;
  control: string;
};

export type ScreeningSupport = {
  available: boolean;
  reason?: string;
  adapter_id?: string;
  adapter_version?: string;
  display_name?: string;
  evaluation_type?: string;
  summary?: string;
  change_summary?: string;
  mechanism?: string;
  scope_note?: string;
  correctness_rules?: string[];
  controls: string[];
  modes?: AdapterMode[];
  execution_note?: string;
  evidence?: string[];
};

export type ScreeningChange = {
  control: string;
  label: string;
  from: unknown;
  to: unknown;
  unit: string;
};

export type ScreeningMetrics = {
  p50_ms: number;
  p95_ms: number;
  throughput_rps: number;
  error_rate_pct: number;
  cost_index: number;
  utilization: number;
  db_wait_ms: number;
};

export type ScreeningRun = ScreeningMetrics & {seed: number};

export type ScreeningVariant = {
  id: string;
  label: string;
  controls: Record<string, unknown>;
  changes: ScreeningChange[];
  metrics: ScreeningMetrics;
  runs: ScreeningRun[];
  change_pct: number;
  error_delta_pct: number;
  cost_multiplier: number;
  qualifies: boolean;
  score: number;
};

export type ScreeningRecommendation = {
  status: 'IMPROVEMENT_CANDIDATE' | 'BASELINE_RETAINED' | 'INCONCLUSIVE';
  label: string;
  summary: string;
  candidate_id: string;
  controls: Record<string, unknown>;
  changes: ScreeningChange[];
  modelled_change_pct: number;
  baseline_p95_ms?: number;
  candidate_p95_ms?: number;
  error_rate_pct?: number;
  cost_multiplier?: number;
  measured: false;
  evidence_kind: 'simulated';
  seed_sensitivity?: {seeds: number[]; min_change_pct: number; max_change_pct: number};
  mode?: 'quick' | 'full';
};

export type ScreeningResult = {
  adapter_id: string;
  adapter_version: string;
  model_version: string;
  evaluation_type: 'architecture_screening';
  evidence_kind: 'simulated';
  label: 'SIMULATED';
  not_measured: true;
  mode: 'quick' | 'full';
  seeds: number[];
  workload: {
    name: string;
    arrival_rate_rps: number;
    burst_factor: number;
    routes: number;
    read_routes: number;
    read_ratio: number;
    write_ratio: number;
    external_integrations: number;
    datastores: number;
    queues: number;
    auth: boolean;
    services: number;
    note: string;
  };
  controls: string[];
  baseline: {
    label: string;
    controls: Record<string, unknown>;
    metrics: ScreeningMetrics;
    runs: ScreeningRun[];
  };
  variants: ScreeningVariant[];
  recommendation: ScreeningRecommendation;
  verdict: Verdict;
  policy: {
    minimum_improvement_pct?: number;
    regression_limit_pct?: number;
    maximum_error_rate_pct?: number;
    maximum_error_delta_pct?: number;
    maximum_cost_multiplier?: number;
    primary_metric?: string;
    evidence_kind?: string;
    label?: string;
    not_measured?: boolean;
  };
  assumptions: string[];
  limitations: string[];
  hotspots_addressed: {hotspot: string; title: string; control: string; addressed: boolean}[];
};


export type SupportedEvaluation = {
  adapter_id: string;
  adapter_version: string;
  display_name: string;
  evaluation_type: string;
  summary: string;
  change_summary: string;
  mechanism: string;
  correctness_rules: string[];
  scope_note: string;
  modes: AdapterMode[];
  execution_allowed: boolean;
  execution_note: string;
  evidence: string[];
  ready?: boolean;
  prerequisite?: string;
  capabilities?: {
    inspect?: boolean;
    deploy?: boolean;
    dimensions?: string[];
    faults?: string[];
    metrics?: string[];
    invariants?: string[];
    search?: string;
    limits?: string[];
  };
  challenges?: string[];
};

export type ArchitectureMetrics = {
  p50_ms?: number;
  p95_ms?: number;
  p99_ms?: number;
  requests_per_s?: number;
  error_rate?: number;
  cpu_seconds?: number;
  memory_peak_mb?: number;
  sample_count?: number;
};

export type ArchitectureMetricRow = {
  candidate_id: string;
  label: string;
  p95_ms?: number | null;
  requests_per_s?: number | null;
  error_rate?: number | null;
  cpu_seconds?: number | null;
  memory_peak_mb?: number | null;
  recovery_s?: number | null;
  replicas?: number;
  workers?: number;
};

export type ArchitectureRepetition = {
  repetition: number;
  metrics: {
    p50_ms: number; p95_ms: number; p99_ms: number; requests_per_s: number;
    error_rate: number; cpu_seconds?: number; memory_peak_mb?: number;
    sample_count?: number;
  };
  recovery_s?: number | null;
  ready_s?: number | null;
};

export type ArchitectureRun = ArchitectureMetricRow & {
  description?: string;
  baseline?: boolean;
  metrics?: ArchitectureMetrics;
  compose_sha256?: string;
  repetitions?: ArchitectureRepetition[];
  recovery_detail?: {
    recovery_s?: number; restart_command_s?: number; probes?: number;
    failed_probes?: number; observed_outage?: boolean; note?: string;
  } | null;
  resources?: {
    measured?: boolean;
    source?: string;
    memory_basis?: string;
    containers?: {name: string; cpu_us?: number; memory_bytes?: number}[];
  } | null;
  cleanup_status?: string;
};

export type ArchitectureMeasurement = {
  challenge?: string;
  runs: ArchitectureRun[];
  pareto?: {candidate_id: string; objectives: number[]}[];
  comparison?: {
    baseline?: ArchitectureRun | null;
    candidates?: ArchitectureRun[];
    challenge?: string;
    complete?: boolean;
    skipped?: {candidate_id: string; reason: string}[];
    repetitions?: number;
    wall_clock_s?: number;
  };
  environment?: {
    isolation?: string;
    platform?: string;
    repository_compose_used?: boolean;
    load_window_s?: number;
    load_rate_per_s?: number;
  };
  complete?: boolean;
  skipped?: {candidate_id: string; reason: string}[];
  repetitions_requested?: number;
};

export type CandidatePreview = {
  eligible: boolean;
  reason?: string;
  support_level?: string;
  prerequisites?: string[];
  adapter_id?: string;
  adapter_version?: string;
  capabilities?: SupportedEvaluation['capabilities'];
  challenges?: string[];
  unsupported?: string[];
  candidates: {
    candidate_id: string;
    label: string;
    description: string;
    dimension: {replicas: number; workers: number};
    challenges: string[];
  }[];
};

export type Source = {
  url: string;
  owner: string;
  repo: string;
  requested_ref: string;
  commit_sha: string;
  short_sha: string;
  trusted: boolean;
  cache_key: string;
  file_count: number;
  size_bytes: number;
  metadata?: {size?: number; default_branch?: string; language?: string; license?: unknown; pushed_at?: string};
};

export type Inspection = {
  inspection_id: string;
  created_at: string;
  status: string;
  source: Source;
  project: {
    type: string;
    display_type: string;
    summary: string;
    note?: ProjectNote;
    application_host: string;
    persistence: string;
    is_server_backend: boolean;
    languages: string[];
    backend?: BackendProfile;
    adapter_checks: Record<string, boolean>;
  };
  architecture?: Architecture;
  facts: ProjectFact[];
  not_supported: UnsupportedCapability[];
  supported_evaluations: SupportedEvaluation[];
  hotspots?: Hotspot[];
  screening?: ScreeningSupport;
  guesses: Guess[];
  readiness: {
    node_available: boolean;
    node_version: string | null;
    source_paths_present: boolean;
    adapter_approved: boolean;
    container_runner_available?: boolean | null;
    source_tests_available: boolean;
  };
  warnings: string[];
  execution_allowed: boolean;
  support_level?: 'READY_FOR_MEASURED_EVOLUTION' | 'EVALUABLE_WITH_SETUP' | 'INSPECTABLE';
  prerequisites?: string[];
  evaluation_status: string;
  policy: Record<string, string>;
};

export type Measurement = {
  size: number;
  seeds: number[];
  baseline_median_ms: number;
  candidate_median_ms: number;
  baseline_p95_ms: number;
  candidate_p95_ms: number;
  baseline_range_ms: [number, number];
  candidate_range_ms: [number, number];
  change_pct: number;
  paired_win_rate: number;
  paired_lower_decile_pct: number;
  samples: number;
};

export type VerdictStatus =
  | 'VERIFIED_IMPROVEMENT'
  | 'BASELINE_RETAINED'
  | 'INCONCLUSIVE'
  | 'REJECTED_INCORRECT'
  | 'NO_FEASIBLE_CANDIDATE'
  | 'UNSUPPORTED_PROJECT'
  | 'NOT_MEASURED'
  | 'INTERRUPTED'
  | 'FAILED_INFRASTRUCTURE';

export type Verdict = {
  status: VerdictStatus;
  label: string;
  reason: string;
  policy: {
    evidence_kind?: string;
    label?: string;
    not_measured?: boolean;
    minimum_improvement_pct?: number;
    regression_limit_pct?: number;
    minimum_paired_win_rate?: number;
    maximum_error_rate_pct?: number;
    maximum_error_rate?: number;
    maximum_error_delta_pct?: number;
    maximum_cost_multiplier?: number;
    primary_rule?: string;
    primary_metric?: string;
    simulation_cannot_win?: boolean;
    challenge?: string;
  };
  per_size: Measurement[];
  primary_size?: number;
  baseline_median_ms?: number;
  candidate_median_ms?: number;
  change_pct?: number;
  winner_id?: string | null;
  baseline_id?: string | null;
  baseline_metrics?: ArchitectureMetrics | null;
  comparison?: ArchitectureMetricRow[];
  baseline_p95_ms?: number;
  candidate_p95_ms?: number;
  baseline_rps?: number;
  candidate_rps?: number;
  baseline_recovery_s?: number;
  candidate_recovery_s?: number;
  regressions?: {metric: string; label: string; baseline: number; candidate: number; change_pct: number}[];
  recovery_notes?: string[];
  explanation?: string;
  correctness: {
    passed: boolean;
    checks_passed: number;
    checks_total: number;
    failures: {name: string; passed: boolean; detail?: string}[];
    note?: string;
  };
  recommendation?: ScreeningRecommendation;
};

export type Check = {name: string; passed: boolean; detail?: string};

export type SourceTest = {
  status: 'passed' | 'failed' | 'skipped' | 'not_run';
  reason?: string;
  command?: string[];
  duration_s?: number;
  exit_code?: number;
  tests_passed?: number;
  tests_failed?: number;
  tests_skipped?: number;
  tests_total?: number;
  output_tail?: string;
  suite?: string;
};

export type EvidenceFile = {name: string; sha256: string; bytes: number};

export type Evaluation = {
  evaluation_id: string;
  inspection_id: string;
  created_at: string;
  requested_at: string;
  started_at?: string;
  finished_at?: string;
  duration_s?: number;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  stage: string;
  progress: {stage: string; completed: number; total: number; label: string; percent: number};
  evidence_kind: string;
  adapter_id: string;
  adapter_version: string;
  evaluation_type: string;
  mode: 'quick' | 'full';
  source: Source;
  inspection: {
    project: Inspection['project'];
    architecture?: Architecture;
    facts: ProjectFact[];
    not_supported: UnsupportedCapability[];
    hotspots?: Hotspot[];
    screening?: ScreeningSupport;
    guesses: Guess[];
    readiness: Inspection['readiness'];
    warnings: string[];
    policy: Record<string, string>;
  };
  candidate: null | {
    candidate_id: string;
    label: string;
    description: string;
    files: string[];
    wiring: {call_site?: string; checks?: Check[]};
    diff_sha256: string;
  };
  workload: {
    preset: string;
    challenge?: string;
    seeds: number[];
    sizes: number[];
    repetitions: number;
    warmups: number;
    include_source_tests: boolean;
    fixtures: {id: string; seed: number; size: number; currency: string; timed: boolean; file: string}[];
    note?: string;
  };
  correctness: null | {
    passed: boolean;
    checks_passed: number;
    checks_total: number;
    failures: Check[];
    checks: Check[];
  };
  measurements: Measurement[];
  environment: null | {
    node_version?: string;
    platform?: string;
    arch?: string;
    cpu_model?: string;
    total_memory_bytes?: number;
    heap_limit_bytes?: number;
    forced_gc?: boolean;
  };
  source_tests: SourceTest | null;
  screening?: ScreeningResult | null;
  recommendation?: ScreeningRecommendation | null;
  architecture?: ArchitectureMeasurement | null;
  verdict: Verdict | null;
  error: string | null;
  cleanup_status: string;
  evidence: {dir: string; files: EvidenceFile[]; manifest_sha256?: string};
};

export type ProjectEvent = {
  evaluation_id: string;
  sequence: number;
  occurred_at: string;
  type: string;
  status: string;
  stage: string;
  message: string;
};

export type Catalog = {
  schema_version: number;
  examples: {
    id: string;
    name: string;
    subtitle: string;
    repository_url: string;
    default_ref: string;
    pinned_commit: string;
    summary: string;
    evaluation_type: string;
    adapter: {
      adapter_id: string;
      adapter_version: string;
      display_name: string;
      change_summary: string;
      mechanism: string;
      correctness_rules: string[];
      scope_note: string;
      modes: AdapterMode[];
    };
  }[];
  policy: Record<string, string>;
  screening?: {
    adapter_id: string;
    adapter_version: string;
    display_name: string;
    evaluation_type: string;
    evidence_kind: string;
    label: string;
    scope_note: string;
  };
  presets: Record<'quick' | 'full', {
    seeds: number[];
    sizes: number[];
    repetitions: number;
    warmups: number;
    include_source_tests: boolean;
  }>;
};

async function readError(response: Response): Promise<string> {
  try {
    const value = await response.json();
    if (typeof value?.detail === 'string') return value.detail;
    if (value?.detail) return JSON.stringify(value.detail);
  } catch { /* Fall through to the status text. */ }
  return response.statusText || `HTTP ${response.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw Error(await readError(response));
  return response.json() as Promise<T>;
}

export const api = {
  catalog: () => request<Catalog>('/api/repositories/catalog'),
  inspections: () => request<Inspection[]>('/api/repositories/inspections'),
  inspection: (id: string) => request<Inspection>(`/api/repositories/inspections/${encodeURIComponent(id)}`),
  inspect: (url: string, ref: string, consent: boolean) => request<Inspection>('/api/repositories/inspect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url, ref, consent}),
  }),
  evaluations: () => request<Evaluation[]>('/api/project-evaluations'),
  evaluation: (id: string) => request<Evaluation>(`/api/project-evaluations/${encodeURIComponent(id)}`),
  candidates: (inspectionId: string) =>
    request<CandidatePreview>(`/api/repositories/inspections/${encodeURIComponent(inspectionId)}/candidates`),
  start: (inspectionId: string, mode: 'quick' | 'full', includeSourceTests?: boolean,
          adapterId?: string, challenge: string = 'faster') =>
    request<Evaluation>('/api/project-evaluations', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        inspection_id: inspectionId, adapter_id: adapterId, mode,
        include_source_tests: includeSourceTests, challenge,
      }),
    }),
  cancel: (id: string) => request<Evaluation>(`/api/project-evaluations/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
  }),
  events: (id: string, after = 0) =>
    request<ProjectEvent[]>(`/api/project-evaluations/${encodeURIComponent(id)}/events?after=${after}`),
  diff: async (id: string) => {
    const response = await fetch(`/api/project-evaluations/${encodeURIComponent(id)}/diff`);
    if (!response.ok) throw Error(await readError(response));
    return response.text();
  },
  change: async (id: string) => {
    const response = await fetch(`/api/project-evaluations/${encodeURIComponent(id)}/change`);
    if (!response.ok) throw Error(await readError(response));
    return response.text();
  },
};

export const diffUrl = (id: string) => `/api/project-evaluations/${encodeURIComponent(id)}/diff`;
export const changeUrl = (id: string) => `/api/project-evaluations/${encodeURIComponent(id)}/change`;
export const bundleUrl = (id: string) => `/api/project-evaluations/${encodeURIComponent(id)}/bundle`;
export const artifactUrl = (id: string, name: string) =>
  `/api/project-evaluations/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(name)}`;

const terminal = new Set(['completed', 'failed', 'cancelled']);
export const isTerminal = (evaluation: Evaluation | null) => Boolean(evaluation && terminal.has(evaluation.status));
export const isRunning = (evaluation: Evaluation | null) =>
  Boolean(evaluation && (evaluation.status === 'queued' || evaluation.status === 'running'));

export function tone(status?: VerdictStatus | Evaluation['status'] | null): 'good' | 'bad' | 'warn' | 'active' | 'muted' {
  if (!status) return 'muted';
  if (status === 'VERIFIED_IMPROVEMENT' || status === 'completed') return 'good';
  if (status === 'REJECTED_INCORRECT' || status === 'FAILED_INFRASTRUCTURE' || status === 'failed') return 'bad';
  if (status === 'BASELINE_RETAINED' || status === 'INCONCLUSIVE' || status === 'NOT_MEASURED'
    || status === 'INTERRUPTED' || status === 'cancelled') return 'warn';
  return 'active';
}

export function formatMs(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value < 1) return `${(value * 1000).toFixed(0)} µs`;
  if (value < 100) return `${value.toFixed(2)} ms`;
  return `${value.toFixed(1)} ms`;
}

export function formatRows(value?: number | null): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString();
}

export function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function formatDuration(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value < 60) return `${value.toFixed(1)} s`;
  const minutes = Math.floor(value / 60);
  return `${minutes} min ${Math.round(value - minutes * 60)} s`;
}

export function formatBytes(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function changeLabel(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value === 0) return '0.0%';
  return `${value > 0 ? '−' : '+'}${Math.abs(value).toFixed(1)}%`;
}

const controlNames: Record<string, string> = {
  replicas: 'Service replicas',
  cache_ttl_s: 'Cache TTL',
  offload_jobs: 'Background offload',
  retry_policy: 'Retry policy',
  db_pool: 'Database pool',
  read_replicas: 'Read replicas',
  rate_limit: 'Rate limit',
};

export function controlLabel(control: string): string {
  return controlNames[control] ?? control.replaceAll('_', ' ');
}

export function stageLabel(stage?: string): string {
  return {
    queued: 'Queued',
    preparing: 'Preparing pinned source',
    simulating: 'Simulating architecture variants',
    evaluating: 'Applying the screening policy',
    checking_correctness: 'Checking correctness',
    measuring: 'Measuring report time',
    verdict: 'Deriving verdict',
    done: 'Complete',
    failed: 'Stopped',
    cancelled: 'Cancelled',
    no_candidate: 'No candidate',
  }[stage ?? ''] ?? 'Waiting';
}

export const stageOrder = ['queued', 'preparing', 'simulating', 'evaluating', 'checking_correctness', 'measuring', 'verdict', 'done'] as const;

export function stageState(current: string, stage: string): 'done' | 'current' | 'pending' {
  const currentIndex = stageOrder.indexOf(current as typeof stageOrder[number]);
  const index = stageOrder.indexOf(stage as typeof stageOrder[number]);
  if (current === 'failed' || current === 'cancelled' || current === 'no_candidate') {
    return stage === 'queued' ? 'done' : 'pending';
  }
  if (index < currentIndex) return 'done';
  if (index === currentIndex) return 'current';
  return 'pending';
}
