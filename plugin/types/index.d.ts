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

/** The status the band's first line draws: plumb's status card, SP8's progress, and the
 * owner's card setting (full, compact or off). */
export type PlumbStatus = {
  state: string
  summary: string
  progress: string
  card: string
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
}

declare module 'claude-code' {
  interface PluginState {
    plumb: {
      link: PlumbLink | null
      degraded: boolean
      told: PlumbTold | null
      view: PlumbView
      band: PlumbBand
    }
  }
}
