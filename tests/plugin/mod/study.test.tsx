// A new study announced (SR-294): the band's study line in brass while the study is new, no
// toast; the line is a Button whose press runs `plumb mod room` (the key on stdin, the agent
// marker emptied), which opens the browser room on the study and marks it opened, so the line
// goes. Nothing opens the room without the press. Each case runs on the terminal and the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { BRASS } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, world } from './harness'

const LOOP = `${ROOT}/.plumb/session/${SESSION}/intent/aaaaaaaaaaaa.json`
const SLUG = 'how-plumb-s-background-jobs-run'
const STUDY = `${ROOT}/.plumb/studies/${SLUG}.md`
const TITLE = "How plumb's background jobs run"
const LINE = `new study: ${TITLE}`

function study(status: string): string {
  return `---\ntitle: ${JSON.stringify(TITLE)}\ntopic: "background jobs"\nstep: "plan"\nloop: "aaaaaaaaaaaa"\n` +
    `why: "the plan adds a job"\nstatus: ${JSON.stringify(status)}\n---\n\nA dispatcher hands each job to a worker.\n`
}

async function band($: any, on: any, surface: (typeof SURFACES)[number]) {
  const w = world()
  const answer = w.answer
  // what plumb mod room does: the room opens on the study, which is marked opened
  w.answer = (action, argv) => {
    if (action !== 'room') return answer(action, argv)
    w.files[STUDY] = study('opened')
    return { exitCode: 0, data: { origin: 'http://127.0.0.1:50123', slug: SLUG, status: 'opened' } }
  }
  w.files[LOOP] = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z',
    step: 'plan', tasks: null, stopped: null, stages: {} })
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  install(on, w)
  await $.session.start(START)
  return { w, ui: await $.ui.mount({ plugin: 'plumb', surface, ...BAND }) }
}

const rooms = (w: ReturnType<typeof world>) => w.runs.filter(r => r.argv[4] === 'room')

for (const surface of SURFACES) {
  describe(`a new study on the ${surface}`, () => {
    test("SR-294 EX-1: a study written in the plan step: the band's brass line, no toast", async ($, on) => {
      const { w, ui } = await band($, on, surface)
      expect(await ui.find({ type: 'Text', text: /^new study/ })).toBeUndefined()
      w.files[STUDY] = study('new')
      await $.tool.call({ tool: 'Bash', command: 'plumb study add --title "x" --why y --file b.md' } as any)
      const line = await ui.find({ type: 'Text', text: /^new study/ })
      expect(line?.text).toBe(LINE)
      expect(line?.props.color).toBe(BRASS)
      expect(await ui.find({ key: 'study' })).toBeDefined()
      await $.turn.complete(TURN_DONE)
      expect(w.toasts.filter(t => t.startsWith('new study'))).toEqual([])
      await ui.unmount()
    })

    test('SR-294 EX-2: the owner does nothing: the room stays closed and the study waits', async ($, on) => {
      const { w, ui } = await band($, on, surface)
      w.files[STUDY] = study('new')
      await $.turn.complete(TURN_DONE)
      await $.turn.complete(TURN_DONE)
      expect(rooms(w)).toEqual([])
      expect((await ui.find({ type: 'Text', text: /^new study/ }))?.text).toBe(LINE)
      await ui.unmount()
    })

    test('SR-294 EX-3: pressing the line opens the room on that study, the key on stdin only', async ($, on) => {
      const { w, ui } = await band($, on, surface)
      w.files[STUDY] = study('new')
      await $.turn.complete(TURN_DONE)
      await ui.press({ key: 'study' })
      const [room] = rooms(w)
      expect(room?.argv.slice(3)).toEqual(['mod', 'room', '--session', SESSION, '--root', ROOT, '--json', '--study', SLUG])
      const key = JSON.parse(room?.stdin ?? '{}').key as string
      expect(key).toMatch(/^[0-9a-f]{64}$/)
      expect(room?.argv.join(' ')).not.toContain(key)
      expect(room?.env.PLUMB_AGENT_SESSION).toBe('')
      await ui.unmount()
    })

    test("SR-294 EX-4: once the owner opened it from the band, the band's line goes", async ($, on) => {
      const { w, ui } = await band($, on, surface)
      w.files[STUDY] = study('new')
      await $.turn.complete(TURN_DONE)
      expect((await ui.find({ type: 'Text', text: /^new study/ }))?.text).toBe(LINE)
      await ui.press({ key: 'study' })
      expect(await ui.find({ type: 'Text', text: /^new study/ })).toBeUndefined()
      expect(w.toasts.filter(t => t.startsWith('new study'))).toEqual([])
      await ui.unmount()
    })
  })
}
