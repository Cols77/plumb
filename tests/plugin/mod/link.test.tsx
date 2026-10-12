// How plumb's panel reaches plumb (SR-125, SR-126): it finds the interpreter the session-start
// hook named, even when that hook names it a moment after the panel starts or ran the old way
// (the repository's own Python); when it cannot reach plumb it says why in one dim line, once
// per session, and stays silent in a repository plumb has not adopted.
import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { PYTHON, ROOT, SESSION } from './fixtures'
import { BAND, install, NOW, START, SURFACES, world } from './harness'
import type { World } from './harness'

const SESSION_DIR = `${ROOT}/.plumb/session/${SESSION}`
const HOST = `${SESSION_DIR}/host.json`
const VENV_PYTHON = `${ROOT}/.venv/Scripts/python.exe`
const TURN = { text: 'add late fees', turnId: 't-2' }

/** The world with no interpreter named yet: no host.json, no mod.json (no hello so far). */
function unnamed(over: Partial<World> = {}): World {
  const w = world(over)
  delete w.files[HOST]
  delete w.files[`${SESSION_DIR}/mod.json`]
  return w
}

/** The harness's `on`, less the nouns this test answers itself (each noun takes one hook). */
function except(on: On, nouns: string[]): On {
  return ((name: string, ...rest: unknown[]) =>
    nouns.some(n => name === n || name.startsWith(`${n}.`))
      ? undefined
      : (on as any)(name, ...rest)) as unknown as On
}

/** Every `plumb mod` run answering `exitCode` with `stderr`; the rest of the harness as is. */
function helloAnswers(on: On, w: World, exitCode: number, stderr: string): void {
  on('process.run', (_$, e) => {
    w.runs.push({ argv: [...e.argv], stdin: e.init?.stdin ?? '', env: { ...(e.init?.env ?? {}) } })
    return { value: { exitCode, stdout: '', stderr, isStdoutTruncated: false, isStderrTruncated: false } }
  })
  install(except(on, ['process.run']), w)
}

function hellos(w: World): string[][] {
  return w.runs.filter(r => r.argv[4] === 'hello').map(r => r.argv)
}

