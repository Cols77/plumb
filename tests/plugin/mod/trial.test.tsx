// A trial card is the read-back of one record (SR-133, SR-106): Yes, No or Fix it, each press
// names that record's offer, and the next card opens once it is answered.
import { describe, expect, mock, test } from 'claude-code/testing'

import { findPress, pressKey } from '../../../plugin/hooks/cards'
import { DRAW_TRIAL, PRESS_TRIAL_NO } from './fixtures'
import { BAND, install, START, SURFACES, world } from './harness'

const CARD = DRAW_TRIAL.cards[0] as any
const OFFER = CARD.offers[0].offer_id as string

/** The next record's trial card. */
function other() {
  const card = JSON.parse(JSON.stringify(CARD))
  card.id = 'trial:SR-009'
  card.offers[0].offer_id = 'sha256:t009'
  card.offers[0].record = 'SR-009'
  return card
}

for (const surface of SURFACES) {
  describe(`a trial card on the ${surface}`, () => {
    test('shows the owner words with their date and Yes, No, Fix it for the one record', async ($, on) => {
      install(on, world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: DRAW_TRIAL } : world().answer(action, argv) }))
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: CARD.content.context[0] })).toBeDefined()
      const labels = (await ui.findAll({ type: 'Button' })).filter(b => b.key?.startsWith('press:')).map(b => b.props.label)
      expect(labels.slice(0, 3)).toEqual(['Yes', 'No', 'Fix it'])
      await ui.unmount()
    })

    test('No presses that record offer and the next card opens', async ($, on) => {
      let pressed = false
      const w = world({
        answer: (action, argv) => {
          if (action === 'draw') return { exitCode: 0, data: { ...DRAW_TRIAL, cards: [pressed ? other() : CARD] } }
          if (action === 'press') {
            pressed = true
            return { exitCode: 0, data: PRESS_TRIAL_NO }
          }
          return world().answer(action, argv)
        },
      })
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: `press:1:${OFFER}` })
      const [run] = w.runs.filter(r => r.argv[4] === 'press')
      expect(run?.argv.slice(-4)).toEqual(['--offer', OFFER, '--choice', '1'])
      expect(session.appended().map(r => (r.message.content as any)[0]?.text)).toEqual([
        PRESS_TRIAL_NO.line, PRESS_TRIAL_NO.model_note])
      expect(await ui.find({ key: `press:0:${OFFER}` })).toBeUndefined()
      expect(await ui.find({ key: 'press:0:sha256:t009' })).toBeDefined()
      await ui.unmount()
    })
  })
}

describe('a press key names its offer, not its place', () => {
  test('a press from an out-of-date draw never lands on the record now in its place', () => {
    const next = other()
    const stale = pressKey(CARD.offers[0], 1)
    expect(findPress([next], stale)).toBeNull()
    const kept = findPress([next], pressKey(next.offers[0], 1))
    expect(kept?.offer.record).toBe('SR-009')
    expect(kept?.button.label).toBe('No')
    expect(findPress([next, CARD], stale)?.card.id).toBe(CARD.id)
    expect(findPress([CARD], `press:9:${OFFER}`)).toBeNull()
    expect(findPress([CARD], 'press:1:sha256:gone')).toBeNull()
  })
})
