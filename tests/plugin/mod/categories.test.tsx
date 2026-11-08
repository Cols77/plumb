// One band line of class chips and one docked pane with a class switch (SR-409..SR-413, DEC-506):
// loops, studies, problems, judge, build. Chips are keyed `chip:<class>`, the pane's switch
// `class:<class>`, a row `row:<class>:<id>`, an action `act:<name>`. Each case runs on the
// terminal and the desktop.
import { describe, expect } from 'claude-code/testing'

import { BRASS, PLUM, RED } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, test, world } from './harness'

const SESS = `${ROOT}/.plumb/session/${SESSION}`
const STATUS = `${ROOT}/.plumb/session/status.json`
const JUDGES = `${ROOT}/.plumb/session/judges.json`
const BUILD = `${SESS}/build.json`
const LOOP = `${SESS}/intent/aaaaaaaaaaaa.json`
const REGISTER = `${ROOT}/.plumb/known-issues.json`
const STAMP = `${ROOT}/.git/plumb-loops.stamp`
const PANE = 'plumb-pane'

const study = (slug: string, title: string, status: string, extra = '') =>
  [`${ROOT}/.plumb/studies/${slug}.md`, `---\ntitle: ${JSON.stringify(title)}\ntopic: "t"\nstep: "plan"\nloop: "aaaaaaaaaaaa"\n` +
    `why: "the plan adds ${slug}"\nrecommend: "diagrams"\ndepth: ""\nstatus: ${JSON.stringify(status)}\n${extra}---\n`] as const

const issue = (n: number, state: string) => ({ id: `KI-${n}`, title: `problem ${n}`, symptom: `symptom ${n}`, cause: `cause ${n}`,
  fix: state === 'open' ? '' : `abc${n}`, fixed: state === 'open' ? '' : '2026-10-20', state, history: [] as string[] })

const loopRow = (id: string, goal: string, live: boolean) => ({ kind: 'intent', id, goal, goal_full: `${goal}, in full`, progress: 'plan · 3/7',
  done: ['clarify'], left: ['build'], waits: '', live, state: live ? 'working' : 'idle', last: '2026-10-11T11:59:00Z',
  idle_since: live ? '' : '2026-10-01', branch: 'intent/x', root: ROOT, session: 'other', message: null, reopen: !live, send: live })

type Opt = { loops?: any[]; known?: any[]; studies?: (readonly [string, string])[]; judges?: unknown; build?: unknown; loop?: boolean }

function mk({ loops = [], known = [], studies = [], judges, build, loop = false }: Opt = {}) {
  const w = world()
  const base = w.answer
  const n = (live: boolean) => loops.filter(r => r.live === live).length
  w.answer = (action, argv) => {
    if (action === 'loops') return { exitCode: 0, data: { rows: loops, live: n(true), idle: n(false), stamp: STAMP,
      counts: { intent: { live: n(true), idle: n(false) }, debug: { live: 0, idle: 0 }, evaluate: { live: 0, idle: 0 } } } }
    if (action === 'known') return { exitCode: 0, data: { open: known.filter(k => k.state === 'open').length, issues: known } }
    return base(action, argv)
  }
  w.files[STAMP] = 'one'
  w.files[REGISTER] = JSON.stringify({ issues: known })
  for (const [path, text] of studies) w.files[path] = text
  if (judges) w.files[JUDGES] = JSON.stringify(judges)
  if (build) w.files[BUILD] = JSON.stringify(build)
  if (loop) w.files[LOOP] = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z',
    step: 'build', tasks: { label: 'building', done: 3, total: 4, started_at: '2026-10-11T11:00:00Z', left: [] }, stopped: null, stages: {} })
  return w
}

const pane = (surface: 'terminal' | 'desktop') => ({ plugin: 'plumb', surface, component: 'Pane' as const, requestId: PANE,
  props: { title: 'plumb', bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 } } }) as any

async function open($: any, on: any, surface: 'terminal' | 'desktop', o: Opt, chip?: string) {
  const w = mk(o)
  install(on, w)
  await $.session.start(START)
  const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
  if (chip) await band.press({ key: `chip:${chip}` })
  return { w, band, view: chip ? await $.ui.mount(pane(surface)) : undefined as any }
}

