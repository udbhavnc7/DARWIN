export type Genome = {
  app_replicas: number;
  catalog_cache_ttl_s: number;
  notification_mode: 'sync' | 'queued';
  retry_policy: 'none' | 'idempotent_only';
};

export const baseline: Genome = {
  app_replicas: 1, catalog_cache_ttl_s: 0, notification_mode: 'sync', retry_policy: 'idempotent_only',
};

export const cached: Genome = {
  ...baseline, app_replicas: 3, catalog_cache_ttl_s: 10, notification_mode: 'queued',
};

export function isBaseline(genome: Genome) {
  return Object.keys(baseline).every(key => genome[key as keyof Genome] === baseline[key as keyof Genome]);
}

export function describeGenome(genome: Genome) {
  const replicas = `${genome.app_replicas} API ${genome.app_replicas === 1 ? 'replica' : 'replicas'}`;
  const cache = genome.catalog_cache_ttl_s ? `${genome.catalog_cache_ttl_s}s cache` : 'cache off';
  const retries = genome.retry_policy === 'none' ? 'no retries' : 'idempotent retries';
  return `${replicas} · ${cache} · ${genome.notification_mode} notifications · ${retries}`;
}

export function readDraft(key: 'builder' | 'experiment'): Genome | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(`darwin-${key}-draft`) ?? 'null') as Genome | null;
    if (value && [1, 2, 3].includes(value.app_replicas) && [0, 10, 30].includes(value.catalog_cache_ttl_s)
        && ['sync', 'queued'].includes(value.notification_mode) && ['none', 'idempotent_only'].includes(value.retry_policy)) {
      return value;
    }
  } catch { /* A damaged or inaccessible draft can be recreated. */ }
  return null;
}

export function saveDraft(key: 'builder' | 'experiment', genome: Genome) {
  try {sessionStorage.setItem(`darwin-${key}-draft`, JSON.stringify(genome));} catch { /* Storage can be disabled. */ }
}
