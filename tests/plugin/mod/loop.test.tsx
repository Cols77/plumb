// The band during an intent loop (SR-291): the strip of the loop's steps in plum, the current
// step's task with a brass fill (or the elapsed time with no fill), a refused gate's stop, and
// the one line again once the loop is proven or when none is open. Each case runs on the
// terminal and the desktop.
import { describe, expect } from 'claude-code/testing'

import { BRASS, PLUM } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, test, world } from './harness'

// the strip, the task's words and the brass fill, as the band draws them
const STRIP = /^clarify /
const TASK = /^(writing|clarifying|building)/
const FILL = /^[█░]+$/

const LOOP = `${ROOT}/.plumb/session/${SESSION}/intent/aaaaaaaaaaaa.json`

function loop(step: string, tasks: unknown = null, stopped: string | null = null): string {
  return JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z',
    step, tasks, stopped, stages: {} })
}

async function bandWith($: any, on: any, surface: (typeof SURFACES)[number], file: string | null) {
  const w = world()
  if (file !== null) w.files[LOOP] = file
  install(on, w)
  await $.session.start(START)
  return { w, ui: await $.ui.mount({ plugin: 'plumb', surface, ...BAND }) }
}

for (const surface of SURFACES) {
  describe(`the intent loop's band on the ${surface}`, () => {
    test('SR-291 EX-1: plan step, 3 of 7 written: the strip in plum and a brass bar', async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('plan', { label: 'writing the plan', done: 3, total: 7, started_at: '2026-10-11T11:59:00Z' }))
      const strip = await ui.find({ type: 'Text', text: STRIP })
      expect(strip?.text).toBe('clarify ✓  plan ●  build ○  proven ○')
      expect(strip?.props.color).toBe(PLUM.dark)
      expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('writing the plan · 3/7')
      const fill = await ui.find({ type: 'Text', text: FILL })
      expect(fill?.props.color).toBe(BRASS)
      expect(fill?.text).toBe('████░░░░░░')
      await ui.unmount()
    })

    test('SR-291 EX-2: clarify with 2 of 4 answered reads clarifying · 2/4', async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('clarify', { label: 'clarifying', done: 2, total: 4, started_at: '2026-10-11T11:59:00Z' }))
      expect((await ui.find({ type: 'Text', text: STRIP }))?.text).toBe('clarify ●  plan ○  build ○  proven ○')
      expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('clarifying · 2/4')
      await ui.unmount()
    })

    test('SR-291 EX-3: build with an unknown total: the step and the elapsed time, no fill', async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('build', { label: 'building', done: 0, total: null, started_at: '2026-10-11T11:48:05Z' }))
      expect((await ui.find({ type: 'Text', text: STRIP }))?.text).toBe('clarify ✓  plan ✓  build ●  proven ○')
      expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('building · 12m')
      expect(await ui.find({ type: 'Text', text: FILL })).toBeUndefined()
      await ui.unmount()
    })

    test('SR-291 EX-4: after intent done the band is back to its one line', async ($, on) => {
      const { w, ui } = await bandWith($, on, surface,
        loop('build', { label: 'building', done: 0, total: null, started_at: '2026-10-11T11:48:05Z' }))
      expect(await ui.find({ type: 'Text', text: STRIP })).toBeDefined()
      w.files[LOOP] = loop('proven')
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ type: 'Text', text: STRIP })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: TASK })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: /^plumb / })).toBeDefined()
      await ui.unmount()
    })

    test('SR-291 EX-5: no loop open: one line with the long job\'s progress (SR-272)', async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.plumb/session/${SESSION}/progress`] = JSON.stringify({ state: 'running', step: 'judging the backlog', done: 10, total: 160 })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'plumb ● 2 await you · judging the backlog · 10/160' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: STRIP })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: TASK })).toBeUndefined()
      await ui.unmount()
    })

    test('SR-291 EX-6: a refused gate marks the step stopped, in one line naming what it waits for', async ($, on) => {
      const { ui } = await bandWith($, on, surface, loop('clarify', null, 'the clarify gate: 2 finding(s) to fix'))
      expect((await ui.find({ type: 'Text', text: STRIP }))?.text).toBe(
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

    test("SR-291 EX-8: a phase's gate failed: the bar names the phase, no agents of plumb's own", async ($, on) => {
      const { ui } = await bandWith($, on, surface,
        loop('build', { label: 'colours gate failed', done: 2, total: 4, started_at: '2026-10-11T11:48:05Z' }))
      expect((await ui.find({ type: 'Text', text: /^build · / }))?.text).toBe('build · slice 2/4 · colours gate failed')
      expect(await ui.find({ type: 'Text', text: /agent/ })).toBeUndefined()
      await ui.unmount()
    })
  })
}

test('SR-291: the bar moves within the turn, read again after the agent runs plumb intent progress', async ($, on) => {
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  const { w, ui } = await bandWith($, on, 'terminal',
    loop('clarify', { label: 'clarifying', done: 1, total: 4, started_at: '2026-10-11T11:59:00Z' }))
  w.files[LOOP] = loop('clarify', { label: 'clarifying', done: 2, total: 4, started_at: '2026-10-11T11:59:00Z' })
  await $.tool.call({ tool: 'Bash', command: 'plumb intent progress --task clarifying --done 2 --total 4' } as any)
  expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('clarifying · 2/4')
  await ui.unmount()
})

test('SR-291 / SR-294: plumb intent progress in the PowerShell tool moves the bar within the turn', async ($, on) => {
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  const { w, ui } = await bandWith($, on, 'terminal',
    loop('clarify', { label: 'clarifying', done: 1, total: 4, started_at: '2026-10-11T11:59:00Z' }))
  w.files[LOOP] = loop('clarify', { label: 'clarifying', done: 3, total: 4, started_at: '2026-10-11T11:59:00Z' })
  await $.tool.call({ tool: 'PowerShell', command: 'plumb intent progress --task clarifying --done 3 --total 4' } as any)
  expect((await ui.find({ type: 'Text', text: TASK }))?.text).toBe('clarifying · 3/4')
  await ui.unmount()
})

test("SR-291 EX-7: a workflow's agent moves the bar with no tool event in the owner's session", async ($, on) => {
  const w = world()
  w.files[LOOP] = loop('build', { label: 'colours gate passed', done: 1, total: 4, started_at: '2026-10-11T11:48:05Z' })
  const clock = install(on, w)
  await $.session.start(START)
  const ui = await $.ui.mount({ plugin: 'plumb', surface: 'terminal', ...BAND })
  w.files[LOOP] = loop('build', { label: 'colours gate passed', done: 2, total: 4, started_at: '2026-10-11T11:48:05Z' })
  await clock.advance(2000) // the band's period (POLL_MS in register.tsx)
  expect((await ui.find({ type: 'Text', text: /^build · / }))?.text).toBe('build · slice 2/4 · colours gate passed')
  await ui.unmount()
})
