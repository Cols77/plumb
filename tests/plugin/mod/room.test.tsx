// A question waiting in the room (SR-333, DEC-294): the owner chose 'Study it in the room' in the
// question tool, so plumb marks the question for the band; the band draws a brass line 'a
// question waits in the room', whose press runs `plumb mod room --card` (the key on stdin) and
// the room opens on that question; the line goes. Nothing opens the room without the press.
// Each case runs on the terminal and the desktop.
import { describe, expect } from 'claude-code/testing'

import { BRASS } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, test, world } from './harness'

const MARK = `${ROOT}/.plumb/session/${SESSION}/room_waits.json`
const CARD = 'choice:0123456789ab'
const LINE = 'a question waits in the room'

async function band($: any, on: any, surface: (typeof SURFACES)[number]) {
  const w = world()
  const answer = w.answer
  // what plumb mod room --card does: the room opens on the question, the mark goes
  w.answer = (action, argv) => {
    if (action !== 'room') return answer(action, argv)
    delete w.files[MARK]
    return { exitCode: 0, data: { origin: 'http://127.0.0.1:50123', card: CARD } }
  }
  install(on, w)
  await $.session.start(START)
  return { w, ui: await $.ui.mount({ plugin: 'plumb', surface, ...BAND }) }
}

const rooms = (w: ReturnType<typeof world>) => w.runs.filter(r => r.argv[4] === 'room')

for (const surface of SURFACES) {
  describe(`a question waiting in the room on the ${surface}`, () => {
    test('SR-333 EX-2: no question chosen for the room: no line, the room stays closed', async ($, on) => {
      const { w, ui } = await band($, on, surface)
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ type: 'Text', text: LINE })).toBeUndefined()
      expect(await ui.find({ key: 'roomq' })).toBeUndefined()
      expect(rooms(w)).toEqual([])
      await ui.unmount()
    })

    test("SR-333 EX-3: the question chosen for the room: the band's brass line; its press opens the room on it", async ($, on) => {
      const { w, ui } = await band($, on, surface)
      w.files[MARK] = JSON.stringify({ card: CARD })
      await $.turn.complete(TURN_DONE)
      const line = await ui.find({ type: 'Text', text: LINE })
      expect(line?.props.color).toBe(BRASS)
      expect(rooms(w)).toEqual([]) // the room never opens by itself
      await ui.press({ key: 'roomq' })
      const [room] = rooms(w)
      expect(room?.argv.slice(3)).toEqual(['mod', 'room', '--session', SESSION, '--root', ROOT, '--json', '--card', CARD])
      const key = JSON.parse(room?.stdin ?? '{}').key as string
      expect(key).toMatch(/^[0-9a-f]{64}$/)
      expect(room?.argv.join(' ')).not.toContain(key)
      expect(await ui.find({ type: 'Text', text: LINE })).toBeUndefined()
      expect(w.toasts).toEqual([])
      await ui.unmount()
    })
  })
}
