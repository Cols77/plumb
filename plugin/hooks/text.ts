// What plumb's panel says to the owner (SP7 6.3: titles and plain words, never IDs, paths of
// plumb's own files, hashes or commands).

export const GLYPHS: Record<string, string> = {
  aligned: '✓',
  'awaits you': '●',
  'something changed': '△',
  'a check fails': '✗',
  'two versions': '⇄',
}

/** plumb's own colours wherever the mod draws (SR-159, SR-290; the room's `--plumb` and
 * `--brass` in ui/src/app.css hold the same values): plum for its text, the darker shade on a
 * light theme, and brass for fills and highlights. Never Claude Code's orange, lavender, cyan or green. */
export const PLUM = { dark: '#B05FB0', light: '#8E3B8E' }
export const BRASS = '#C9A227'
// SR-358, SR-359: what is broken and needs the owner (an old build, a judge that cannot settle)
export const RED = '#D9443A'
// brass on a light theme: about 4.9:1 on white, where #C9A227 is 2.4:1 (SR-290 EX-3)
export const BRASS_LIGHT = '#8A6D0B'

const isLight = (theme: unknown) => typeof theme === 'string' && theme.startsWith('light')

/** The plum for the host's theme (`theme` in /config, as `light`, `light-daltonized`, ...);
 * the dark shade when the surface does not say. */
export const plumbColor = (theme: unknown): string => (isLight(theme) ? PLUM.light : PLUM.dark)

/** The brass for the host's theme, by the same check as the plum. */
export const brassColor = (theme: unknown): string => (isLight(theme) ? BRASS_LIGHT : BRASS)

export const T = {
  name: 'plumb',
  awaiting: (n: number) => (n === 1 ? '1 awaits you' : `${n} await you`),
  nothingAwaits: 'nothing awaits you',
  stopped: (what: string) => `stopped, waits for ${what}`,
  newStudy: (title: string) => `new study: ${title}`,
  newStudies: (n: number) => (n === 1 ? 'new study' : `${n} new studies`),
  studyIdea: (title: string) => `study idea: ${title}`,
  moreIdeas: (n: number) => `+${n} more (Tab)`,
  studyIdeaFolded: 'study idea',
  // DEC-207: the depths the owner chooses from; video since INT-093 (SR-316)
  depths: { md: 'Markdown only', diagrams: 'with diagrams', video: 'video' } as Record<string, string>,
  notNow: 'not now',
  // SR-360 EX-2: a study whose records changed, and the offer to rewrite it at the same depth
  outOfDate: (title: string, changed: string) => `study out of date: ${title} (${changed} changed)`,
  rewrite: 'Rewrite it',
  refreshFailed: 'plumb could not record that; the study stays as it is. Try again.',
  chooseFailed: 'plumb could not record that choice; nothing changed. Try again.',
  judged: (n: number) => `${n} judge-approved`,
  unchecked: "plumb could not check its repository for a newer version",
  setAside: (question: string, why: string) => `the judge's question was set aside: "${question}" (${why})`,
  roomFailed: 'plumb could not open the study in the browser room; nothing changed. Try again.',
  roomWaits: 'a question waits in the room',
  roomQuestionFailed: 'plumb could not open the question in the browser room; nothing changed. Try again.',
  loopTitle: 'plumb: the intent loop',
  // SR-367: the known problems, one band line and a pane
  knownOpen: (n: number) => (n === 1 ? '1 known problem open' : `${n} known problems open`),
  knownTitle: 'plumb: known problems',
  knownState: (state: string, fixed: string) => (state === 'open' ? 'open' : `fixed${fixed ? ` ${fixed}` : ''}`),
  knownSymptom: (s: string) => `  symptom: ${s}`,
  knownCause: (s: string) => `  cause: ${s}`,
  knownFix: (s: string) => `  fix: ${s || 'none yet'}`,
  knownHistory: (h: string) => `  history: ${h}`,
  lowLeft: (n: number) => (n === 1 ? '1 low finding left' : `${n} low findings left`),
  tasksLeft: (left: string[]) => `left: ${left.join(', ')}`,
  records: 'Records written or changed',
  proofs: 'Proof',
  shown: 'shown',
  notShown: 'not shown yet',
  hide: 'Hide',
  show: 'Show',
  recommended: ' (recommended)',
  degraded: "plumb's panel is off for this session; plumb keeps working in the background.",
  // SR-126: why the panel could not reach plumb, said once per session
  noPython: (looked: string[]) =>
    `plumb's panel is off: no Python for plumb was found (looked in ${looked.join(', ')}); ` +
    'it tries again at your next message, and plumb keeps working in the background.',
  helloFailed: (error: string) =>
    `plumb's panel is off: plumb could not start it (${error}); plumb keeps working in the background.`,
  helloRefused: (reason: string) =>
    `plumb's panel is off: plumb refused it (${reason}); plumb keeps working in the background.`,
}
