// plumb's mod: the values it keeps in $.state (SP7 5.6) and the shapes it reads from plumb
// (status.json, `plumb intent status --json`; present.json from plumb.mod.handshake).

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

/** The status the band's first line draws: plumb's status card, SP8's progress and the count
 * of questions waiting for the owner (SR-337); `loop` while an intent loop is open; `study` the
 * title of a study the owner has not opened yet (SR-294). */
export type PlumbStatus = {
  state: string
  summary: string
  progress: string
  /** status.json's `awaiting`: the questions waiting for the owner, the head's "N await you" */
  awaiting: number
  loop?: PlumbLoop | null
  study?: string
  /** the new study's slug, which the band's press opens in the room (SR-294) */
  studySlug?: string
  /** every study still new, oldest first: the band's 'new study' menu once no loop is open (SR-294 EX-6) */
  studies?: { title: string; slug: string }[]
  /** study ideas the agent proposed, waiting for the owner's choice, oldest first: the band's
   * brass idea line, whose press shows the why and the depths (SR-294 EX-7, DEC-207) */
  ideas?: { title: string; slug: string; why: string; recommend: string }[]
  /** the accepted study being written now, with `plumb study progress` once the agent reports it */
  writing?: { title: string; step?: string; done?: number; total?: number }
  /** written studies one of whose records changed, the owner not asked yet: the band's brass
   * line offering a rewrite at the same depth (SR-360 EX-2, DEC-336) */
  outdated?: { title: string; slug: string; changed: string }[]
  /** the requirements a judge approved (auto-jev, auto-model), counted in the head (SR-251) */
  judged?: number
  /** red lines: each misalignment of the running plumb, its local main and its repository (SR-358), a judge that cannot settle and why
   * (SR-359); each until it is fixed */
  red?: string[]
  /** SR-358: plumb's repository could not be read, so the build is not checked (never red) */
  unchecked?: string
  /** the judge's questions plumb set aside, and why: shown apart, never as unreachable (SR-359 EX-2) */
  setAside?: string[]
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

/** The known problems (SR-367), as `plumb mod known --json` answers them: how many are open
 * (the band's one line), and each with its symptom, cause, fix, state and case history, open
 * ones first (the pane). `seen`: the register's files as last read, so plumb runs only when they
 * moved. */
export type PlumbKnown = {
  seen: string
  open: number
  issues: { id: string; title: string; symptom: string; cause: string; fix: string; fixed: string;
    state: string; history: string[] }[]
}

/** One loop of the project as `plumb mod loops --json` gives it (SR-393): an intent loop, a
 * problem being fixed or an evaluate run, live or idle. */
export type PlumbLoopRow = {
  kind: string
  id: string
  goal: string
  goal_full: string
  progress: string
  done: string[]
  left: string[]
  waits: string
  live: boolean
  idle_since: string
  branch: string
  reopen: boolean
  send: boolean
  session: string
  message: { state: string; at: string } | null
}

/** The loops of the project (SR-393): the band's count and the pane's rows. `stamp`: the one
 * file plumb moves whenever a loop changes; `seen`: its text when the list was read, so plumb
 * runs again only when it moved. */
export type PlumbLoops = {
  seen: string
  stamp: string
  live: number
  idle: number
  counts: Record<string, { live: number; idle: number }>
  rows: PlumbLoopRow[]
}

/** The loops pane's own state: the type shown and the rows whose detail is open. */
export type PlumbLoopsPane = { type: string; open: string[] }

/** What the panel draws, as plumb last answered it. */
export type PlumbView = {
  present: PlumbPresent | null
  status: PlumbStatus | null
  /** The last press's answer, as the owner reads it. */
  line: string
}

/** How the owner left the band: hidden until the owner presses Show, whatever arrives (SR-337). */
export type PlumbBand = {
  isHidden: boolean
  /** the band's 'new study' menu is open (SR-294 EX-6) */
  studies?: boolean
  /** the front study idea's choices are shown (SR-294 EX-7) */
  idea?: boolean
  /** the slug of the study idea Tab brought to the front; absent, the newest (SR-369) */
  front?: string
}

declare module 'claude-code' {
  interface PluginState {
    plumb: {
      link: PlumbLink | null
      degraded: boolean
      told: PlumbTold | null
      view: PlumbView
      band: PlumbBand
      /** the loop the pane shows (SR-305); `known`: the known problems pane was opened (SR-367); `loops`: the loops pane's state (SR-393) */
      pane: { loop: PlumbLoopPane | null; known?: boolean; loops?: PlumbLoopsPane | null }
      known: PlumbKnown
      loops: PlumbLoops
    }
  }
}
