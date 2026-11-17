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

  // React and the graph renderer rarely change; keep them cacheable across
  // deploys. The calibration scene is a lazy 534 kB chunk of its own, so the
  // threshold sits above it while still catching an oversized entry bundle.
  const build = {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-dom/client'],
          flow: ['@xyflow/react'],
        },
      },
    },
  };

  // The showcase is published as a GitHub Pages project site and never talks to a backend.
  if (mode === 'showcase') return {base: '/DARWIN/', preview: {port: 4173, strictPort: true}, build};

  return {
    server: {port: 5173, strictPort: true, proxy},
    preview: {proxy},
    build,
  };
});
