// SR-342 EX-1: a study room tab opened before a landing rebuilt the bundle asks for a mermaid
// chunk that is gone; the page reloads onto the new build (once per build) instead of leaving
// the diagram as its source.
import { describe, expect, it, vi } from 'vitest';
import { reloadOnStaleBuild } from '../lib/stale';

function fakeWindow() {
  const target = new EventTarget();
  const reload = vi.fn();
  const win = Object.assign(target, { sessionStorage, location: { reload } }) as unknown as Window;
  return { win, reload };
}

function chunkGone(win: Window) {
  const event = new Event('vite:preloadError', { cancelable: true });
  win.dispatchEvent(event);
  return event;
}

describe('a tab from before a rebuild (SR-342 EX-1)', () => {
  it('reloads onto the new build when a lazy chunk is gone', () => {
    const { win, reload } = fakeWindow();
    reloadOnStaleBuild(win, '/assets/index-old.js');
    const event = chunkGone(win);
    expect(reload).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  it('does not reload in a loop when the fresh build itself misses a chunk', () => {
    const { win, reload } = fakeWindow();
    reloadOnStaleBuild(win, '/assets/index-new.js');
    chunkGone(win);
    const again = fakeWindow();   // the page after the reload, same build
    reloadOnStaleBuild(again.win, '/assets/index-new.js');
    const event = chunkGone(again.win);
    expect(reload).toHaveBeenCalledOnce();
    expect(again.reload).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false); // the error goes on: the diagram keeps its note
  });

  it('reloads again after a later landing, from the newer build', () => {
    const { win, reload } = fakeWindow();
    reloadOnStaleBuild(win, '/assets/index-a.js');
    chunkGone(win);
    const later = fakeWindow();
    reloadOnStaleBuild(later.win, '/assets/index-b.js');
    chunkGone(later.win);
    expect(reload).toHaveBeenCalledOnce();
    expect(later.reload).toHaveBeenCalledOnce();
  });
});
