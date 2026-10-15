import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
export default defineConfig({
  plugins: [svelte()],
  resolve: { conditions: ['browser'] },
  build: { outDir: '../src/plumb/browser/static', emptyOutDir: true, assetsInlineLimit: 0 },
  server: { proxy: { '/api': { target: process.env.PLUMB_API ?? 'http://127.0.0.1:8765', changeOrigin: true, configure(proxy) { proxy.on('proxyReq', req => req.setHeader('Origin', process.env.PLUMB_API ?? 'http://127.0.0.1:8765')); } } } },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], include: ['src/**/*.test.ts'], restoreMocks: true },
});
