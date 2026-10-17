// The loop pane (SR-305): while a loop is open the band's step strip is a Button; its press
// runs `plumb intent status --json` (the agent marker emptied) and opens plumb's docked pane on
// the loop: each step with its gate and the low findings left, the build's tasks done and left,
// the records of the loop's intent and each requirement's proof, by title; no agents or tokens;
// Esc closes it and the band stays. The judge-approval count in the band's head (SR-251) is here
// too. Each case runs on the terminal and the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { BRASS, PLUM } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, world } from './harness'

const LOOP = `${ROOT}/.plumb/session/${SESSION}/intent/aaaaaaaaaaaa.json`
const OPENED = '2026-10-11T11:00:00Z'

// the open loop as `plumb intent status --json` answers it
const STATUS = [{
  digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-090', opened_at: OPENED, step: 'build', stopped: null,
  stages: {
    clarify: { state: 'passed', findings: 2, left: ['the study names no owner', 'one word is jargon'] },
    plan: { state: 'passed', findings: 2, left: ['task 3 is broad', 'no rollback named'] },
    build: { state: 'open' },
  },
  tasks: { label: 'building', done: 3, total: 4, started_at: OPENED, left: ['the pane of the loop'] },
  records: [{ id: 'INT-090', kind: 'intent', title: 'Intent loop visuals' },
    { id: 'SR-291', kind: 'requirement', title: 'Step strip and bar' },
    { id: 'SR-292', kind: 'requirement', title: 'Understanding picture' }],
  proofs: [{ id: 'SR-291', title: 'Step strip and bar', shown: true },
    { id: 'SR-292', title: 'Understanding picture', shown: false }],
}]

function loopWorld(file: unknown = STATUS[0]) {
  const w = world()
  const answer = w.answer
  w.answer = (action, argv) => action === 'status' ? { exitCode: 0, data: STATUS } : answer(action, argv)
  if (file !== null) w.files[LOOP] = JSON.stringify(file)
  return w
}

const pane = (surface: 'terminal' | 'desktop') => ({
  plugin: 'plumb', surface, component: 'Pane' as const, requestId: 'plumb-cards',
  props: { title: 'plumb', bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 } },
}) as any

async function pressed($: any, on: any, surface: 'terminal' | 'desktop') {
  const w = loopWorld()
  install(on, w)
  await $.session.start(START)
  const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
  await band.press({ key: 'loop' })
  return { w, band, view: await $.ui.mount(pane(surface)) }
}

