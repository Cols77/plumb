import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/svelte';
import { afterEach, beforeEach, vi } from 'vitest';
beforeEach(() => { sessionStorage.clear(); localStorage.clear(); history.replaceState({}, '', '/#token=test-token'); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
