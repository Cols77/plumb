// What plumb's panel says to the owner (SP7 6.3: titles and plain words, never IDs, paths of
// plumb's own files, hashes or commands). The card texts themselves come from plumb.

export const GLYPHS: Record<string, string> = {
  aligned: '✓',
  'awaits you': '●',
  'something changed': '△',
  'a check fails': '✗',
  'two versions': '⇄',
}

export const T = {
  name: 'plumb',
  awaiting: (n: number) => (n === 1 ? '1 awaits you' : `${n} await you`),
  leftOpen: (n: number) => `${n} left open`,
  nothingAwaits: 'nothing awaits you',
  hide: 'Hide',
  show: 'Show',
  showAll: 'Show all',
  showFewer: 'Show fewer',
  openPane: 'Open in a pane',
  paneTitle: 'plumb: what awaits you',
  recommended: ' (recommended)',
  assumed: 'Assumed: ',
  wont: 'Not doing: ',
  diagramLine: (path: string) => `Diagram: ${path} (open it to see it)`,
  pressFailed: "plumb could not record that press; nothing changed. Try again, or answer in words.",
  degraded: "plumb's panel is off for this session; plumb keeps working in the background.",
  // SR-126: why the panel could not reach plumb, said once per session
  noPython: (looked: string[]) =>
    `plumb's panel is off: no Python for plumb was found (looked in ${looked.join(', ')}); ` +
    'it tries again at your next message, and plumb keeps working in the background.',
  helloFailed: (error: string) =>
    `plumb's panel is off: plumb could not start it (${error}); plumb keeps working in the background.`,
  helloRefused: (reason: string) =>
    `plumb's panel is off: plumb refused it (${reason}); plumb keeps working in the background.`,
  noBox: (topic: string) =>
    ` The panel could not put "Change to '${topic}': " in the owner's message box: ask them, in ` +
    'one question in your next reply, what to change.',
  toastAwaiting: (n: number) => `plumb: ${n === 1 ? 'a card awaits' : `${n} cards await`} you`,
}
