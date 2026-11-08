import { defineConfig } from 'vite';
const proxy = {'/api':'http://127.0.0.1:8000', '/shop':'http://127.0.0.1:8010'};
export default defineConfig({server:{port:5173,strictPort:true,proxy:{...proxy,'/ws':{target:'ws://127.0.0.1:8000',ws:true}}},preview:{proxy}});
