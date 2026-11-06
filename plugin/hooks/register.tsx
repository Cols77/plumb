// plumb's mod (SP7 5 as re-aligned by sp7-realign-sp8; SR-085, SR-087, SR-116, SR-337): the
// band above the prompt (plumb's status with the count of questions waiting, SP8's progress, the
// intent loop's and the studies' lines, the known problems' one line; no card), the loop pane, the
// known problems pane, the owner's notice after a press, and the fallback. plumb's command hooks keep doing the work (DEC-024): while this panel
// is active the stop hook writes present.json instead of printing.
//
// The engine wants every `$` call spelled at its hook's call site: each hook hands plumb.ts an
// `Io` of closures over its own `$`, and every Button is answered by the `ui.press` hook below.
//
// Linking (SR-125, SR-126): the session's start says hello as soon as plumb's interpreter is
// known; the session-start command hook names it in host.json, maybe a moment after this mod
// starts, so the start keeps trying for a few seconds, and each turn's start tries again. The
// same holds while plumb still keeps a resumed session's old panel registered (the hook retires
// it) and while only the repository's .venv was there to try. When the panel cannot reach plumb
// it says why in one dim line, once per session; in a repository plumb has not adopted it stays
// silent.
import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { PlumbBand, PlumbKnown, PlumbLink, PlumbLoop, PlumbLoopPane, PlumbLoopRow, PlumbLoops, PlumbLoopsPane, PlumbStatus, PlumbTold, PlumbView } from '../types'
import * as plumb from './plumb'
import type { Hello, Io, Unlinked } from './plumb'
import { brassColor, GLYPHS, plumbColor, RED, T } from './text'

/** The surface's element table, as `$.ui.resolve(e)` answers it. */
type Ui = { Box: any; Text: any; Button: any }

const uiOf = ($: any, e: any): Ui => $.ui.resolve(e)

const PANE = 'plumb-loop'
const KNOWN_PANE = 'plumb-known'
const LOOPS_PANE = 'plumb-loops'
const LOOP_TYPES = ['intent', 'debug', 'evaluate']
const EMPTY_VIEW: PlumbView = { present: null, status: null, line: '' }
const BAND: PlumbBand = { isHidden: false }

const linkAtom = atom({ plugin: 'plumb', key: 'link' } as const, null)
const degradedAtom = atom({ plugin: 'plumb', key: 'degraded' } as const, false)
const toldAtom = atom({ plugin: 'plumb', key: 'told' } as const, null as PlumbTold | null)
const viewAtom = atom({ plugin: 'plumb', key: 'view' } as const, EMPTY_VIEW)
const bandAtom = atom({ plugin: 'plumb', key: 'band' } as const, BAND)
const paneAtom = atom({ plugin: 'plumb', key: 'pane' } as const,
  { loop: null as PlumbLoopPane | null, known: false as boolean | undefined, loops: null as PlumbLoopsPane | null | undefined })
const loopsAtom = atom({ plugin: 'plumb', key: 'loops' } as const, plumb.NO_LOOPS)
const knownAtom = atom({ plugin: 'plumb', key: 'known' } as const, plumb.NO_KNOWN)

// the width the pane asks for when it docks beside the conversation
const PANE_COLUMNS = 80

function statusLine(view: PlumbView): string {
  const waiting = view.status?.awaiting ?? 0 // SR-337 EX-1: status.json's count, never a card
  const state = view.status?.state ?? ''
  const glyph = waiting ? GLYPHS['awaits you'] : GLYPHS[state] ?? '·'
  const word = waiting ? T.awaiting(waiting) : state || T.nothingAwaits
  const judged = view.status?.judged ? T.judged(view.status.judged) : '' // SR-251
  return [`${T.name} ${glyph} ${word}`, judged, view.status?.progress].filter(Boolean).join(' · ')
}

/** The band's status read again (files only, no process): null when nothing moved (SR-291).
 * A new study gets no toast: the band's line announces it (SR-294 EX-1). */
async function reread(io: Io, link: PlumbLink, view: PlumbView) {
  const status = await plumb.readStatus(io, link)
  return JSON.stringify(status) === JSON.stringify(view.status) ? null : { status }
}

/** SR-305: the loop pane, while open, follows the band: read again when the band's status moved.
 * A closed pane is never told (the host gives no close event), so it is read again at most once
 * per move of the status; closed when the loop is gone, whether the band's files or
 * `plumb intent status` say so first (SR-305 EX-6). */
async function refreshPane($: any, io: Io, link: PlumbLink) {
  if ((await read($, paneAtom)).loop === null) return
  const loop = (await read($, viewAtom)).status?.loop ? await plumb.loopPane(io, link) : null
  if (loop === null) {
    // the loop ended: its pane closes (rounds 4 and 5)
    await update($, paneAtom, p => ({ ...p, loop: null }))
    await $.ui.close({ id: PANE })
    return
  }
  await update($, paneAtom, p => ({ ...p, loop: p.loop === null ? null : loop }))
}

