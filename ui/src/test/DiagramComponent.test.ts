import { render, screen, waitFor } from '@testing-library/svelte';
import { it, expect, vi } from 'vitest';
import Diagram from '../components/Diagram.svelte';
const svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><text x="2" y="10">Diagram</text></svg>';
const props={session:'s',card:'c',capability:'t',source:'a.svg',available:true};
it('reloads a changed diagram path and revokes the replaced image URL', async () => {
  const create=vi.fn().mockReturnValueOnce('blob:first').mockReturnValueOnce('blob:second'); const revoke=vi.fn();
  vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:revoke}));
  const fetcher=vi.fn(async () => Response.json({text:svg})); vi.stubGlobal('fetch',fetcher);
  const view=render(Diagram,{props}); await screen.findByRole('img');
  await view.rerender({...props,source:'b.svg'});
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByRole('img')).toHaveAttribute('src','blob:second'));
  expect(revoke).toHaveBeenCalledWith('blob:first');
  view.unmount(); expect(revoke).toHaveBeenCalledWith('blob:second');
});
it('shows unavailable fallback when a pending diagram disappears', async () => {
  vi.stubGlobal('fetch',vi.fn(() => new Promise(() => {})));
  const view=render(Diagram,{props}); await screen.findByText('Loading diagram…');
  await view.rerender({...props,available:false,problem:'Missing diagram file'});
  expect(await screen.findByText('Missing diagram file')).toBeInTheDocument();
  expect(screen.queryByText('Loading diagram…')).not.toBeInTheDocument();
});
