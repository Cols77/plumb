// plumb's mod (SP7 5 as re-aligned by sp7-realign-sp8; SR-085, SR-086, SR-087, SR-116): the
// band above the prompt (plumb's status, SP8's progress, the cards awaiting per feature), each
// awaiting card in full with its buttons, Show all, Undo on the settled line, a toast, the
// owner's notice and the model's note after a press, and the fallback. plumb's command hooks
// keep doing the work (DEC-024): while this panel is active the stop hook writes present.json
// instead of printing.
//
// The engine wants every `$` call spelled at its hook's call site: each hook hands plumb.ts an
// `Io` of closures over its own `$`, and every Button is answered by the `ui.press` hook below.
//
// Linking (SR-125, SR-126): the session's start says hello as soon as plumb's interpreter is
// known; the session-start command hook names it in host.json, maybe a moment after this mod
// starts, so the start keeps trying for a few seconds, and each turn's start tries again. The
// same holds while plumb still keeps a resumed session's old panel registered (the hook retires
// it) and while only the repository's .venv was there to try. When the panel cannot reach plumb
// it says why in one dim line, once per session; in a repository plumb has not adopted it stays
// silent.
import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { PlumbBand, PlumbLink, PlumbTold, PlumbView } from '../types'
import { CardView, contentKey, findPress, perFeature } from './cards'
import type { Ui } from './cards'
import * as plumb from './plumb'
import type { Hello, Io, Unlinked } from './plumb'
import { GLYPHS, T } from './text'

const PANE = 'plumb-cards'
const EMPTY_VIEW: PlumbView = { cards: [], present: null, status: null, line: '' }
const BAND: PlumbBand = { isHidden: false, showAll: false, unfolded: [], shown: [] }

const linkAtom = atom({ plugin: 'plumb', key: 'link' } as const, null)
const degradedAtom = atom({ plugin: 'plumb', key: 'degraded' } as const, false)
const toldAtom = atom({ plugin: 'plumb', key: 'told' } as const, null as PlumbTold | null)
const viewAtom = atom({ plugin: 'plumb', key: 'view' } as const, EMPTY_VIEW)
const bandAtom = atom({ plugin: 'plumb', key: 'band' } as const, BAND)

function statusLine(view: PlumbView): string {
  const waiting = view.cards.filter(c => c.repeats).length
  const state = view.status?.state ?? ''
  const glyph = waiting ? GLYPHS['awaits you'] : GLYPHS[state] ?? '·'
  const word = waiting ? T.awaiting(waiting) : state || T.nothingAwaits
  return [`${T.name} ${glyph} ${word}`, view.status?.progress].filter(Boolean).join(' · ')
}

// the session-start hook writes host.json within its first second: about ten seconds of tries
const RETRY_MS = 500
const RETRIES = 20

// one hello at a time: the start's retries and a turn's start never both register the session
let helloing: Promise<Hello> | null = null
function helloOnce(io: Io): Promise<Hello> {
  if (helloing === null) {
    helloing = plumb.hello(io).finally(() => {
      helloing = null
    })
  }
  return helloing
}

function unlinkedLine(u: Unlinked): string {
  if (u.why === 'no-python') return T.noPython(u.looked)
  if (u.why === 'refused') return T.helloRefused(u.reason)
  return T.helloFailed(u.error)
}

/** The band: one line of status, the cards awaiting per feature, the settled line with its
 * Undo buttons, then the awaiting card in full (every card with Show all). */
