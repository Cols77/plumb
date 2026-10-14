// The card pane (SR-155): opened only by the owner's press, it shows one waiting card at a time
// with Back and Next and 'n of m', asks to dock 80 columns wide, and where it sits inline says
// how to get it beside the conversation. Each case runs on the terminal and the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { DRAW, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, world } from './harness'

const PATH = '.plumb/diagrams/hooks.html'
const first = JSON.parse(JSON.stringify(DRAW.cards[0]))
const second = { ...JSON.parse(JSON.stringify(DRAW.cards[1])), diagram: PATH }
const third = { ...JSON.parse(JSON.stringify(DRAW.cards[0])), id: 'clarify:SR-003', topic: 'Third' }
const THREE = { session: SESSION, cards: [first, second, third] }

const drawing = (data: unknown) =>
  world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data } : world().answer(action, argv) })

const pane = (surface: 'terminal' | 'desktop', placement: 'dock' | 'inline' = 'dock') => ({
  plugin: 'plumb', surface, component: 'Pane' as const, requestId: 'plumb-cards',
  props: { title: 'plumb', bodyColumns: 80, placement, scroll: { offset: 0, bodyRows: 40 } },
}) as any

for (const surface of SURFACES) {
  describe(`the pane on the ${surface}`, () => {
    test('EX-1: Next shows the second card, its diagram above its question, and 2 of 3', async ($, on) => {
      install(on, drawing(THREE))
      await $.session.start(START)
      const ui = await $.ui.mount(pane(surface))
      expect(await ui.find({ type: 'Text', text: '1 of 3' })).toBeDefined()
      await ui.press({ key: 'next' })
      expect(await ui.find({ type: 'Text', text: '2 of 3' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: `Diagram: ${PATH} (open it to see it)` })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'Confirm button' })).toBeDefined()
      await ui.unmount()
    })

    test('EX-2: Next on the last stays; Back moves to the one before', async ($, on) => {
      install(on, drawing(THREE))
      await $.session.start(START)
      const ui = await $.ui.mount(pane(surface))
      for (let i = 0; i < 4; i++) await ui.press({ key: 'next' })
      expect(await ui.find({ type: 'Text', text: '3 of 3' })).toBeDefined()
      await ui.press({ key: 'back' })
      expect(await ui.find({ type: 'Text', text: '2 of 3' })).toBeDefined()
      await ui.press({ key: 'back' })
      await ui.press({ key: 'back' })
      expect(await ui.find({ type: 'Text', text: '1 of 3' })).toBeDefined()
      await ui.unmount()
    })

    test('EX-3: nothing waits: it says so and draws no Back or Next', async ($, on) => {
      install(on, drawing({ session: SESSION, cards: [] }))
      await $.session.start(START)
      const ui = await $.ui.mount(pane(surface))
      expect(await ui.find({ type: 'Text', text: 'nothing awaits you' })).toBeDefined()
      expect(await ui.find({ key: 'back' })).toBeUndefined()
      expect(await ui.find({ key: 'next' })).toBeUndefined()
      await ui.unmount()
    })

    test('EX-4: the press asks for 80 columns; inline, one line says it docks from 110', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'pane' })
      expect(w.opens).toEqual([{ id: 'plumb-cards', columns: 80 }])
      await band.unmount()
      const line = /docks on the right beside the conversation/
      const inline = await $.ui.mount(pane(surface, 'inline'))
      expect(await inline.find({ type: 'Text', text: line })).toBeDefined()
      await inline.unmount()
      const docked = await $.ui.mount(pane(surface))
      expect(await docked.find({ type: 'Text', text: line })).toBeUndefined()
      await docked.unmount()
    })

    test('EX-5: a turn ending with cards waiting opens no pane', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      await $.turn.complete(TURN_DONE)
      expect(w.opens).toEqual([])
    })
  })
}
