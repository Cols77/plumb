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
const OTHER_SLUG = 'what-counts-as-a-word'
const OTHER = `${ROOT}/.plumb/studies/${OTHER_SLUG}.md`
const OTHER_TITLE = 'What counts as a word'
const other = (status: string) => study(status).replace(JSON.stringify(TITLE), JSON.stringify(OTHER_TITLE))

function study(status: string): string {
  return `---\ntitle: ${JSON.stringify(TITLE)}\ntopic: "background jobs"\nstep: "plan"\nloop: "aaaaaaaaaaaa"\n` +
    `why: "the plan adds a job"\nstatus: ${JSON.stringify(status)}\n---\n\nA dispatcher hands each job to a worker.\n`
}

async function band($: any, on: any, surface: (typeof SURFACES)[number], loop = true) {
  const w = world()
  const answer = w.answer
  // what plumb mod room does: the room opens on the study, which is marked opened
  w.answer = (action, argv) => {
    if (action !== 'room') return answer(action, argv)
    w.files[STUDY] = study('opened')
    return { exitCode: 0, data: { origin: 'http://127.0.0.1:50123', slug: SLUG, status: 'opened' } }
  }
  if (loop) w.files[LOOP] = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64), intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z',
    step: 'plan', tasks: null, stopped: null, stages: {} })
  on('tool.call', () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }) as any)
  install(on, w)
  await $.session.start(START)
  return { w, ui: await $.ui.mount({ plugin: 'plumb', surface, ...BAND }) }
}

const rooms = (w: ReturnType<typeof world>) => w.runs.filter(r => r.argv[4] === 'room')
const chosen = (w: ReturnType<typeof world>) => w.runs.filter(r => r.argv[4] === 'study')

// DEC-207: a study idea, as `plumb study propose` writes it: no page yet
const IDEA_SLUG = 'how-the-dispatcher-hands-out-jobs'
const IDEA = `${ROOT}/.plumb/studies/${IDEA_SLUG}.md`
const IDEA_TITLE = 'How the dispatcher hands out jobs'
const idea = (status: string, depth = '') =>
  `---\ntitle: ${JSON.stringify(IDEA_TITLE)}\ntopic: "dispatcher"\nstep: "plan"\nloop: "aaaaaaaaaaaa"\n` +
  `why: "the plan adds a dispatcher you will tune later"\nrecommend: "diagrams"\ndepth: ${JSON.stringify(depth)}\n` +
  `status: ${JSON.stringify(status)}\n---\n`