/** SR-367: the known problems read again when the register or one of its cases moved (files
 * only); plumb runs only then. */
async function refreshKnown($: any, io: Io, link: PlumbLink) {
  const seen = await plumb.knownSeen(io, link)
  if (seen === (await read($, knownAtom)).seen) return
  const known = seen ? await plumb.known(io, link, seen) : plumb.NO_KNOWN
  if (known !== null) await update($, knownAtom, () => known)
}

/** SR-393: the project's loops read again at link, at each turn's end and when the pane
 * opens (`force`), and otherwise only when the one change stamp moved; plumb runs only then,
 * and never while no stamp exists: no loop was ever written. */
async function refreshLoops($: any, io: Io, link: PlumbLink, force = false) {
  const have = await read($, loopsAtom)
  const stamp = have.stamp || await plumb.loopsStamp(io, link.root)
  const seen = await plumb.loopsSeen(io, stamp)
  if (!force && seen === have.seen) return
  const loops = seen ? await plumb.loops(io, link, stamp, seen) : { ...plumb.NO_LOOPS, stamp }
  if (loops !== null) await update($, loopsAtom, () => loops)
}

// SR-291 EX-7: a workflow's agents raise no event in the owner's session, so the band reads
// its files again on this period (the mod API has no file watch)
const POLL_MS = 2000
let polling: { cancel: () => void } | null = null
// SR-393: the loops' stamp is looked at every LOOPS_EVERY-th period (10 s)
const LOOPS_EVERY = 5
let polls = 0

// the session-start hook writes host.json within its first second: about ten seconds of tries
const RETRY_MS = 500
const RETRIES = 20
// a live-looking old panel is taken over once its heartbeat is a minute old (SR-350): keep
// asking, every 10 s after the first RETRIES tries, for a little over that
const HELD_RETRIES = 160

// one hello at a time: the start's retries and a turn's start never both register the session
let helloing: Promise<Hello> | null = null
function helloOnce(io: Io): Promise<Hello> {
  if (helloing === null) {
    helloing = plumb.hello(io).finally(() => {
      helloing = null
    })
  }
  return helloing
}

function unlinkedLine(u: Unlinked): string {
  if (u.why === 'no-python') return T.noPython(u.looked)
  if (u.why === 'refused') return T.helloRefused(u.reason)
  return T.helloFailed(u.error)
}

const LOOP_STEPS = ['clarify', 'plan', 'build', 'proven']
const BAR_CELLS = 10

/** A step's mark: done, current (stopped where a gate refused), to come. */
function stepMark(loop: { step: string; stopped: string }, i: number): string {
  const at = LOOP_STEPS.indexOf(loop.step)
  return i < at ? '✓' : i > at ? '○' : loop.stopped ? '✗' : '●'
}

/** An intent loop's lines under the status (SR-291): the strip of its steps in plum (done,
 * current, to come; a refused gate marks the current one stopped and names what it waits for),
 * then the current step's task, a brass fill of done over total, or the elapsed time with no
 * fill when the total is unknown. The strip is a Button: its press opens the loop's pane (SR-305). */
function loopLines(ui: Ui, loop: PlumbLoop, color: string, brass: string) {
  const { Box, Button, Text } = ui
  const strip = LOOP_STEPS.map((s, i) => `${s} ${stepMark(loop, i)}`).join('  ')
  const task = loop.task
  const filled = task?.total ? Math.round(BAR_CELLS * Math.min(task.done, task.total) / task.total) : 0
  // a workflow phase's gate reports itself (DEC-157): the step, the phase of the script's, the gate
  const words = task?.total && / gate (passed|failed)$/.test(task.label)
    ? `${loop.step} · slice ${task.done}/${task.total} · ${task.label}`
    : [task?.label, task?.total ? `${task?.done}/${task.total}` : task?.elapsed].filter(Boolean).join(' · ')
  return [
    <Button key="loop" plain onPress={() => {}}>
      <Text key="loop:strip" color={color}>{loop.stopped ? `${strip} · ${T.stopped(loop.stopped)}` : strip}</Text>
    </Button>,
    task ? (
      <Box key="loop:bar" flexDirection="row" gap={1}>
        {task.total ? <Text key="loop:fill" color={brass}>{'█'.repeat(filled) + '░'.repeat(BAR_CELLS - filled)}</Text> : null}
        <Text key="loop:task">{words}</Text>
      </Box>
    ) : null,
  ]
}

/** The loop pane (SR-305): each step with its gate and the low findings left, the build's
 * tasks done and left, the records of the loop's intent and each requirement's proof, by title;
 * never an agent, a count of them or tokens. */
