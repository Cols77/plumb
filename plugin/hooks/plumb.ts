// How plumb's panel reaches plumb (SP7 5.1, 5.7; DEC-025): it finds the repository and the
// interpreter that runs plumb, makes the session's key, registers its digest with
// `plumb mod hello`, and runs `plumb mod draw|press|undo` with the key on stdin, never in argv,
// and with the agent session marker emptied.
//
// The engine wants every `$` call spelled at its hook's call site, so the hooks hand these
// functions an `Io`: the few host calls they need, each a closure over the hook's own `$`.
import type { ProcessRunInit, ProcessRunResult } from 'claude-code'

import type { PlumbCard, PlumbLink, PlumbPresent, PlumbStatus, PlumbView } from '../types'
import { contentKey } from './cards'

export type Io = {
  exists: (path: string) => Promise<boolean>
  read: (path: string) => Promise<string>
  write: (path: string, text: string) => Promise<void>
  run: (argv: readonly string[], init: ProcessRunInit) => Promise<ProcessRunResult>
  root: () => Promise<string>
  id: () => Promise<string>
  now: () => Promise<number>
  env: () => Promise<Record<string, string | undefined>>
}

export type Ran = { ok: boolean; exitCode: number; data: any; stderr: string }

export function join(...parts: string[]): string {
  const sep = parts[0]?.includes('\\') ? '\\' : '/'
  return parts
    .map((p, i) => (i === 0 ? p.replace(/[\\/]+$/, '') : p.replace(/^[\\/]+|[\\/]+$/g, '')))
    .join(sep)
}

function parent(dir: string): string | null {
  const trimmed = dir.replace(/[\\/]+$/, '')
  const cut = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'))
  if (cut < 0) return null
  if (cut === 0) return trimmed.length > 1 ? trimmed.slice(0, 1) : null
  const up = trimmed.slice(0, cut)
  return /^[A-Za-z]:$/.test(up) ? up + trimmed.charAt(cut) : up
}

async function readJson(io: Io, path: string): Promise<any> {
  try {
    if (!(await io.exists(path))) return null
    return JSON.parse(await io.read(path))
  } catch {
    return null
  }
}

/** The repository plumb adopted: the session's root or the nearest folder above it with .plumb. */
export async function findRoot(io: Io): Promise<string | null> {
  let dir: string | null = await io.root()
  for (let depth = 0; dir !== null && depth < 64; depth += 1) {
    if (await io.exists(join(dir, '.plumb'))) return dir
    const up = parent(dir)
    dir = up === dir ? null : up
  }
  return null
}

export function sessionDir(root: string, session: string): string {
  return join(root, '.plumb', 'session', session)
}

/** The interpreter that runs plumb: the one the session-start hook ran with (host.json), else
 * the plugin's bundled environment (PLUMB_HOME/current.json). None: the panel stays idle. */
export async function findPython(io: Io, root: string, session: string): Promise<string | null> {
  const host = await readJson(io, join(sessionDir(root, session), 'host.json'))
  const env = await io.env()
  const homes = [env.PLUMB_HOME, env.CLAUDE_PLUGIN_DATA,
    env.HOME ? join(env.HOME, '.plumb') : undefined,
    env.USERPROFILE ? join(env.USERPROFILE, '.plumb') : undefined]
  const candidates: unknown[] = [host?.python]
  for (const home of homes) {
    if (home) candidates.push((await readJson(io, join(home, 'current.json')))?.python)
  }
  for (const python of candidates) {
    if (typeof python === 'string' && python && (await io.exists(python))) return python
  }
  return null
}

function hex(bytes: Uint8Array): string {
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

/** 32 random bytes as 64 lowercase hex characters, and the sha256 hex of those bytes. */
export async function makeKey(): Promise<{ key: string; digest: string }> {
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))
  return { key: hex(bytes), digest: hex(digest) }
}

/** `<python> -m plumb mod <action> --session <s> --root <root> --json [...]` with one JSON
 * object on stdin; PLUMB_AGENT_SESSION emptied, so plumb knows its panel, not the agent, ran it. */
