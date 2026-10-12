// A trial batch in the panel (SR-106, INT-032 (2), INT-025): every record of the batch has its
// own Yes and No, each press names that record's offer, and a record answered is not offered
// again; the No is the owner's "not what I meant", which plumb counts as a real 'no' example.
import { describe, expect, mock, test } from 'claude-code/testing'

import { DRAW_TRIAL, PRESS_TRIAL_NO } from './fixtures'
import { BAND, install, START, SURFACES, world } from './harness'

const CARD = DRAW_TRIAL.cards[0] as any
const ID = CARD.id as string

/** What plumb draws once the owner answered the second record: the first one only. */
function afterNo() {
  const card = JSON.parse(JSON.stringify(CARD))
  card.questions = card.questions.slice(0, 1)
  card.offers = card.offers.slice(0, 1)
  card.answers = [{ question: 'trial:5d1c0a9e7b21#2', answer: 'rejected', digest: '' }]
  return { ...DRAW_TRIAL, cards: [card] }
}

function trialWorld() {
  let pressed = false
  const w = world({
    answer: (action, argv) => {
      if (action === 'draw') return { exitCode: 0, data: pressed ? afterNo() : DRAW_TRIAL }
      if (action === 'press') {
        pressed = true
        return { exitCode: 0, data: PRESS_TRIAL_NO }
      }
      return world().answer(action, argv)
    },
  })
  return w
}

for (const surface of SURFACES) {
  describe(`a trial batch on the ${surface}`, () => {
    test('each record has its own Yes and No under its own words', async ($, on) => {
      install(on, trialWorld())
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: '• CSV export' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '• Late fees' })).toBeDefined()
      await ui.press({ key: `items:${ID}` })
      for (const q of [0, 1]) {
        expect((await ui.find({ key: `press:${q}:0:${ID}` }))?.props.label).toBe('Yes, that is what I meant')
        expect((await ui.find({ key: `press:${q}:1:${ID}` }))?.props.label).toBe('No, that is not what I meant')
      }
      expect(await ui.find({ type: 'Text', text: 'CSV export' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'Late fees' })).toBeDefined()
      await ui.unmount()
    })

    test("No on one record presses that record's offer and it is not offered again", async ($, on) => {
      const w = trialWorld()
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: `items:${ID}` })
      await ui.press({ key: `press:1:1:${ID}` })
      const [run] = w.runs.filter(r => r.argv[4] === 'press')
      expect(run?.argv.slice(-4)).toEqual(['--offer', 'sha256:t009', '--choice', '1'])
      expect(session.appended().map(r => (r.message.content as any)[0]?.text)).toEqual([
        PRESS_TRIAL_NO.line, PRESS_TRIAL_NO.model_note])
      // drawn again: the answered record is gone, the other keeps its own buttons and words
      expect(await ui.find({ key: `press:1:0:${ID}` })).toBeUndefined()
      expect((await ui.find({ key: `press:0:1:${ID}` }))?.props.label).toBe('No, that is not what I meant')
      expect(await ui.find({ key: `press:1:1:${ID}` })).toBeUndefined()
      await ui.unmount()
    })
  })
}
