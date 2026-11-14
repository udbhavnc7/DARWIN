export function rememberRunInUrl(kind: 'experiment' | 'search', id: string) {
  const url = new URL(window.location.href);
  url.searchParams.set(kind, id);
  window.history.replaceState(null, '', url);
}
