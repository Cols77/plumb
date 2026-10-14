// Every card the panel draws is a read-back or a choice and stands alone (SR-129, INT-036): the
// topic and the question, the context, what plumb assumed and the one thing it will not do,
// each option with what it does, the recommended one first, then the buttons.
import { describe, expect, test } from 'claude-code/testing'

import { DRAW, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, world } from './harness'

const CHOICE = DRAW.cards[1] as any
const READBACK = DRAW.cards[0] as any

function drawing(card: any) {
  return world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: { session: SESSION, cards: [card] } } : world().answer(action, argv) })
}

for (const surface of SURFACES) {
  describe(`cards on the ${surface}`, () => {
    test('a choice shows its question, its context and each option with what it does', async ($, on) => {
      install(on, drawing(CHOICE))
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      const text = async (t: string | RegExp) => (await ui.find({ type: 'Text', text: t }))?.text
      expect(await text('Confirm button')).toBeDefined()
      expect(await text(CHOICE.content.issue)).toBeDefined()
      for (const line of CHOICE.content.context) expect(await text(line)).toBeDefined()
      expect(await text('1. Keep the requirement and re-pin it (recommended)')).toBeDefined()
      expect(await text(/the button is one more way you confirm/)).toBeDefined()
      expect(await text('2. Reword the requirement')).toBeDefined()
      expect(await text(/The requirement names the button/)).toBeDefined()
      expect(await text(/Assumed:/)).toBeUndefined()
      const labels = (await ui.findAll({ type: 'Button' })).filter(b => b.key?.startsWith('press:')).map(b => b.props.label)
      expect(labels).toEqual(['Keep the requirement and re-pin it', 'Reword the requirement', 'Ask for a change', 'Leave open'])
      await ui.unmount()
    })

    test('a read-back shows what it assumed and the one thing it will not do', async ($, on) => {
      install(on, drawing(READBACK))
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      const text = async (t: string | RegExp) => (await ui.find({ type: 'Text', text: t }))?.text
      expect(await text('CSV export')).toBeDefined()
      expect(await text('The report exports as CSV with one row per invoice.')).toBeDefined()
      expect(await text('You asked for this on 11 Oct.')).toBeDefined()
      expect(await text('Assumed: Dates are written as YYYY-MM-DD.')).toBeDefined()
      expect(await text('Not doing: No other export format.')).toBeDefined()
      // a card with no diagram draws nothing of one (SR-145 EX-4)
      expect(await text(/Diagram:/)).toBeUndefined()
      await ui.unmount()
    })
  })
}