function drawBand(ui: Ui, view: PlumbView, band: PlumbBand, columns: number) {
  const { Box, Button, Text } = ui
  const head = statusLine(view)
  if (band.isHidden) {
    return (
      <Box flexDirection="row" gap={1}>
        <Text dimColor>{head}</Text>
        <Button key="show" label={T.show} plain onPress={() => {}} />
      </Box>
    )
  }
  const waiting = view.cards.filter(c => c.repeats)
  const leftOpen = view.cards.filter(c => !c.repeats)
  const compact = view.status?.card === 'compact'
  const shown = band.showAll ? view.cards : compact ? [] : waiting.slice(0, 1)
  const settled = view.present?.settled_records ?? []
  return (
    <Box flexDirection="column" width={columns}>
      <Box flexDirection="row" gap={1}>
        <Text bold>{head}</Text>
        {view.status?.summary ? <Text dimColor>{view.status.summary}</Text> : null}
        <Button key="hide" label={T.hide} plain onPress={() => {}} />
      </Box>
      {waiting.length ? <Text key="waiting">{`${T.awaiting(waiting.length)}: ${perFeature(waiting)}`}</Text> : null}
      {leftOpen.length ? <Text key="left" dimColor>{`${T.leftOpen(leftOpen.length)}: ${perFeature(leftOpen)}`}</Text> : null}
      {view.line ? <Text key="line" dimColor>{view.line}</Text> : null}
      {(view.present?.confirmations ?? []).map(c => <Text key={`confirmed:${c}`}>{c}</Text>)}
      {settled.length ? (
        <Box key="settled" flexDirection="row" flexWrap="wrap" gap={1}>
          <Text>{T.settledHead}</Text>
          {settled.map(r => (
            <Box key={`settled:${r.id}`} flexDirection="row" gap={1}>
              <Text>{r.title}</Text>
              <Button key={`undo:${r.id}`} label={T.undo} onPress={() => {}} />
            </Box>
          ))}
        </Box>
      ) : null}
      {shown.map(card => CardView(ui, card, { isOpen: band.unfolded.includes(card.id), showAll: band.showAll }))}
      {view.cards.length > shown.length ? (
        <Box flexDirection="row" gap={1}>
          <Button key="showall" label={T.showAll} onPress={() => {}} />
          <Button key="pane" label={T.openPane} onPress={() => {}} />
        </Box>
      ) : null}
      {band.showAll ? <Button key="fewer" label={T.showFewer} onPress={() => {}} /> : null}
    </Box>
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    // SR-126: why the panel cannot reach plumb, said once per session
    const tell = async (u: Unlinked) => {
      const session = await $.session.id()
      const told = await read($, toldAtom)
      if (told !== null && told.session === session) return
      await update($, toldAtom, () => ({ session, why: u.why, retry: plumb.mayLinkLater(u) }))
      $.ui.log(unlinkedLine(u))
    }
    const linked = async (link: PlumbLink) => {
      await update($, linkAtom, () => link)
      const band = await read($, bandAtom)
      const snap = await plumb.snapshot(io, link, await read($, viewAtom), band.shown, false)
      await update($, viewAtom, () => snap.view)
      $.ui.status(statusLine(snap.view))
    }
    if ((await read($, degradedAtom)) || (await read($, linkAtom)) !== null) return started
    const said = await helloOnce(io)
    if (said.link !== null) {
      await linked(said.link)
      return started
    }
    if (said.unlinked === null) return started // a repository plumb has not adopted: silent
    if (!plumb.mayLinkLater(said.unlinked)) {
      await tell(said.unlinked)
      return started
    }
    // the session-start hook may not have named the interpreter (or retired a resumed
    // session's old panel) yet: try again for a while, without holding up the first prompt,
    // then say why
    let tries = 0
    let busy = false
    const retry = $.clock.every(RETRY_MS, async () => {
      if (busy) return
      busy = true
      try {
        tries += 1
        if ((await read($, degradedAtom)) || (await read($, linkAtom)) !== null) {
          retry.cancel()
          return
        }
        const again = await helloOnce(io)
        if (again.link !== null) {
          retry.cancel()
          await linked(again.link)
        } else if (again.unlinked === null) {
          retry.cancel()
        } else if (!plumb.mayLinkLater(again.unlinked) || tries >= RETRIES) {
          retry.cancel()
          await tell(again.unlinked)
        }
      } catch {
        retry.cancel() // the turn's start tries again
      } finally {
        busy = false
      }
    })
    return started
  }).catch(async ($, e, next) => {
    const result = await next(e)
    try {
      await update($, degradedAtom, () => true)
      $.ui.log(T.degraded)
    } catch {
      // a re-entry: this handler's own $ calls reject; the session goes on
    }
    return result
  })

  on('turn.start', async ($, e, next) => {
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    if (await read($, degradedAtom)) return next(e)
    const session = await $.session.id()
    let link = await read($, linkAtom)
    if (link !== null && link.session !== session) {
      // a /clear: the conversation goes on under a new session id, and no session.start fires
      link = null
      await update($, linkAtom, () => null)
      await update($, viewAtom, () => EMPTY_VIEW)
    }
    const told = await read($, toldAtom)
    // a refusal or a failure already said this session is not retried every turn, unless a
    // later try may link (mayLinkLater)
    const settled = told !== null && told.session === session && told.why !== 'no-python' &&
      told.retry !== true
    if (link === null && !settled) {
      // the session-start hook may only now have said which interpreter runs plumb
      const said = await helloOnce(io)
      if (said.link !== null) {
        const held = said.link
        await update($, linkAtom, () => held)
        // the band draws from now on: plumb's status at once (no process), the cards at the turn's end
        const view = { ...(await read($, viewAtom)), status: await plumb.readStatus(io, held) }
        await update($, viewAtom, () => view)
        $.ui.status(statusLine(view))
        link = held
      } else if (said.unlinked !== null) {
        // SR-126: once per session; read again after the hello, which the start's retry may
        // have told meanwhile
        const now = await read($, toldAtom)
        if (now === null || now.session !== session) {
          const why = said.unlinked
          await update($, toldAtom, () => ({ session, why: why.why, retry: plumb.mayLinkLater(why) }))
          $.ui.log(unlinkedLine(why))
        }
      }
    }
    if (link !== null) await plumb.heartbeat(io, link)
    return next(e)
  }).catch(async ($, e, next) => {
    const result = await next(e)
    try {
      await update($, degradedAtom, () => true)
      $.ui.log(T.degraded)
    } catch {
      // a re-entry: this handler's own $ calls reject; the turn goes on
    }
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result // a subagent's turn: the owner's band waits
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    if (await read($, degradedAtom)) return result
    const link = await read($, linkAtom)
    if (link === null) return result
    const band = await read($, bandAtom)
    const snap = await plumb.snapshot(io, link, await read($, viewAtom), band.shown, true)
    await update($, viewAtom, () => snap.view)
    if (snap.fresh) {
      await update($, bandAtom, b => ({ ...b, isHidden: false }))
      $.ui.toast(T.toastAwaiting(snap.view.cards.filter(c => c.repeats).length))
    }
    $.ui.status(statusLine(snap.view))
    return result // the answer is never rewritten; no summary line is added (realign a)
  }).catch(async ($, e, next) => {
    const result = await next(e)
    try {
      await update($, degradedAtom, () => true)
      $.ui.log(T.degraded)
    } catch {
      // a re-entry: this handler's own $ calls reject; the turn's answer still stands
    }
    return result
  })

  // every Button the panel draws: what it does, by its key
  on('ui.press', async ($, e, next) => {
    if (e.plugin !== 'plumb') return next(e)
    const key = e.element
    const view = await read($, viewAtom)
    const band = await read($, bandAtom)
    if (key === 'hide') {
      await update($, bandAtom, b => ({ ...b, isHidden: true, showAll: false,
        shown: view.cards.map(contentKey) }))
      return next(e)
    }
    if (key === 'show') {
      await update($, bandAtom, b => ({ ...b, isHidden: false }))
      return next(e)
    }
    if (key === 'showall' || key.startsWith('items:')) {
      await update($, bandAtom, b => ({ ...b, showAll: true })) // records nothing, runs nothing
      return next(e)
    }
    if (key === 'fewer') {
      await update($, bandAtom, b => ({ ...b, showAll: false }))
      return next(e)
    }
    if (key === 'pane') {
      await $.ui.open({ id: PANE, title: T.paneTitle })
      return next(e)
    }
    if (key.startsWith('fold:')) {
      const id = key.slice('fold:'.length)
      await update($, bandAtom, b => ({ ...b, unfolded: b.unfolded.includes(id)
        ? b.unfolded.filter(x => x !== id) : [...b.unfolded, id] }))
      return next(e)
    }
    const link = await read($, linkAtom)
    if (link === null || (await read($, degradedAtom))) return next(e)
    const io: Io = {
      exists: p => $.fs.exists(p),
      read: async p => String(await $.fs.read(p)),
      write: (p, t) => $.fs.write(p, t),
      run: (argv, init) => $.process.run(argv, init),
      root: () => $.session.root(),
      id: () => $.session.id(),
      now: () => $.clock.now(),
      env: async () => ({
        PLUMB_HOME: await $.env.get('PLUMB_HOME'),
        CLAUDE_PLUGIN_DATA: await $.env.get('CLAUDE_PLUGIN_DATA'),
        HOME: await $.env.get('HOME'),
        USERPROFILE: await $.env.get('USERPROFILE'),
      }),
    }
    let line = ''
    let note = ''
    if (key.startsWith('undo:')) {
      const ran = await plumb.undo(io, link, key.slice('undo:'.length))
      line = ran.ok ? String(ran.data.line ?? '') : T.undoFailed
      note = ran.ok ? String(ran.data.model_note ?? '') : ''
    } else if (key.startsWith('press:')) {
      const found = findPress(view.cards, key)
      if (found === null) return next(e)
      const ran = await plumb.press(io, link, found.offer.offer_id, found.button.index)
      line = ran.ok ? String(ran.data.line ?? '') : T.pressFailed
      note = ran.ok ? String(ran.data.model_note ?? '') : ''
      if (ran.ok && ran.data.prefill) {
        // DEC-032: the owner's words go to the message box, already started
        const filled = await $.prompt.fill({ text: String(ran.data.prefill), mode: 'replace' })
        if (!filled.isFilled) note += T.noBox(found.card.topic)
      }
    } else {
      return next(e)
    }
    // the owner's notice (the model never reads it) and the model's note (never shown as
    // typed), each its own row; a toast says it now (SP7 5.4, SR-087 EX-3)
    if (line) {
      $.ui.toast(line)
      await $.session.append({ message: { type: 'system', content: [{ type: 'text', text: line }] } })
    }
    if (note) {
      await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: note }] } })
    }
    const snap = await plumb.snapshot(io, link, { ...view, line }, band.shown, false)
    const undone = key.startsWith('undo:') ? key.slice('undo:'.length) : null
    const present = snap.view.present && undone
      ? { ...snap.view.present, settled_records: snap.view.present.settled_records.filter(r => r.id !== undone) }
      : snap.view.present
    await update($, viewAtom, () => ({ ...snap.view, present }))
    $.ui.status(statusLine(snap.view))
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    if ((await read($, degradedAtom)) || (await read($, linkAtom)) === null) return next(e)
    const view = await read($, viewAtom)
    if (view.status?.card === 'off') return next(e)
    const ui = $.ui.resolve(e) as unknown as Ui
    return drawBand(ui, view, await read($, bandAtom), e.props.bodyColumns)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e) as unknown as Ui
    const { Box, Text } = ui
    const view = await read($, viewAtom)
    const band = await read($, bandAtom)
    if (!view.cards.length) return <Text dimColor>{T.nothingAwaits}</Text>
    return (
      <Box flexDirection="column">
        {view.cards.map(card => CardView(ui, card, { isOpen: band.unfolded.includes(card.id), showAll: true }))}
      </Box>
    )
  })
}