function loopPane(ui: Ui, loop: PlumbLoopPane, color: string, brass: string) {
  const { Box, Text } = ui
  const rows = LOOP_STEPS.map((s, i) => {
    const left = loop.stages[s]?.left ?? []
    const now = s === loop.step ? loop.task : null
    const notes = [left.length ? T.lowLeft(left.length) : '', now?.left.length ? T.tasksLeft(now.left) : '']
    const head = `${s} ${stepMark(loop, i)}${now?.total ? ` ${now.done}/${now.total}` : ''}`
    return (
      <Box key={`step:${s}`} flexDirection="column">
        <Text key={`step:${s}:head`} color={color}>{[head, ...notes].filter(Boolean).join(' · ')}</Text>
        {left.map((what, n) => <Text key={`low:${s}:${n}`} dimColor>{`  low: ${what}`}</Text>)}
      </Box>
    )
  })
  return (
    <Box flexDirection="column">
      {rows}
      {loop.records.length ? <Text key="records" bold color={color}>{T.records}</Text> : null}
      {loop.records.map((title, n) => <Text key={`record:${n}`}>{`  ${title}`}</Text>)}
      {loop.proofs.length ? <Text key="proofs" bold color={color}>{T.proofs}</Text> : null}
      {loop.proofs.map((p, n) => (
        <Text key={`proof:${n}`} color={p.shown ? brass : undefined}>
          {`  ${p.shown ? '✓' : '○'} ${p.title}: ${p.shown ? T.shown : T.notShown}`}
        </Text>
      ))}
    </Box>
  )
}

/** The known problems pane (SR-367): each problem by title with its state, symptom, cause, fix
 * and its case's history, open ones first (plumb's order). */
function knownPane(ui: Ui, known: PlumbKnown, color: string) {
  const { Box, Text } = ui
  return (
    <Box flexDirection="column">
      {known.issues.map(k => (
        <Box key={`known:${k.id}`} flexDirection="column">
          <Text key={`known:${k.id}:head`} bold color={color}>{`${k.title || k.symptom} · ${T.knownState(k.state, k.fixed)}`}</Text>
          <Text key={`known:${k.id}:symptom`} dimColor>{T.knownSymptom(k.symptom)}</Text>
          {k.cause ? <Text key={`known:${k.id}:cause`}>{T.knownCause(k.cause)}</Text> : null}
          <Text key={`known:${k.id}:fix`}>{T.knownFix(k.fix)}</Text>
          {k.history.map((was, n) => <Text key={`known:${k.id}:history:${n}`} dimColor>{T.knownHistory(was)}</Text>)}
        </Box>
      ))}
    </Box>
  )
}

/** The loops pane (SR-393): a switch between the three types, then the shown type's rows, live
 * first and idle apart; a row's press folds its detail in or out. Never an agent or tokens. */
function loopsPane(ui: Ui, loops: PlumbLoops, state: PlumbLoopsPane, color: string) {
  const { Box, Button, Text } = ui
  const rows = loops.rows.filter(r => r.kind === state.type)
  const one = (r: PlumbLoopRow) => {
    const key = `${r.kind}:${r.id}`
    return (
      <Box key={`loops:${key}`} flexDirection="column">
        <Button key={`loops:row:${key}`} plain onPress={() => {}}>
          <Text key={`loops:text:${key}`}>{`${r.goal} · ${r.progress}${r.live ? '' : ` · ${T.loopsIdleSince(r.idle_since)}`}`}</Text>
        </Button>
        {r.reopen ? (
          <Button key={`loops:reopen:${r.id}`} plain onPress={() => {}}>
            <Text key={`loops:reopen:text:${r.id}`} color={color}>{T.loopsReopen}</Text>
          </Button>
        ) : null}
        {state.open.includes(key) ? [
          <Text key={`${key}:goal`} dimColor>{T.loopGoal(r.goal_full)}</Text>,
          <Text key={`${key}:done`} dimColor>{T.loopDone(r.done)}</Text>,
          <Text key={`${key}:left`} dimColor>{T.loopLeft(r.left)}</Text>,
          <Text key={`${key}:waits`} dimColor>{T.loopWaits(r.waits)}</Text>,
          <Text key={`${key}:branch`} dimColor>{T.loopBranch(r.branch)}</Text>,
          r.message ? <Text key={`${key}:message`} dimColor>{T.loopMessage(r.message.state)}</Text> : null,
        ] : null}
      </Box>
    )
  }
  const live = rows.filter(r => r.live)
  const idle = rows.filter(r => !r.live)
  return (
    <Box flexDirection="column">
      <Box key="loops:switch" flexDirection="row" gap={1}>
        {LOOP_TYPES.map(t => (
          <Button key={`loops:type:${t}`} plain onPress={() => {}}>
            <Text key={`loops:label:${t}`} bold={t === state.type} color={color}>
              {T.loopsType(t === state.type, t, loops.counts[t]?.live ?? 0, loops.counts[t]?.idle ?? 0)}
            </Text>
          </Button>
        ))}
      </Box>
      {rows.length ? null : <Text key="loops:none" dimColor>{T.loopsNone[state.type]}</Text>}
      {live.map(one)}
      {idle.length ? <Text key="loops:idle" bold color={color}>{T.loopsIdle}</Text> : null}
      {idle.map(one)}
    </Box>
  )
}

