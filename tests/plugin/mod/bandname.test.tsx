// SR-415: the band's line begins with the Claude Code session's name (the one other sessions use
// to message it), read from ~/.claude/sessions/<pid>.json ({sessionId, name}); 'iaso' when none.
import { describe, expect } from 'claude-code/testing'

import { SESSION } from './fixtures'
import { BAND, install, START, SURFACES, test, world } from './harness'

const HOME = '/home/owner'

for (const surface of SURFACES) {
  describe(`band name on the ${surface}`, () => {
    test('SR-415 EX-1: the session is named iaso-c8: the line begins with iaso-c8', async ($, on) => {
      const w = world()
      w.files[`${HOME}/.claude/sessions/4242.json`] = JSON.stringify({ sessionId: 'other', name: 'iaso-zz' })
      w.files[`${HOME}/.claude/sessions/4243.json`] = JSON.stringify({ sessionId: SESSION, name: 'iaso-c8', nameSource: 'user' })
      install(on, w, { HOME })
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^iaso-c8 / })).toBeDefined()
      await ui.unmount()
    })

    test('SR-415 EX-2: no name can be found: the line begins with iaso, as before', async ($, on) => {
      const w = world()
      w.files[`${HOME}/.claude/sessions/4242.json`] = JSON.stringify({ sessionId: 'other', name: 'iaso-zz' })
      install(on, w, { HOME })
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^iaso [●✓·]/ })).toBeDefined()
      await ui.unmount()
    })
  })
}
