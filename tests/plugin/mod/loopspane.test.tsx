// The loops count and pane (SR-393): the band's first line says how many loops are worked on in
// the project, whether or not this session has one, and never grows a line for them; its press
// opens plumb's docked pane on the project's loops, one type at a time (intent, debug, evaluate)
// behind a switch always in view; Enter on a row shows its detail; the pane follows the answer
// of `plumb mod loops`, which plumb is asked again only when the one change stamp moved. The
// known problems line and the loop pane stay as they are. Each case runs on the terminal and
// the desktop.
import { describe, expect } from 'claude-code/testing'

import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, test, world } from './harness'

const STAMP = `${ROOT}/.git/plumb-loops.stamp`
const LOOP = `${ROOT}/.plumb/session/${SESSION}/intent/aaaaaaaaaaaa.json`
const PROBLEMS = [{ id: 'KI-1', title: 'a known problem' }]

const row = (kind: string, id: string, goal: string, progress: string, over: Record<string, unknown> = {}) => ({
  kind, id, goal, goal_full: `${goal}, in full`, progress, done: [], left: [], waits: '', live: true,
  state: 'working', last: '2026-10-11T11:59:00Z', idle_since: '', branch: 'intent/x', root: ROOT,
  session: 'other', message: null, ...over,
})

const answer = (rows: any[]) => {
  const n = (kind: string, live: boolean) => rows.filter(r => r.kind === kind && r.live === live).length
  const c = (kind: string) => ({ live: n(kind, true), idle: n(kind, false) })
  return {
    rows, live: rows.filter(r => r.live).length, idle: rows.filter(r => !r.live).length, stamp: STAMP,
    counts: { intent: c('intent'), debug: c('debug'), evaluate: c('evaluate') },
  }
}

const LIVE = [
  row('intent', 'aaaaaaaaaaaa', 'invoices that charge late fees', 'plan · 3/7',
    { done: ['clarify'], left: ['the plan tasks', 'build'], waits: "the owner's answer" }),
  row('intent', 'bbbbbbbbbbbb', 'a loop list', 'clarify'),
  row('debug', 'KI-9', 'the stop hook is slow', 'fix being written (round 1)'),
  row('evaluate', 'run-1', 'how a model does the simple task', 'simple · fable · first run'),
]
const IDLE = row('intent', 'cccccccccccc', 'an old loop nobody works on', 'build',
  { live: false, state: 'idle', idle_since: '2026-10-01' })

function loopsWorld(data: () => unknown, stamp = 'one') {
  const w = world()
  const base = w.answer
  w.answer = (action, argv) => action === 'loops' ? { exitCode: 0, data: data() } : base(action, argv)
  w.files[STAMP] = stamp
  return w
}

const pane = (surface: 'terminal' | 'desktop') => ({
  plugin: 'plumb', surface, component: 'Pane' as const, requestId: 'plumb-loops',
  props: { title: 'plumb', bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 } },
}) as any

const loopsRuns = (w: { runs: { argv: string[] }[] }) => w.runs.filter(r => r.argv[4] === 'loops')

