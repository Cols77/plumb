// What plumb's panel says to the owner (SP7 6.3: titles and plain words, never IDs, paths of
// plumb's own files, hashes or commands). The card texts themselves come from plumb.

export const FOLD_AT = 4000 // characters of a change above which it is folded, never cut

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
  asItReads: 'As it now reads',
  whatChanged: 'What changed',
  evidence: 'What it rests on',
  yourWords: 'Your words',
  options: 'Your options',
  why: 'Why the recommended one',
  recommended: ' (recommended)',
  consequence: 'does and leaves undone: ',
  notWritten: 'not written yet',
  folded: (size: number, lines: number) =>
    `folded: ${size.toLocaleString('en')} characters, ${lines} lines`,
  unfold: 'Open the change in full',
  fold: 'Fold the change',
  changeHead: (path: string, added: number, removed: number, size: number) =>
    `${path} (+${added}/-${removed} lines, ${size.toLocaleString('en')} characters)`,
  items: (n: number) => `${n} items`,
  undo: 'Undo',
  settledHead: 'Settled from your words:',
  pressFailed: "plumb could not record that press; nothing changed. Try again, or answer in words.",
  undoFailed: 'plumb could not take that back; nothing changed.',
  degraded: "plumb's panel is off for this session; plumb keeps working in the background.",
  noBox: (topic: string) =>
    ` The panel could not put "Change to '${topic}': " in the owner's message box: ask them, in ` +
    'one question in your next reply, what to change.',
  toastAwaiting: (n: number) => `plumb: ${n === 1 ? 'a card awaits' : `${n} cards await`} you`,
}
