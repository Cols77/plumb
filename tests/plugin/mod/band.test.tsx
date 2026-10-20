// The band above the prompt (SP7 5.2 as re-aligned: plumb's status with the count of questions
// waiting, SP8's progress; SR-085 EX-2, DEC-034, SR-337: no card, Hide holds until Show). Each
// case runs on the terminal and the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, world } from './harness'

const STATUS = `${ROOT}/.plumb/session/status.json`

for (const surface of SURFACES) {
  describe(`band on the ${surface}`, () => {
    test('with nothing awaiting, one line: the state, the intent summary and Hide', async ($, on) => {
      const w = world()
      w.files[STATUS] = JSON.stringify({ state: 'aligned', intent_summary: 'invoices · late fees' })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect((await ui.find({ type: 'Text', text: /^plumb / }))?.text).toBe('plumb ✓ aligned')
      expect(await ui.find({ type: 'Text', text: 'invoices · late fees' })).toBeDefined()
      expect(await ui.find({ key: 'hide' })).toBeDefined()
      expect(await ui.findAll({ type: 'Button' })).toHaveLength(1)
      await ui.unmount()
    })

    test('SR-337 EX-1: two questions wait: the line says two await you, no card or button for them', async ($, on) => {
      const w = world()
      w.files[STATUS] = JSON.stringify({ state: 'awaits you', intent_summary: '', awaiting: 2 })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'plumb ● 2 await you' })).toBeDefined()
      expect(await ui.findAll({ type: 'Button' })).toHaveLength(1) // Hide alone
      expect(await ui.findAll({ type: 'Text' })).toHaveLength(1) // the one line
      expect(w.runs.map(r => r.argv[4])).toEqual(['hello']) // nothing drawn from plumb but the files
      await ui.unmount()
    })

    test('SR-337 EX-2: hidden, a turn ends with a new question waiting: the band stays hidden', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'hide' })
      w.files[STATUS] = JSON.stringify({ state: 'awaits you', intent_summary: '', awaiting: 3 })
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ key: 'show' })).toBeDefined()
      expect(await ui.find({ key: 'hide' })).toBeUndefined()
      expect(w.toasts).toEqual([])
      await ui.unmount()
    })

    test('SR-337 EX-3: hidden, the owner presses Show: the band draws its line again', async ($, on) => {
      install(on, world())
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'hide' })
      await ui.press({ key: 'show' })
      expect(await ui.find({ type: 'Text', text: 'plumb ● 2 await you' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'invoices · late fees' })).toBeDefined()
      expect(await ui.find({ key: 'hide' })).toBeDefined()
      expect(await ui.find({ key: 'show' })).toBeUndefined()
      await ui.unmount()
    })

    test("SP8's progress joins the status line while a long step runs", async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.plumb/session/${SESSION}/progress`] = JSON.stringify({ state: 'running', step: 'judging the backlog', done: 10, total: 160 })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'plumb ● 2 await you · judging the backlog · 10/160' })).toBeDefined()
      expect(w.statuses).toEqual([]) // the band alone shows the status: nothing pinned under the prompt
      await ui.unmount()
    })

    test('idle in a repository plumb has not adopted: no process, no band', async ($, on) => {
      const w = world({ files: {} })
      install(on, w)
      await $.session.start(START)
      expect(w.runs).toHaveLength(0)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /plumb/ })).toBeUndefined()
      await ui.unmount()
    })
  })
}
