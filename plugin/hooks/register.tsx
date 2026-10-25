// plumb's mod (SP7 5 as re-aligned by sp7-realign-sp8; SR-085, SR-087, SR-116, SR-337): the
// band above the prompt (plumb's status with the count of questions waiting, SP8's progress, the
// intent loop's and the studies' lines; no card), the loop pane, the owner's notice after a
// press, and the fallback. plumb's command hooks keep doing the work (DEC-024): while this panel
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

import type { PlumbBand, PlumbLink, PlumbLoop, PlumbLoopPane, PlumbTold, PlumbView } from '../types'
import * as plumb from './plumb'
import type { Hello, Io, Unlinked } from './plumb'
import { brassColor, GLYPHS, plumbColor, RED, T } from './text'

/** The surface's element table, as `$.ui.resolve(e)` answers it. */
type Ui = { Box: any; Text: any; Button: any }

const uiOf = ($: any, e: any): Ui => $.ui.resolve(e)

const PANE = 'plumb-loop'
const EMPTY_VIEW: PlumbView = { present: null, status: null, line: '' }
const BAND: PlumbBand = { isHidden: false }

const linkAtom = atom({ plugin: 'plumb', key: 'link' } as const, null)
const degradedAtom = atom({ plugin: 'plumb', key: 'degraded' } as const, false)
const toldAtom = atom({ plugin: 'plumb', key: 'told' } as const, null as PlumbTold | null)
const viewAtom = atom({ plugin: 'plumb', key: 'view' } as const, EMPTY_VIEW)
const bandAtom = atom({ plugin: 'plumb', key: 'band' } as const, BAND)
const paneAtom = atom({ plugin: 'plumb', key: 'pane' } as const, { loop: null as PlumbLoopPane | null })

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

// SR-291 EX-7: a workflow's agents raise no event in the owner's session, so the band reads
// its files again on this period (the mod API has no file watch)
const POLL_MS = 2000
let polling: { cancel: () => void } | null = null

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

/** The band: one line of status, then the loop's and the studies' lines; no card (SR-337). */
function drawBand(ui: Ui, view: PlumbView, band: PlumbBand, columns: number, color: string, brass: string) {
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
  const idea = (view.status?.ideas ?? []).at(-1) // DEC-207: the newest idea waiting for a choice
  const outdated = (view.status?.outdated ?? []).at(-1)
  return (
    <Box flexDirection="column" width={columns}>
      <Box flexDirection="row" gap={1}>
        <Text bold color={color}>{head}</Text>
        {view.status?.summary ? <Text dimColor>{view.status.summary}</Text> : null}
        <Button key="hide" label={T.hide} plain onPress={() => {}} />
        {!loop && studies.length ? (
          // SR-294 EX-5 (DEC-183): no loop open, the study folds into the one line; a press opens its menu
          <Button key="studies" plain onPress={() => {}}>
            <Text key="head:studies" color={brass}>{T.newStudies(studies.length)}</Text>
          </Button>
        ) : null}
        {!loop && idea ? (
          // DEC-183 style: no loop open, the idea folds into the one line too
          <Button key="idea" plain onPress={() => {}}>
            <Text key="head:idea" color={brass}>{T.studyIdeaFolded}</Text>
          </Button>
        ) : null}
      </Box>
      {(view.status?.red ?? []).map((r, n) => <Text key={`red:${n}`} color={RED}>{r}</Text>)}
      {(view.status?.setAside ?? []).map((a, n) => <Text key={`aside:${n}`} dimColor>{a}</Text>)}
      {view.status?.roomCard ? (
        // SR-333 EX-3, DEC-294: the question the owner chose to study; a press opens the room on it
        <Button key="roomq" plain onPress={() => {}}>
          <Text key="line:roomq" color={brass}>{T.roomWaits}</Text>
        </Button>
      ) : null}
      {outdated ? (
        // SR-360 EX-2, DEC-336: a study whose records changed; nothing is rewritten without the yes
        <Box key="outdated" flexDirection="row" gap={1}>
          <Text key="line:outdated" color={brass}>{T.outOfDate(outdated.title, outdated.changed)}</Text>
          <Button key="refresh:yes" label={T.rewrite} onPress={() => {}} />
          <Button key="refresh:no" label={T.notNow} onPress={() => {}} />
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
          {idea ? (
            // SR-294: the agent's study idea; a press shows its choices
            <Button key="idea" plain onPress={() => {}}>
              <Text key="loop:idea" color={brass}>{T.studyIdea(idea.title)}</Text>
            </Button>
          ) : null}
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
    polling = $.clock.every(POLL_MS, async () => {
      if (reading) return
      reading = true
      try {
        const link = await read($, linkAtom)
        if (link === null || (await read($, degradedAtom))) return
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
      await update($, paneAtom, () => ({ loop }))
      await $.ui.open({ id: PANE, title: T.loopTitle, columns: PANE_COLUMNS, closeOnEscape: true })
      return pressed
    }
    let line = ''
    if (key === 'roomq') {
      // SR-333 EX-3: the room opens on the question, which leaves the band
      const card = view.status?.roomCard
      if (!card) return pressed
      const ran = await plumb.roomQuestion(io, link, card)
      line = ran.ok ? '' : T.roomQuestionFailed
    } else if (key === 'study' || key.startsWith('study:')) {
      // SR-294 EX-3, EX-4, EX-6: the room opens on the study, which is marked opened, so it leaves
      // the band; a choice from the menu closes the menu
      const slug = key === 'study' ? view.status?.studySlug : key.slice('study:'.length)
      if (key !== 'study') await update($, bandAtom, b => ({ ...b, studies: false }))
      if (!slug) return pressed
      const ran = await plumb.room(io, link, slug)
      line = ran.ok ? '' : T.roomFailed
    } else if (key === 'idea:md' || key === 'idea:diagrams' || key === 'idea:none') {
      // SR-294 EX-8, EX-9: the owner's choice on the idea is recorded; the room stays closed
      const idea = (view.status?.ideas ?? []).at(-1)
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
    return drawBand(ui, view, await read($, bandAtom), e.props.bodyColumns, plumbColor(theme), brassColor(theme))
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
}
