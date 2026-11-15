// The loop's strip (SR-305 as DEC-506 decides it): while a loop is open the band's step strip is
// a Button; its press opens iaso's one docked pane (SR-410) on the loops class; no agents or
// tokens; Esc closes it and the band stays. The loop's own pane, with its gates and findings, is
// retired with its id (SR-410). The judge-approval count in the band's head (SR-251) is here too.
// Each case runs on the terminal and the desktop.
import { describe, expect } from 'claude-code/testing'

import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, test, world } from './harness'

const LOOP = `${ROOT}/.iaso/session/${SESSION}/intent/aaaaaaaaaaaa.json`
const OPENED = '2026-10-11T11:00:00Z'

// the open loop as `iaso intent status --json` answers it
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
  plugin: 'iaso', surface, component: 'Pane' as const, requestId: 'iaso-pane',
  props: { title: 'iaso', bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 } },
}) as any

async function pressed($: any, on: any, surface: 'terminal' | 'desktop') {
  const w = loopWorld()
  install(on, w)
  await $.session.start(START)
  const band = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
  await band.press({ key: 'step:build' })
  return { w, band, view: await $.ui.mount(pane(surface)) }
}

for (const surface of SURFACES) {
  describe(`the loop's strip on the ${surface}`, () => {
    test('SR-305 EX-3: run as a workflow, the pane shows no agent names, counts or tokens', async ($, on) => {
      const { band, view } = await pressed($, on, surface)
      expect(await view.find({ type: 'Text', text: /agent|token/i })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-305 EX-4: the strip opens the one pane on loops, which closes on Esc; the band stays', async ($, on) => {
      const { w, band, view } = await pressed($, on, surface)
      expect(w.opens).toEqual([{ id: 'iaso-pane', columns: 400, closeOnEscape: true }])
      expect((await view.find({ type: 'Text', text: /^loops / }))?.props.bold).toBe(true)
      await view.unmount() // Esc: the host closes a pane opened with closeOnEscape
      expect(await band.find({ type: 'Text', text: 'build ●' })).toBeDefined()
      await band.unmount()
    })

    test("SR-291 EX-4: the loop ends while the pane is open: the strip goes, the one pane stays", async ($, on) => {
      const w = loopWorld()
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      await band.press({ key: 'step:build' })
      expect(w.closed).toEqual([])
      w.files[LOOP] = JSON.stringify({ ...STATUS[0], step: 'proven' }) // intent done
      await clock.advance(2000) // the band's period (POLL_MS in register.tsx)
      expect(await band.find({ type: 'Text', text: /^clarify / })).toBeUndefined()
      expect(w.closed).toEqual([])
      await band.unmount()
    })

    test('SR-305 EX-5: no loop open: no strip, and nothing opens the pane for a loop', async ($, on) => {
      const w = loopWorld(null)
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await band.find({ key: 'loop:fold' })).toBeUndefined()
      expect(await band.find({ type: 'Text', text: /^clarify / })).toBeUndefined()
      await band.unmount()
      expect(w.opens).toEqual([])
    })

    test("SR-251 EX-1: the band's status counts one judge approval", async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.iaso/session/status.json`] = JSON.stringify({ state: 'awaits you', intent_summary: '',
        awaiting: 2, confirmed_by: { 'auto-model': 1, owner: 4 } })
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: 'iaso ● 2 await you · 1 judge-approved' })).toBeDefined()
      expect(w.statuses).toEqual([]) // the band alone shows the status: nothing pinned under the prompt
      await band.unmount()
    })

    test("SR-251 EX-1: the band counts every record the judge approved, as iaso status lists them", async ($, on) => {
      const w = world()
      // round 3: 2 requirements and 4 decisions judge-approved; confirmed_by counts requirements only
      w.files[`${ROOT}/.iaso/session/status.json`] = JSON.stringify({ state: 'awaits you', intent_summary: '',
        awaiting: 2, confirmed_by: { 'auto-model': 2 }, judge_approved: 6 })
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: 'iaso ● 2 await you · 6 judge-approved' })).toBeDefined()
      await band.unmount()
    })
  })
}
