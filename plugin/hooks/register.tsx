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

import type { PlumbBand, PlumbKnown, PlumbLink, PlumbLoop, PlumbLoopPane, PlumbLoopRow, PlumbLoops, PlumbLoopsPane, PlumbPane, PlumbStatus, PlumbTold, PlumbView } from '../types'
import * as plumb from './plumb'
import type { Hello, Io, Unlinked } from './plumb'
import { brassColor, GLYPHS, plumbColor, RED, T } from './text'

/** The surface's element table, as `$.ui.resolve(e)` answers it. */
type Ui = { Box: any; Text: any; Button: any; Input: any }

const uiOf = ($: any, e: any): Ui => $.ui.resolve(e)

const PANE = 'plumb-pane' // the one docked pane (SR-410)
const LOOP_TYPES = ['intent', 'debug', 'evaluate']
const EMPTY_VIEW: PlumbView = { present: null, status: null, line: '' }
const BAND: PlumbBand = { isHidden: false }

const linkAtom = atom({ plugin: 'plumb', key: 'link' } as const, null)
const degradedAtom = atom({ plugin: 'plumb', key: 'degraded' } as const, false)
const toldAtom = atom({ plugin: 'plumb', key: 'told' } as const, null as PlumbTold | null)
const viewAtom = atom({ plugin: 'plumb', key: 'view' } as const, EMPTY_VIEW)
const bandAtom = atom({ plugin: 'plumb', key: 'band' } as const, BAND)
const paneAtom = atom({ plugin: 'plumb', key: 'pane' } as const,
  { loop: null as PlumbLoopPane | null, known: false as boolean | undefined, loops: null as PlumbLoopsPane | null | undefined,
    cls: undefined as string | undefined, row: undefined as string | undefined, step: undefined as string | undefined })
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

/** SR-367: the known problems read again when the register or one of its cases moved (files
 * only); plumb runs only then. */
async function refreshKnown($: any, io: Io, link: PlumbLink) {
  const seen = await plumb.knownSeen(io, link)
  if (seen === (await read($, knownAtom)).seen) return
  const known = seen ? await plumb.known(io, link, seen) : plumb.NO_KNOWN
  if (known !== null) await update($, knownAtom, () => known)
}

/** SR-393: the project's loops read again at link and when the pane opens (`force`), and
 * otherwise (the poll, each turn's end) only when the one change stamp moved; plumb runs only then,
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

/** An intent loop's section under the status (SR-291, SR-305): its title (a Button that folds the
 * section to the title alone) with the strip of its steps in plum, each its own Button (done,
 * current, to come; a refused gate marks the current one stopped and names what it waits for),
 * then the current step's task, a brass fill of done over total, or the elapsed time with no
 * fill when the total is unknown. A step's press opens the pane on this loop at that step. */
function loopLines(ui: Ui, loop: PlumbLoop, title: string, folded: boolean, color: string, brass: string) {
  const { Box, Button, Text } = ui
  const task = folded ? null : loop.task
  const filled = task?.total ? Math.round(BAR_CELLS * Math.min(task.done, task.total) / task.total) : 0
  // a workflow phase's gate reports itself (DEC-157): the step, the phase of the script's, the gate
  const words = task?.total && / gate (passed|failed)$/.test(task.label)
    ? `${loop.step} · slice ${task.done}/${task.total} · ${task.label}`
    : [task?.label, task?.total ? `${task?.done}/${task.total}` : task?.elapsed].filter(Boolean).join(' · ')
  return [
    <Box key="loop:head" flexDirection="row" gap={2}>
      <Button key="loop:fold" plain onPress={() => {}}>
        <Text key="loop:title" bold color={color}>{`${folded ? '▸' : '▾'} ${title}`}</Text>
      </Button>
      {folded ? null : LOOP_STEPS.map((s, i) => (
        <Button key={`step:${s}`} plain onPress={() => {}}>
          <Text key={`step:${s}:text`} color={color}>{`${s} ${stepMark(loop, i)}`}</Text>
        </Button>
      ))}
      {folded || !loop.stopped ? null : <Text key="loop:stopped" color={color}>{T.stopped(loop.stopped)}</Text>}
    </Box>,
    task ? (
      <Box key="loop:bar" flexDirection="row" gap={1}>
        {task.total ? <Text key="loop:fill" color={brass}>{'█'.repeat(filled) + '░'.repeat(BAR_CELLS - filled)}</Text> : null}
        <Text key="loop:task">{words}</Text>
      </Box>
    ) : null,
  ]
}

