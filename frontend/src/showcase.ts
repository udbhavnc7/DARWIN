// Hosted showcase mode (`vite build --mode showcase`).
//
// The public showcase has no backend. A fetch shim answers the dashboard's read requests
// from snapshots captured by scripts/capture_showcase.py against a real local stack, and
// refuses everything that would need the engine. Nothing recorded is presented as live.

export const showcase = import.meta.env.VITE_SHOWCASE === '1';
export const setupUrl = 'https://github.com/udbhavnc7/DARWIN#quickstart';
export const localOnly = 'Needs a local install. Follow the README quickstart to run this yourself.';

export type Manifest = {captured_at: string; commit: string; experiments: number; searches: number};
type Genome = {app_replicas: number; catalog_cache_ttl_s: number; notification_mode: string; retry_policy: string};
type Keyed = {experiment_id?: string; search_id?: string};

const root = `${import.meta.env.BASE_URL}showcase/`;
const cache = new Map<string, Promise<unknown>>();
let nativeFetch: typeof fetch = (...args) => fetch(...args);

function load<T>(file: string): Promise<T> {
  if (!cache.has(file)) {
    cache.set(file, nativeFetch(root + file).then(response => {
      if (!response.ok) throw Error(`Missing showcase snapshot ${file}`);
      return response.json();
    }).catch(reason => {cache.delete(file); throw reason;}));
  }
  return cache.get(file) as Promise<T>;
}

export const manifest = () => load<Manifest>('manifest.json');

const key = (genome: Genome) => `${genome.app_replicas}-${genome.catalog_cache_ttl_s}-${genome.notification_mode}-${genome.retry_policy}`;
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json'}});
const missing = (detail = 'Not part of the recorded showcase.') => json({detail}, 404);
const refused = () => json({detail: localOnly}, 503);

function body(init?: RequestInit): any {
  try {return typeof init?.body === 'string' ? JSON.parse(init.body) : null;} catch {return null;}
}

async function find(file: string, field: keyof Keyed, id: string) {
  const rows = await load<Keyed[]>(file);
  const row = rows.find(item => item[field] === id);
  return row ? json(row) : missing();
}

async function events(kind: 'experiment' | 'search', id: string) {
  try {return json(await load(`events/${kind}-${encodeURIComponent(id)}.json`));} catch {return json([]);}
}

async function answer(method: string, url: URL, init?: RequestInit): Promise<Response> {
  const path = url.pathname;
  let match: RegExpMatchArray | null;
  if (method === 'GET') {
    if (path === '/api/project') return json(await load('project.json'));
    if (path === '/api/preflight') return json(await load('preflight.json'));
    if (path === '/api/exhibition/scenarios') {
      return json(await load(`scenarios-${url.searchParams.get('runtime') === 'docker' ? 'docker' : 'native'}.json`));
    }
    if (path === '/api/experiments') return json(await load('experiments.json'));
    if ((match = path.match(/^\/api\/experiments\/([^/]+)\/events$/))) return events('experiment', decodeURIComponent(match[1]));
    if ((match = path.match(/^\/api\/experiments\/([^/]+)$/))) return find('experiments.json', 'experiment_id', decodeURIComponent(match[1]));
    if (path === '/api/searches') return json(await load('searches.json'));
    if ((match = path.match(/^\/api\/searches\/([^/]+)\/events$/))) return events('search', decodeURIComponent(match[1]));
    if ((match = path.match(/^\/api\/searches\/([^/]+)$/))) return find('searches.json', 'search_id', decodeURIComponent(match[1]));
    if (path === '/shop/catalog' || path === '/shop/ledger') {
      const shop = await load<{catalog: unknown; ledger: unknown}>('shop.json');
      const value = path === '/shop/catalog' ? shop.catalog : shop.ledger;
      return value ? json(value) : json({detail: 'The shop was not recorded.'}, 503);
    }
    return missing();
  }
  // Deterministic, side-effect-free reads that were captured for every configuration.
  const request = body(init);
  if (method === 'POST' && path === '/api/genomes/preview' && request) {
    const value = (await load<Record<string, unknown>>('previews.json'))[key(request)];
    return value ? json(value) : missing();
  }
  if (method === 'POST' && path === '/api/genomes/compose' && request) {
    const value = (await load<Record<string, string>>('compose.json'))[key(request)];
    return value ? new Response(value, {headers: {'Content-Type': 'application/yaml'}}) : missing();
  }
  if (method === 'POST' && path === '/api/simulate' && request?.genome && request.duration_s === 12) {
    const value = (await load<Record<string, unknown>>('simulations.json'))[`${key(request.genome)}|${request.workload_profile}`];
    return value ? json(value) : missing();
  }
  return refused();
}

export function installShowcase() {
  nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const href = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(href, location.origin);
    if (url.origin === location.origin && url.pathname === '/recorded-example.json') {
      return nativeFetch(`${import.meta.env.BASE_URL}recorded-example.json`, init);
    }
    if (url.origin !== location.origin || !/^\/(api|shop)\//.test(url.pathname)) return nativeFetch(input, init);
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    // A short, realistic delay keeps loading states visible without slowing browsing.
    await new Promise(resolve => setTimeout(resolve, 120));
    if (init?.signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
    return answer(method, url, init);
  };
}
