// A study whose records changed (SR-360 EX-2, DEC-336): the band's brass line names the study and
// what changed, with 'Rewrite it' and 'not now'; a press runs `plumb mod study --refresh`, the key
// on stdin only; nothing is rewritten without the owner's yes. Each case runs on both surfaces.
import { describe, expect } from 'claude-code/testing'

import { BRASS } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, test, world } from './harness'

const SLUG = 'how-merges-are-held'
const STUDY = `${ROOT}/.plumb/studies/${SLUG}.md`
const CHANGED = 'A merge is held until the owner confirms its records'
const LINE = `study out of date: How merges are held (${CHANGED} changed)`

const study = (changed: string, refresh = '') =>
  `---\ntitle: "How merges are held"\ntopic: "merges"\nstep: ""\nloop: ""\nwhy: "the owner asked"\n` +
  `recommend: "diagrams"\ndepth: "diagrams"\nrecords: [{"id": "SR-901", "title": ${JSON.stringify(CHANGED)}, "hash": "sha256:a"}]\n` +
  `changed: ${JSON.stringify(changed)}\nrefresh: ${JSON.stringify(refresh)}\nstatus: "opened"\n---\n\nA merge waits.\n`

async function band($: any, on: any, surface: (typeof SURFACES)[number], changed = CHANGED) {
  const w = world()
  const answer = w.answer
  // what plumb mod study --refresh does: the owner's answer recorded on the study
  w.answer = (action, argv) => {
    if (action !== 'study') return answer(action, argv)
    const yes = argv[argv.indexOf('--refresh') + 1] === 'yes'
    w.files[STUDY] = study(CHANGED, yes ? 'asked' : 'no')
    return { exitCode: 0, data: { slug: SLUG, status: 'opened', depth: 'diagrams', refresh: yes ? 'asked' : 'no' } }
  }
  w.files[STUDY] = study(changed)
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  install(on, w)
  await $.session.start(START)
  const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
  await $.turn.complete(TURN_DONE)
  return { w, ui }
}

const refreshes = (w: ReturnType<typeof world>) => w.runs.filter(r => r.argv[4] === 'study')

for (const surface of SURFACES) {
  describe(`a study out of date on the ${surface}`, () => {
    test('SR-360 EX-2: the band names the study and what changed, and offers a rewrite', async ($, on) => {
      const { w, ui } = await band($, on, surface)
      const line = await ui.find({ type: 'Text', text: LINE })
      expect(line?.props.color).toBe(BRASS)
      expect((await ui.find({ key: 'refresh:yes' }))?.props.label).toBe('Rewrite it')
      expect((await ui.find({ key: 'refresh:no' }))?.props.label).toBe('not now')
      expect(refreshes(w)).toEqual([]) // nothing asked without the press
      await ui.unmount()
    })

    test("SR-360 EX-2: 'Rewrite it' asks plumb, the key on stdin only, and the line goes", async ($, on) => {
      const { w, ui } = await band($, on, surface)
      await ui.press({ key: 'refresh:yes' })
      const [run] = refreshes(w)
      expect(run?.argv.slice(3)).toEqual(['mod', 'study', '--session', SESSION, '--root', ROOT, '--json',
        '--study', SLUG, '--refresh', 'yes'])
      const key = JSON.parse(run?.stdin ?? '{}').key as string
      expect(key).toMatch(/^[0-9a-f]{64}$/)
      expect(run?.argv.join(' ')).not.toContain(key)
      expect(await ui.find({ type: 'Text', text: LINE })).toBeUndefined()
      await ui.unmount()
    })

    test("SR-360 EX-2: 'not now' records the no and the line goes", async ($, on) => {
      const { w, ui } = await band($, on, surface)
      await ui.press({ key: 'refresh:no' })
      expect(refreshes(w)[0]?.argv.slice(-2)).toEqual(['--refresh', 'no'])
      expect(await ui.find({ type: 'Text', text: LINE })).toBeUndefined()
      await ui.unmount()
    })

    test('SR-360 EX-2: a study whose records did not change has no such line', async ($, on) => {
      const { ui } = await band($, on, surface, '')
      expect(await ui.find({ key: 'refresh:yes' })).toBeUndefined()
      await ui.unmount()
    })
  })
}