const IDEAS = [study('first-idea', 'First idea', 'idea'), study('second-idea', 'Second idea', 'idea')]
const NEW = study('a-new-study', 'A new study', 'new')

for (const surface of SURFACES) {
  describe(`the class band and pane on the ${surface}`, () => {
    test('SR-409 EX-1: ideas, a new study, a problem and a live loop: one line of chips, no title', async ($, on) => {
      const { band } = await open($, on, surface, { studies: [...IDEAS, NEW], known: [issue(1, 'open')], loops: [loopRow('bbbbbbbbbbbb', 'other loop', true)] })
      expect(await band.find({ type: 'Text', text: 'loops 1' })).toBeDefined()
      expect((await band.find({ type: 'Text', text: 'studies 3' }))?.props.color).toBe(BRASS)
      expect((await band.find({ type: 'Text', text: 'problems 1' }))?.props.color).toBe(PLUM.dark)
      expect(await band.find({ key: 'hide' })).toBeDefined()
      expect(await band.find({ type: 'Text', text: /First idea|A new study|problem 1|new study:|study idea/ })).toBeUndefined()
      expect(await band.findAll({ type: 'Text', text: /^plumb / })).toHaveLength(1)
      await band.unmount()
    })

    test('SR-409 EX-2: nothing in any class: the state, the loops chip when any loop exists, and Hide', async ($, on) => {
      const { band } = await open($, on, surface, {})
      expect(await band.find({ key: 'chip:loops' })).toBeUndefined()
      for (const c of ['studies', 'problems', 'judge', 'build']) expect(await band.find({ key: `chip:${c}` })).toBeUndefined()
      expect(await band.find({ key: 'hide' })).toBeDefined()
      await band.unmount()
    })

    test('SR-409 EX-2: only an idle loop exists: the loops chip is drawn', async ($, on) => {
      const { band } = await open($, on, surface, { loops: [loopRow('cccccccccccc', 'old', false)] })
      expect(await band.find({ key: 'chip:loops' })).toBeDefined()
      await band.unmount()
    })

    test('SR-409 EX-3: this session has a loop at build: chips, then the step strip, then the task bar', async ($, on) => {
      const { band } = await open($, on, surface, { loop: true, studies: [...IDEAS, NEW] })
      expect(await band.find({ type: 'Text', text: 'studies 3' })).toBeDefined()
      expect(await band.find({ key: 'step:build' })).toBeDefined() // the strip
      expect(await band.find({ type: 'Text', text: /study idea|new study/ })).toBeUndefined()
      await band.unmount()
    })

    test('SR-409 EX-4: a build misalignment and a judge that cannot settle: one red chip each, no red line', async ($, on) => {
      const { band } = await open($, on, surface, { build: { lines: ["plumb 5ca4e4c is behind local main's 92d6d27: reload plugins"], unchecked: false },
        judges: { down: { JEV: { code: 'no-key', line: 'JEV judge, no key (OPENROUTER_API_KEY not found)' } } } })
      expect((await band.find({ type: 'Text', text: /^build/ }))?.props.color).toBe(RED)
      expect((await band.find({ type: 'Text', text: /^judge/ }))?.props.color).toBe(RED)
      expect(await band.find({ type: 'Text', text: /reload plugins|OPENROUTER/ })).toBeUndefined()
      await band.unmount()
    })

    test('SR-409 EX-5: hidden, a study idea arrives: the band stays its one dim line with Show', async ($, on) => {
      const w = mk({})
      install(on, w)
      await $.session.start(START)
      const band = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await band.press({ key: 'hide' })
      const [p, t] = IDEAS[0]!
      w.files[p] = t
      await $.turn.complete({ answer: 'Done.', durationMs: 1000, isAborted: false, turnId: 't-1', reason: 'answer' as const })
      expect(await band.find({ key: 'show' })).toBeDefined()
      expect(await band.find({ key: 'chip:studies' })).toBeUndefined()
      await band.unmount()
    })

    test('SR-410 EX-1: the studies chip opens the pane: the switch with studies bold, the study rows below', async ($, on) => {
      const { w, view, band } = await open($, on, surface, { studies: [...IDEAS, NEW], known: [issue(1, 'open')] }, 'studies')
      expect(w.opens).toEqual([{ id: PANE, columns: 80, closeOnEscape: true }])
      for (const c of ['loops', 'studies', 'problems', 'judge', 'build']) expect(await view.find({ key: `class:${c}` })).toBeDefined()
      expect((await view.find({ type: 'Text', text: /^studies 3/ }))?.props.bold).toBe(true)
      expect(await view.find({ type: 'Text', text: /First idea/ })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-410 EX-2: Enter on an idle loop row: bold title, dim detail lines, one action row with reopen', async ($, on) => {
      const { view, band } = await open($, on, surface, { loops: [loopRow('aaaaaaaaaaaa', 'live loop', true), loopRow('cccccccccccc', 'idle loop', false)] }, 'loops')
      await view.press({ key: 'row:loops:cccccccccccc' })
      expect((await view.find({ type: 'Text', text: /idle loop/ }))?.props.bold).toBe(true)
      expect(await view.find({ type: 'Text', text: /done: clarify/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /left: build/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /branch: intent\/x/ })).toBeDefined()
      expect(await view.findAll({ key: 'act:reopen' })).toHaveLength(1)
      await view.unmount()
      await band.unmount()
    })

    test('SR-410 EX-3: the message field is on the expanded loop row only', async ($, on) => {
      const { view, band } = await open($, on, surface, { loops: [loopRow('aaaaaaaaaaaa', 'live loop', true), loopRow('bbbbbbbbbbbb', 'second loop', true)] }, 'loops')
      expect(await view.find({ type: 'Input' })).toBeUndefined()
      await view.press({ key: 'row:loops:aaaaaaaaaaaa' })
      expect(await view.findAll({ type: 'Input' })).toHaveLength(1)
      await view.unmount()
      await band.unmount()
    })

    test('SR-410 EX-4: the right arrow on the switch shows the next class, bold; the band is unchanged', async ($, on) => {
      const { view, band } = await open($, on, surface, { loops: [loopRow('aaaaaaaaaaaa', 'live loop', true)], studies: [...IDEAS] }, 'loops')
      const before = (await band.findAll({ type: 'Text' })).map(t => t.text)
      // the right arrow from class:loops: the ring lands on the next tab, as the person moves it
      await $.ui.focus({ component: 'Pane', requestId: PANE, plugin: 'plumb', element: 'class:studies', origin: { kind: 'person' } } as any)
      expect((await view.find({ type: 'Text', text: /^studies/ }))?.props.bold).toBe(true)
      expect((await band.findAll({ type: 'Text' })).map(t => t.text)).toEqual(before)
      await view.unmount()
      await band.unmount()
    })

    test('SR-410 EX-5: a title longer than the pane is cut with an ellipsis on one line', async ($, on) => {
      const long = 'a very long loop goal that runs far beyond the eighty columns of the docked pane and then some more'
      const { view, band } = await open($, on, surface, { loops: [loopRow('aaaaaaaaaaaa', long, true)] }, 'loops')
      const line = await view.find({ type: 'Text', text: /…$/ })
      expect(line).toBeDefined()
      expect(line!.text.length).toBeLessThanOrEqual(80)
      await view.unmount()
      await band.unmount()
    })

    test('SR-410 EX-6: Esc closes the pane and the band is exactly as before', async ($, on) => {
      const { band, view } = await open($, on, surface, { studies: [...IDEAS] }, 'studies')
      const before = (await band.findAll({ type: 'Text' })).map(t => t.text)
      await view.unmount()
      expect((await band.findAll({ type: 'Text' })).map(t => t.text)).toEqual(before)
      await band.unmount()
    })

    test('SR-411 EX-1: an idea arrives: the studies chip appears in brass, no toast', async ($, on) => {
      const { w, band } = await open($, on, surface, {})
      expect(await band.find({ key: 'chip:studies' })).toBeUndefined()
      const [p, t] = IDEAS[0]!
      w.files[p] = t
      await $.turn.complete({ answer: 'Done.', durationMs: 1000, isAborted: false, turnId: 't-1', reason: 'answer' as const })
      expect((await band.find({ type: 'Text', text: 'studies 1' }))?.props.color).toBe(BRASS)
      expect(w.toasts).toEqual([])
      await band.unmount()
    })

    test('SR-411 EX-2: expand the second idea: its why and four choices; with diagrams accepts that idea only', async ($, on) => {
      const { w, view, band } = await open($, on, surface, { studies: IDEAS }, 'studies')
      await view.press({ key: 'row:studies:second-idea' })
      expect(await view.find({ type: 'Text', text: /the plan adds second-idea/ })).toBeDefined()
      for (const k of ['text', 'diagrams', 'video', 'notnow']) expect(await view.find({ key: `act:${k}` })).toBeDefined()
      await view.press({ key: 'act:diagrams' })
      const ran = w.runs.filter(r => r.argv[4] === 'study')
      expect(ran).toHaveLength(1)
      expect(ran[0]!.argv).toContain('second-idea')
      expect(ran[0]!.argv).toContain('diagrams')
      expect(ran[0]!.argv).not.toContain('first-idea')
      await view.unmount()
      await band.unmount()
    })

    test('SR-411 EX-3: open in the room on a new study: the room opens on it and the row moves to read', async ($, on) => {
      const { w, view, band } = await open($, on, surface, { studies: [NEW] }, 'studies')
      w.answer = ((base) => (action: string, argv: string[]) => {
        if (action !== 'room') return base(action, argv)
        w.files[NEW[0]] = study('a-new-study', 'A new study', 'opened')[1]
        return { exitCode: 0, data: { origin: 'http://127.0.0.1:50123', slug: 'a-new-study', status: 'opened' } }
      })(w.answer)
      await view.press({ key: 'row:studies:a-new-study' })
      await view.press({ key: 'act:room' })
      expect(w.runs.filter(r => r.argv[4] === 'room')).toHaveLength(1)
      expect(await view.find({ type: 'Text', text: /read/ })).toBeDefined()
      expect(await band.find({ type: 'Text', text: /^studies/ })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-411 EX-4: a written study out of date: listed naming what changed; not now rewrites nothing', async ($, on) => {
      const old = study('old-study', 'Old study', 'opened', 'changed: "SR-100"\n')
      const { w, view, band } = await open($, on, surface, { studies: [old] }, 'studies')
      expect(await view.find({ type: 'Text', text: /out of date/ })).toBeDefined()
      await view.press({ key: 'row:studies:old-study' })
      expect(await view.find({ type: 'Text', text: /SR-100|changed/ })).toBeDefined()
      expect(await view.find({ key: 'act:rewrite' })).toBeDefined()
      await view.press({ key: 'act:notnow' })
      expect(w.runs.filter(r => r.argv[4] === 'study' && r.argv.includes('rewrite'))).toHaveLength(0)
      expect(w.submits).toEqual([])
      await view.unmount()
      await band.unmount()
    })

    test('SR-411 EX-5: a study being written: the writing section shows its title, step and a brass bar', async ($, on) => {
      const writing = study('being-written', 'Being written', 'accepted', 'progress: "outline"\n')
      const { view, band } = await open($, on, surface, { studies: [writing] }, 'studies')
      expect(await view.find({ type: 'Text', text: /writing/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /Being written/ })).toBeDefined()
      expect((await view.find({ type: 'Text', text: /█|▓|━/ }))?.props.color).toBe(BRASS)
      await view.unmount()
      await band.unmount()
    })

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

    const OLD = { lines: ["plumb 5ca4e4c is behind local main's 92d6d27: reload plugins"], unchecked: false }

    test('SR-413 EX-1: main rebuilt after the cache: one red build chip; the class names both builds and the fix', async ($, on) => {
      const { view, band } = await open($, on, surface, { build: OLD }, 'build')
      expect((await band.find({ type: 'Text', text: /^build/ }))?.props.color).toBe(RED)
      expect(await view.find({ type: 'Text', text: /5ca4e4c/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /92d6d27/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /reload plugins/ })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-413 EX-2: the plugin updated: the build chip is gone', async ($, on) => {
      const { w, band } = await open($, on, surface, { build: OLD })
      expect(await band.find({ key: 'chip:build' })).toBeDefined()
      w.files[BUILD] = JSON.stringify({ lines: [], unchecked: false })
      await $.turn.complete({ answer: 'Done.', durationMs: 1000, isAborted: false, turnId: 't-1', reason: 'answer' as const })
      expect(await band.find({ key: 'chip:build' })).toBeUndefined()
      await band.unmount()
    })

    test('SR-413 EX-3: the repository cannot be read: the build class says so in plain colour, no red chip', async ($, on) => {
      const { view, band } = await open($, on, surface, { build: { lines: [], unchecked: true } }, 'build')
      const note = await view.find({ type: 'Text', text: /could not check/ })
      expect(note).toBeDefined()
      expect(note!.props.color).not.toBe(RED)
      expect((await band.find({ type: 'Text', text: /^build/ }))?.props.color).not.toBe(RED)
      await view.unmount()
      await band.unmount()
    })

    test('SR-413 EX-4: no JEV key: one red judge chip; expanded, the judge, no key and the variable', async ($, on) => {
      const { view, band } = await open($, on, surface, { judges: { down: { JEV: { code: 'no-key', line: 'JEV judge, no key (OPENROUTER_API_KEY not found)' } } } }, 'judge')
      expect((await band.find({ type: 'Text', text: /^judge/ }))?.props.color).toBe(RED)
      await view.press({ key: 'row:judge:JEV' })
      expect(await view.find({ type: 'Text', text: /JEV judge, no key/ }))
      expect(await view.find({ type: 'Text', text: /OPENROUTER_API_KEY/ })).toBeDefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-413 EX-5: a question set aside: one plum row naming it, expanded to why; never called unreachable', async ($, on) => {
      const { view, band } = await open($, on, surface, { judges: { down: {}, set_aside: [{ question: 'Was this settled?', why: "a question names plumb's own words" }] } }, 'judge')
      const row = await view.find({ type: 'Text', text: /Was this settled\?/ })
      expect(row?.props.color).toBe(PLUM.dark)
      await view.press({ key: 'row:judge:aside:0' })
      expect(await view.find({ type: 'Text', text: /a question names plumb's own words/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /no judge can be reached/ })).toBeUndefined()
      expect((await band.find({ type: 'Text', text: /^judge/ }))?.props.color).not.toBe(RED)
      await view.unmount()
      await band.unmount()
    })
  })
}

// SR-414 and SR-305 (DEC-512, DEC-513): a loop's row shows its main details and its steps; the
// action on a live row brings the loop's own window to the front; each step shows its details.
const steps = (current: 'clarify' | 'plan' | 'build') => [
  { name: 'clarify', mark: current === 'clarify' ? 'current' : 'done', gate: current === 'clarify' ? 'open' : 'passed', findings: 2, left: ['jargon', 'no owner'] },
  { name: 'plan', mark: current === 'plan' ? 'current' : current === 'clarify' ? 'todo' : 'done', gate: current === 'plan' ? 'open' : current === 'clarify' ? 'to come' : 'passed', findings: current === 'clarify' ? 0 : 2, left: current === 'clarify' ? [] : ['broad task', 'no rollback'] },
  { name: 'build', mark: current === 'build' ? 'current' : 'todo', gate: current === 'build' ? 'open' : 'to come', findings: 0, left: [] },
  { name: 'proven', mark: 'todo', gate: 'to come', findings: 0, left: [] },
]
const stepped = (id: string, goal: string, current: 'clarify' | 'plan' | 'build', session = 'other') =>
  ({ ...loopRow(id, goal, true), session, steps: steps(current), tasks: { done: 3, total: 4, left: ['the colours slice'] } })

for (const surface of SURFACES) {
  describe(`SR-414 and SR-305 in the pane on the ${surface}`, () => {
    test('SR-414 EX-1: a live row offers show its window; pressing it asks plumb to reopen and says what plumb answers', async ($, on) => {
      const { w, view, band } = await open($, on, surface, { loops: [stepped('bbbbbbbbbbbb', 'second window', 'plan')] }, 'loops')
      const base = w.answer
      w.answer = (a, v) => a === 'reopen' ? { exitCode: 0, data: { opened: false, shown: true, line: 'brought the window of second window to the front' } } : base(a, v)
      await view.press({ key: 'row:loops:bbbbbbbbbbbb' })
      expect((await view.find({ key: 'act:reopen' }))).toBeDefined()
      expect(await view.find({ type: 'Text', text: 'show its window' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: 'reopen in a new session' })).toBeUndefined()
      await view.press({ key: 'act:reopen' })
      const ran = w.runs.filter(r => r.argv[4] === 'reopen')
      expect(ran).toHaveLength(1)
      expect(ran[0]!.argv).toContain('bbbbbbbbbbbb')
      expect(w.toasts).toEqual(['brought the window of second window to the front'])
      await view.unmount()
      await band.unmount()
    })

    test('SR-414 EX-2: the platform cannot raise it: the owner is told the session and its folder', async ($, on) => {
      const { w, view, band } = await open($, on, surface, { loops: [stepped('bbbbbbbbbbbb', 'second window', 'plan')] }, 'loops')
      const base = w.answer
      const line = `plumb cannot bring that window forward here; it is session other in ${ROOT}`
      w.answer = (a, v) => a === 'reopen' ? { exitCode: 1, data: { opened: false, shown: false, line } } : base(a, v)
      await view.press({ key: 'row:loops:bbbbbbbbbbbb' })
      await view.press({ key: 'act:reopen' })
      expect(w.toasts).toEqual([line])
      await view.unmount()
      await band.unmount()
    })

    test('SR-414 EX-3: an idle row still reads reopen in a new session', async ($, on) => {
      const { view, band } = await open($, on, surface, { loops: [loopRow('cccccccccccc', 'idle loop', false)] }, 'loops')
      await view.press({ key: 'row:loops:cccccccccccc' })
      expect(await view.find({ type: 'Text', text: 'reopen in a new session' })).toBeDefined()
      expect(await view.find({ type: 'Text', text: 'show its window' })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-305 EX-2: another session loop expanded: pressing its plan step shows the gate and findings left, no records or proofs', async ($, on) => {
      const { view, band } = await open($, on, surface, { loops: [stepped('bbbbbbbbbbbb', 'second window', 'build')] }, 'loops')
      await view.press({ key: 'row:loops:bbbbbbbbbbbb' })
      for (const s of ['clarify', 'plan', 'build', 'proven']) expect(await view.find({ key: `step:${s}` })).toBeDefined()
      await view.press({ key: 'step:plan' })
      expect(await view.find({ type: 'Text', text: /gate.*passed/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /broad task/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /no rollback/ })).toBeDefined()
      expect(await view.find({ type: 'Text', text: /records|proofs?:/i })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-305 EX-3: the pane draws no agent names, counts or tokens', async ($, on) => {
      const { view, band } = await open($, on, surface, { loops: [stepped('bbbbbbbbbbbb', 'second window', 'build')] }, 'loops')
      await view.press({ key: 'row:loops:bbbbbbbbbbbb' })
      expect(await view.find({ type: 'Text', text: /\btokens?\b|agents? (names?|counts?)|\d+ agents?/i })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })

    test('SR-305 EX-7: this session loop ends with the pane open: the pane stays open on loops', async ($, on) => {
      const { w, view, band } = await open($, on, surface, { loop: true, loops: [stepped('aaaaaaaaaaaa', 'this loop', 'build', SESSION)] }, 'loops')
      w.files[LOOP] = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z', step: 'proven', tasks: null, stopped: null, stages: {} })
      await $.turn.complete({ answer: 'Done.', durationMs: 1000, isAborted: false, turnId: 't-1', reason: 'answer' as const })
      expect(w.closed).toEqual([])
      expect(await view.find({ key: 'class:loops' })).toBeDefined()
      expect(await band.find({ key: 'loop:fold' })).toBeUndefined()
      await view.unmount()
      await band.unmount()
    })
  })
}
