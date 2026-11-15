import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({mode}) => {
  const token = loadEnv(mode, '.', '').DARWIN_API_TOKEN;
  const api = {
    target: 'http://127.0.0.1:8000',
    ...(token ? { headers: { authorization: `Bearer ${token}` } } : {}),
  };
  const ws = {
    target: 'ws://127.0.0.1:8000',
    ws: true,
    ...(token ? { headers: { authorization: `Bearer ${token}` } } : {}),
  };
  const proxy = {'/api': api, '/shop': 'http://127.0.0.1:8010', '/ws': ws};

  // The showcase is published as a GitHub Pages project site and never talks to a backend.
  if (mode === 'showcase') return {base: '/DARWIN/', preview: {port: 4173, strictPort: true}};

  return {
    server: {port: 5173, strictPort: true, proxy},
    preview: {proxy},
  };
});
