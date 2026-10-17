// A new study announced (SR-294): a toast with plumb's words and the band's study line in brass
// while the study is new; the line goes once the owner opens it in the room. Each case runs on
// the terminal and the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { BRASS } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, world } from './harness'

const LOOP = `${ROOT}/.plumb/session/${SESSION}/intent/aaaaaaaaaaaa.json`
const STUDY = `${ROOT}/.plumb/studies/how-plumb-s-background-jobs-run.md`
const TITLE = "How plumb's background jobs run"
const LINE = `new study: ${TITLE}`

function study(status: string): string {
  return `---\ntitle: ${JSON.stringify(TITLE)}\ntopic: "background jobs"\nstep: "plan"\nloop: "aaaaaaaaaaaa"\n` +
    `why: "the plan adds a job"\nstatus: ${JSON.stringify(status)}\n---\n\nA dispatcher hands each job to a worker.\n`
}

async function band($: any, on: any, surface: (typeof SURFACES)[number]) {
  const w = world()
  w.files[LOOP] = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z',
    step: 'plan', tasks: null, stopped: null, stages: {} })
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  install(on, w)
  await $.session.start(START)
  return { w, ui: await $.ui.mount({ plugin: 'plumb', surface, ...BAND }) }
}

for (const surface of SURFACES) {
  describe(`a new study on the ${surface}`, () => {
    test("SR-294 EX-1: a study written in the plan step: a toast and the band's brass line", async ($, on) => {
      const { w, ui } = await band($, on, surface)
      expect(await ui.find({ type: 'Text', text: /^new study/ })).toBeUndefined()
      w.files[STUDY] = study('new')
      await $.tool.call({ tool: 'Bash', command: 'plumb study add --title "x" --why y --file b.md' } as any)
      expect(w.toasts).toEqual([LINE])
      const line = await ui.find({ type: 'Text', text: /^new study/ })
      expect(line?.text).toBe(LINE)
      expect(line?.props.color).toBe(BRASS)
      await $.turn.complete(TURN_DONE)
      expect(w.toasts.filter(t => t.startsWith('new study'))).toEqual([LINE])   // once, not again at the turn's end
      await ui.unmount()
    })

    test("SR-294 EX-3: the owner reads the study in the room: the band's line goes", async ($, on) => {
      const { w, ui } = await band($, on, surface)
      w.files[STUDY] = study('new')
      await $.turn.complete(TURN_DONE)
      expect((await ui.find({ type: 'Text', text: /^new study/ }))?.text).toBe(LINE)
      w.files[STUDY] = study('opened')
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ type: 'Text', text: /^new study/ })).toBeUndefined()
      await ui.unmount()
    })
  })
}
