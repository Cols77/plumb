// The world beneath plumb's panel in its tests (SP7 5.10): the repository's files, the
// `plumb mod ...` answers, the clock, and what the panel showed (toasts, the status line, log
// lines, panes). Every process call is
// recorded with its argv and stdin, so a test can say the key never reaches argv.
import type { On } from 'claude-code'
import { mock, test as kitTest } from 'claude-code/testing'
import type { MockClock, TestBody, TestOptions } from 'claude-code/testing'

import { PRESENT, PYTHON, ROOT, SESSION } from './fixtures'

/** A case's wall-clock budget. The kit's 5 s is real time while the panel runs on the mocked
 * clock: a case taking 1-2 s alone took 5-23 s with the machine loaded (pytest -n 2 beside
 * other runs) and timed out, and a timed-out case runs on into the next one. */
export const TEST_MS = 60_000

/** The kit's `test`, with TEST_MS unless the case names its own budget. */
export function test(name: string, ...rest: readonly [TestBody] | readonly [TestOptions, TestBody]): void {
  const [options, body] = rest.length === 1 ? [{}, rest[0]] : rest
  kitTest(name, { timeoutMs: TEST_MS, ...options }, body)
}

export const SURFACES = ['terminal', 'desktop'] as const
export const NOW = Date.parse('2026-10-11T12:00:05Z')

export const BAND = {
  component: 'AbovePrompt' as const,
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 200,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 200 },
    view: {},
  },
}

export type Run = { argv: string[]; stdin: string; env: Record<string, string> }

export type World = {
  files: Record<string, string>
  writes: { path: string; text: string }[]
  runs: Run[]
  toasts: string[]
  statuses: (string | undefined)[]
  logs: string[]
  opened: string[]
  opens: { id: string; columns?: number; closeOnEscape?: boolean }[]
  closed: string[]
  /** What the panel submitted as a prompt (SR-395's wake). */
  submits: { text: string; asUser?: unknown }[]
  /** The surface draws no `Input` (SR-395 EX-6). */
  noInput?: boolean
  /** What `plumb mod <action>` answers: its exit code and JSON, by action and argv. */
  answer: (action: string, argv: string[]) => { exitCode: number; data: unknown }
  /** Every process call and file write is refused: a hook of the panel fails. */
  broken?: boolean
}

const MOD_JSON = { active: true, since: '2026-10-11T12:00:00Z', key_digest: 'd'.repeat(64), heartbeat: '2026-10-11T12:00:00Z' }

export function world(over: Partial<World> = {}): World {
  const sessionDir = `${ROOT}/.plumb/session/${SESSION}`
  return {
    files: {
      [`${ROOT}/.plumb/config.yaml`]: '',
      [`${sessionDir}/host.json`]: JSON.stringify({ python: PYTHON }),
      [PYTHON]: '',
      [`${sessionDir}/mod.json`]: JSON.stringify(MOD_JSON),
      [`${sessionDir}/present.json`]: JSON.stringify(PRESENT),
      [`${ROOT}/.plumb/session/status.json`]: JSON.stringify({ state: 'awaits you', intent_summary: 'invoices · late fees', awaiting: 2 }),
    },
    writes: [],
    runs: [],
    toasts: [],
    statuses: [],
    logs: [],
    opened: [],
    opens: [],
    closed: [],
    submits: [],
    answer: (action, argv) => {
      if (action === 'hello') return { exitCode: 0, data: { active: true, since: '2026-10-11T12:00:00Z', session: SESSION } }
      return { exitCode: 2, data: null }
    },
    ...over,
  }
}

/** A path as the test's files name it: the host resolves the panel's paths for its platform
 * (`C:\work\shop\...` on Windows) before the hooks beneath see them. */
export function norm(path: string): string {
  return path.replace(/\\/g, '/').replace(/^[A-Za-z]:/, '')
}

/** The test's hooks beneath the panel: the host as `w` says it is. */
export function install(on: On, w: World): MockClock {
  mock.env(on, {})
  const clock = mock.clock(on, { now: NOW })
  // what the engine draws where the panel passes: an empty box
  on('ui.render', ($, e) => {
    const { Box } = $.ui.resolve(e) as any
    return h(Box, { key: 'engine' }) as any
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('turn.start', (_$, e) => ({ turnId: e.turnId }))
  on('turn.complete', (_$, e) => ({ text: e.answer }))
  on('session.root', () => ({ value: ROOT }))
  on('session.id', () => ({ value: SESSION }))
  on('fs.exists', (_$, e) => {
    const path = norm(e.path)
    return { value: path in w.files || Object.keys(w.files).some(p => p.startsWith(`${path}/`)) }
  })
  on('fs.read', (_$, e) => {
    const path = norm(e.path)
    return path in w.files ? { value: w.files[path] as string } : { deny: `ENOENT: ${path}` }
  })
  on('fs.list', (_$, e) => {
    const dir = `${norm(e.path)}/`
    const names = new Set(Object.keys(w.files).filter(p => p.startsWith(dir)).map(p => p.slice(dir.length).split('/')[0]!))
    return { value: [...names].map(name => ({ name, kind: 'file' as const })) as any }
  })
  on('fs.write', (_$, e) => {
    const path = norm(e.path)
    if (w.broken) return { deny: 'the file could not be written' }
    w.writes.push({ path, text: e.text })
    w.files[path] = e.text
    return { value: undefined }
  })
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    if (w.broken) return { deny: 'the process could not start' }
    w.runs.push({ argv, stdin: e.init?.stdin ?? '', env: { ...(e.init?.env ?? {}) } })
    const { exitCode, data } = w.answer(argv[4] ?? '', argv)
    return {
      value: {
        exitCode,
        stdout: data === null ? '' : JSON.stringify(data),
        stderr: exitCode === 0 ? '' : 'refused',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  on('ui.toast', (_$, e) => {
    w.toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.status', (_$, e) => {
    w.statuses.push(e.text)
    return { value: undefined }
  })
  on('ui.log', (_$, e) => {
    w.logs.push(e.text)
    return { value: undefined }
  })
  on('ui.open', (_$, e) => {
    w.opened.push(e.id)
    w.opens.push({ id: e.id, columns: e.columns, ...(e.closeOnEscape ? { closeOnEscape: true } : {}) })
    return { value: { isPlaced: true } as any }
  })
  on('prompt.submit', (_$, e) => {
    w.submits.push({ text: e.text, asUser: (e as { asUser?: unknown }).asUser })
    return { text: e.text }
  })
  if (w.noInput) on('ui.resolve', async (_$, e, next) => { const { Input: _gone, ...rest } = (await next(e)) as any; return rest })
  on('ui.close', (_$, e) => {
    w.closed.push(e.id)
    return { value: undefined }
  })
  return clock
}

export const START = { cwd: ROOT, surface: 'terminal' as const, isInteractive: true }
export const TURN_DONE = { answer: 'Done.', durationMs: 1000, isAborted: false, turnId: 't-1', reason: 'answer' as const }
