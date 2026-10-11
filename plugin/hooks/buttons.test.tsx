// The card buttons (sp7-realign-sp8 C3-C6; SR-086 EX-1, EX-6, EX-7, EX-10; DEC-032, DEC-033;
// SR-087 EX-3): each button runs `plumb mod press` with the offer and the button, the key on
// stdin and never in argv, with the agent session marker emptied; the answer becomes a toast,
// an owner notice and a model note; Show all runs nothing; Undo on the settled line.
import { describe, expect, mock, test } from 'claude-code/testing'

import { PRESS_CHANGE, PRESS_CONFIRM, PRESS_LEAVE_OPEN, PYTHON, ROOT, SESSION, UNDO } from './fixtures'
import { BAND, install, START, SURFACES, TURN_DONE, world } from './harness'
import type { World } from './harness'

function hex(bytes: Uint8Array): string {
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

async function sha256(keyHex: string): Promise<string> {
  const bytes = new Uint8Array((keyHex.match(/../g) ?? []).map(h => parseInt(h, 16)))
  return hex(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
}

function runsOf(w: World, action: string) {
  return w.runs.filter(r => r.argv[4] === action)
}

for (const surface of SURFACES) {
  describe(`buttons on the ${surface}`, () => {
    test('Confirm runs plumb mod press with the offer and the key on stdin, never in argv', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'press:0:0:show_first:SR-001' })
      const [hello] = runsOf(w, 'hello')
      const [pressed] = runsOf(w, 'press')
      expect(hello?.argv).toEqual([PYTHON, '-m', 'plumb', 'mod', 'hello', '--session', SESSION, '--root', ROOT, '--json'])
      expect(pressed?.argv).toEqual([PYTHON, '-m', 'plumb', 'mod', 'press', '--session', SESSION, '--root', ROOT, '--json',
        '--offer', 'sha256:aaaa', '--choice', '0'])
      const key = JSON.parse(pressed?.stdin ?? '{}').key as string
      expect(key).toMatch(/^[0-9a-f]{64}$/)
      // hello registered the digest of that same key, and nothing else ever carried the key
      expect(JSON.parse(hello?.stdin ?? '{}')).toEqual({ key_digest: await sha256(key) })
      for (const run of w.runs) {
        expect(run.argv.join(' ')).not.toContain(key)
        expect(run.env.PLUMB_AGENT_SESSION).toBe('')
      }
      for (const written of w.writes) expect(written.text).not.toContain(key)
      await ui.unmount()
    })

    test('after Confirm: a toast, the owner notice and the model note, and the cards drawn again', async ($, on) => {
      const w = world()
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      const drawsBefore = runsOf(w, 'draw').length
      await ui.press({ key: 'press:0:0:show_first:SR-001' })
      expect(w.toasts).toContain(PRESS_CONFIRM.line)
      const rows = session.appended().map(r => ({ type: r.message.type, text: (r.message.content as any)[0]?.text }))
      expect(rows).toEqual([
        { type: 'system', text: PRESS_CONFIRM.line },
        { type: 'user', text: PRESS_CONFIRM.model_note },
      ])
      expect(runsOf(w, 'draw').length).toBe(drawsBefore + 1)
      expect(await ui.find({ type: 'Text', text: PRESS_CONFIRM.line })).toBeDefined()
      await ui.unmount()
    })

    test('Leave open presses the Leave open button and confirms nothing', async ($, on) => {
      const w = world()
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'press:0:3:show_first:SR-001' })
      expect(runsOf(w, 'press')[0]?.argv.slice(-4)).toEqual(['--offer', 'sha256:aaaa', '--choice', '3'])
      expect(session.appended().map(r => (r.message.content as any)[0]?.text)).toEqual([
        PRESS_LEAVE_OPEN.line, PRESS_LEAVE_OPEN.model_note])
      expect(w.fills).toEqual([])
      await ui.unmount()
    })

    test("Ask for a change puts \"Change to '<topic>': \" in the message box (DEC-032)", async ($, on) => {
      const w = world()
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'press:0:2:show_first:SR-001' })
      expect(w.fills).toEqual(["Change to 'CSV export': "])
      expect(session.appended().map(r => (r.message.content as any)[0]?.text)).toEqual([
        PRESS_CHANGE.line, PRESS_CHANGE.model_note])
      await ui.unmount()
    })

    test('when the box cannot take the words, the model is told to ask one question instead', async ($, on) => {
      const w = world({ canFill: false })
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'press:0:2:show_first:SR-001' })
      const note = (session.appended().find(r => r.message.type === 'user')?.message.content as any)[0]?.text
      expect(note).toStartWith(PRESS_CHANGE.model_note)
      expect(note).toContain('one question in your next reply')
      await ui.unmount()
    })

    test('No is a button only where the card suggests it (DEC-033)', async ($, on) => {
      install(on, world())
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'showall' })
      const labels = async (id: string) =>
        (await ui.findAll({ type: 'Button' })).filter(b => b.key?.endsWith(`:${id}`) && b.key.startsWith('press:')).map(b => b.props.label)
      expect(await labels('show_first:SR-001')).toEqual(['Confirm', 'No', 'Ask for a change', 'Leave open'])
      expect(await labels('stale:SR-005#0')).toEqual(['Keep the requirement and re-pin it', 'Reword the requirement', 'Ask for a change', 'Leave open'])
      await ui.unmount()
    })

    test('Show all draws every card with its buttons and runs no process', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      const before = w.runs.length
      await ui.press({ key: 'showall' })
      expect(w.runs.length).toBe(before)
      for (const id of ['show_first:SR-001', 'stale:SR-005#0', 'show_first:SR-009']) {
        expect(await ui.find({ key: `card:${id}` })).toBeDefined()
        expect(await ui.find({ key: `press:0:0:${id}` })).toBeDefined()
      }
      await ui.press({ key: 'fewer' })
      expect(await ui.find({ key: 'card:stale:SR-005#0' })).toBeUndefined()
      await ui.unmount()
    })

    test('Undo on the settled line runs plumb mod undo with the key on stdin', async ($, on) => {
      const w = world()
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      await $.turn.complete(TURN_DONE) // present.json: the settled line
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: 'Deadline reminders' })).toBeDefined()
      await ui.press({ key: 'undo:SR-007' })
      const [undone] = runsOf(w, 'undo')
      expect(undone?.argv.slice(-2)).toEqual(['--record', 'SR-007'])
      expect(Object.keys(JSON.parse(undone?.stdin ?? '{}'))).toEqual(['key'])
      expect(session.appended().map(r => (r.message.content as any)[0]?.text)).toEqual([UNDO.line, UNDO.model_note])
      expect(await ui.find({ key: 'undo:SR-007' })).toBeUndefined()
      await ui.unmount()
    })

    test('a press plumb refuses changes nothing and says so', async ($, on) => {
      const w = world()
      install(on, w)
      const session = mock.session(on)
      await $.session.start(START)
      w.answer = (action, argv) => action === 'press' ? { exitCode: 3, data: null } : world().answer(action, argv)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      await ui.press({ key: 'press:0:0:show_first:SR-001' })
      const texts = session.appended().map(r => (r.message.content as any)[0]?.text)
      expect(texts).toEqual(['plumb could not record that press; nothing changed. Try again, or answer in words.'])
      expect(session.appended().some(r => r.message.type === 'user')).toBe(false)
      await ui.unmount()
    })
  })
}
