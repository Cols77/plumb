import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import App from '../App.svelte';

// SR-380 EX-5: the room shows the studies and the understanding page, and no card.
describe('The study room', () => {
  it('shows the studies and no question card or press', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      if (input === '/api/workspace') return Response.json({project: {name: 'Test project', root: '/test'}});
      if (input === '/api/studies') return Response.json({studies: [], understanding: {text: '', knows: [], needs: []}});
      throw Error('Unexpected route ' + input);
    }));
    render(App);
    expect(await screen.findByText('Test project')).toBeInTheDocument();
    expect(await screen.findByRole('navigation', {name: 'Studies'})).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Leave open'})).toBeNull();
    expect(screen.queryByText('Issues')).toBeNull();
    const calls = (fetch as unknown as {mock: {calls: string[][]}}).mock.calls.map(c => c[0]);
    expect(calls.some(url => url.includes('/draw') || url.includes('/press'))).toBe(false);
  });
});