for (const surface of SURFACES) {
  describe(`the loops pane on the ${surface}`, () => {
    test('SR-393 EX-1: four loops worked on: \'loops 4\' in the first line, no line per loop', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: 'loops 4' })).toBeDefined()
      expect(await band.find({ type: 'Text', text: /charge late fees|stop hook|simple task/ })).toBeUndefined()
      const ran = loopsRuns(w)[0]
      expect(ran?.argv.slice(3)).toEqual(['mod', 'loops', '--session', SESSION, '--root', ROOT, '--json'])
      expect(ran?.env.PLUMB_AGENT_SESSION).toBe('')
      await band.unmount()
    })

    test('SR-393 EX-2: the press opens the pane on intent rows, idle apart, switch intent 2 debug 1 evaluate 1', async ($, on) => {
      const w = loopsWorld(() => answer([...LIVE, IDLE]))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: 'loops 4 · 1 idle' })).toBeDefined()
      await band.press({ key: 'loops' })
      expect(w.opens).toEqual([{ id: 'plumb-loops', columns: 80, closeOnEscape: true }])
      const view = await $.ui.mount(pane(surface))
      expect(await view.find({ type: 'Text', text: '● intent 2 +1 idle' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '○ debug 1' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '○ evaluate 1' })).toBeDefined()
      const rows = await view.findAll({ type: 'Text', text: / · / })
      expect(rows.map(t => t.text)).toEqual([
        'invoices that charge late fees · plan · 3/7', 'a loop list · clarify',
        'an old loop nobody works on · build · idle since 2026-10-01'])
      expect(await view.find({ type: 'Text', text: 'idle' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /stop hook/ })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-393 EX-3: Enter on a row shows its goal, steps done, what is left and what it waits for', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      expect(await view.find({ type: 'Text', text: /in full/ })).toBeUndefined()
      await view.press({ key: 'loops:row:intent:aaaaaaaaaaaa' })
      expect(await view.find({ type: 'Text', text: '  goal: invoices that charge late fees, in full' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '  done: clarify' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '  left: the plan tasks, build' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: "  waits for: the owner's answer" })).toBeDefined()
      await view.press({ key: 'loops:row:intent:aaaaaaaaaaaa' }) // a second Enter folds it
      expect(await view.find({ type: 'Text', text: /in full/ })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-393 EX-4: no loop of its own, another session\'s loop at plan: count and row shown', async ($, on) => {
      const w = loopsWorld(() => answer([row('intent', 'dddddddddddd', 'a loop of another session', 'plan')]))
      install(on, w)
      await $.session.start(START)
      expect(w.files[LOOP]).toBeUndefined()
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: 'loops 1' })).toBeDefined()
      expect(await band.find({ key: 'loop' })).toBeUndefined() // no strip: no loop of its own
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      expect(await view.find({ type: 'Text', text: 'a loop of another session · plan' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-393 EX-5: with its own loop open the strip and task bar stay and the count is in the first line', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE))
      w.files[LOOP] = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z',
        step: 'plan', stopped: null, stages: {}, tasks: { label: 'writing the plan', done: 3, total: 7, started_at: '2026-10-11T11:59:00Z' } })
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ key: 'loop' })).toBeDefined()
      expect(await band.find({ type: 'Text', text: 'writing the plan · 3/7' })).toBeDefined()
      const texts = (await band.findAll({ type: 'Text' })).map(t => t.text)
      expect(texts.indexOf('loops 4')).toBeGreaterThan(-1)
      expect(texts.indexOf('loops 4')).toBeLessThan(texts.findIndex(t => /^clarify /.test(t))) // before the strip
      await band.unmount()
    })

    test('SR-393 EX-6: nothing open nor idle: no count', async ($, on) => {
      const w = loopsWorld(() => answer([]))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ key: 'loops' })).toBeUndefined()
      expect(await band.find({ type: 'Text', text: /loops|idle/ })).toBeUndefined()
      await band.unmount()
    })

    test('SR-393 EX-7: only idle loops: the count names them idle and opens the pane', async ($, on) => {
      const w = loopsWorld(() => answer([IDLE, { ...IDLE, id: 'eeeeeeeeeeee' }, { ...IDLE, id: 'ffffffffffff' }]))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: '3 idle loops' })).toBeDefined()
      await band.press({ key: 'loops' })
      expect(w.opened).toEqual(['plumb-loops'])
      const view = await $.ui.mount(pane(surface))
      expect(await view.find({ type: 'Text', text: 'an old loop nobody works on · build · idle since 2026-10-01' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-393 EX-8: the known problems line opens its own pane, not the loops pane', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE))
      const base = w.answer
      w.answer = (action, argv) => action === 'known'
        ? { exitCode: 0, data: { open: 1, issues: PROBLEMS.map(p => ({ ...p, symptom: 's', cause: '', fix: '', fixed: '', state: 'open', history: [] })) } }
        : base(action, argv)
      w.files[`${ROOT}/.plumb/known-issues.json`] = JSON.stringify({ issues: PROBLEMS })
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'known' })
      expect(w.opens.map(o => o.id)).toEqual(['plumb-known'])
      await band.unmount()
    })

    test('SR-393 EX-9: the open pane shows the new step after the next refresh', async ($, on) => {
      let step = 'plan'
      const w = loopsWorld(() => answer([row('intent', 'dddddddddddd', 'a loop of another session', step)]))
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      expect(await view.find({ type: 'Text', text: 'a loop of another session · plan' })).toBeDefined()
      step = 'build'
      w.files[STAMP] = 'two' // the loop passed a gate: its writer moved the stamp
      await clock.advance(10_000)
      expect(await view.find({ type: 'Text', text: 'a loop of another session · build' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-393 EX-10: the switch moves to debug, then evaluate', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:type:debug' })
      expect(await view.find({ type: 'Text', text: '● debug 1' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '○ intent 2' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: 'the stop hook is slow · fix being written (round 1)' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /late fees/ })).toBeUndefined()
      await view.press({ key: 'loops:type:evaluate' })
      expect(await view.find({ type: 'Text', text: '● evaluate 1' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: 'how a model does the simple task · simple · fable · first run' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /stop hook/ })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-393 EX-11: evaluate 0 says no evaluate run is going', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE.slice(0, 3)))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:type:evaluate' })
      expect(await view.find({ type: 'Text', text: '● evaluate 0' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: 'no evaluate run is going' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-394: the reopen press runs plumb mod reopen with the key on stdin', async ($, on) => {
      const w = loopsWorld(() => answer([{ ...IDLE, reopen: true }]))
      const base = w.answer
      w.answer = (action, argv) => action === 'reopen'
        ? { exitCode: 0, data: { opened: true, command: ['claude'], line: 'opened a new session for an old loop' } }
        : base(action, argv)
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:reopen:cccccccccccc' })
      const ran = w.runs.filter(r => r.argv[4] === 'reopen')
      expect(ran.length).toBe(1)
      expect(ran[0]?.argv.slice(3)).toEqual(['mod', 'reopen', '--session', SESSION, '--root', ROOT, '--json', '--loop', 'cccccccccccc'])
      expect(JSON.parse(ran[0]?.stdin ?? '{}').key).toMatch(/^[0-9a-f]{64}$/)
      expect(ran[0]?.argv.join(' ')).not.toContain(JSON.parse(ran[0]?.stdin ?? '{}').key) // never in argv
      expect(w.toasts).toEqual(['plumb is opening a new session on that loop; its window can take a few seconds', 'opened a new session for an old loop'])
      // SR-394: the row says it is opening, and a second press while it opens runs nothing
      expect(await view.find({ type: 'Text', text: 'opening a new session…' })).toBeDefined()
      await view.press({ key: 'loops:reopen:cccccccccccc' })
      expect(w.runs.filter(r => r.argv[4] === 'reopen').length).toBe(1)
      await view.unmount()
      await band.unmount()
    })

    test('SR-394: a live row draws no reopen', async ($, on) => {
      const w = loopsWorld(() => answer([...LIVE.map(r => ({ ...r, reopen: false })), { ...IDLE, reopen: true }]))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      expect((await view.findAll({ type: 'Text', text: 'reopen in a new session' })).length).toBe(1)
      expect(await view.find({ key: 'loops:reopen:aaaaaaaaaaaa' })).toBeUndefined()
      expect(await view.find({ key: 'loops:reopen:cccccccccccc' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-394: a failed open toasts the hand command', async ($, on) => {
      const line = 'no terminal window could be opened here; open the session by hand:\nclaude --session-id x'
      const w = loopsWorld(() => answer([{ ...IDLE, reopen: true }]))
      const base = w.answer
      w.answer = (action, argv) => action === 'reopen' ? { exitCode: 1, data: { opened: false, command: ['claude'], line } } : base(action, argv)
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:reopen:cccccccccccc' })
      expect(w.toasts).toEqual(['plumb is opening a new session on that loop; its window can take a few seconds', line])
      // a failed open can be pressed again
      expect(await view.find({ type: 'Text', text: 'reopen in a new session' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-394, SR-395: a refused press toasts what plumb said, not a generic failure', async ($, on) => {
      const w = loopsWorld(() => answer([{ ...IDLE, reopen: true }, row('intent', 'bbbbbbbbbbbb', 'a loop list', 'build', { send: true })]))
      const base = w.answer
      const said = (action: string) => `plumb mod ${action}: ${action === 'send' ? 'no session works on this loop; it can be reopened' : 'a session works on this loop already'}`
      w.answer = (action, argv) => action === 'reopen' || action === 'send'
        ? { exitCode: 1, data: null, stderr: said(action) } : base(action, argv)
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:reopen:cccccccccccc' })
      await view.input({ key: 'loops:say:bbbbbbbbbbbb', text: 'rebase please' })
      expect(w.toasts).toEqual(['plumb is opening a new session on that loop; its window can take a few seconds', 'a session works on this loop already', 'no session works on this loop; it can be reopened'])
      await view.unmount()
      await band.unmount()
    })

    test('SR-395 EX-6: with no Input the row says to tell the agent', async ($, on) => {
      const w = loopsWorld(() => answer([row('intent', 'bbbbbbbbbbbb', 'a loop list', 'build', { send: true })]))
      w.noInput = true
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:row:intent:bbbbbbbbbbbb' })
      expect(await view.find({ type: 'Text', text: 'tell the agent of this session what to send' })).toBeDefined()
      expect(await view.find({ key: 'loops:say:bbbbbbbbbbbb' })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-395 EX-7: a waiting session is never woken by its band: the message waits for its next turn and the row reads sent, not read yet', async ($, on) => {
      let message: { state: string; at: string } = { state: 'sent', at: 't1' }
      const w = loopsWorld(() => answer([row('intent', 'aaaaaaaaaaaa', 'my own loop', 'build', { send: true, session: SESSION, message })]))
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      w.files[STAMP] = 'two'
      await clock.advance(10_000)
      await $.turn.complete(TURN_DONE)
      expect(w.submits.length).toBe(0) // the owner chose (2026-11-07): plumb starts no turn
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:row:intent:aaaaaaaaaaaa' })
      expect(await view.find({ type: 'Text', text: '  last message: sent, not read yet' })).toBeDefined()
      message = { state: 'delivered', at: 't1' } // its next turn read it
      w.files[STAMP] = 'three'
      await clock.advance(10_000)
      expect(await view.find({ type: 'Text', text: '  last message: delivered' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-395: typing on a working row runs plumb mod send with the words on stdin, the row then reads delivered once the list says so', async ($, on) => {
      let message: { state: string; at: string } | null = null
      const w = loopsWorld(() => answer([row('intent', 'bbbbbbbbbbbb', 'a loop list', 'build', { send: true, message })]))
      const base = w.answer
      w.answer = (action, argv) => {
        if (action !== 'send') return base(action, argv)
        message = { state: 'sent', at: 't1' }
        return { exitCode: 0, data: { sent: true, line: 'sent' } }
      }
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.input({ key: 'loops:say:bbbbbbbbbbbb', text: 'skip the colours slice' })
      const ran = w.runs.filter(r => r.argv[4] === 'send')
      expect(ran.length).toBe(1)
      expect(ran[0]?.argv.slice(3)).toEqual(['mod', 'send', '--session', SESSION, '--root', ROOT, '--json', '--loop', 'bbbbbbbbbbbb'])
      const stdin = JSON.parse(ran[0]?.stdin ?? '{}')
      expect(stdin.text).toBe('skip the colours slice')
      expect(ran[0]?.argv.join(' ')).not.toContain(stdin.key) // the key is never in argv
      await view.press({ key: 'loops:row:intent:bbbbbbbbbbbb' })
      expect(await view.find({ type: 'Text', text: '  last message: sent, not read yet' })).toBeDefined()
      message = { state: 'delivered', at: 't1' }
      w.files[STAMP] = 'two'
      await clock.advance(10_000)
      expect(await view.find({ type: 'Text', text: '  last message: delivered' })).toBeDefined()
      expect(w.submits.length).toBe(0) // another session's loop: this band wakes nobody
      await view.unmount()
      await band.unmount()
    })

    test('SR-395: the row reads sent, not read yet', async ($, on) => {
      const w = loopsWorld(() => answer([row('intent', 'bbbbbbbbbbbb', 'a loop list', 'build',
        { send: true, message: { state: 'sent', at: 't1' } })]))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:row:intent:bbbbbbbbbbbb' })
      expect(await view.find({ type: 'Text', text: '  last message: sent, not read yet' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('the pane lists no agents or tokens', async ($, on) => {
      const w = loopsWorld(() => answer([...LIVE, IDLE]))
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loops' })
      const view = await $.ui.mount(pane(surface))
      await view.press({ key: 'loops:row:intent:aaaaaaaaaaaa' })
      expect(await view.find({ type: 'Text', text: /agent|token/i })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-375: a turn\'s end never waits on the listing: the next period runs it, the count says updating meanwhile', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE))
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(loopsRuns(w).length).toBe(1)
      w.files[STAMP] = 'two'
      await $.turn.complete(TURN_DONE)
      expect(loopsRuns(w).length).toBe(1) // the turn ended without the listing
      await clock.advance(2_000) // the next period, not the 10 s one
      expect(loopsRuns(w).length).toBe(2)
      expect(await band.find({ type: 'Text', text: /updating/ })).toBeUndefined() // done: the count is plain again
      await band.unmount()
    })

    test('the poll reads only the stamp and runs plumb only when it moved', async ($, on) => {
      const w = loopsWorld(() => answer(LIVE))
      const touched: string[] = []
      w.files = new Proxy(w.files, {
        get: (t, k) => { if (typeof k === 'string') touched.push(k); return t[k as string] },
        has: (t, k) => { if (typeof k === 'string') touched.push(k); return k in t },
        ownKeys: t => { touched.push('<list>'); return Reflect.ownKeys(t) },
      })
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(loopsRuns(w).length).toBe(1)
      touched.length = 0
      await clock.advance(30_000) // the stamp did not move
      expect(loopsRuns(w).length).toBe(1)
      // the band's own status reads (the session's files) are older than the loops; they add the
      // stamp and nothing else: no case, loop or run file, no listing
      const extra = touched.filter(p => !p.startsWith(`${ROOT}/.plumb/session`) && p !== '<list>')
      expect(extra.length).toBeGreaterThan(0)
      expect(new Set(extra)).toEqual(new Set([STAMP]))
      w.files[STAMP] = 'two'
      await clock.advance(10_000)
      expect(loopsRuns(w).length).toBe(2)
      await band.unmount()
    })
  })
}