/** A study idea's why and the depths the owner chooses from (SR-294 EX-7, DEC-207): Markdown
 * only, with diagrams, video (SR-316), and 'not now';
 * the agent's recommended depth marked. */
function ideaChoices(ui: Ui, idea: { title: string; why: string; recommend: string }, titled: boolean, brass: string,
                     inline = false) {
  const { Box, Button, Text } = ui
  const label = (d: string) => T.depths[d] + (idea.recommend === d ? T.recommended : '')
  return (
    // inline: in a loop the choices take the third line's place, one row (SR-291, DEC-146)
    <Box key="idea:choices" flexDirection={inline ? 'row' : 'column'} gap={inline ? 1 : 0}>
      <Text key="idea:why" dimColor>{`  ${titled ? `${idea.title}: ` : ''}${idea.why}`}</Text>
      <Box key="idea:depths" flexDirection="row" gap={1}>
        <Button key="idea:md" label={label('md')} onPress={() => {}} />
        <Button key="idea:diagrams" label={label('diagrams')} onPress={() => {}} />
        <Button key="idea:video" label={label('video')} onPress={() => {}} />
        <Button key="idea:none" label={T.notNow} onPress={() => {}} />
      </Box>
    </Box>
  )
}

type Idea = NonNullable<PlumbStatus['ideas']>[number]

/** The idea in front: the one Tab last brought there, else the newest (SR-369). */
function frontIdea(ideas: Idea[], band: PlumbBand): Idea | undefined {
  return ideas.find(i => i.slug === band.front) ?? ideas.at(-1)
}

/** The slug after the front one, wrapping from the last to the first (SR-369). */
function nextIdea(ideas: Idea[], band: PlumbBand): string | undefined {
  const front = frontIdea(ideas, band)
  return front && ideas[(ideas.indexOf(front) + 1) % ideas.length]?.slug
}

/** SR-291's bar for a study being written: five cells and the percent. */
function writingBar(done: number, total: number): string {
  const f = Math.min(done, total) / total
  const n = Math.round(5 * f)
  return `${'▰'.repeat(n)}${'▱'.repeat(5 - n)} ${Math.round(100 * f)}%`
}

/** The band: one line of status, then the loop's and the studies' lines; no card (SR-337). The
 * known problems are one line when any is open, never one per problem (SR-367). */
