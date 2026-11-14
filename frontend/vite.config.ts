import { defineConfig } from 'vite';

const token = process.env.DARWIN_API_TOKEN;
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

export default defineConfig({
  server: {port: 5173, strictPort: true, proxy},
  preview: {proxy},
});
