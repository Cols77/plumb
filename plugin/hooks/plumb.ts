// How plumb's panel reaches plumb (SP7 5.1, 5.7; DEC-025): it finds the repository and the
// interpreter that runs plumb, makes the session's key, registers its digest with
// `plumb mod hello`, and runs `plumb mod room|study` with the key on stdin, never in argv,
// and with the agent session marker emptied.
//
// The engine wants every `$` call spelled at its hook's call site, so the hooks hand these
// functions an `Io`: the few host calls they need, each a closure over the hook's own `$`.
import type { ProcessRunInit, ProcessRunResult } from 'claude-code'

import { T } from './text'
import type { PlumbKnown, PlumbLink, PlumbLoop, PlumbLoopPane, PlumbLoopRow, PlumbLoops, PlumbPresent, PlumbStatus, PlumbView } from '../types'

export type Io = {
  exists: (path: string) => Promise<boolean>
  read: (path: string) => Promise<string>
  /** The names of a folder's entries; none where it does not exist. */
  list: (path: string) => Promise<string[]>
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

/** The repository plumb adopted: the session's root or the nearest folder above it with .plumb,
 * never plumb's own home (a .plumb holding env/ or current.json, as paths.holds_records) and
 * never above the git root (a folder holding .git). */
export async function findRoot(io: Io): Promise<string | null> {
  let dir: string | null = await io.root()
  for (let depth = 0; dir !== null && depth < 64; depth += 1) {
    if (await io.exists(join(dir, '.plumb'))
      && !(await io.exists(join(dir, '.plumb', 'env'))) && !(await io.exists(join(dir, '.plumb', 'current.json')))) return dir
    if (await io.exists(join(dir, '.git'))) return null
    const up = parent(dir)
    dir = up === dir ? null : up
  }
  return null
}

export function sessionDir(root: string, session: string): string {
  return join(root, '.plumb', 'session', session)
}

/** The interpreter that runs plumb: the one the session-start hook ran with (host.json, written
 * first thing by that hook, SR-125), else the plugin's bundled environment
 * (PLUMB_HOME/current.json), else the repository's own .venv (an install the old way).
 * `looked`: every place tried, for the line that says why the panel is off (SR-126); `fallback`:
 * the interpreter is the repository's .venv, tried only because nothing named one yet. */
export async function findPython(io: Io, root: string, session: string):
  Promise<{ python: string | null; looked: string[]; fallback: boolean }> {
  const hostPath = join(sessionDir(root, session), 'host.json')
  const host = await readJson(io, hostPath)
  const env = await io.env()
  const homes = [env.PLUMB_HOME, env.CLAUDE_PLUGIN_DATA,
    env.HOME ? join(env.HOME, '.plumb') : undefined,
    env.USERPROFILE ? join(env.USERPROFILE, '.plumb') : undefined]
  const looked = [hostPath]
  const candidates: unknown[] = [host?.python]
  for (const home of homes) {
    if (!home) continue
    const current = join(home, 'current.json')
    if (looked.includes(current)) continue
    looked.push(current)
    candidates.push((await readJson(io, current))?.python)
  }
  // the platform's own layout first: a .venv carried over from the other OS cannot run
  const layouts = [join(root, '.venv', 'Scripts', 'python.exe'), join(root, '.venv', 'bin', 'python')]
  if (env.OS !== 'Windows_NT') layouts.reverse()
  for (const venv of layouts) {
    looked.push(venv)
    candidates.push(venv)
  }
  const named = candidates.length - 2 // host.json's, then each home's current.json
  for (const [n, python] of candidates.entries()) {
    if (typeof python === 'string' && python && (await io.exists(python))) {
      return { python, looked, fallback: n >= named && !host?.python }
    }
  }
  return { python: null, looked, fallback: false }
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

/** Why the panel could not reach plumb (SR-126): no interpreter found (where it looked),
 * `plumb mod hello` failed (its error), or plumb refused the hello (plumb's reason). */
export type Unlinked =
  | { why: 'no-python'; looked: string[] }
  | { why: 'failed'; error: string; fallback?: boolean }
  | { why: 'refused'; reason: string }

/** Whether a later try may link where this one did not: no interpreter named yet; plumb still
 * holding the registration of the panel a resumed session ran before (the session-start hook
 * retires it a moment later, or its heartbeat goes a minute silent: a reloaded panel's takeover); or the repository's .venv tried before host.json named the
 * interpreter (a .venv without plumb fails). Any other refusal or failure stands. */
export function mayLinkLater(u: Unlinked): boolean {
  if (u.why === 'no-python') return true
  if (u.why === 'refused') return /already has its panel/.test(u.reason)
  return u.fallback === true
}

/** A hello's outcome: the link, or why there is none; `unlinked` null where plumb has not
 * adopted the repository (no .plumb/), where the panel stays silent. */
export type Hello = { link: PlumbLink; unlinked: null } | { link: null; unlinked: Unlinked | null }

const EXIT_REFUSED = 3 // plumb mod's exit code for a refusal (src/plumb/mod/cli.py)

/** The last line of a process's error output, cut to one readable line. */
function lastLine(text: string): string {
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
  const line = lines[lines.length - 1] ?? ''
  return line.length > 200 ? `${line.slice(0, 199)}…` : line
}

/** The handshake: find plumb, make the key, register its digest. */
export async function hello(io: Io): Promise<Hello> {
  const root = await findRoot(io)
  if (root === null) return { link: null, unlinked: null }
  const session = await io.id()
  const found = await findPython(io, root, session)
  if (found.python === null) return { link: null, unlinked: { why: 'no-python', looked: found.looked } }
  const { key, digest } = await makeKey()
  const link: PlumbLink = { session, root, python: found.python, key }
  let ran: Ran
  try {
    ran = await plumbMod(io, link, 'hello', { key_digest: digest })
  } catch (err) {
    const error = lastLine(String((err as Error)?.message ?? err)) || 'it could not start'
    return { link: null, unlinked: { why: 'failed', error, fallback: found.fallback } }
  }
  if (ran.ok && ran.data?.active === true) return { link, unlinked: null }
  const said = lastLine(ran.stderr)
  if (ran.exitCode === EXIT_REFUSED) {
    const reason = said.replace(/^plumb mod hello refused:\s*/, '') || 'no reason given'
    return { link: null, unlinked: { why: 'refused', reason } }
  }
  const error = said || (ran.exitCode === 0 ? 'it answered without registering the panel' : `exit code ${ran.exitCode}`)
  return { link: null, unlinked: { why: 'failed', error, fallback: found.fallback } }
}

/** The owner pressed the band's new study line (SR-294 EX-3): plumb opens the browser room on
 * it, starting the room when it is not running, and marks the study opened. */
export function room(io: Io, link: PlumbLink, slug: string): Promise<Ran> {
  return plumbMod(io, link, 'room', { key: link.key }, ['--study', slug])
}

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : [])

/** The session's open loop as the pane shows it (SR-305), from `plumb intent status --json`;
 * null when none is open or plumb did not answer. */
export async function loopPane(io: Io, link: PlumbLink): Promise<PlumbLoopPane | null> {
  const ran = await io.run([link.python, '-m', 'plumb', 'intent', 'status', '--session', link.session,
    '--root', link.root, '--json'], {
    cwd: link.root,
    env: { PLUMB_AGENT_SESSION: '', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    timeoutMs: 60000,
  })
  let loops: any[] = []
  try {
    loops = ran.exitCode === 0 ? JSON.parse(ran.stdout) : []
  } catch {
    return null
  }
  const loop = Array.isArray(loops) ? loops.at(-1) : null
  if (!loop || typeof loop !== 'object') return null
  const stages: PlumbLoopPane['stages'] = {}
  for (const [name, stage] of Object.entries(loop.stages ?? {}) as [string, any][]) {
    stages[name] = { state: String(stage?.state ?? 'open'), left: strings(stage?.left) }
  }
  const t = loop.tasks
  return {
    step: String(loop.step ?? ''),
    stopped: String(loop.stopped ?? ''),
    stages,
    task: t && typeof t === 'object' && t.label
      ? { label: String(t.label), done: Number(t.done ?? 0), total: t.total ? Number(t.total) : null, left: strings(t.left) }
      : null,
    records: (Array.isArray(loop.records) ? loop.records : []).map((r: any) => String(r?.title ?? '')).filter(Boolean),
    proofs: (Array.isArray(loop.proofs) ? loop.proofs : []).map((p: any) => ({ title: String(p?.title ?? ''), shown: p?.shown === true })),
  }
}

export const NO_KNOWN: PlumbKnown = { seen: '', open: 0, issues: [] }

/** The known problems register and its issues' case files as they are now (files only, no
 * process): what moved since `seen` sends the band back to plumb (SR-367). */
export async function knownSeen(io: Io, link: PlumbLink): Promise<string> {
  const path = join(link.root, '.plumb', 'known-issues.json')
  let text = ''
  let ids: string[] = []
  try {
    if (!(await io.exists(path))) return ''
    text = await io.read(path)
    ids = strings(JSON.parse(text)?.issues?.map((r: any) => r?.id).filter(Boolean))
  } catch {
    return text
  }
  const cases = await Promise.all(ids.map(async id => {
    // the case file's name, as debug._case_path makes it
    const file = join(link.root, '.plumb', 'cache', 'debug', `${id.replace(/[^\w.-]/g, '_')}.json`)
    return (await io.exists(file)) ? io.read(file).catch(() => '') : ''
  }))
  return [text, ...cases].join('\n')
}

/** The known problems as plumb counts and lists them (SR-367), from `plumb mod known --json`;
 * null when plumb did not answer. */
export async function known(io: Io, link: PlumbLink, seen: string): Promise<PlumbKnown | null> {
  const ran = await plumbMod(io, link, 'known', {})
  if (!ran.ok || !Array.isArray(ran.data?.issues)) return null
  return {
    seen,
    open: Number(ran.data.open ?? 0),
    issues: ran.data.issues.map((r: any) => ({
      id: String(r?.id ?? ''), title: String(r?.title ?? ''), symptom: String(r?.symptom ?? ''),
      cause: String(r?.cause ?? ''), fix: String(r?.fix ?? ''), fixed: String(r?.fixed ?? ''),
      state: String(r?.state ?? ''), history: strings(r?.history),
    })),
  }
}

export const NO_LOOPS: PlumbLoops = { seen: '', stamp: '', live: 0, idle: 0, counts: {}, rows: [] }

/** Where plumb keeps the one change stamp: in the repository's common git directory, which a
 * linked worktree's `.git` file points into (files only). shortcut: git's standard layout
 * (`<common>/worktrees/<name>`); a differently arranged one reads as no stamp, so no loops. */
export async function loopsStamp(io: Io, root: string): Promise<string> {
  const git = join(root, '.git')
  let dir = git
  try {
    const pointer = /^gitdir:\s*(.+)$/m.exec(await io.read(git))
    if (pointer) dir = pointer[1]!.trim().replace(/[\\/]worktrees[\\/][^\\/]+$/, '')
  } catch {
    // a directory: the main checkout
  }
  return join(dir, 'plumb-loops.stamp')
}

/** The one change stamp's text (SR-393): plumb moves it whenever a loop changes, so the poll
 * reads this file alone, never a loop, case or note file. '' when it is not there. */
export async function loopsSeen(io: Io, stamp: string): Promise<string> {
  try {
    return await io.read(stamp)
  } catch {
    return ''
  }
}

/** The project's loops as plumb lists them (SR-393), from `plumb mod loops --json`; null when
 * plumb did not answer. `seen`: the stamp's text read before the run, at `stamp`. */
export async function loops(io: Io, link: PlumbLink, stamp: string, seen: string): Promise<PlumbLoops | null> {
  const ran = await plumbMod(io, link, 'loops', {})
  if (!ran.ok || !Array.isArray(ran.data?.rows)) return null
  const count = (c: any) => ({ live: Number(c?.live ?? 0), idle: Number(c?.idle ?? 0) })
  return {
    seen,
    stamp,
    live: Number(ran.data.live ?? 0),
    idle: Number(ran.data.idle ?? 0),
    counts: Object.fromEntries(['intent', 'debug', 'evaluate'].map(k => [k, count(ran.data.counts?.[k])])),
    rows: ran.data.rows.map((r: any): PlumbLoopRow => ({
      kind: String(r?.kind ?? ''), id: String(r?.id ?? ''), goal: String(r?.goal ?? ''),
      goal_full: String(r?.goal_full ?? r?.goal ?? ''), progress: String(r?.progress ?? ''),
      done: strings(r?.done), left: strings(r?.left), waits: String(r?.waits ?? ''), live: r?.live === true,
      idle_since: String(r?.idle_since ?? ''), branch: String(r?.branch ?? ''),
      message: r?.message && typeof r.message === 'object'
        ? { state: String(r.message.state ?? ''), at: String(r.message.at ?? '') } : null,
    })),
  }
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
  }
}

const STEPS = ['clarify', 'plan', 'build', 'proven']

/** How long a task has run, in the owner's words: `40s`, `12m`, `2h 5m`. */
export function elapsed(fromIso: string, now: number): string {
  // shortcut: computed when the status is read (a tool call, a turn's end), so it does not tick
  // while the agent is quiet; upgrade to a timer redraw if owners watch a long silent build
  const s = Math.max(0, Math.floor((now - Date.parse(fromIso)) / 1000))
  if (!Number.isFinite(s)) return ''
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`
}

/** The session's open intent loop (SR-291): its newest loop file whose step is not proven
 * (`intent done` proves it, and the band is one line again); null when none is open. */
export async function readLoop(io: Io, link: PlumbLink): Promise<PlumbLoop | null> {
  const folder = join(sessionDir(link.root, link.session), 'intent')
  let names: string[] = []
  try {
    names = (await io.list(folder)).filter(n => n.endsWith('.json'))
  } catch {
    return null
  }
  const open: any[] = []
  for (const name of names) {
    const data = await readJson(io, join(folder, name))
    if (data && STEPS.includes(data.step) && data.step !== 'proven') open.push(data)
  }
  const loop = open.sort((a, b) => String(a.opened_at ?? '').localeCompare(String(b.opened_at ?? ''))).at(-1)
  if (!loop) return null
  const t = loop.tasks
  const task = t && typeof t === 'object' && t.label
    ? { label: String(t.label), done: Number(t.done ?? 0), total: t.total ? Number(t.total) : null,
        elapsed: t.started_at ? elapsed(String(t.started_at), await io.now()) : '' }
    : null
  return { step: String(loop.step), task, stopped: String(loop.stopped ?? '') }
}

/** A frontmatter value of a study file: plumb writes each as JSON (valid YAML too). */
function front(text: string, key: string): string {
  const raw = new RegExp(`^${key}: (.*)$`, 'm').exec(text.split('\n---\n')[0] ?? '')?.[1] ?? ''
  try {
    return String(JSON.parse(raw))
  } catch {
    return raw
  }
}

/** The `progress` of an accepted study being written (a JSON object in the frontmatter). */
function progressOf(text: string): StudyFile['progress'] {
  const raw = /^progress: (.*)$/m.exec(text.split('\n---\n')[0] ?? '')?.[1]
  try {
    const p = raw ? JSON.parse(raw) : null
    return p && typeof p === 'object' ? { step: String(p.step ?? ''), done: Number(p.done) || 0, total: Number(p.total) || 0 } : null
  } catch {
    return null
  }
}

type StudyFile = { title: string; slug: string; status: string; why: string; recommend: string; changed: string; refresh: string; progress: { step: string; done: number; total: number } | null }

/** Every study file in `.plumb/studies`, oldest first by file name. */
async function studyFiles(io: Io, link: PlumbLink): Promise<StudyFile[]> {
  const folder = join(link.root, '.plumb', 'studies')
  let names: string[] = []
  const found: StudyFile[] = []
  try {
    names = (await io.list(folder)).filter(n => n.endsWith('.md')).sort()
  } catch {
    return found
  }
  for (const name of names) {
    try {
      const text = await io.read(join(folder, name))
      const title = front(text, 'title')
      if (title) {
        found.push({ title, slug: name.slice(0, -3), status: front(text, 'status'), why: front(text, 'why'),
          recommend: front(text, 'recommend'), changed: front(text, 'changed'), refresh: front(text, 'refresh'), progress: progressOf(text) })
      }
    } catch {
      // a study being written: the next read names it
    }
  }
  return found
}

/** The studies still `new` (SR-294): the band names them until the owner opens each in the
 * room; empty when none waits. */
export async function readStudies(io: Io, link: PlumbLink): Promise<{ title: string; slug: string }[]> {
  return (await studyFiles(io, link)).filter(s => s.status === 'new').map(({ title, slug }) => ({ title, slug }))
}

/** The owner pressed a choice on a study idea (SR-294 EX-7..EX-9, DEC-207): plumb records it
 * accepted at `depth` (`md`, `diagrams`) or declined (`none`); the room does not open. */
export function chooseStudy(io: Io, link: PlumbLink, slug: string, depth: string): Promise<Ran> {
  return plumbMod(io, link, 'study', { key: link.key }, ['--study', slug, '--depth', depth])
}

/** The owner pressed 'Rewrite it' or 'not now' on a study whose records changed (SR-360 EX-2,
 * DEC-336): plumb asks the agent to rewrite it at the same depth, or leaves it marked. */
export function refreshStudy(io: Io, link: PlumbLink, slug: string, yes: boolean): Promise<Ran> {
  return plumbMod(io, link, 'study', { key: link.key }, ['--study', slug, '--refresh', yes ? 'yes' : 'no'])
}

/** The band's first line: plumb's status card (status.json) and SP8's progress, if running. */
export async function readStatus(io: Io, link: PlumbLink): Promise<PlumbStatus> {
  const status = await readJson(io, join(link.root, '.plumb', 'session', 'status.json'))
  const progress = await readJson(io, join(sessionDir(link.root, link.session), 'progress'))
  // SR-336 EX-2: the study the owner chose to read before answering its questions
  const first = await readJson(io, join(sessionDir(link.root, link.session), 'study_first.json'))
  // SR-358: this session's plugin against plumb's local and repository main; SR-359: the judges that cannot settle
  const build = await readJson(io, join(sessionDir(link.root, link.session), 'build.json'))
  const judges = await readJson(io, join(link.root, '.plumb', 'session', 'judges.json'))
  const down = judges?.down && typeof judges.down === 'object' ? Object.values(judges.down) as any[] : []
  const red = [...(Array.isArray(build?.lines) ? build.lines.map(String) : []),
    ...down.map(d => String(d?.line ?? '')).filter(Boolean)]
  const setAside = (Array.isArray(judges?.set_aside) ? judges.set_aside : [])
    .map((q: any) => T.setAside(String(q?.question ?? ''), String(q?.why ?? '')))
  const files = await studyFiles(io, link)
  const studies = files.filter(s => s.status === 'new').map(({ title, slug }) => ({ title, slug }))
  const study = studies.find(s => s.slug === first?.study) ?? studies.at(-1) ?? { title: '', slug: '' }
  // DEC-207: ideas waiting for the owner's choice, oldest first
  const ideas = files.filter(s => s.status === 'idea').map(({ title, slug, why, recommend }) => ({ title, slug, why, recommend }))
  // SR-251: the records a judge approved, the set `plumb status` lists (judge_approved); an
  // older status.json without it counts the requirements in confirmed_by
  const by = status?.confirmed_by && typeof status.confirmed_by === 'object' ? status.confirmed_by : {}
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
    awaiting: Number(status?.awaiting ?? 0), // SR-337: the questions waiting for the owner
    loop: await readLoop(io, link),
    study: study.title,
    studySlug: study.slug,
    studies,
    ideas,
    // an accepted idea the agent is writing now: the band's progress line
    writing: files.filter(s => s.status === 'accepted' || s.progress).map(({ title, progress }) => ({ title, ...(progress ?? {}) })).at(-1),
    // SR-360 EX-2: out of date, the owner not asked yet
    outdated: files.filter(s => s.changed && !s.refresh).map(({ title, slug, changed }) => ({ title, slug, changed })),
    judged: Number(status?.judge_approved ?? Number(by['auto-jev'] ?? 0) + Number(by['auto-model'] ?? 0)),
    red,
    ...(build?.unchecked === true ? { unchecked: T.unchecked } : {}),
    setAside,
  }
}

/** What plumb holds now: the status and, at the end of a turn, present.json. */
export async function snapshot(io: Io, link: PlumbLink, view: PlumbView, atTurnEnd: boolean): Promise<PlumbView> {
  const status = await readStatus(io, link)
  const present = atTurnEnd ? await readPresent(io, link) : view.present
  return { ...view, status, present }
}