for (const surface of SURFACES) {
  describe(`linking on the ${surface}`, () => {
    test('SR-125: host.json written a moment after the panel starts: the start links and draws the band', async ($, on) => {
      const clock = mock.clock(on, { now: NOW })
      const w = unnamed()
      install(except(on, ['clock']), w)
      await $.session.start(START)
      expect(hellos(w)).toHaveLength(0)
      w.files[HOST] = JSON.stringify({ python: PYTHON })
      await clock.advance(600)
      expect(hellos(w)).toHaveLength(1)
      expect(hellos(w)[0]?.[0]).toBe(PYTHON)
      expect(w.logs).toEqual([])
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^plumb / })).toBeDefined()
      await ui.unmount()
    })

    test("SR-125 EX-2: host.json naming the repository's own Python (the old hooks): the panel runs plumb with it", async ($, on) => {
      const w = world()
      w.files[HOST] = JSON.stringify({ python: VENV_PYTHON })
      w.files[VENV_PYTHON] = ''
      delete w.files[PYTHON]
      install(on, w)
      await $.session.start(START)
      expect(hellos(w).map(a => a[0])).toEqual([VENV_PYTHON])
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^plumb / })).toBeDefined()
      await ui.unmount()
    })

    test('SR-125: no host.json at all but the repository has its own .venv: the panel tries it', async ($, on) => {
      const w = unnamed()
      w.files[VENV_PYTHON] = ''
      install(on, w)
      await $.session.start(START)
      expect(hellos(w).map(a => a[0])).toEqual([VENV_PYTHON])
    })

    test('SR-126 EX-1: no Python for plumb found: one dim line says so and where it looked, once', async ($, on) => {
      const clock = mock.clock(on, { now: NOW })
      const w = unnamed()
      install(except(on, ['clock']), w)
      await $.session.start(START)
      await clock.advance(60_000) // every try of the start, then the line
      await $.turn.start(TURN)
      await $.turn.start({ ...TURN, turnId: 't-3' })
      expect(w.runs).toHaveLength(0)
      expect(w.logs).toHaveLength(1)
      expect(w.logs[0]).toContain("plumb's panel is off: no Python for plumb was found")
      expect(w.logs[0]).toContain('host.json')
      expect(w.logs[0]).toContain('.venv')
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^plumb / })).toBeUndefined()
      await ui.unmount()
    })

    test('SR-126 EX-1: the first turn says it when the start has not yet', async ($, on) => {
      const w = unnamed()
      install(on, w)
      await $.session.start(START)
      await $.turn.start(TURN)
      expect(w.logs).toHaveLength(1)
      expect(w.logs[0]).toContain('no Python for plumb was found')
    })

    test('SR-126: the interpreter named after the line: the next turn links and the band shows', async ($, on) => {
      const w = unnamed()
      install(on, w)
      await $.session.start(START)
      await $.turn.start(TURN)
      w.files[HOST] = JSON.stringify({ python: PYTHON })
      await $.turn.start({ ...TURN, turnId: 't-3' })
      expect(hellos(w)).toHaveLength(1)
      expect(w.logs).toHaveLength(1)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^plumb / })).toBeDefined()
      await ui.unmount()
    })

    test("SR-126 EX-2: plumb refuses the hello: one line gives plumb's reason, and no turn asks again", async ($, on) => {
      const w = unnamed()
      w.files[HOST] = JSON.stringify({ python: PYTHON })
      helloAnswers(on, w, 3, 'plumb mod hello refused: no key digest (64 hex characters) on stdin\n')
      await $.session.start(START)
      await $.turn.start(TURN)
      expect(w.logs).toEqual(["plumb's panel is off: plumb refused it (no key digest (64 hex characters) on stdin); plumb keeps working in the background."])
      expect(hellos(w)).toHaveLength(1)
    })

    test("SR-126: a resumed session: plumb still holds the old panel a moment, then the hook retires it and the panel links with no line", async ($, on) => {
      const clock = mock.clock(on, { now: NOW })
      const w = unnamed()
      w.files[HOST] = JSON.stringify({ python: PYTHON })
      let retired = false
      on('process.run', (_$, e) => {
        w.runs.push({ argv: [...e.argv], stdin: e.init?.stdin ?? '', env: { ...(e.init?.env ?? {}) } })
        const ok = retired || e.argv[4] !== 'hello'
        const data = e.argv[4] === 'hello' ? { active: true, since: '2026-10-11T12:00:00Z', session: SESSION } : { session: SESSION, cards: [] }
        return { value: { exitCode: ok ? 0 : 3, stdout: ok ? JSON.stringify(data) : '', stderr: ok ? '' : 'plumb mod hello refused: this session already has its panel\n', isStdoutTruncated: false, isStderrTruncated: false } }
      })
      install(except(on, ['process.run', 'clock']), w)
      await $.session.start(START)
      expect(hellos(w)).toHaveLength(1)
      retired = true // the session-start hook retired the old registration
      await clock.advance(600)
      expect(hellos(w)).toHaveLength(2)
      await $.turn.start(TURN)
      expect(w.logs).toEqual([])
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^plumb / })).toBeDefined()
      await ui.unmount()
    })

    test('SR-126: the old panel never released: one line after the start tries, still once, and each turn tries again', async ($, on) => {
      const clock = mock.clock(on, { now: NOW })
      const w = unnamed()
      w.files[HOST] = JSON.stringify({ python: PYTHON })
      helloAnswers(except(on, ['clock']), w, 3, 'plumb mod hello refused: this session already has its panel\n')
      await $.session.start(START)
      await clock.advance(60_000)
      const afterStart = hellos(w).length
      expect(afterStart).toBeGreaterThan(1)
      await $.turn.start(TURN)
      await $.turn.start({ ...TURN, turnId: 't-3' })
      expect(hellos(w).length).toBe(afterStart + 2)
      expect(w.logs).toEqual(["plumb's panel is off: plumb refused it (this session already has its panel); plumb keeps working in the background."])
    })

    test("SR-125: the repository's .venv tried before host.json, and it has no plumb: once host.json names the interpreter, the panel links", async ($, on) => {
      const w = unnamed()
      w.files[VENV_PYTHON] = ''
      on('process.run', (_$, e) => {
        w.runs.push({ argv: [...e.argv], stdin: e.init?.stdin ?? '', env: { ...(e.init?.env ?? {}) } })
        const ok = e.argv[0] === PYTHON
        const data = e.argv[4] === 'hello' ? { active: true, since: '2026-10-11T12:00:00Z', session: SESSION } : { session: SESSION, cards: [] }
        return { value: { exitCode: ok ? 0 : 1, stdout: ok ? JSON.stringify(data) : '', stderr: ok ? '' : "ModuleNotFoundError: No module named 'plumb'\n", isStdoutTruncated: false, isStderrTruncated: false } }
      })
      install(except(on, ['process.run']), w)
      await $.session.start(START)
      expect(hellos(w).map(a => a[0])).toEqual([VENV_PYTHON])
      w.files[HOST] = JSON.stringify({ python: PYTHON })
      await $.turn.start(TURN)
      expect(hellos(w).map(a => a[0])).toEqual([VENV_PYTHON, PYTHON])
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^plumb / })).toBeDefined()
      await ui.unmount()
    })

    test('SR-126: plumb mod hello fails: one line gives its error', async ($, on) => {
      const w = unnamed()
      w.files[HOST] = JSON.stringify({ python: PYTHON })
      helloAnswers(on, w, 1, "Traceback (most recent call last):\n  ...\nModuleNotFoundError: No module named 'plumb'\n")
      await $.session.start(START)
      expect(w.logs).toEqual(["plumb's panel is off: plumb could not start it (ModuleNotFoundError: No module named 'plumb'); plumb keeps working in the background."])
    })

    test('SR-126 EX-3: the panel connects: no such line', async ($, on) => {
      const w = world()
      install(on, w)
      await $.session.start(START)
      await $.turn.start(TURN)
      expect(w.logs).toEqual([])
    })

    test('a repository plumb has not adopted: silent', async ($, on) => {
      const clock = mock.clock(on, { now: NOW })
      const w = unnamed()
      for (const path of Object.keys(w.files)) if (path.includes('/.plumb/')) delete w.files[path]
      install(except(on, ['clock']), w)
      await $.session.start(START)
      await clock.advance(60_000)
      await $.turn.start(TURN)
      expect(w.runs).toHaveLength(0)
      expect(w.logs).toEqual([])
    })

    for (const [name, above] of [["plumb's own home above the repository", { '/work/.plumb/env/py/python': '' }],
      ['records above the git root', { '/work/.plumb/requirements/SR-001.md': '', '/work/shop/.git/HEAD': '' }]] as const) {
      test(`a repository plumb has not adopted: ${name} is not its records`, async ($, on) => {
        const clock = mock.clock(on, { now: NOW })
        const w = unnamed()
        for (const path of Object.keys(w.files)) if (path.includes('/.plumb/')) delete w.files[path]
        Object.assign(w.files, above)
        install(except(on, ['clock']), w)
        await $.session.start(START)
        await clock.advance(60_000)
        await $.turn.start(TURN)
        expect(w.runs).toHaveLength(0)
        expect(w.logs).toEqual([])
      })
    }
  })
}