/** A loop row's steps with their marks, each pressable, and the shown step's details (SR-305,
 * DEC-512): its gate, the low findings left and, for the current step, the tasks done and left. */
function stepsOf(ui: Ui, r: PlumbLoopRow, shown: string | undefined, color: string): any[] {
  const { Button, Text } = ui
  const mark = (m: string) => (m === 'done' ? '✓' : m === 'current' ? '●' : '○')
  return (r.steps ?? []).flatMap(st => {
    const low = st.findings ? ` · ${T.lowLeft(st.findings)}` : ''
    const line = <Button key={`step:${st.name}`} plain onPress={() => {}}>
      <Text key={`step:${st.name}:text`} bold={st.name === shown} color={color}>{cutTo(`${mark(st.mark)} ${st.name} · ${st.gate}${low}`)}</Text>
    </Button>
    if (st.name !== shown) return [line]
    const tasks = st.mark === 'current' && r.tasks?.total ? [`${r.tasks.done} of ${r.tasks.total} tasks done`,
      ...(r.tasks.left.length ? [T.tasksLeft(r.tasks.left)] : [])] : []
    return [line, ...[`gate ${st.gate}`, ...st.left.map(l => `low finding: ${l}`), ...tasks]
      .map((d, n) => <Text key={`step:${st.name}:d${n}`} dimColor>{cutTo(`    ${d}`)}</Text>)]
  })
}

/** One row of the pane's class (SR-410): folded it is one line, glyph, title, short state;
 * expanded, the title in bold plum, 2-4 dim detail lines and the actions row. */
type Row = { id: string; glyph: string; title: string; state: string; live: boolean; details: string[]; actions: any[]; color?: string; extra?: any[] }

const CLASSES = ['loops', 'studies', 'problems', 'judge', 'build']

/** a line cut to the pane's width with an ellipsis: nothing wraps (SR-410 EX-5) */
const cutTo = (t: string, n = PANE_COLUMNS) => (t.length > n ? `${t.slice(0, n - 1)}…` : t)

/** The pane's class counts, as its switch names them (SR-410). */
function classCounts(view: PlumbView, loops: PlumbLoops, known: PlumbKnown): Record<string, number> {
  const st = view.status
  return { loops: loops.live + loops.idle,
    studies: (st?.ideas?.length ?? 0) + (st?.studies?.length ?? 0) + (st?.writing ? 1 : 0) + (st?.outdated?.length ?? 0),
    problems: known.open,
    judge: (st?.judgeLines?.length ?? 0) + (st?.setAside?.length ?? 0), build: (st?.buildLines?.length ?? 0) + (st?.unchecked ? 1 : 0) }
}

/** The problems class's rows (SR-412): open ones first, fixed dim below; expanded, symptom, cause, fix, history. */
function problemRows(known: PlumbKnown): Row[] {
  return [...known.issues].sort((a, b) => Number(b.state === 'open') - Number(a.state === 'open')).map(i => ({
    id: i.id, glyph: i.state === 'open' ? '●' : '○', title: i.title, live: i.state === 'open',
    state: T.knownState(i.state, i.fixed),
    details: [T.knownSymptom(i.symptom), T.knownCause(i.cause), T.knownFix(i.fix), T.knownHistory(i.history.join('; '))].map(d => d.trim()),
    actions: [],
  }))
}

/** The build class's rows (SR-413): each misalignment red, expanded to the fix; "could not check" in plain colour. */
function buildRows(st: PlumbStatus | undefined): Row[] {
  const row = (id: string, line: string, color?: string): Row =>
    ({ id, glyph: '●', title: line, state: '', live: true, details: [line], actions: [], color })
  return [...(st?.buildLines ?? []).map((l, i) => row(`build:${i}`, l, RED)), ...(st?.unchecked ? [row('build:unchecked', st.unchecked)] : [])]
}