for (const surface of SURFACES) {
  describe(`the loop pane on the ${surface}`, () => {
    test('SR-305 EX-1: clarify and plan passed with their low findings, build 3/4 with the task left', async ($, on) => {
      const { w, band, view } = await pressed($, on, surface)
      const status = w.runs.find(r => r.argv[4] === 'status')
      expect(status?.argv.slice(3)).toEqual(['intent', 'status', '--session', SESSION, '--root', ROOT, '--json'])
      expect(status?.env.PLUMB_AGENT_SESSION).toBe('')
      const clarify = await view.find({ type: 'Text', text: /^clarify / })
      expect(clarify?.text).toBe('clarify ✓ · 2 low findings left')
      expect(clarify?.props.color).toBe(PLUM.dark)
      expect(await view.find({ type: 'Text', text: '  low: one word is jargon' })).toBeDefined()
      expect((await view.find({ type: 'Text', text: /^plan / }))?.text).toBe('plan ✓ · 2 low findings left')
      expect((await view.find({ type: 'Text', text: /^build / }))?.text).toBe('build ● 3/4 · left: the pane of the loop')
      expect((await view.find({ type: 'Text', text: /^proven / }))?.text).toBe('proven ○')
      await view.unmount()
      await band.unmount()
    })

    test('SR-305 EX-2: the requirements by title, the first shown and the second not shown yet', async ($, on) => {
      const { band, view } = await pressed($, on, surface)
      const shown = await view.find({ type: 'Text', text: '  ✓ Step strip and bar: shown' })
      expect(shown?.props.color).toBe(BRASS)
      expect(await view.find({ type: 'Text', text: '  ○ Understanding picture: not shown yet' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '  Intent loop visuals' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /SR-\d+|INT-\d+/ })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-305 EX-3: run as a workflow, the pane shows no agent names, counts or tokens', async ($, on) => {
      const { band, view } = await pressed($, on, surface)
      expect(await view.find({ type: 'Text', text: /agent|token/i })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-305 EX-4: the pane docks and closes on Esc; the band stays', async ($, on) => {
      const { w, band, view } = await pressed($, on, surface)
      expect(w.opens).toEqual([{ id: 'plumb-cards', columns: 80, closeOnEscape: true }])
      await view.unmount() // Esc: the host closes a pane opened with closeOnEscape
      expect(await band.find({ type: 'Text', text: /^clarify ✓  plan ✓  build ●/ })).toBeDefined()
      await band.unmount()
    })

    test('SR-305 EX-1: the open pane follows the band: build 3/4 becomes 4/4 on the next read', async ($, on) => {
      const w = loopWorld()
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loop' })
      const view = await $.ui.mount(pane(surface))
      expect((await view.find({ type: 'Text', text: /^build / }))?.text).toBe('build ● 3/4 · left: the pane of the loop')
      const done = { ...STATUS[0], tasks: { ...STATUS[0]!.tasks, done: 4, left: [] } }
      STATUS[0] = done // what `plumb intent status --json` answers now
      w.files[LOOP] = JSON.stringify(done)
      await clock.advance(2000) // the band's period (POLL_MS in register.tsx)
      expect((await band.find({ type: 'Text', text: /building · 4\/4/ }))).toBeDefined()
      expect((await view.find({ type: 'Text', text: /^build / }))?.text).toBe('build ● 4/4')
      STATUS[0] = { ...done, tasks: { ...done.tasks, done: 3, left: ['the pane of the loop'] } }
      await view.unmount()
      await band.unmount()
    })

    test("SR-291 EX-4: the loop ends while its pane is open: the pane closes, never 'nothing awaits you'", async ($, on) => {
      const w = loopWorld()
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loop' })
      expect(w.closed).toEqual([])
      w.files[LOOP] = JSON.stringify({ ...STATUS[0], step: 'proven' }) // intent done
      await clock.advance(2000) // the band's period (POLL_MS in register.tsx)
      expect(await band.find({ type: 'Text', text: /^clarify / })).toBeUndefined()
      expect(w.closed).toEqual(['plumb-cards'])
      await band.unmount()
    })

    test('SR-305 EX-6: plumb says the loop ended before the band does: the pane still closes by itself', async ($, on) => {
      const w = loopWorld()
      let open = true
      const answer = w.answer
      w.answer = (action, argv) => action === 'status' && !open ? { exitCode: 0, data: [] } : answer(action, argv)
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'loop' })
      // intent done: `plumb intent status` has no open loop while the band's file still moves
      open = false
      w.files[LOOP] = JSON.stringify({ ...STATUS[0], tasks: { ...STATUS[0]!.tasks, done: 4 } })
      await clock.advance(2000) // the band's period (POLL_MS in register.tsx)
      expect(w.closed).toEqual(['plumb-cards'])
      w.files[LOOP] = JSON.stringify({ ...STATUS[0], step: 'proven' })
      await clock.advance(2000)
      expect(w.closed).toEqual(['plumb-cards'])
      await band.unmount()
    })

    test('SR-305 EX-5: no loop open: no strip, and nothing opens the pane for a loop', async ($, on) => {
      const w = loopWorld(null)
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ key: 'loop' })).toBeUndefined()
      expect(await band.find({ type: 'Text', text: /^clarify / })).toBeUndefined()
      await band.unmount()
      expect(w.opens).toEqual([])
    })

    test("SR-251 EX-1: the band's status counts one judge approval", async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.plumb/session/status.json`] = JSON.stringify({ state: 'awaits you', intent_summary: '',
        confirmed_by: { 'auto-model': 1, owner: 4 }, present: { card: 'full' } })
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: 'plumb ● 2 await you · 1 judge-approved' })).toBeDefined()
      expect(w.statuses.at(-1)).toBe('● 2 await you · 1 judge-approved')
      await band.unmount()
    })

    test("SR-251 EX-1: the band counts every record the judge approved, as plumb status lists them", async ($, on) => {
      const w = world()
      // round 3: 2 requirements and 4 decisions judge-approved; confirmed_by counts requirements only
      w.files[`${ROOT}/.plumb/session/status.json`] = JSON.stringify({ state: 'awaits you', intent_summary: '',
        confirmed_by: { 'auto-model': 2 }, judge_approved: 6, present: { card: 'full' } })
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: 'plumb ● 2 await you · 6 judge-approved' })).toBeDefined()
      await band.unmount()
    })
  })
}
