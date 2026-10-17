// The world beneath plumb's panel in its tests (SP7 5.10): the repository's files, the
// `plumb mod ...` answers recorded from real runs (fixtures.ts), the clock, and what the panel
// showed (toasts, the status line, log lines, the message box, panes). Every process call is
// recorded with its argv and stdin, so a test can say the key never reaches argv.
import type { On } from 'claude-code'
import { mock } from 'claude-code/testing'

import { DRAW, PRESS_CHANGE, PRESS_CONFIRM, PRESS_LEAVE_OPEN, PRESENT, PYTHON, ROOT, SESSION } from './fixtures'

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
  fills: string[]
  opened: string[]
  opens: { id: string; columns?: number }[]
  /** What `plumb mod <action>` answers: its exit code and JSON, by action and argv. */
  answer: (action: string, argv: string[]) => { exitCode: number; data: unknown }
  canFill: boolean
  /** Every process call is refused: a hook of the panel fails. */
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
      [`${ROOT}/.plumb/session/status.json`]: JSON.stringify({ state: 'awaits you', intent_summary: 'invoices · late fees', present: { card: 'full' } }),
    },
    writes: [],
    runs: [],
    toasts: [],
    statuses: [],
    logs: [],
    fills: [],
    opened: [],
    opens: [],
    canFill: true,
    answer: (action, argv) => {
      if (action === 'hello') return { exitCode: 0, data: { active: true, since: '2026-10-11T12:00:00Z', session: SESSION } }
      if (action === 'draw') return { exitCode: 0, data: DRAW }
      if (action === 'press') {
        const choice = argv[argv.indexOf('--choice') + 1]
        const answer = choice === '3' ? PRESS_LEAVE_OPEN : choice === '2' ? PRESS_CHANGE : PRESS_CONFIRM
        return { exitCode: 0, data: answer }
      }
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
export function install(on: On, w: World): void {
  mock.env(on, {})
  mock.clock(on, { now: NOW })
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
    w.opens.push({ id: e.id, columns: e.columns })
    return { value: { isPlaced: true } as any }
  })
  on('prompt.fill', (_$, e) => {
    if (w.canFill) w.fills.push(e.text)
    return { isFilled: w.canFill } as any
  })
}

export const START = { cwd: ROOT, surface: 'terminal' as const, isInteractive: true }
export const TURN_DONE = { answer: 'Done.', durationMs: 1000, isAborted: false, turnId: 't-1', reason: 'answer' as const }