/** The judge class's rows (SR-413): a judge that cannot settle red with its cause; a set-aside question in plum, expanded to why. */
function judgeRows(st: PlumbStatus | undefined, plum: string): Row[] {
  const row = (id: string, line: string, color: string): Row => {
    const m = /^(.*?) \((.*)\)$/.exec(line)
    return { id, glyph: '●', title: m ? m[1]! : line, state: '', live: true, details: [m ? m[2]! : line], actions: [], color }
  }
  return [...(st?.judgeLines ?? []).map((l, i) => row(st?.judgeNames?.[i] ?? String(i), l, RED)), ...(st?.setAside ?? []).map((l, i) => row(`aside:${i}`, l, plum))]
}

/** The loops class's rows (SR-410): the type shown, this session's loop first, live before idle. */
function loopRows(ui: Ui, loops: PlumbLoops, state: PlumbLoopsPane, session: string, color: string, step?: string): Row[] {
  const { Button, Input, Text } = ui
  return loops.rows.filter(r => r.kind === state.type)
    .sort((a, b) => Number(b.live) - Number(a.live) || Number(b.session === session) - Number(a.session === session))
    .map(r => ({
      id: r.id, glyph: r.live ? '●' : '○', title: r.goal, live: r.live,
      state: r.live ? r.progress : `${r.progress} · ${T.loopsIdleSince(r.idle_since)}`,
      // the message state outranks the branch when the four lines run out (SR-395, DEC-515)
      details: [T.loopDone(r.done), T.loopLeft(r.left), r.waits ? T.loopWaits(r.waits) : '',
        r.message ? T.loopMessage(r.message.state) : '', T.loopBranch(r.branch)].filter(Boolean).slice(0, 4).map(d => d.trim()),
      extra: stepsOf(ui, r, step, color),
      actions: [
        r.live || (r.reopen ?? true) ? (
          <Button key="act:reopen" plain onPress={() => {}}>
            <Text key="act:reopen:text" color={color}>{r.live ? T.loopsShow : T.loopsReopen}</Text>
          </Button>
        ) : null,
        // SR-395 EX-6: a surface that draws no Input says to tell the agent instead
        // (Input is a proxy, always truthy: a surface without one draws it as a fragment, so the line is always drawn)
        !(r.send ?? r.live) ? null : <Input key={`loops:say:${r.id}`} placeholder={T.loopSay} submitLabel={T.loopSend} onSubmit={() => {}} />,
        !(r.send ?? r.live) ? null : <Text key={`loops:tell:${r.id}`} dimColor>{T.loopTell}</Text>,
      ],
    }))
}

/** The one docked pane (SR-410): the class switch with counts (the shown one bold), the loops
 * class's type switch, then the class's rows, live first, the rest dim; an Enter expands one row.
 * Never an agent or tokens. */
