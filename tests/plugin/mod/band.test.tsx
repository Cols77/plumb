// The band above the prompt (SP7 5.2 as re-aligned: iaso's status with the count of questions
// waiting, SP8's progress; SR-085 EX-2, DEC-034). The chips, Hide and the build and judge faults
// are SR-409 and SR-413, in categories.test.tsx. Each case runs on the terminal and the desktop.
import { describe, expect } from 'claude-code/testing'

import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, test, world } from './harness'

const STATUS = `${ROOT}/.iaso/session/status.json`

for (const surface of SURFACES) {
  describe(`band on the ${surface}`, () => {
    test('with nothing awaiting, one line: the state, the intent summary and Hide', async ($, on) => {
      const w = world()
      w.files[STATUS] = JSON.stringify({ state: 'aligned', intent_summary: 'invoices · late fees' })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect((await ui.find({ type: 'Text', text: /^iaso / }))?.text).toBe('iaso ✓ aligned')
      expect(await ui.find({ type: 'Text', text: 'invoices · late fees' })).toBeDefined()
      expect(await ui.find({ key: 'hide' })).toBeDefined()
      expect(await ui.findAll({ type: 'Button' })).toHaveLength(1)
      await ui.unmount()
    })

    test("SP8's progress joins the status line while a long step runs", async ($, on) => {
      const w = world()
      w.files[`${ROOT}/.iaso/session/${SESSION}/progress`] = JSON.stringify({ state: 'running', step: 'judging the backlog', done: 10, total: 160 })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'iaso ● 2 await you · judging the backlog · 10/160' })).toBeDefined()
      expect(w.statuses).toEqual([]) // the band alone shows the status: nothing pinned under the prompt
      await ui.unmount()
    })

    test('idle in a repository iaso has not adopted: no process, no band', async ($, on) => {
      const w = world({ files: {} })
      install(on, w)
      await $.session.start(START)
      expect(w.runs).toHaveLength(0)
      const ui = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /iaso/ })).toBeUndefined()
      await ui.unmount()
    })
  })
}
