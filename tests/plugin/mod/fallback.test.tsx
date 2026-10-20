// The fallback (SP7 5.8; SR-087 EX-4): without plumb's interpreter the panel registers nothing
// and draws nothing (the command hooks print everything as before); a hook that fails hands
// the event on unchanged, says so once, and stops the heartbeat, so the stop hook prints again.
import { describe, expect, test } from 'claude-code/testing'

import { ROOT, SESSION } from './fixtures'
import { BAND, install, NOW, START, SURFACES, TURN_DONE, world } from './harness'

const MOD = `${ROOT}/.plumb/session/${SESSION}/mod.json`
const TURN = { text: 'add late fees', turnId: 't-2' }

for (const surface of SURFACES) {
  describe(`fallback on the ${surface}`, () => {
    test('no interpreter for plumb: no hello, no band', async ($, on) => {
      const w = world()
      delete w.files[`${ROOT}/.plumb/session/${SESSION}/host.json`]
      install(on, w)
      await $.session.start(START)
      await $.turn.start(TURN)
      expect(w.runs).toHaveLength(0)
      expect(w.writes).toHaveLength(0)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /plumb/ })).toBeUndefined()
      await ui.unmount()
    })

    test('the interpreter named only once the session-start hook ran: the first turn says hello', async ($, on) => {
      const w = world()
      const host = w.files[`${ROOT}/.plumb/session/${SESSION}/host.json`] as string
      delete w.files[`${ROOT}/.plumb/session/${SESSION}/host.json`]
      install(on, w)
      await $.session.start(START)
      expect(w.runs).toHaveLength(0)
      w.files[`${ROOT}/.plumb/session/${SESSION}/host.json`] = host
      await $.turn.start(TURN)
      expect(w.runs.map(r => r.argv[4])).toEqual(['hello'])
    })

    test('while it works, each turn refreshes the heartbeat in mod.json', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      await $.turn.start(TURN)
      const beat = w.writes.filter(x => x.path === MOD).map(x => JSON.parse(x.text))
      expect(beat).toHaveLength(1)
      expect(beat[0]).toMatchObject({ active: true, key_digest: 'd'.repeat(64), heartbeat: new Date(NOW).toISOString().replace(/\.\d+Z$/, 'Z') })
    })

    test('a hook that fails hands the event on, says so once, and stops the heartbeat', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      w.broken = true
      await $.turn.start(TURN) // the heartbeat cannot be written
      const done = await $.turn.complete(TURN_DONE)
      expect(done.text).toBe(TURN_DONE.answer) // the answer, unchanged
      expect(w.logs).toEqual(["plumb's panel is off for this session; plumb keeps working in the background."])
      w.broken = false
      w.writes.length = 0
      await $.turn.start(TURN)
      expect(w.writes.filter(x => x.path === MOD)).toHaveLength(0)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /plumb/ })).toBeUndefined()
      await ui.unmount()
    })
  })
}
