// The band above the prompt (SP7 5.2 as re-aligned: plumb's status, SP8's progress, the cards
// awaiting per feature; SR-085 EX-2, EX-3, EX-6; DEC-034). Each case runs on the terminal and
// the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { DRAW, ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, world } from './harness'

const NONE = { session: SESSION, cards: [] }

for (const surface of SURFACES) {
  describe(`band on the ${surface}`, () => {
    test('with nothing awaiting, one line: the state, the intent summary and Hide', async ($, on) => {
      const w = world({ answer: (action) => action === 'draw' ? { exitCode: 0, data: NONE } : world().answer(action, []) })
      w.files[`${ROOT}/.plumb/session/status.json`] = JSON.stringify({ state: 'aligned', intent_summary: 'invoices · late fees' })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect((await ui.find({ type: 'Text', text: /^plumb / }))?.text).toBe('plumb ✓ aligned')
      expect(await ui.find({ type: 'Text', text: 'invoices · late fees' })).toBeDefined()
      expect(await ui.find({ key: 'hide' })).toBeDefined()
      expect(await ui.findAll({ type: 'Button' })).toHaveLength(1)
      await ui.unmount()
    })

    test('cards awaiting: counted per feature, the first drawn in full, a left-open card only listed', async ($, on) => {
      install(on, world())
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'plumb ● 2 await you' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '2 await you: CSV export, Confirm button' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '1 left open: Late fees' })).toBeDefined()
      // the first awaiting card, whole, with its buttons
      expect(await ui.find({ key: 'card:clarify:SR-001' })).toBeDefined()
      expect(await ui.find({ key: 'press:0:sha256:aaaa' })).toBeDefined()
      expect(await ui.find({ key: 'card:stale:SR-005#0' })).toBeUndefined()
      expect(await ui.find({ key: 'card:clarify:SR-009' })).toBeUndefined()
      expect(await ui.find({ key: 'showall' })).toBeDefined()
      await ui.unmount()
    })

    test('Hide collapses to one line; Show restores; a new card shows it again', async ($, on) => {
      install(on, world())
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'hide' })
      expect(await ui.find({ key: 'card:clarify:SR-001' })).toBeUndefined()
      expect(await ui.find({ key: 'show' })).toBeDefined()
      await ui.press({ key: 'show' })
      expect(await ui.find({ key: 'card:clarify:SR-001' })).toBeDefined()
      await ui.press({ key: 'hide' })
      // the same cards at the end of a turn: still hidden
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ key: 'show' })).toBeDefined()
      await ui.unmount()
    })

    test('a card that changed since the owner hid the band shows it again, with a toast', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'hide' })
      const changed = JSON.parse(JSON.stringify(DRAW))
      changed.cards[0].offers[0].hash = 'sha256:2222'
      w.answer = (action, argv) => action === 'draw' ? { exitCode: 0, data: changed } : world().answer(action, argv)
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ key: 'card:clarify:SR-001' })).toBeDefined()
      expect(w.toasts).toContain('2 cards await you') // the host heads a toast with plumb's name (SR-290)
      await ui.unmount()
    })

    test('compact never draws a card; off draws nothing', async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.plumb/session/status.json`] = JSON.stringify({ state: 'awaits you', intent_summary: '', present: { card: 'compact' } })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: '2 await you: CSV export, Confirm button' })).toBeDefined()
      expect(await ui.find({ key: 'card:clarify:SR-001' })).toBeUndefined()
      await ui.unmount()
      w.files[`${ROOT}/.plumb/session/status.json`] = JSON.stringify({ state: 'aligned', present: { card: 'off' } })
      await $.turn.complete(TURN_DONE)
      const off = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await off.find({ type: 'Text', text: /plumb/ })).toBeUndefined()
      await off.unmount()
    })

    test("SP8's progress joins the status line while a long step runs", async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.plumb/session/${SESSION}/progress`] = JSON.stringify({ state: 'running', step: 'judging the backlog', done: 10, total: 160 })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'plumb ● 2 await you · judging the backlog · 10/160' })).toBeDefined()
      expect(w.statuses.at(-1)).toBe('● 2 await you · judging the backlog · 10/160') // SR-290: the host heads it 'plumb:', never 'plumb: plumb'
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
