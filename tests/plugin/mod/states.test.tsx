// SR-160: the pane groups the session's cards by where they stand: waiting for you, being
// processed, blocked (with its reason) and done; empty groups are not drawn.
import { describe, expect, test } from 'claude-code/testing'

import { DRAW, SESSION } from './fixtures'
import { install, START, SURFACES, world } from './harness'

const PANE = { component: 'Pane' as const, requestId: 'plumb-cards', props: { bodyColumns: 100 } }
const card = (id: string, state: string, reason = '') =>
  ({ ...(DRAW.cards[0] as any), id, topic: id, state, reason, repeats: state === 'waiting', offers: state === 'waiting' ? (DRAW.cards[0] as any).offers : [] })

function drawing(cards: any[]) {
  return world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: { session: SESSION, cards } } : world().answer(action, argv) })
}

for (const surface of SURFACES) {
  describe(`card states on the ${surface}`, () => {
    test('a pressed card is under being processed, a changed one under blocked with why, a finished one under done', async ($, on) => {
      install(on, drawing([card('wait-1', 'waiting'), card('press-1', 'processing'),
        card('stale-1', 'blocked', '"X" changed since it was shown; nothing was confirmed.'), card('over-1', 'done')]))
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...PANE })
      const text = async (t: string | RegExp) => (await ui.find({ type: 'Text', text: t }))?.text
      expect(await text('Waiting for you (1)')).toBeDefined()
      expect(await text('Being processed (1)')).toBeDefined()
      expect(await text('press-1')).toBeDefined()
      expect(await text('Blocked (1)')).toBeDefined()
      expect(await text(/stale-1: "X" changed since it was shown/)).toBeDefined()
      expect(await text('Done this session (1)')).toBeDefined()
      await ui.unmount()
    })

    test('three cards waiting and none answered: all under waiting, no other group', async ($, on) => {
      install(on, drawing([card('a', 'waiting'), card('b', 'waiting'), card('c', 'waiting')]))
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...PANE })
      const text = async (t: string | RegExp) => (await ui.find({ type: 'Text', text: t }))?.text
      expect(await text('Waiting for you (3)')).toBeDefined()
      expect(await text(/Being processed|Blocked|Done this session/)).toBeUndefined()
      await ui.unmount()
    })
  })
}
