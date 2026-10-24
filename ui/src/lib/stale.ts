// A landing rebuilds the bundle under a running room and removes the old hashed chunks; a tab
// opened before it then fails to load mermaid (or any lazy chunk) and shows a diagram's source
// (SR-342). Vite reports that as `vite:preloadError`: reload once onto the new build. `build` is
// the running entry's URL, so a build whose own chunk is missing is not reloaded in a loop.
const KEY = 'plumb.reloaded-from';

export function reloadOnStaleBuild(win: Window, build: string): void {
  win.addEventListener('vite:preloadError', (event) => {
    try {
      if (win.sessionStorage.getItem(KEY) === build) return; // already reloaded from this build
      win.sessionStorage.setItem(KEY, build);
    } catch { return; } // no storage: no loop guard, so no reload; the diagram keeps its note
    event.preventDefault();
    win.location.reload();
  });
}