export async function plumbMod(io: Io, link: PlumbLink, action: string,
  stdin: Record<string, unknown>, extra: string[] = []): Promise<Ran> {
  const argv = [link.python, '-m', 'plumb', 'mod', action, '--session', link.session,
    '--root', link.root, '--json', ...extra]
  const ran = await io.run(argv, {
    cwd: link.root,
    env: { PLUMB_AGENT_SESSION: '', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    stdin: JSON.stringify(stdin),
    timeoutMs: 60000,
  })
  let data: any = null
  try {
    data = ran.stdout.trim() ? JSON.parse(ran.stdout) : null
  } catch {
    data = null
  }
  return { ok: ran.exitCode === 0 && data !== null, exitCode: ran.exitCode, data, stderr: ran.stderr }
}

/** The handshake: find plumb, make the key, register its digest. Null: stay idle. */
export async function hello(io: Io): Promise<PlumbLink | null> {
  const root = await findRoot(io)
  if (root === null) return null
  const session = await io.id()
  const python = await findPython(io, root, session)
  if (python === null) return null
  const { key, digest } = await makeKey()
  const link: PlumbLink = { session, root, python, key }
  const ran = await plumbMod(io, link, 'hello', { key_digest: digest })
  return ran.ok && ran.data?.active === true ? link : null
}

export async function draw(io: Io, link: PlumbLink): Promise<PlumbCard[] | null> {
  const ran = await plumbMod(io, link, 'draw', { key: link.key })
  return ran.ok && Array.isArray(ran.data?.cards) ? (ran.data.cards as PlumbCard[]) : null
}

export function press(io: Io, link: PlumbLink, offer: string, choice: number): Promise<Ran> {
  return plumbMod(io, link, 'press', { key: link.key }, ['--offer', offer, '--choice', String(choice)])
}

export function undo(io: Io, link: PlumbLink, record: string): Promise<Ran> {
  return plumbMod(io, link, 'undo', { key: link.key }, ['--record', record])
}

/** The panel is alive this turn: refresh the heartbeat in mod.json (no process). */
export async function heartbeat(io: Io, link: PlumbLink): Promise<void> {
  const path = join(sessionDir(link.root, link.session), 'mod.json')
  const held = await readJson(io, path)
  if (held === null || held.active !== true) return
  const now = new Date(await io.now()).toISOString().replace(/\.\d+Z$/, 'Z')
  await io.write(path, JSON.stringify({ ...held, heartbeat: now }, null, 1) + '\n')
}

export async function readPresent(io: Io, link: PlumbLink): Promise<PlumbPresent | null> {
  const data = await readJson(io, join(sessionDir(link.root, link.session), 'present.json'))
  if (data === null || typeof data !== 'object') return null
  return {
    turn: Number(data.turn ?? 0),
    turn_id: String(data.turn_id ?? ''),
    written_at: String(data.written_at ?? ''),
    confirmations: Array.isArray(data.confirmations) ? data.confirmations.map(String) : [],
    settled: Array.isArray(data.settled) ? data.settled.map(String) : [],
    settled_records: Array.isArray(data.settled_records) ? data.settled_records : [],
  }
}

/** The band's first line: plumb's status card (status.json) and SP8's progress, if running. */
export async function readStatus(io: Io, link: PlumbLink): Promise<PlumbStatus> {
  const status = await readJson(io, join(link.root, '.plumb', 'session', 'status.json'))
  const progress = await readJson(io, join(sessionDir(link.root, link.session), 'progress'))
  let step = ''
  if (progress && progress.state === 'running' && progress.step) {
    step = progress.total
      ? `${progress.step} · ${progress.done ?? 0}/${progress.total}`
      : String(progress.step)
  }
  return {
    state: String(status?.state ?? ''),
    summary: String(status?.intent_summary ?? ''),
    progress: step,
    card: String(status?.present?.card ?? 'full'),
  }
}

/** What plumb holds now: the cards (drawing them records their offers), the status and, at
 * the end of a turn, present.json. `fresh`: an awaiting card the owner has not hidden. */
export async function snapshot(io: Io, link: PlumbLink, view: PlumbView, shown: string[],
  atTurnEnd: boolean): Promise<{ view: PlumbView; fresh: number }> {
  const cards = await draw(io, link)
  const status = await readStatus(io, link)
  const present = atTurnEnd ? await readPresent(io, link) : view.present
  const next: PlumbView = { ...view, cards: cards ?? view.cards, status, present }
  const fresh = next.cards.filter(c => c.repeats && !shown.includes(contentKey(c))).length
  return { view: next, fresh }
}
