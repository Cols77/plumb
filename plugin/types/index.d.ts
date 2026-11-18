// iaso's mod: the values it keeps in $.state (SP7 5.6) and the shapes it reads from iaso
// (status.json, `iaso intent status --json`; present.json from iaso.mod.handshake).

/** present.json: what the stop hook hands the panel for a turn (sp7-realign-sp8 C7). */
export type IasoPresent = {
  turn: number
  turn_id: string
  written_at: string
  confirmations: string[]
}

/** The session's link to iaso: where it runs and the key only the panel holds (DEC-025). */
export type IasoLink = {
  session: string
  root: string
  python: string
  key: string
}

/** SR-126: the session the panel said it could not reach iaso in, and why (`no-python`,
 * `failed`, `refused`): said once per session; a missing interpreter, and what `retry` marks
 * (a resumed session's old panel still registered, a .venv tried before host.json), is tried
 * again each turn. */
export type IasoTold = {
  session: string
  why: string
  retry?: boolean
}

/** The session's open intent loop as the band draws it (SR-291): its current step, the
 * step's task (no total: the elapsed time, read when the status was), and what a refused gate
 * left it waiting for. */
export type IasoLoop = {
  step: string
  task: { label: string; done: number; total: number | null; elapsed: string } | null
  stopped: string
}

/** The status the band's first line draws: iaso's status card, SP8's progress and the count
 * of questions waiting for the owner (SR-337); `loop` while an intent loop is open; `study` the
 * title of a study the owner has not opened yet (SR-294). */
export type IasoStatus = {
  /** SR-415: the session's name, which the band's line begins with; '' when none */
  name?: string
  state: string
  summary: string
  progress: string
  /** status.json's `awaiting`: the questions waiting for the owner, the head's "N await you" */
  awaiting: number
  loop?: IasoLoop | null
  study?: string
  /** the new study's slug, which the band's press opens in the room (SR-294) */
  studySlug?: string
  /** every study still new, oldest first: the band's 'new study' menu once no loop is open (SR-294 EX-6) */
  studies?: { title: string; slug: string }[]
  /** studies the owner has opened, kept folded and dim in the pane's read section (SR-411) */
  read?: { title: string; slug: string }[]
  /** study ideas the agent proposed, waiting for the owner's choice, oldest first: the band's
   * brass idea line, whose press shows the why and the depths (SR-294 EX-7, DEC-207) */
  ideas?: { title: string; slug: string; why: string; recommend: string }[]
  /** the accepted study being written now, with `iaso study progress` once the agent reports it */
  writing?: { title: string; step?: string; done?: number; total?: number }
  /** written studies one of whose records changed, the owner not asked yet: the band's brass
   * line offering a rewrite at the same depth (SR-360 EX-2, DEC-336) */
  outdated?: { title: string; slug: string; changed: string }[]
  /** the requirements a judge approved (auto-jev, auto-model), counted in the head (SR-251) */
  judged?: number
  /** red lines: each misalignment of the running iaso, its local main and its repository (SR-358), a judge that cannot settle and why
   * (SR-359); each until it is fixed */
  red?: string[]
  /** the build lines and the judge lines of `red`, apart, for the band's two chips (SR-409) */
  buildLines?: string[]
  judgeLines?: string[]
  /** the name of each judge in judgeLines, in the same order: its row's key in the pane (SR-413) */
  judgeNames?: string[]
  /** judges that ran but could not settle a record, plain colour with the cause, and their names (SR-413 EX-6) */
  unsettledLines?: string[]
  unsettledNames?: string[]
  /** SR-358: iaso's repository could not be read, so the build is not checked (never red) */
  unchecked?: string
  /** SR-358 EX-6: the version of the plugin the session runs, always on the band's line */
  version?: string
  /** the judge's questions iaso set aside, and why: shown apart, never as unreachable (SR-359 EX-2) */
  setAside?: string[]
}

/** What the loop pane shows (SR-305), as `iaso intent status --json` gives the open loop:
 * its steps' gates with the low findings left, the task and the tasks left, the records of
 * its intent by title, and each requirement's proof shown or not. */
export type IasoLoopPane = {
  step: string
  stopped: string
  stages: Record<string, { state: string; left: string[] }>
  task: { label: string; done: number; total: number | null; left: string[] } | null
  records: string[]
  proofs: { title: string; shown: boolean }[]
}

/** The known problems (SR-367), as `iaso mod known --json` answers them: how many are open
 * (the band's one line), and each with its symptom, cause, fix, state and case history, open
 * ones first (the pane). `seen`: the register's files as last read, so iaso runs only when they
 * moved. */
export type IasoKnown = {
  seen: string
  open: number
  issues: { id: string; title: string; symptom: string; cause: string; fix: string; fixed: string;
    state: string; history: string[] }[]
}

/** One loop of the project as `iaso mod loops --json` gives it (SR-393): an intent loop, a
 * problem being fixed or an evaluate run, live or idle. */
export type IasoLoopRow = {
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
  /** an intent loop's steps with mark (done, current, todo), gate (passed, open, refused, to come)
   * and the low findings its gate left (SR-305); none for debug and evaluate rows */
  steps?: { name: string; mark: string; gate: string; findings: number; left: string[] }[]
  tasks?: { done: number; total: number | null; left: string[] } | null
}

/** The loops of the project (SR-393): the band's count and the pane's rows. `stamp`: the one
 * file iaso moves whenever a loop changes; `seen`: its text when the list was read, so iaso
 * runs again only when it moved. */
export type IasoLoops = {
  seen: string
  stamp: string
  live: number
  idle: number
  counts: Record<string, { live: number; idle: number }>
  rows: IasoLoopRow[]
  /** SR-375: iaso is reading the loops again; the band says so and keeps the last list */
  updating?: boolean
}

/** The loops pane's own state: the type shown, the rows whose detail is open and the loops a
 * reopen press is opening (SR-394: a second press on one does nothing). */
export type IasoLoopsPane = { type: string; open: string[]; opening?: string[] }

/** The one pane's state (SR-410): the class shown, the one expanded row, the loops type, the known flag. */
export type IasoPane = { loop: IasoLoopPane | null; known?: boolean; loops?: IasoLoopsPane | null; cls?: string; row?: string; step?: string }

/** What the panel draws, as iaso last answered it. */
export type IasoView = {
  present: IasoPresent | null
  status: IasoStatus | null
  /** The last press's answer, as the owner reads it. */
  line: string
}

/** How the owner left the band: hidden until the owner presses Show, whatever arrives (SR-337). */
export type IasoBand = {
  isHidden: boolean
  /** the loop section folded to its title (SR-305) */
  loopFolded?: boolean
}

declare module 'claude-code' {
  interface PluginState {
    iaso: {
      link: IasoLink | null
      degraded: boolean
      told: IasoTold | null
      view: IasoView
      band: IasoBand
      /** the loop the pane shows (SR-305); `known`: the known problems pane was opened (SR-367); `loops`: the loops pane's state (SR-393) */
      pane: IasoPane
      known: IasoKnown
      loops: IasoLoops
    }
  }
}