function drawBand(ui: Ui, view: PlumbView, band: PlumbBand, known: number, loops: PlumbLoops, columns: number, color: string,
                  brass: string) {
  const { Box, Button, Text } = ui
  const head = statusLine(view)
  if (band.isHidden) {
    return (
      <Box flexDirection="row" gap={1}>
        <Text color={color} dimColor>{head}</Text>
        <Button key="show" label={T.show} plain onPress={() => {}} />
      </Box>
    )
  }
  const loop = view.status?.loop
  const studies = view.status?.studies ?? []
  // DEC-207: the ideas waiting for a choice; one in front, the newest until Tab moves it (SR-369)
  const ideas = view.status?.ideas ?? []
  const idea = frontIdea(ideas, band)
  const ideaLine = (tag: string) => idea ? [
    <Button key="idea" plain onPress={() => {}}>
      <Text key={`${tag}:idea`} color={brass}>{T.studyIdea(idea.title)}</Text>
    </Button>,
    ideas.length > 1 ? (
      // Tab onto the count brings the next idea to the front (the ui.focus hook)
      <Button key="idea:next" plain onPress={() => {}}>
        <Text key={`${tag}:idea:next`} dimColor>{T.moreIdeas(ideas.length - 1)}</Text>
      </Button>
    ) : null,
  ] : null
  const outdated = (view.status?.outdated ?? []).at(-1)
  return (
    <Box flexDirection="column" width={columns}>
      <Box flexDirection="row" gap={1}>
        <Text bold color={color}>{head}</Text>
        {view.status?.summary ? <Text dimColor>{view.status.summary}</Text> : null}
        {loops.live + loops.idle > 0 ? (
          // SR-393 EX-1, EX-6: the loops of the project as a count in this line, never a line each
          <Button key="loops" plain onPress={() => {}}>
            <Text key="head:loops" color={color}>{T.loopsLive(loops.live, loops.idle)}</Text>
          </Button>
        ) : null}
        <Button key="hide" label={T.hide} plain onPress={() => {}} />
        {!loop && studies.length ? (
          // SR-294 EX-5 (DEC-183): no loop open, the study folds into the one line; a press opens its menu
          <Button key="studies" plain onPress={() => {}}>
            <Text key="head:studies" color={brass}>{T.newStudies(studies.length)}</Text>
          </Button>
        ) : null}
        {/* DEC-183 style: no loop open, the ideas fold into the one line too, each by its title */}
        {!loop ? ideaLine('head') : null}
      </Box>
      {known > 0 ? (
        // SR-367 EX-1, EX-3: one collapsed line; a press opens the known problems pane
        <Button key="known" plain onPress={() => {}}>
          <Text key="line:known" dimColor>{T.knownOpen(known)}</Text>
        </Button>
      ) : null}
      {(view.status?.red ?? []).map((r, n) => <Text key={`red:${n}`} color={RED}>{r}</Text>)}
      {view.status?.unchecked ? <Text key="unchecked" dimColor>{view.status.unchecked}</Text> : null}
      {(view.status?.setAside ?? []).map((a, n) => <Text key={`aside:${n}`} dimColor>{a}</Text>)}
      {outdated ? (
        // SR-360 EX-2, DEC-336: a study whose records changed; nothing is rewritten without the yes
        <Box key="outdated" flexDirection="row" gap={1}>
          <Text key="line:outdated" color={brass}>{T.outOfDate(outdated.title, outdated.changed)}</Text>
          <Button key="refresh:yes" label={T.rewrite} onPress={() => {}} />
          <Button key="refresh:no" label={T.notNow} onPress={() => {}} />
        </Box>
      ) : null}
      {view.status?.writing ? (
        // the accepted study is being written: its step, a bar and a percent as the agent reports
        <Box key="writing" flexDirection="row" gap={1}>
          <Text key="line:writing" color={brass}>{T.writing(view.status.writing.title, view.status.writing.step)}</Text>
          {view.status.writing.total ? (
            <Text key="writing:bar" color={brass}>{writingBar(view.status.writing.done ?? 0, view.status.writing.total)}</Text>
          ) : null}
        </Box>
      ) : null}
      {loop ? loopLines(ui, loop, color, brass) : null}
      {loop && idea && band.idea ? ideaChoices(ui, idea, true, brass, true) : loop && (view.status?.study || idea) ? (
        // SR-291, DEC-146: the loop's third and last line holds the new study and the idea side by side
        <Box key="loop:third" flexDirection="row" gap={2}>
          {view.status?.study ? (
            // a press opens the room on the study
            <Button key="study" plain onPress={() => {}}>
              <Text key="loop:study" color={brass}>{T.newStudy(view.status.study)}</Text>
            </Button>
          ) : null}
          {/* SR-294: the agent's study idea; a press shows its choices */}
          {ideaLine('loop')}
        </Box>
      ) : null}
      {!loop && idea && band.idea ? ideaChoices(ui, idea, true, brass) : null}
      {!loop && band.studies ? studies.map(st => (
        // SR-294 EX-6: the small menu in the band, the new studies by title
        <Button key={`study:${st.slug}`} plain onPress={() => {}}>
          <Text key={`menu:${st.slug}`} color={brass}>{`  ${st.title}`}</Text>
        </Button>
      )) : null}
      {view.line ? <Text key="line" dimColor>{view.line}</Text> : null}
      {(view.present?.confirmations ?? []).map(c => <Text key={`confirmed:${c}`}>{c}</Text>)}
    </Box>
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      list: async p => (await $.fs.list(p)).map(f => f.name),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    try {
      polling?.cancel() // a previous session's period in this process
    } catch {
      // already gone
    }
    let reading = false
    polls = 0
    polling = $.clock.every(POLL_MS, async () => {
      if (reading) return
      reading = true
      try {
        const link = await read($, linkAtom)
        if (link === null || (await read($, degradedAtom))) return
        // SR-367: the open known problems pane follows the register
        // shortcut: no close event, so once opened this reads the register's files each period
        // for the rest of the session; drop the flag on close if the host ever says so
        if ((await read($, paneAtom)).known) await refreshKnown($, io, link)
        polls += 1
        if (polls % LOOPS_EVERY === 0) await refreshLoops($, io, link)
        const moved = await reread(io, link, await read($, viewAtom))
        if (moved === null) return
        const view = await update($, viewAtom, v => ({ ...v, status: moved.status }))
        await refreshPane($, io, link)
      } catch {
        // the band keeps what it drew; the turn's end reads it again
      } finally {
        reading = false
      }
    })
    // SR-126: why the panel cannot reach plumb, said once per session
    const tell = async (u: Unlinked) => {
      const session = await $.session.id()
      const told = await read($, toldAtom)
      if (told !== null && told.session === session) return
      await update($, toldAtom, () => ({ session, why: u.why, retry: plumb.mayLinkLater(u) }))
      $.ui.log(unlinkedLine(u))
    }
    const linked = async (link: PlumbLink) => {
      await update($, linkAtom, () => link)
      const view = await plumb.snapshot(io, link, await read($, viewAtom), false)
      await update($, viewAtom, () => view)
      await refreshKnown($, io, link)
      await refreshLoops($, io, link, true)
    }
    if ((await read($, degradedAtom)) || (await read($, linkAtom)) !== null) return started
    const said = await helloOnce(io)
    if (said.link !== null) {
      await linked(said.link)
      return started
    }
    if (said.unlinked === null) return started // a repository plumb has not adopted: silent
    if (!plumb.mayLinkLater(said.unlinked)) {
      await tell(said.unlinked)
      return started
    }
    // the session-start hook may not have named the interpreter (or retired a resumed
    // session's old panel) yet: try again for a while, without holding up the first prompt,
    // then say why
    let tries = 0
    let busy = false
    const retry = $.clock.every(RETRY_MS, async () => {
      if (busy) return
      busy = true
      try {
        tries += 1
        if ((await read($, degradedAtom)) || (await read($, linkAtom)) !== null) {
          retry.cancel()
          return
        }
        if (tries > RETRIES && tries % RETRIES !== 0) return
        const again = await helloOnce(io)
        if (again.link !== null) {
          retry.cancel()
          await linked(again.link)
        } else if (again.unlinked === null) {
          retry.cancel()
        } else if (!plumb.mayLinkLater(again.unlinked)
            || tries >= (again.unlinked.why === 'refused' ? HELD_RETRIES : RETRIES)) {
          retry.cancel()
          await tell(again.unlinked)
        }
      } catch {
        retry.cancel() // the turn's start tries again
      } finally {
        busy = false
      }
    })
    return started
  }).catch(async ($, e, next) => {
    const result = await next(e)
    try {
      await update($, degradedAtom, () => true)
      $.ui.log(T.degraded)
    } catch {
      // a re-entry: this handler's own $ calls reject; the session goes on
    }
    return result
  })

  on('turn.start', async ($, e, next) => {
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      list: async p => (await $.fs.list(p)).map(f => f.name),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    if (await read($, degradedAtom)) return next(e)
    const session = await $.session.id()
    let link = await read($, linkAtom)
    if (link !== null && link.session !== session) {
      // a /clear: the conversation goes on under a new session id, and no session.start fires
      link = null
      await update($, linkAtom, () => null)
      await update($, viewAtom, () => EMPTY_VIEW)
    }
    const told = await read($, toldAtom)
    // a refusal or a failure already said this session is not retried every turn, unless a
    // later try may link (mayLinkLater)
    const settled = told !== null && told.session === session && told.why !== 'no-python' &&
      told.retry !== true
    if (link === null && !settled) {
      // the session-start hook may only now have said which interpreter runs plumb
      const said = await helloOnce(io)
      if (said.link !== null) {
        const held = said.link
        await update($, linkAtom, () => held)
        // the band draws from now on: plumb's status at once (no process)
        const view = { ...(await read($, viewAtom)), status: await plumb.readStatus(io, held) }
        await update($, viewAtom, () => view)
        link = held
      } else if (said.unlinked !== null) {
        // SR-126: once per session; read again after the hello, which the start's retry may
        // have told meanwhile
        const now = await read($, toldAtom)
        if (now === null || now.session !== session) {
          const why = said.unlinked
          await update($, toldAtom, () => ({ session, why: why.why, retry: plumb.mayLinkLater(why) }))
          $.ui.log(unlinkedLine(why))
        }
      }
    }
    if (link !== null) {
      // the plugin's environment may have been built after the link (a first run): run plumb with
      // the interpreter now named, or the panel keeps an older plumb that lacks the newer fields
      const now = (await plumb.findPython(io, link.root, link.session)).python
      if (now !== null && now !== link.python) {
        link = { ...link, python: now }
        const relinked = link
        await update($, linkAtom, () => relinked)
      }
      await plumb.heartbeat(io, link)
    }
    return next(e)
  }).catch(async ($, e, next) => {
    const result = await next(e)
    try {
      await update($, degradedAtom, () => true)
      $.ui.log(T.degraded)
    } catch {
      // a re-entry: this handler's own $ calls reject; the turn goes on
    }
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result // a subagent's turn: the owner's band waits
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      list: async p => (await $.fs.list(p)).map(f => f.name),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    if (await read($, degradedAtom)) return result
    const link = await read($, linkAtom)
    if (link === null) return result
    // SR-337 EX-2: a hidden band stays hidden, whatever arrives, until the owner presses Show
    const view = await plumb.snapshot(io, link, await read($, viewAtom), true)
    await update($, viewAtom, () => view)
    await refreshKnown($, io, link)
    await refreshLoops($, io, link, true)
    return result // the answer is never rewritten; no summary line is added (realign a)
  }).catch(async ($, e, next) => {
    const result = await next(e)
    try {
      await update($, degradedAtom, () => true)
      $.ui.log(T.degraded)
    } catch {
      // a re-entry: this handler's own $ calls reject; the turn's answer still stands
    }
    return result
  })

  // SR-291: `plumb intent progress` runs in the agent's shell (Bash, PowerShell or any tool that
  // runs a command); the band's status (files only, no process) is read again after each, so the
  // strip and the bar move within the turn, and a `plumb study add` is announced at once (SR-294)
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    try {
      const command = (e as { command?: unknown }).command
      if (typeof command !== 'string' || !/\b(intent|study)\b/.test(command) ||
        (await read($, degradedAtom))) return ran
      const link = await read($, linkAtom)
      if (link === null) return ran
      const io: Io = {
        exists: p => $.fs.exists(p),
        read: async p => String(await $.fs.read(p)),
        list: async p => (await $.fs.list(p)).map(f => f.name),
        write: (p, t) => $.fs.write(p, t),
        run: (argv, init) => $.process.run(argv, init),
        root: () => $.session.root(),
        id: () => $.session.id(),
        now: () => $.clock.now(),
        env: async () => ({}),
      }
      const moved = await reread(io, link, await read($, viewAtom))
      if (moved === null) return ran
      const view = await update($, viewAtom, v => ({ ...v, status: moved.status }))
      await refreshPane($, io, link)
    } catch {
      // the band keeps what it drew; the turn's end reads it again
    }
    return ran
  })

  // every Button the panel draws: what it does, by its key
  on('ui.press', async ($, e, next) => {
    if (e.plugin !== 'plumb') return next(e)
    // the pressed Button's handler first, while its drawing still holds it: the work below
    // redraws the band, and a Button it takes away (an idea's depths) frees its handle
    const pressed = await next(e)
    const key = e.element
    const view = await read($, viewAtom)
    if (key === 'hide') {
      await update($, bandAtom, b => ({ ...b, isHidden: true }))
      return pressed
    }
    if (key === 'show') {
      await update($, bandAtom, b => ({ ...b, isHidden: false }))
      return pressed
    }
    if (key === 'studies') {
      await update($, bandAtom, b => ({ ...b, studies: !b.studies })) // opens or closes the menu
      return pressed
    }
    if (key === 'idea') {
      await update($, bandAtom, b => ({ ...b, idea: !b.idea })) // shows or hides the choices
      return pressed
    }
    if (key === 'idea:next') {
      // SR-369: the next waiting idea comes to the front
      const ideas = view.status?.ideas ?? []
      await update($, bandAtom, b => ({ ...b, front: nextIdea(ideas, b) }))
      return pressed
    }
    if (key.startsWith('loops:type:')) {
      await update($, paneAtom, p => ({ ...p, loops: { type: key.slice('loops:type:'.length), open: [] } }))
      return pressed
    }
    if (key.startsWith('loops:row:')) {
      // SR-393 EX-3: Enter on a row shows its detail, or folds it again
      const row = key.slice('loops:row:'.length)
      await update($, paneAtom, p => {
        const open = p.loops?.open ?? []
        return { ...p, loops: { type: p.loops?.type ?? 'intent', open: open.includes(row) ? open.filter(o => o !== row) : [...open, row] } }
      })
      return pressed
    }
    const link = await read($, linkAtom)
    if (link === null || (await read($, degradedAtom))) return pressed
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      list: async p => (await $.fs.list(p)).map(f => f.name),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    if (key === 'loop') {
      // SR-305: the loop as plumb knows it, in the docked pane; Esc closes it, the band stays
      const loop = await plumb.loopPane(io, link)
      if (loop === null) return pressed
      await update($, paneAtom, p => ({ ...p, loop }))
      await $.ui.open({ id: PANE, title: T.loopTitle, columns: PANE_COLUMNS, closeOnEscape: true })
      return pressed
    }
    if (key === 'loops') {
      // SR-393 EX-2: the project's loops in their own docked pane, on the intent type
      await refreshLoops($, io, link, true)
      await update($, paneAtom, p => ({ ...p, loops: { type: LOOP_TYPES[0]!, open: [] } }))
      await $.ui.open({ id: LOOPS_PANE, title: T.loopsTitle, columns: PANE_COLUMNS, closeOnEscape: true })
      return pressed
    }
    if (key === 'known') {
      // SR-367 EX-2: the known problems in their own docked pane, opened as the loop's is
      await refreshKnown($, io, link)
      await update($, paneAtom, p => ({ ...p, known: true }))
      await $.ui.open({ id: KNOWN_PANE, title: T.knownTitle, columns: PANE_COLUMNS, closeOnEscape: true })
      return pressed
    }
    let line = ''
    if (key === 'study' || key.startsWith('study:')) {
      // SR-294 EX-3, EX-4, EX-6: the room opens on the study, which is marked opened, so it leaves
      // the band; a choice from the menu closes the menu
      const slug = key === 'study' ? view.status?.studySlug : key.slice('study:'.length)
      if (key !== 'study') await update($, bandAtom, b => ({ ...b, studies: false }))
      if (!slug) return pressed
      const ran = await plumb.room(io, link, slug)
      line = ran.ok ? '' : T.roomFailed
    } else if (key.startsWith('loops:reopen:')) {
      // SR-394: the press opens a new session on the idle loop; plumb's line says it or gives the command
      const ran = await plumb.reopen(io, link, key.slice('loops:reopen:'.length))
      line = String(ran.data?.line ?? '') || T.reopenFailed
    } else if (key === 'idea:md' || key === 'idea:diagrams' || key === 'idea:video' || key === 'idea:none') {
      // SR-294 EX-8, EX-9: the owner's choice on the idea is recorded; the room stays closed
      const idea = frontIdea(view.status?.ideas ?? [], await read($, bandAtom))
      await update($, bandAtom, b => ({ ...b, idea: false }))
      if (!idea) return pressed
      const ran = await plumb.chooseStudy(io, link, idea.slug, key.slice('idea:'.length))
      line = ran.ok ? '' : T.chooseFailed
    } else if (key === 'refresh:yes' || key === 'refresh:no') {
      // SR-360 EX-2: the owner's yes asks the agent to rewrite the study; 'not now' leaves it marked
      const outdated = (view.status?.outdated ?? []).at(-1)
      if (!outdated) return pressed
      const ran = await plumb.refreshStudy(io, link, outdated.slug, key === 'refresh:yes')
      line = ran.ok ? '' : T.refreshFailed
    } else {
      return pressed
    }
    // the owner's notice (the model never reads it), its own row; a toast says it now (SP7 5.4,
    // SR-087 EX-3)
    if (line) {
      $.ui.toast(line)
      await $.session.append({ message: { type: 'system', content: [{ type: 'text', text: line }] } })
    }
    const drawn = await plumb.snapshot(io, link, { ...view, line }, false)
    await update($, viewAtom, () => drawn)
    if (key.startsWith('idea:') || key.startsWith('study:') || key.startsWith('refresh:')) {
      // a choice takes its lines away: the band keeps its head line, the ring back on Hide
      await $.ui.focus({ requestId: e.requestId, key: 'hide' }).catch(() => undefined)
      await $.ui.scroll({ in: e.requestId, to: 'start' }).catch(() => undefined)
    }
    return pressed
  })

  // SR-369: Tab onto the band's idea count brings the next idea to the front, wrapping from the
  // last to the first; the ring stays on the idea, so each Tab moves one idea on
  on('ui.focus', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.plugin !== 'plumb' || e.element !== 'idea:next') return next(e)
    const ideas = (await read($, viewAtom)).status?.ideas ?? []
    await update($, bandAtom, b => ({ ...b, front: nextIdea(ideas, b) }))
    return {}
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    if ((await read($, degradedAtom)) || (await read($, linkAtom)) === null) return next(e)
    const view = await read($, viewAtom)
    const ui = uiOf($, e)
    let theme: unknown
    try {
      theme = (await $.config.list()).find(row => row.key === 'theme')?.value
    } catch {
      // a surface without the settings rows: the dark shade
    }
    return drawBand(ui, view, await read($, bandAtom), (await read($, knownAtom)).open, await read($, loopsAtom), e.props.bodyColumns,
      plumbColor(theme), brassColor(theme))
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = uiOf($, e)
    const pane = await read($, paneAtom)
    // the pane shows only the intent loop (SR-305, SR-337); it closes when the loop ends
    if (!pane.loop) return <ui.Box flexDirection="column" />
    let theme: unknown
    try {
      theme = (await $.config.list()).find(row => row.key === 'theme')?.value
    } catch {
      // a surface without the settings rows: the dark shade
    }
    return loopPane(ui, pane.loop, plumbColor(theme), brassColor(theme))
  })

  on('ui.render', { component: 'Pane', requestId: KNOWN_PANE }, async ($, e) => {
    const ui = uiOf($, e)
    let theme: unknown
    try {
      theme = (await $.config.list()).find(row => row.key === 'theme')?.value
    } catch {
      // a surface without the settings rows: the dark shade
    }
    return knownPane(ui, await read($, knownAtom), plumbColor(theme))
  })

  on('ui.render', { component: 'Pane', requestId: LOOPS_PANE }, async ($, e) => {
    const ui = uiOf($, e)
    let theme: unknown
    try {
      theme = (await $.config.list()).find(row => row.key === 'theme')?.value
    } catch {
      // a surface without the settings rows: the dark shade
    }
    const state = (await read($, paneAtom)).loops ?? { type: LOOP_TYPES[0]!, open: [] }
    return loopsPane(ui, await read($, loopsAtom), state, plumbColor(theme))
  })
}
