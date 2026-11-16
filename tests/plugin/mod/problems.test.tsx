// SR-412: the problems chip in the band and the problems class of the pane. Its EX-5 (the owning
// session is told once at its next prompt) is a Python behaviour, tested in
// tests/debug/test_known_issues.py; this file checks only what the band and the pane draw.
import { describe, expect } from 'claude-code/testing'

import { PLUM } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, test, world } from './harness'

const REGISTER = `${ROOT}/.iaso/known-issues.json`
const STAMP = `${ROOT}/.git/iaso-loops.stamp`
const PANE = 'iaso-pane'

const issue = (n: number, state: string) => ({ id: `KI-${n}`, title: `problem ${n}`, symptom: `symptom ${n}`, cause: `cause ${n}`,
  fix: state === 'open' ? '' : `abc${n}`, fixed: state === 'open' ? '' : '2026-10-20', state, history: [] as string[] })

function mk(known: any[]) {
  const w = world()
  const base = w.answer
  w.answer = (action, argv) => {
    if (action === 'loops') return { exitCode: 0, data: { rows: [], live: 0, idle: 0, stamp: STAMP,
      counts: { intent: { live: 0, idle: 0 }, debug: { live: 0, idle: 0 }, evaluate: { live: 0, idle: 0 } } } }
    if (action === 'known') return { exitCode: 0, data: { open: known.filter(k => k.state === 'open').length, issues: known } }
    return base(action, argv)
  }
  w.files[STAMP] = 'one'
  w.files[REGISTER] = JSON.stringify({ issues: known })
  return w
}

const pane = (surface: 'terminal' | 'desktop') => ({ plugin: 'iaso', surface, component: 'Pane' as const, requestId: PANE,
  props: { title: 'iaso', bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 } } }) as any

async function open($: any, on: any, surface: 'terminal' | 'desktop', o: { known: any[] }, chip?: string) {
  const w = mk(o.known)
  install(on, w)
  await $.session.start(START)
  const band = await $.ui.mount({ plugin: 'iaso', surface, ...BAND })
  if (chip) await band.press({ key: `chip:${chip}` })
  return { w, band, view: chip ? await $.ui.mount(pane(surface)) : undefined as any }
}

for (const surface of SURFACES) {
  describe(`the problems chip and class on the ${surface}`, () => {
    test('SR-412 EX-1: two open problems: the chip problems 2 in plum and no line per problem', async ($, on) => {
      const { band } = await open($, on, surface, { known: [issue(1, 'open'), issue(2, 'open')] })
      expect((await band.find({ type: 'Text', text: 'problems 2' }))?.props.color).toBe(PLUM.dark)
      expect(await band.find({ type: 'Text', text: /problem \d|known problems/ })).toBeUndefined()
      await band.unmount()
    })

    test('SR-412 EX-2: the problems chip opens problems bold; each problem a folded row with its state', async ($, on) => {
      const { view, band } = await open($, on, surface, { known: [issue(1, 'open'), issue(2, 'fixed')] }, 'problems')
      expect((await view.find({ type: 'Text', text: /^problems/ }))?.props.bold).toBe(true)
      expect(await view.find({ type: 'Text', text: /problem 1.*open/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /problem 2.*fixed/ })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-412 EX-3: an expanded problem shows symptom, cause, fix, history; fixed rows are below, dim', async ($, on) => {
      const { view, band } = await open($, on, surface, { known: [issue(2, 'fixed'), issue(1, 'open')] }, 'problems')
      const rows = await view.findAll({ type: 'Text', text: /^.{0,3}problem \d/ })
      expect(rows.map(t => t.text.match(/problem \d/)![0])).toEqual(['problem 1', 'problem 2'])
      expect(rows[1]!.props.dimColor).toBe(true)
      await view.press({ key: 'row:problems:KI-1' })
      for (const s of ['symptom 1', 'cause 1', 'fix', 'history']) expect(await view.find({ type: 'Text', text: new RegExp(s) })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-412 EX-4: a fix lands while the pane is open: the row reads fixed and moves below', async ($, on) => {
      const known = [issue(1, 'open'), issue(2, 'open')]
      const { w, view, band } = await open($, on, surface, { known }, 'problems')
      const fixed = [issue(1, 'fixed'), issue(2, 'open')]
      w.files[REGISTER] = JSON.stringify({ issues: fixed })
      const base = w.answer
      w.answer = (a, v) => a === 'known' ? { exitCode: 0, data: { open: 1, issues: fixed } } : base(a, v)
      await $.turn.complete({ answer: 'Done.', durationMs: 1000, isAborted: false, turnId: 't-1', reason: 'answer' as const })
      const rows = await view.findAll({ type: 'Text', text: /problem \d/ })
      expect(rows.map(t => t.text.match(/problem \d/)![0])).toEqual(['problem 2', 'problem 1'])
      expect(rows[1]!.text).toMatch(/fixed/)
      await view.unmount()
      await band.unmount()
    })
  })
}
