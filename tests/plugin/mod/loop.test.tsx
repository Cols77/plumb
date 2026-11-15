// The band during an intent loop (SR-291): the strip of the loop's steps in plum, the current
// step's task with a brass fill (or the elapsed time with no fill), a refused gate's stop, and
// the one line again once the loop is proven or when none is open. Each case runs on the
// terminal and the desktop.
import { describe, expect } from 'claude-code/testing'

import { BRASS, PLUM } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, test, world } from './harness'

// the strip, the task's words and the brass fill, as the band draws them
const TASK = /^(writing|clarifying|building)/
const FILL = /^[█░]+$/
const NAMES = ['clarify', 'plan', 'build', 'proven']

/** The strip as the owner reads it: each step's own Button text (a Text inside a Button keeps no key of its own), then the stop, if any (SR-305). */
async function strip(ui: any): Promise<string | undefined> {
  const parts = []
  for (const s of NAMES) parts.push((await ui.find({ key: `step:${s}` }))?.text)
  if (parts[0] === undefined) return undefined
  const stopped = await ui.find({ type: 'Text', text: /^stopped, waits for/ })
  return parts.join('  ') + (stopped ? ` · ${stopped.text}` : '')
}

const LOOP = `${ROOT}/.iaso/session/${SESSION}/intent/aaaaaaaaaaaa.json`

function loop(step: string, tasks: unknown = null, stopped: string | null = null): string {
  return JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z',
    step, tasks, stopped, stages: {} })
}

async function bandWith($: any, on: any, surface: (typeof SURFACES)[number], file: string | null) {
  const w = world()
  if (file !== null) w.files[LOOP] = file
  install(on, w)
  await $.session.start(START)
  return { w, ui: await $.ui.mount({ plugin: 'iaso', surface, ...BAND }) }
}