function classPane(ui: Ui, view: PlumbView, loops: PlumbLoops, known: PlumbKnown, pane: PlumbPane, session: string, color: string,
                   brass: string) {
  const { Box, Button, Text } = ui
  const cls = pane.cls ?? CLASSES[0]!
  const counts = classCounts(view, loops, known)
  const state = pane.loops ?? { type: LOOP_TYPES[0]!, open: [] }
  const rows = cls === 'loops' ? loopRows(ui, loops, state, session, color, pane.step) : cls === 'problems' ? problemRows(known)
    : cls === 'judge' ? judgeRows(view.status ?? undefined, color) : cls === 'build' ? buildRows(view.status ?? undefined) : []
  // expanded, the title stays the row's Button: Enter on it folds the row again
  const fold = (r: Row) => {
    const line = cutTo(r.state ? `${r.glyph} ${r.title} · ${r.state}` : `${r.glyph} ${r.title}`)
    return r.id === pane.row ? (
      <Box key={`row:${cls}:${r.id}:open`} flexDirection="column">
        <Button key={`row:${cls}:${r.id}`} plain onPress={() => {}}>
          <Text key={`row:${cls}:${r.id}:title`} bold color={'color' in r ? r.color : color}>{cutTo(r.title)}</Text>
        </Button>
        {r.details.map((d, n) => <Text key={`row:${cls}:${r.id}:d${n}`} dimColor>{cutTo(`  ${d}`)}</Text>)}
        {r.extra}
        <Box key={`row:${cls}:${r.id}:actions`} flexDirection="row" gap={1}>{r.actions}</Box>
      </Box>
    ) : (
      <Button key={`row:${cls}:${r.id}`} plain onPress={() => {}}>
        <Text key={`row:${cls}:${r.id}:text`} dimColor={!r.live} color={r.color}>{line}</Text>
      </Button>
    )
  }
  return (
    <Box flexDirection="column">
      <Box key="class:switch" flexDirection="row" gap={1}>
        {CLASSES.map(c => (
          <Button key={`class:${c}`} plain onPress={() => {}}>
            <Text key={`class:${c}:text`} bold={c === cls} color={color}>{`${c} ${counts[c]}`}</Text>
          </Button>
        ))}
      </Box>
      {cls === 'loops' ? (
        <Box key="loops:switch" flexDirection="row" gap={1}>
          {LOOP_TYPES.map(t => (
            <Button key={`loops:type:${t}`} plain onPress={() => {}}>
              <Text key={`loops:label:${t}`} bold={t === state.type} color={color}>
                {T.loopsType(t === state.type, t, loops.counts[t]?.live ?? 0, loops.counts[t]?.idle ?? 0)}
              </Text>
            </Button>
          ))}
        </Box>
      ) : null}
      {cls === 'studies' ? studiesClass(ui, view.status ?? undefined, fold, brass)
        : rows.length ? rows.map(fold) : <Text key="none" dimColor>{cls === 'loops' ? T.loopsNone[state.type] : ''}</Text>}
    </Box>
  )
}

/** The studies class of the pane (SR-411): sections ideas, new, writing (its bar), out of date and
 * read (dim), each row folded by the pane's `fold`; an action acts on the expanded row only. */
function studiesClass(ui: Ui, st: PlumbStatus | undefined, fold: (r: Row) => any, brass: string) {
  const { Button, Text } = ui
  const act = (k: string, label: string) => <Button key={`act:${k}`} label={label} onPress={() => {}} />
  const row = (s: { slug: string; title: string }, glyph: string, state: string, live: boolean, details: string[], actions: any[]): Row =>
    ({ id: s.slug, glyph, title: s.title, state, live, details, actions, color: live ? brass : undefined })
  const outdated = st?.outdated ?? []
  const w = st?.writing
  const sections: [string, any[]][] = [
    ['ideas', (st?.ideas ?? []).map(i => fold(row(i, '?', T.studyIdeaState, true, [i.why], [
      ...['md', 'diagrams', 'video'].map(d => act(d === 'md' ? 'text' : d, T.depths[d]! + (i.recommend === d ? T.recommended : ''))),
      act('notnow', T.notNow)])))],
    ['new', (st?.studies ?? []).map(s => fold(row(s, '●', T.studyNewState, true, [], [act('room', T.openInRoom)])))],
    ['writing', w ? [
      <Text key="studies:writing" color={brass}>{cutTo(`… ${w.title} · ${w.step || 'starting'}`)}</Text>,
      <Text key="studies:writing:bar" color={brass}>{writingBar(w.done ?? 0, w.total ?? 0)}</Text>,
    ] : []],
    ['outdated', outdated.map(s => fold(row(s, '!', T.studyOutdatedState(s.changed), true, [T.outOfDate(s.title, s.changed)],
      [act('rewrite', T.rewrite), act('notnow', T.notNow)])))],
    // an opened study whose records changed is listed out of date, not twice
    ['read', (st?.read ?? []).filter(s => !outdated.some(o => o.slug === s.slug)).map(s => fold(row(s, '·', T.studyReadState, false, [], [])))],
  ]
  return sections.flatMap(([k, items]) => items.length ? [<Text key={`studies:head:${k}`} bold>{T.studySection[k]}</Text>, ...items] : [])
}

/** SR-291's bar for a study being written: five cells and the percent; the empty track before a step count. */
function writingBar(done: number, total: number): string {
  if (!total) return '━'.repeat(5)
  const f = Math.min(done, total) / total
  const n = Math.round(5 * f)
  return `${'█'.repeat(n)}${'━'.repeat(5 - n)} ${Math.round(100 * f)}%`
}

