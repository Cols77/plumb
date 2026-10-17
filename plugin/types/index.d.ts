// plumb's mod: the values it keeps in $.state (SP7 5.6) and the shapes `plumb mod` answers
// (src/plumb/mod: draw, press; present.json from plumb.mod.handshake).

/** One button of a drawn card question: a suggested choice, Ask for a change, Leave open. */
export type PlumbButton = {
  index: number
  label: string
  answer: 'accepted' | 'rejected' | 'change' | 'open'
  change: string | null
  consequence?: string
}

/** One question of a card as drawn, with the offer the press names. */
export type PlumbOffer = {
  offer_id: string
  question: string
  record: string | null
  hash: string
  drawn_at: string
  buttons: PlumbButton[]
}

export type PlumbQuestion = {
  id: string
  text: string
  resolutions: string[]
  record: string | null
  hash: string
}

/** What a card shows (SR-129): a read-back or a choice, as plumb derives it (understand.fullcard). */
export type PlumbContent = {
  topic: string
  issue: string
  context: string[]
  assumptions: string[]
  wont: string | null
  options: { n: number; text: string; consequence: string | null; recommended: boolean }[]
  diagram: string
}

/** A card as `plumb mod draw` answers it: the card as cards.json holds it, plus its offers. */
export type PlumbCard = {
  id: string
  kind: string
  topic: string
  issue: string
  evidence: string
  resolutions: string[]
  questions: PlumbQuestion[]
  status: string
  answers: unknown[]
  owner_only: boolean
  turn: number
  repeats: boolean
  /** SR-160: where the card stands: waiting, processing, blocked, done or left_open */
  state?: string
  /** why a blocked card could not be applied */
  reason?: string
  offers: PlumbOffer[]
  content: PlumbContent | null
  feature?: string
  /** the path of the card's diagram file ('' for none) */
  diagram?: string
  /** the diagram drawn by the diagram mod's noun when the snapshot was taken (null: not drawn) */
  drawn?: { rows: string[]; svg: string } | null
}

/** present.json: what the stop hook hands the panel for a turn (sp7-realign-sp8 C7). */
export type PlumbPresent = {
  turn: number
  turn_id: string
  written_at: string
  confirmations: string[]
}

/** The session's link to plumb: where it runs and the key only the panel holds (DEC-025). */
export type PlumbLink = {
  session: string
  root: string
  python: string
  key: string
}

/** SR-126: the session the panel said it could not reach plumb in, and why (`no-python`,
 * `failed`, `refused`): said once per session; a missing interpreter, and what `retry` marks
 * (a resumed session's old panel still registered, a .venv tried before host.json), is tried
 * again each turn. */
export type PlumbTold = {
  session: string
  why: string
  retry?: boolean
}

/** The session's open intent loop as the band draws it (SR-291): its current step, the
 * step's task (no total: the elapsed time, read when the status was), and what a refused gate
 * left it waiting for. */
export type PlumbLoop = {
  step: string
  task: { label: string; done: number; total: number | null; elapsed: string } | null
  stopped: string
}

/** The status the band's first line draws: plumb's status card, SP8's progress, and the
 * owner's card setting (full, compact or off); `loop` while an intent loop is open; `study` the
 * title of a study the owner has not opened yet (SR-294). */
export type PlumbStatus = {
  state: string
  summary: string
  progress: string
  card: string
  loop?: PlumbLoop | null
  study?: string
  /** the new study's slug, which the band's press opens in the room (SR-294) */
  studySlug?: string
  /** every study still new, oldest first: the band's 'new study' menu once no loop is open (SR-294 EX-6) */
  studies?: { title: string; slug: string }[]
  /** the requirements a judge approved (auto-jev, auto-model), counted in the head (SR-251) */
  judged?: number
}

/** What the loop pane shows (SR-305), as `plumb intent status --json` gives the open loop:
 * its steps' gates with the low findings left, the task and the tasks left, the records of
 * its intent by title, and each requirement's proof shown or not. */
export type PlumbLoopPane = {
  step: string
  stopped: string
  stages: Record<string, { state: string; left: string[] }>
  task: { label: string; done: number; total: number | null; left: string[] } | null
  records: string[]
  proofs: { title: string; shown: boolean }[]
}

/** What the panel draws, as plumb last answered it. */
export type PlumbView = {
  cards: PlumbCard[]
  present: PlumbPresent | null
  status: PlumbStatus | null
  /** The last press's answer, as the owner reads it. */
  line: string
}

/** How the owner left the band: hidden, every card shown, and the cards' contents when the
 * owner hid it (a new content shows the band again). */
export type PlumbBand = {
  isHidden: boolean
  showAll: boolean
  shown: string[]
  /** the band's 'new study' menu is open (SR-294 EX-6) */
  studies?: boolean
}

declare module 'claude-code' {
  interface PluginState {
    plumb: {
      link: PlumbLink | null
      degraded: boolean
      told: PlumbTold | null
      view: PlumbView
      band: PlumbBand
      /** the card the pane shows, among those waiting; the loop it shows instead (SR-305) */
      pane: { index: number; loop?: PlumbLoopPane | null }
    }
  }
}