for (const surface of SURFACES) {
  describe(`the intent loop's band on the ${surface}`, () => {
    test('SR-291 EX-1: plan step, 3 of 7 written: the strip in plum and a brass bar', async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('plan', { label: 'writing the plan', done: 3, total: 7, started_at: '2026-10-11T11:59:00Z' }))
      expect(await strip(ui)).toBe('clarify ✓  plan ●  build ○  proven ○')
      expect((await ui.find({ type: 'Text', text: 'plan ●' }))?.props.color).toBe(PLUM.dark)
      expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('writing the plan · 3/7')
      const fill = await ui.find({ type: 'Text', text: FILL })
      expect(fill?.props.color).toBe(BRASS)
      expect(fill?.text).toBe('████░░░░░░')
      await ui.unmount()
    })

    test('SR-291 EX-2: clarify with 2 of 4 answered reads clarifying · 2/4', async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('clarify', { label: 'clarifying', done: 2, total: 4, started_at: '2026-10-11T11:59:00Z' }))
      expect(await strip(ui)).toBe('clarify ●  plan ○  build ○  proven ○')
      expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('clarifying · 2/4')
      await ui.unmount()
    })

    test('SR-291 EX-3: build with an unknown total: the step and the elapsed time, no fill', async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('build', { label: 'building', done: 0, total: null, started_at: '2026-10-11T11:48:05Z' }))
      expect(await strip(ui)).toBe('clarify ✓  plan ✓  build ●  proven ○')
      expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('building · 12m')
      expect(await ui.find({ type: 'Text', text: FILL })).toBeUndefined()
      await ui.unmount()
    })

    test('SR-291 EX-4: after intent done the band is back to its one line', async ($, on) => {
      const { w, ui } = await bandWith($, on, surface,
        loop('build', { label: 'building', done: 0, total: null, started_at: '2026-10-11T11:48:05Z' }))
      expect(await ui.find({ key: 'step:clarify' })).toBeDefined()
      w.files[LOOP] = loop('proven')
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ key: 'step:clarify' })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: TASK })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: /^iaso / })).toBeDefined()
      await ui.unmount()
    })

    test('SR-291 EX-5: no loop open: one line with the long job\'s progress (SR-272)', async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.iaso/session/${SESSION}/progress`] = JSON.stringify({ state: 'running', step: 'judging the backlog', done: 10, total: 160 })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'iaso ● 2 await you · judging the backlog · 10/160' })).toBeDefined()
      expect(await ui.find({ key: 'step:clarify' })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: TASK })).toBeUndefined()
      await ui.unmount()
    })

    test('SR-291 EX-6: a refused gate marks the step stopped, in one line naming what it waits for', async ($, on) => {
      const { ui } = await bandWith($, on, surface, loop('clarify', null, 'the clarify gate: 2 finding(s) to fix'))
      expect(await strip(ui)).toBe(
        'clarify ✗  plan ○  build ○  proven ○ · stopped, waits for the clarify gate: 2 finding(s) to fix')
      expect(await ui.find({ type: 'Text', text: TASK })).toBeUndefined()
      await ui.unmount()
    })

    test("SR-291 EX-7: a workflow slice's gate passed: build · slice 2/4 · colours gate passed", async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('build', { label: 'colours gate passed', done: 2, total: 4, started_at: '2026-10-11T11:48:05Z' }))
      expect((await ui.find({ type: 'Text', text: /^build · / }))?.text).toBe('build · slice 2/4 · colours gate passed')
      expect((await ui.find({ type: 'Text', text: FILL }))?.props.color).toBe(BRASS)
      await ui.unmount()
    })

    test("SR-291 EX-8: a phase's gate failed: the bar names the phase, no agents of iaso's own", async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('build', { label: 'colours gate failed', done: 2, total: 4, started_at: '2026-10-11T11:48:05Z' }))
      expect((await ui.find({ type: 'Text', text: /^build · / }))?.text).toBe('build · slice 2/4 · colours gate failed')
      expect(await ui.find({ type: 'Text', text: /agent/ })).toBeUndefined()
      await ui.unmount()
    })
  })
}

test('SR-291: the bar moves within the turn, read again after the agent runs iaso intent progress', async ($, on) => {
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  const { w, ui } = await bandWith($, on, 'terminal',
    loop('clarify', { label: 'clarifying', done: 1, total: 4, started_at: '2026-10-11T11:59:00Z' }))
  w.files[LOOP] = loop('clarify', { label: 'clarifying', done: 2, total: 4, started_at: '2026-10-11T11:59:00Z' })
  await $.tool.call({ tool: 'Bash', command: 'iaso intent progress --task clarifying --done 2 --total 4' } as any)
  expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('clarifying · 2/4')
  await ui.unmount()
})

test('SR-291 / SR-294: iaso intent progress in the PowerShell tool moves the bar within the turn', async ($, on) => {
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  const { w, ui } = await bandWith($, on, 'terminal',
    loop('clarify', { label: 'clarifying', done: 1, total: 4, started_at: '2026-10-11T11:59:00Z' }))
  w.files[LOOP] = loop('clarify', { label: 'clarifying', done: 3, total: 4, started_at: '2026-10-11T11:59:00Z' })
  await $.tool.call({ tool: 'PowerShell', command: 'iaso intent progress --task clarifying --done 3 --total 4' } as any)
  expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('clarifying · 3/4')
  await ui.unmount()
})

test("SR-291 EX-7: a workflow's agent moves the bar with no tool event in the owner's session", async ($, on) => {
  const w = world()
  w.files[LOOP] = loop('build', { label: 'colours gate passed', done: 1, total: 4, started_at: '2026-10-11T11:48:05Z' })
  const clock = install(on, w)
  await $.session.start(START)
  const ui = await $.ui.mount({ plugin: 'iaso', surface: 'terminal', ...BAND })
  w.files[LOOP] = loop('build', { label: 'colours gate passed', done: 2, total: 4, started_at: '2026-10-11T11:48:05Z' })
  await clock.advance(2000) // the band's period (POLL_MS in register.tsx)
  expect((await ui.find({ type: 'Text', text: /^build · / }))?.text).toBe('build · slice 2/4 · colours gate passed')
  await ui.unmount()
})

// SR-305 / DEC-513: the band's loop section is foldable to its title, and each step of the strip
// is its own Button that opens the one pane on the loops class at that step's details.
const STAGES = {
  clarify: { state: 'passed', findings: 2, left: ['the study names no owner', 'one word is jargon'] },
  plan: { state: 'passed', findings: 2, left: ['task 3 is broad', 'no rollback named'] },
  build: { state: 'open' },
}
const BUILDING = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z', step: 'build',
  tasks: { label: 'building', done: 3, total: 4, started_at: '2026-10-11T11:00:00Z', left: ['the colours slice'] }, stopped: null, stages: STAGES })

for (const surface of SURFACES) {
  describe(`SR-305: the foldable loop section on the ${surface}`, () => {
    test('SR-305 EX-6: folding leaves the title alone on line two, no strip, no bar; unfolding brings them back', async ($, on) => {
      const { ui } = await bandWith($, on, surface, BUILDING)
      expect(await ui.find({ key: 'loop:fold' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: TASK })).toBeDefined()
      await ui.press({ key: 'loop:fold' })
      expect(await ui.find({ key: 'loop:fold' })).toBeDefined()
      expect(await ui.find({ key: 'step:build' })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: TASK })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: FILL })).toBeUndefined()
      await ui.press({ key: 'loop:fold' })
      expect(await ui.find({ key: 'step:build' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: TASK })).toBeDefined()
      await ui.unmount()
    })

    test('SR-305: every step of the strip is its own Button, in order, with its mark', async ($, on) => {
      const { ui } = await bandWith($, on, surface, BUILDING)
      const marks = []
      for (const s of ['clarify', 'plan', 'build', 'proven']) marks.push((await ui.find({ key: `step:${s}` }))?.type)
      expect(marks).toEqual(['Button', 'Button', 'Button', 'Button'])
      expect(await ui.find({ type: 'Text', text: 'build ●' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'clarify ✓' })).toBeDefined()
      await ui.unmount()
    })

    test('SR-305 EX-1: pressing build opens the one pane on loops, this loop expanded at build', async ($, on) => {
      const { w, ui } = await bandWith($, on, surface, BUILDING)
      const base = w.answer
      w.answer = (a, v) => a === 'loops'
        ? { exitCode: 0, data: { rows: [{ kind: 'intent', id: 'aaaaaaaaaaaa', goal: 'this loop', goal_full: 'this loop', progress: 'build · 3/4', done: ['clarify', 'plan'],
          left: ['the colours slice'], waits: '', live: true, state: 'working', last: '2026-10-11T11:59:00Z', idle_since: '', branch: 'intent/x', root: ROOT, session: SESSION,
          message: null, reopen: false, send: true, tasks: { done: 3, total: 4, left: ['the colours slice'] },
          steps: [{ name: 'clarify', mark: 'done', gate: 'passed', findings: 2, left: ['a', 'b'] }, { name: 'plan', mark: 'done', gate: 'passed', findings: 2, left: ['c', 'd'] },
            { name: 'build', mark: 'current', gate: 'open', findings: 0, left: [] }, { name: 'proven', mark: 'todo', gate: 'to come', findings: 0, left: [] }] }],
          live: 1, idle: 0, stamp: `${ROOT}/.git/iaso-loops.stamp`, counts: { intent: { live: 1, idle: 0 }, debug: { live: 0, idle: 0 }, evaluate: { live: 0, idle: 0 } } } }
        : base(a, v)
      await ui.press({ key: 'step:build' })
      expect(w.opens.map(o => o.id)).toEqual(['iaso-pane'])
      const view = await $.ui.mount({ plugin: 'iaso', surface, component: 'Pane' as const, requestId: 'iaso-pane',
        props: { title: 'iaso', bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 } } } as any)
      expect((await view.find({ type: 'Text', text: /this loop/ }))?.props.bold).toBe(true) // expanded
      expect(await view.find({ type: 'Text', text: /gate.*open/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /3 of 4/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /the colours slice/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /clarify.*passed.*2 low/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /plan.*passed.*2 low/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /proven.*to come/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /\btokens?\b|agents? (names?|counts?)|\d+ agents?/i })).toBeUndefined() // EX-3, DEC-511
      await view.unmount()
      await ui.unmount()
    })

    test('SR-305 EX-5: no loop open in this session: no loop section; the loops chip still opens the pane', async ($, on) => {
      const { ui } = await bandWith($, on, surface, null)
      expect(await ui.find({ key: 'loop:fold' })).toBeUndefined()
      expect(await ui.find({ key: 'step:build' })).toBeUndefined()
      await ui.unmount()
    })

    test('SR-305 EX-7: the loop ends with the pane open: the pane stays, the band section is gone', async ($, on) => {
      const { w, ui } = await bandWith($, on, surface, BUILDING)
      await ui.press({ key: 'step:build' })
      w.files[LOOP] = loop('proven')
      await $.turn.complete(TURN_DONE)
      expect(w.closed).toEqual([])
      expect(await ui.find({ key: 'loop:fold' })).toBeUndefined()
      expect(await ui.find({ key: 'step:build' })).toBeUndefined()
      await ui.unmount()
    })
  })
}

const WT = '/work/shop-wt'

test('SR-291 EX-10: a loop handed to a worktree shows the worktree copy; its folder gone, main copy', async ($, on) => {
  const handed = JSON.stringify({ ...JSON.parse(loop('clarify')), handed_to: { root: WT, session: 'sess-2' } })
  const { w, ui } = await bandWith($, on, 'terminal', handed)
  w.files[`${WT}/.iaso/session/sess-2/intent/aaaaaaaaaaaa.json`] = loop('build', { label: 'building', done: 7, total: 7, started_at: '2026-10-11T11:48:05Z' }, 'proof shown')
  await $.turn.complete(TURN_DONE)
  expect(await strip(ui)).toBe('clarify ✓  plan ✓  build ✗  proven ○ · stopped, waits for proof shown')
  delete w.files[`${WT}/.iaso/session/sess-2/intent/aaaaaaaaaaaa.json`]
  await $.turn.complete(TURN_DONE)
  expect(await strip(ui)).toBe('clarify ●  plan ○  build ○  proven ○')
  await ui.unmount()
})