/** The band: one line of status, then the loop's and the studies' lines; no card (SR-337). The
 * known problems are one line when any is open, never one per problem (SR-367). */
function drawBand(ui: Ui, view: PlumbView, band: PlumbBand, known: number, loops: PlumbLoops, columns: number, color: string,
                  brass: string, session: string) {
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
  const st = view.status
  // SR-409: one chip per class that has something; brass wants a choice, plum informs, red is broken
  const waiting = (st?.ideas?.length ?? 0) + (st?.studies?.length ?? 0) + (st?.outdated?.length ?? 0)
  const buildN = (st?.buildLines?.length ?? 0) + (st?.unchecked ? 1 : 0)
  const judgeN = (st?.judgeLines?.length ?? 0) + (st?.setAside?.length ?? 0)
  const chips = [
    loops.live + loops.idle > 0 ? { key: 'loops', text: T.loopsLive(loops.live, loops.idle), color } : null,
    waiting || st?.writing ? { key: 'studies', text: waiting ? T.studiesChip(waiting) : T.studiesWriting, color: waiting ? brass : color } : null,
    known > 0 ? { key: 'problems', text: T.problemsChip(known), color } : null,
    judgeN ? { key: 'judge', text: T.judgeChip(judgeN), color: st?.judgeLines?.length ? RED : color } : null,
    buildN ? { key: 'build', text: T.buildChip(buildN), color: st?.buildLines?.length ? RED : undefined } : null,
  ]
  return (
    <Box flexDirection="column" width={columns}>
      <Box flexDirection="row" gap={1}>
        <Text bold color={color}>{head}</Text>
        {st?.summary ? <Text dimColor>{st.summary}</Text> : null}
        {chips.map(c => c ? (
          <Button key={`chip:${c.key}`} plain onPress={() => {}}>
            <Text color={c.color}>{c.text}</Text>
          </Button>
        ) : null)}
        <Button key="hide" label={T.hide} plain onPress={() => {}} />
      </Box>
      {loop ? loopLines(ui, loop, loops.rows.find(r => r.kind === 'intent' && r.session === session)?.goal || T.loopTitle,
        band.loopFolded === true, color, brass) : null}
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
        await update($, viewAtom, v => ({ ...v, status: moved.status }))
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
    await refreshLoops($, io, link) // only when the stamp moved: a listing costs seconds
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
      await update($, viewAtom, v => ({ ...v, status: moved.status }))
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
    if (key === 'loop:fold') {
      await update($, bandAtom, b => ({ ...b, loopFolded: !b.loopFolded }))
      return pressed
    }
    if (key.startsWith('step:') && e.component === 'Pane') {
      await update($, paneAtom, p => ({ ...p, step: p.step === key.slice('step:'.length) ? undefined : key.slice('step:'.length) }))
      return pressed
    }
    if (key.startsWith('loops:type:')) {
      await update($, paneAtom, p => ({ ...p, row: undefined, loops: { type: key.slice('loops:type:'.length), open: [] } }))
      return pressed
    }
    if (key.startsWith('class:')) {
      // SR-410: a press on the switch selects a class (the arrows land in the ui.focus hook below)
      await update($, paneAtom, p => ({ ...p, row: undefined, cls: key.slice('class:'.length) }))
      return pressed
    }
    if (key.startsWith('row:')) {
      // SR-410: Enter expands one row, or folds it again
      const row = key.split(':').slice(2).join(':')
      await update($, paneAtom, p => ({ ...p, step: undefined, row: p.row === row ? undefined : row }))
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
    // the chips, the loop's strip and the old known/loops buttons all open the one pane on their class
    if (key.startsWith('step:')) {
      // SR-305: the band's step opens the pane on this session's loop at that step; plumb lists
      // the loops now, stamp or none, for the row to expand
      const stamp = (await read($, loopsAtom)).stamp || await plumb.loopsStamp(io, link.root)
      const listed = await plumb.loops(io, link, stamp, await plumb.loopsSeen(io, stamp))
      if (listed !== null) await update($, loopsAtom, () => listed)
      const mine = (listed ?? await read($, loopsAtom)).rows.find(r => r.kind === 'intent' && r.session === link.session)
      await refreshKnown($, io, link)
      await update($, paneAtom, p => ({ ...p, known: true, cls: 'loops', row: mine?.id, step: key.slice('step:'.length), loops: { type: 'intent', open: [] } }))
      await $.ui.open({ id: PANE, title: T.paneTitle, columns: PANE_COLUMNS, closeOnEscape: true })
      return pressed
    }
    const opens = key.startsWith('chip:') ? key.slice('chip:'.length) : key === 'known' ? 'problems' : key
    if (CLASSES.includes(opens)) {
      await refreshLoops($, io, link, true)
      await refreshKnown($, io, link)
      await update($, paneAtom, p => ({ ...p, known: true, cls: opens, row: undefined, loops: p.loops ?? { type: LOOP_TYPES[0]!, open: [] } }))
      await $.ui.open({ id: PANE, title: T.paneTitle, columns: PANE_COLUMNS, closeOnEscape: true })
      return pressed
    }
    let line = ''
    const pane = await read($, paneAtom)
    if (key.startsWith('act:') && pane.cls === 'studies' && pane.row) {
      // SR-411: an action acts on the expanded row only; the room opens on the press alone
      const slug = pane.row
      const act = key.slice('act:'.length)
      const outdated = (view.status?.outdated ?? []).some(s => s.slug === slug)
      if (act === 'room') {
        const ran = await plumb.room(io, link, slug) // EX-3: marked opened, the row moves to read
        line = ran.ok ? '' : T.roomFailed
      } else if (act === 'rewrite' || (act === 'notnow' && outdated)) {
        const ran = await plumb.refreshStudy(io, link, slug, act === 'rewrite') // EX-4: not now leaves it marked
        line = ran.ok ? '' : T.refreshFailed
      } else {
        const ran = await plumb.chooseStudy(io, link, slug, act === 'notnow' ? 'none' : act === 'text' ? 'md' : act) // EX-2
        line = ran.ok ? '' : T.chooseFailed
      }
    } else if (key === 'act:reopen' && pane.cls === 'loops' && pane.row) {
      // SR-394: the press opens a new session on the expanded idle loop; plumb's line says it or gives the command
      const ran = await plumb.reopen(io, link, pane.row)
      line = String(ran.data?.line ?? '') || plumb.refusal(ran) || T.reopenFailed
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
    return pressed
  })

  // SR-395: the owner typed a message on a working loop's row: plumb queues it for that session
  on('ui.input', async ($, e, next) => {
    const result = await next(e)
    if (e.plugin !== 'plumb' || e.kind !== 'submit' || !e.element.startsWith('loops:say:')) return result
    const link = await read($, linkAtom)
    if (link === null || (await read($, degradedAtom)) || !e.value.trim()) return result
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
    const ran = await plumb.send(io, link, e.element.slice('loops:say:'.length), e.value)
    if (!ran.ok) $.ui.toast(plumb.refusal(ran) || T.sendFailed)
    await refreshLoops($, io, link, true) // the row now reads sent, not read yet
    return result
  }).catch(($, e, next) => next(e))

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
      plumbColor(theme), brassColor(theme), (await read($, linkAtom))?.session ?? '')
  }).catch(($, e, next) => next(e))

  // SR-410 EX-4: the arrows move the ring across the switch; landing on a class shows it
  on('ui.focus', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    if (e.plugin === 'plumb' && e.origin.kind === 'person' && e.element?.startsWith('class:')) {
      const cls = e.element.slice('class:'.length)
      await update($, paneAtom, p => (p.cls === cls ? p : { ...p, row: undefined, cls }))
    }
    return {}
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = uiOf($, e)
    let theme: unknown
    try {
      theme = (await $.config.list()).find(row => row.key === 'theme')?.value
    } catch {
      // a surface without the settings rows: the dark shade
    }
    const link = await read($, linkAtom)
    return classPane(ui, await read($, viewAtom), await read($, loopsAtom), await read($, knownAtom), await read($, paneAtom),
      link?.session ?? '', plumbColor(theme), brassColor(theme))
  })
}
