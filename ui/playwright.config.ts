import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// The real Python server on isolated data; see tests/e2e/server.py.
const python = process.env.IASO_PYTHON ?? 'python';
// The bundle copy a test rebuilds under an open tab (tests/e2e/studies.spec.ts); workers inherit it.
process.env.IASO_E2E_SWAP ??= join(tmpdir(), 'iaso-e2e-swap');
export default defineConfig({
  testDir: 'tests/e2e',
  outputDir: 'test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  // A loaded machine takes 20 s to open a page and seconds to draw: the defaults (30 s, 5 s) timed out.
  timeout: 60000,
  expect: { timeout: 10000 },
  use: { baseURL: 'http://127.0.0.1:8765', trace: 'retain-on-failure' },
  webServer: {
    command: `"${python}" tests/e2e/server.py`,
    url: 'http://127.0.0.1:8765/',
    reuseExistingServer: false,
    env: { PYTHONPATH: fileURLToPath(new URL('../src', import.meta.url)), IASO_E2E_SWAP: process.env.IASO_E2E_SWAP },
    timeout: 30000,
  },
});