async function ideaBand($: any, on: any, surface: (typeof SURFACES)[number], loop = true) {
  const made = await band($, on, surface, loop)
  const answer = made.w.answer
  // what plumb mod study does: the idea accepted at the depth, or declined
  made.w.answer = (action, argv) => {
    if (action !== 'study') return answer(action, argv)
    const depth = argv[argv.indexOf('--depth') + 1]!
    made.w.files[IDEA] = depth === 'none' ? idea('declined') : idea('accepted', depth)
    return { exitCode: 0, data: { slug: IDEA_SLUG, status: depth === 'none' ? 'declined' : 'accepted', depth } }
  }
  made.w.files[IDEA] = idea('idea')
  await $.turn.complete(TURN_DONE)
  return made
}

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

    test("SR-294 EX-5, SR-291 EX-9: the loop ended with a study still new: one line, ending with a brass 'new study'", async ($, on) => {
      const { w, ui } = await band($, on, surface, false)
      w.files[STUDY] = study('new')
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ type: 'Text', text: /^clarify / })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: /^new study:/ })).toBeUndefined() // no second line
      expect(await ui.find({ key: 'study' })).toBeUndefined()
      const press = await ui.find({ type: 'Text', text: 'new study' })
      expect(press?.props.color).toBe(BRASS)
      expect(await ui.find({ key: 'studies' })).toBeDefined()
      expect(rooms(w)).toEqual([])
      await ui.unmount()
    })

    test('SR-294 EX-5: two studies still new: the press counts them', async ($, on) => {
      const { w, ui } = await band($, on, surface, false)
      w.files[STUDY] = study('new')
      w.files[OTHER] = other('new')
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ type: 'Text', text: '2 new studies' })).toBeDefined()
      await ui.unmount()
    })

    test('SR-294 EX-6: the press opens a menu of the new studies by title; choosing one opens the room on it', async ($, on) => {
      const { w, ui } = await band($, on, surface, false)
      w.files[STUDY] = study('new')
      w.files[OTHER] = other('new')
      await $.turn.complete(TURN_DONE)
      expect(await ui.find({ key: `study:${SLUG}` })).toBeUndefined() // closed until pressed
      await ui.press({ key: 'studies' })
      expect(await ui.find({ type: 'Text', text: `  ${TITLE}` })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: `  ${OTHER_TITLE}` })).toBeDefined()
      await ui.press({ key: `study:${SLUG}` })
      const [room] = rooms(w)
      expect(room?.argv.slice(3)).toEqual(['mod', 'room', '--session', SESSION, '--root', ROOT, '--json', '--study', SLUG])
      // the study leaves the list, the menu closes, the other still waits
      expect(await ui.find({ type: 'Text', text: `  ${TITLE}` })).toBeUndefined()
      expect(await ui.find({ key: `study:${OTHER_SLUG}` })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: 'new study' })).toBeDefined()
      await ui.press({ key: 'studies' })
      expect(await ui.find({ key: `study:${SLUG}` })).toBeUndefined()
      expect(await ui.find({ key: `study:${OTHER_SLUG}` })).toBeDefined()
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

    test("SR-294 EX-7: the band's study idea line; its press shows the why and the depths, the recommended one marked", async ($, on) => {
      const { w, ui } = await ideaBand($, on, surface)
      const line = await ui.find({ type: 'Text', text: `study idea: ${IDEA_TITLE}` })
      expect(line?.props.color).toBe(BRASS)
      expect(await ui.find({ key: 'idea:md' })).toBeUndefined() // closed until pressed
      await ui.press({ key: 'idea' })
      // the choices take the third line's place, so the why names the idea (SR-291, DEC-146)
      expect(await ui.find({ type: 'Text', text: `  ${IDEA_TITLE}: the plan adds a dispatcher you will tune later` })).toBeDefined()
      expect(await ui.find({ key: 'loop:third' })).toBeUndefined()
      expect((await ui.find({ key: 'idea:md' }))?.props.label).toBe('Markdown only')
      expect((await ui.find({ key: 'idea:diagrams' }))?.props.label).toBe('with diagrams (recommended)')
      expect((await ui.find({ key: 'idea:none' }))?.props.label).toBe('not now')
      // video is drawn dim, not offered: no Button to press until video studies exist
      expect((await ui.find({ type: 'Text', text: 'video (not available yet)' }))?.props.dimColor).toBe(true)
      expect(rooms(w)).toEqual([])
      expect(w.toasts.filter(t => /study/.test(t))).toEqual([])
      await ui.unmount()
    })

    test("SR-294 EX-8: choosing 'with diagrams' records it accepted at that depth, the key on stdin; the room stays closed", async ($, on) => {
      const { w, ui } = await ideaBand($, on, surface)
      await ui.press({ key: 'idea' })
      await ui.press({ key: 'idea:diagrams' })
      const [run] = chosen(w)
      expect(run?.argv.slice(3)).toEqual(['mod', 'study', '--session', SESSION, '--root', ROOT, '--json',
        '--study', IDEA_SLUG, '--depth', 'diagrams'])
      const key = JSON.parse(run?.stdin ?? '{}').key as string
      expect(key).toMatch(/^[0-9a-f]{64}$/)
      expect(run?.argv.join(' ')).not.toContain(key)
      expect(run?.env.PLUMB_AGENT_SESSION).toBe('')
      expect(w.files[IDEA]).toContain('status: "accepted"')
      expect(await ui.find({ type: 'Text', text: /^study idea/ })).toBeUndefined()
      expect(rooms(w)).toEqual([])
      await ui.unmount()
    })

    test("SR-294 EX-9: choosing 'not now': the idea's line is gone and nothing was written", async ($, on) => {
      const { w, ui } = await ideaBand($, on, surface)
      await ui.press({ key: 'idea' })
      await ui.press({ key: 'idea:none' })
      expect(chosen(w)[0]?.argv.slice(-2)).toEqual(['--depth', 'none'])
      expect(await ui.find({ type: 'Text', text: /^study idea/ })).toBeUndefined()
      expect(await ui.find({ key: 'idea:md' })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: /^new study/ })).toBeUndefined()
      expect(rooms(w)).toEqual([])
      await ui.unmount()
    })

    test('SR-291 EX-3, DEC-146: a new study and an idea at once share the loop\'s third line', async ($, on) => {
      const { w, ui } = await ideaBand($, on, surface)
      w.files[STUDY] = study('new')
      await $.turn.complete(TURN_DONE)
      const third = await ui.find({ key: 'loop:third' })
      expect(third).toBeDefined()
      expect(await ui.find({ type: 'Text', text: LINE })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: `study idea: ${IDEA_TITLE}` })).toBeDefined()
      expect(JSON.stringify(third)).toContain(LINE)
      expect(JSON.stringify(third)).toContain(`study idea: ${IDEA_TITLE}`)
      await ui.unmount()
    })

    test("SR-294 EX-7, DEC-183: an idea waiting after the loop folds into the one line as a brass 'study idea'", async ($, on) => {
      const { w, ui } = await ideaBand($, on, surface, false)
      expect(await ui.find({ type: 'Text', text: /^study idea:/ })).toBeUndefined() // no second line
      const press = await ui.find({ type: 'Text', text: 'study idea' })
      expect(press?.props.color).toBe(BRASS)
      await ui.press({ key: 'idea' })
      expect(await ui.find({ type: 'Text', text: `  ${IDEA_TITLE}: the plan adds a dispatcher you will tune later` })).toBeDefined()
      await ui.press({ key: 'idea:md' })
      expect(chosen(w)[0]?.argv.slice(-2)).toEqual(['--depth', 'md'])
      expect(rooms(w)).toEqual([])
      await ui.unmount()
    })
  })
}
