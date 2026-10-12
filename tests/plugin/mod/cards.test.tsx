// Every card the panel draws carries all the owner needs to choose (SR-116, INT-031): the
// record as it now reads, the change with its evidence, the owner's words, each option with
// what it does and leaves undone, and why the recommended one; a long change is folded with its
// size and opens in full, never cut (SR-116 EX-2).
import { describe, expect, test } from 'claude-code/testing'

import { DRAW, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, world } from './harness'

const STALE = DRAW.cards[1] as any

/** A diff of about 60,000 characters, as SR-116 EX-2 has it. */
function longDiff(): string {
  const lines = ['--- a/src/plumb/confirm.py', '+++ b/src/plumb/confirm.py', '@@ -1,1 +1,1500 @@', ' def accepted(entry):']
  for (let i = 0; i < 1499; i += 1) lines.push(`+    check_${String(i).padStart(4, '0')}(entry)  # one more line of the change`)
  return lines.join('\n') + '\n'
}

function drawWith(card: any) {
  return { session: SESSION, cards: [card] }
}

for (const surface of SURFACES) {
  describe(`cards on the ${surface}`, () => {
    test('a card shows the record as it reads, the change, your words, each option and why', async ($, on) => {
      const w = world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: drawWith(STALE) } : world().answer(action, argv) })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      const text = async (t: string | RegExp) => (await ui.find({ type: 'Text', text: t }))?.text
      expect(await text('Confirm button')).toBeDefined()
      expect(await text(STALE.issue)).toBeDefined()
      // as it now reads, with its examples
      expect(await text('As it now reads')).toBeDefined()
      expect(await text('Only the owner confirms: A record is confirmed only by the owner.')).toBeDefined()
      expect(await text(/EX-1: given an agent shell/)).toBeDefined()
      // the change itself, drawn as a diff
      expect(await text('What changed')).toBeDefined()
      expect(await text('src/plumb/confirm.py (+2/-1 lines, 160 characters)')).toBeDefined()
      const code = await ui.find({ type: 'Code' })
      expect(code?.props.source).toBe(STALE.content.change.diff)
      expect(code?.props.format).toBe('diff')
      // the owner's words it traces to
      expect(await text('Your words')).toBeDefined()
      expect(await text('Buttons confirm: "a click confirms because only I can click"')).toBeDefined()
      // each option and what it does and leaves undone; the recommended one first
      expect(await text('1. Keep the requirement and re-pin it (recommended)')).toBeDefined()
      expect(await text(/does and leaves undone: SR-005 stays as it reads/)).toBeDefined()
      expect(await text('2. Reword the requirement')).toBeDefined()
      expect(await text(/does and leaves undone: SR-005 names the button/)).toBeDefined()
      // why the recommended one
      expect(await text('Why the recommended one')).toBeDefined()
      expect(await text(STALE.content.why)).toBeDefined()
      // and the buttons
      const labels = (await ui.findAll({ type: 'Button' })).filter(b => b.key?.startsWith('press:')).map(b => b.props.label)
      expect(labels).toEqual(['Keep the requirement and re-pin it', 'Reword the requirement', 'Ask for a change', 'Leave open'])
      await ui.unmount()
    })

    test('a 60,000-character change is folded with its size and opens in full', async ($, on) => {
      const diff = longDiff()
      expect(diff.length).toBeGreaterThan(60000)
      const card = JSON.parse(JSON.stringify(STALE))
      card.content.change = { path: 'src/plumb/confirm.py', diff, size: diff.length, lines: 1503, added: 1499, removed: 0, folded: true, note: '' }
      const w = world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: drawWith(card) } : world().answer(action, argv) })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Code' })).toBeUndefined()
      const size = diff.length.toLocaleString('en')
      expect(await ui.find({ type: 'Text', text: `[folded: ${size} characters, 1503 lines]` })).toBeDefined()
      const runs = w.runs.length
      await ui.press({ key: 'fold:stale:SR-005#0' })
      expect(w.runs.length).toBe(runs) // opening it reads nothing again: the whole change was there
      expect((await ui.find({ type: 'Code' }))?.props.source).toBe(diff)
      await ui.press({ key: 'fold:stale:SR-005#0' })
      expect(await ui.find({ type: 'Code' })).toBeUndefined()
      await ui.unmount()
    })

    test('a card without derived content shows what it rests on, a long one folded', async ($, on) => {
      const card = JSON.parse(JSON.stringify(DRAW.cards[0]))
      card.evidence = 'the owner said: ' + 'keep the CSV export, '.repeat(300)
      card.evidence_size = card.evidence.length
      const w = world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: drawWith(card) } : world().answer(action, argv) })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'As it now reads' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: card.questions[0].text })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'What it rests on' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: `[folded: ${card.evidence_size.toLocaleString('en')} characters, 1 lines]` })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: "1. Yes, that's it (recommended)" })).toBeDefined()
      await ui.press({ key: 'fold:show_first:SR-001' })
      expect(await ui.find({ type: 'Text', text: card.evidence })).toBeDefined()
      await ui.unmount()
    })

    test('a card of several items lists them; Show all gives each its own buttons', async ($, on) => {
      const card = JSON.parse(JSON.stringify(DRAW.cards[0]))
      card.id = 'backlog:merge-check'
      card.kind = 'backlog'
      card.topic = 'merge check'
      const second = JSON.parse(JSON.stringify(card.offers[0]))
      second.offer_id = 'sha256:dddd'
      second.question = 'q2'
      card.offers.push(second)
      card.questions = [{ ...card.questions[0], text: 'Keep the merge check?' }, { ...card.questions[0], id: 'q2', text: 'Keep the full run at push?' }]
      const w = world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: drawWith(card) } : world().answer(action, argv) })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: '• Keep the full run at push?' })).toBeDefined()
      expect(await ui.find({ key: 'press:0:sha256:dddd' })).toBeUndefined()
      await ui.press({ key: 'items:backlog:merge-check' })
      expect(await ui.find({ key: 'press:0:sha256:aaaa' })).toBeDefined()
      expect(await ui.find({ key: 'press:0:sha256:dddd' })).toBeDefined()
      await ui.press({ key: 'press:0:sha256:dddd' })
      expect(w.runs.filter(r => r.argv[4] === 'press')[0]?.argv.slice(-4)).toEqual(['--offer', 'sha256:dddd', '--choice', '0'])
      await ui.unmount()
    })
  })
}
