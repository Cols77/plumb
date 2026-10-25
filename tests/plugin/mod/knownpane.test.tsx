// The known problems (SR-367): the band shows them as one collapsed line, "N known problems
// open", only while any is open and never one line per problem; its press runs
// `plumb mod known --json` (the agent marker emptied) and opens plumb's docked pane, as the loop
// pane opens, listing each problem with its symptom, cause, fix, state and history, open ones
// first. The open pane follows the register. Each case runs on the terminal and the desktop.
import { describe, expect } from 'claude-code/testing'

import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, test, world } from './harness'

const REGISTER = `${ROOT}/.plumb/known-issues.json`
const CASE = `${ROOT}/.plumb/cache/debug/KI-3.json`

const issue = (n: number, state: string, history: string[] = []) => ({
  id: `KI-${n}`, title: `problem ${n}`, symptom: `symptom ${n}`, cause: `cause ${n}`, fix: state === 'open' && !history.length ? '' : `abc${n}`,
  fixed: state === 'open' && !history.length ? '' : '2026-10-20', state, history,
})

// two open (KI-3 fixed once, its case reopened), five fixed lately: as `plumb mod known --json` answers
const KNOWN = {
  open: 2,
  issues: [issue(1, 'open'), issue(3, 'open', ['fixed, fix abc3', 'open again: symptom 3 again']),
    ...[2, 4, 5, 6, 7].map(n => issue(n, 'fixed'))],
}

// `known` is read at each run: a case changes its own answer, never the shared KNOWN (a case
// that ran past its time would change the next case's)
function knownWorld(open = 2, known = () => KNOWN) {
  const w = world()
  const answer = w.answer
  w.answer = (action, argv) => action === 'known' ? { exitCode: 0, data: { ...known(), open } } : answer(action, argv)
  w.files[REGISTER] = JSON.stringify({ issues: KNOWN.issues.map(({ history, ...r }) => r) })
  return w
}

const pane = (surface: 'terminal' | 'desktop') => ({
  plugin: 'plumb', surface, component: 'Pane' as const, requestId: 'plumb-known',
  props: { title: 'plumb', bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 } },
}) as any

for (const surface of SURFACES) {
  describe(`the known problems on the ${surface}`, () => {
    test('SR-367 EX-1: two open and five fixed: one line saying two are open, no line per problem', async ($, on) => {
      const w = knownWorld()
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ type: 'Text', text: '2 known problems open' })).toBeDefined()
      expect(await band.find({ type: 'Text', text: /problem \d|symptom|cause/ })).toBeUndefined()
      const known = w.runs.find(r => r.argv[4] === 'known')
      expect(known?.argv.slice(3)).toEqual(['mod', 'known', '--session', SESSION, '--root', ROOT, '--json'])
      expect(known?.env.PLUMB_AGENT_SESSION).toBe('')
      await band.unmount()
    })

    test('SR-367 EX-2: the press opens a docked pane with each problem, open ones first', async ($, on) => {
      const w = knownWorld()
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'known' })
      expect(w.opens).toEqual([{ id: 'plumb-known', columns: 80, closeOnEscape: true }])
      const view = await $.ui.mount(pane(surface))
      const heads = await view.findAll({ type: 'Text', text: / · (open|fixed)/ })
      expect(heads.map(t => t.text).slice(0, 3)).toEqual(['problem 1 · open', 'problem 3 · open',
        'problem 2 · fixed 2026-10-20'])
      expect(await view.find({ type: 'Text', text: '  symptom: symptom 3' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '  cause: cause 3' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '  fix: abc3' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '  fix: none yet' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: '  history: open again: symptom 3 again' })).toBeDefined()
      await view.unmount() // Esc: the band stays
      expect(await band.find({ type: 'Text', text: '2 known problems open' })).toBeDefined()
      await band.unmount()
    })

    test('SR-367 EX-3: none open: no known problems line', async ($, on) => {
      const w = knownWorld(0)
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await band.find({ key: 'known' })).toBeUndefined()
      expect(await band.find({ type: 'Text', text: /known problem/ })).toBeUndefined()
      await band.unmount()
    })

    test('SR-367: the open pane follows the register; an unchanged register runs no plumb', async ($, on) => {
      let known = KNOWN
      const w = knownWorld(2, () => known)
      const clock = install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'known' })
      const view = await $.ui.mount(pane(surface))
      const runs = w.runs.filter(r => r.argv[4] === 'known').length
      await clock.advance(2000) // the band's period (POLL_MS in register.tsx): nothing moved
      expect(w.runs.filter(r => r.argv[4] === 'known').length).toBe(runs)
      known = { ...KNOWN, issues: KNOWN.issues.map(i => i.id === 'KI-1' ? { ...i, state: 'fixed', fixed: '2026-10-25', fix: 'def1' } : i) }
      w.files[CASE] = JSON.stringify({ id: 'KI-3', state: 'resolved' }) // a case moved
      await clock.advance(2000)
      expect(await view.find({ type: 'Text', text: 'problem 1 · fixed 2026-10-25' })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })
  })
}
