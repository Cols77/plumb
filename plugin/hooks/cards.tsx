// One card as the panel draws it (SR-116, INT-031): everything the owner needs to choose,
// without asking back: the record as it now reads, what changed with its evidence (a long change
// folded with its size, openable in full, never cut), the owner's words it traces to, each
// option with what it does and leaves undone, why the recommended one, then the buttons: the
// card's suggested answers (the recommended one first; No where the card suggests it,
// DEC-033), Ask for a change and Leave open.
//
// Every Button's own handler is a no-op: the panel's `ui.press` hook does the work, by the
// Button's key (pressKey, foldKey, `showall`), where its `$` calls are spelled.
import type { PlumbCard, PlumbOffer } from '../types'
import { FOLD_AT, T } from './text'

/** The surface's element table, as `$.ui.resolve(e)` answers it. */
export type Ui = { Box: any; Text: any; Button: any; Code: any }

export const NOOP = () => {}

export function pressKey(card: PlumbCard, q: number, b: number): string {
  return `press:${q}:${b}:${card.id}`
}

export function foldKey(card: PlumbCard): string {
  return `fold:${card.id}`
}

/** What changes a card's content: its id, status and the versions it shows. */
export function contentKey(card: PlumbCard): string {
  return [card.id, card.status, ...card.offers.map(o => o.hash)].join('|')
}

function line(ui: Ui, text: string, props: Record<string, unknown> = {}) {
  const { Text } = ui
  return <Text {...props}>{text}</Text>
}

function section(ui: Ui, key: string, title: string, children: any[]) {
  const { Box, Text } = ui
  return (
    <Box key={key} flexDirection="column" marginTop={1}>
      <Text bold>{title}</Text>
      {children}
    </Box>
  )
}

function foldButton(ui: Ui, card: PlumbCard, isOpen: boolean) {
  const { Button } = ui
  return <Button key={foldKey(card)} label={isOpen ? T.fold : T.unfold} onPress={NOOP} />
}

/** What changed (the diff) or what the card rests on: whole up to FOLD_AT characters, folded
 * with its size beyond, a button opening it in full. */
function changed(ui: Ui, card: PlumbCard, isOpen: boolean) {
  const { Code } = ui
  const change = card.content?.change
  if (change && (change.diff || change.note)) {
    const body: any[] = []
    if (change.diff) {
      const size = change.size ?? change.diff.length
      const lines = change.lines ?? change.diff.split('\n').length
      const isLong = change.folded ?? size > FOLD_AT
      body.push(line(ui, T.changeHead(change.path ?? '', change.added ?? 0, change.removed ?? 0, size)))
      if (isLong && !isOpen) {
        body.push(line(ui, `[${T.folded(size, lines)}]`, { dimColor: true }))
      } else {
        body.push(<Code key={`diff:${card.id}`} source={change.diff} format="diff" />)
      }
      if (isLong) body.push(foldButton(ui, card, isOpen))
    }
    if (change.note) body.push(line(ui, change.note, { dimColor: true }))
    return section(ui, 'changed', T.whatChanged, body)
  }
  if (!card.evidence) return null
  const size = card.evidence_size || card.evidence.length
  const isLong = size > FOLD_AT
  const body = isLong && !isOpen
    ? [line(ui, `[${T.folded(size, card.evidence.split('\n').length)}]`, { dimColor: true })]
    : [line(ui, card.evidence)]
  if (isLong) body.push(foldButton(ui, card, isOpen))
  return section(ui, 'changed', T.evidence, body)
}

function nowReads(ui: Ui, card: PlumbCard) {
  const now = card.content?.record_now
  if (now?.wording) {
    return section(ui, 'now', T.asItReads, [
      line(ui, now.title ? `${now.title}: ${now.wording}` : now.wording),
      ...(now.examples ?? []).map(ex => line(ui, `  ${ex}`, { dimColor: true })),
    ])
  }
  const asked = card.questions.map(q => q.text).filter(t => t && t !== card.issue)
  return asked.length ? section(ui, 'now', T.asItReads, asked.map(t => line(ui, t))) : null
}

function words(ui: Ui, card: PlumbCard) {
  const said = card.content?.owner_words
  if (!said) return null
  const body = (said.items ?? []).map(item => {
    const quote = item.quote || item.prompt || ''
    return line(ui, item.title ? `${item.title}: "${quote}"` : `"${quote}"`)
  })
  if (said.note) body.push(line(ui, said.note, { dimColor: true }))
  return body.length ? section(ui, 'words', T.yourWords, body) : null
}

function options(ui: Ui, card: PlumbCard) {
  const listed = card.content?.options
  if (listed && listed.length) {
    const body: any[] = []
    for (const option of listed) {
      body.push(line(ui, `${option.n}. ${option.text}${option.recommended ? T.recommended : ''}`))
      body.push(line(ui, `   ${T.consequence}${option.consequence ?? T.notWritten}`, { dimColor: true }))
    }
    return section(ui, 'options', T.options, body)
  }
  if (!card.resolutions.length) return null
  const several = card.resolutions.length > 1
  return section(ui, 'options', T.options, card.resolutions.map((r, i) =>
    line(ui, `${i + 1}. ${r}${i === 0 && several ? T.recommended : ''}`)))
}

function why(ui: Ui, card: PlumbCard) {
  if (!card.content) return null
  return section(ui, 'why', T.why, [line(ui, card.content.why || T.notWritten)])
}

function buttons(ui: Ui, card: PlumbCard, offer: PlumbOffer, q: number) {
  const { Box, Button } = ui
  return (
    <Box key={`buttons:${q}:${card.id}`} flexDirection="row" flexWrap="wrap" gap={1} marginTop={1}>
      {offer.buttons.map((b, i) =>
        i === 0 && b.answer === 'accepted'
          ? <Button key={pressKey(card, q, i)} label={b.label} variant="primary" onPress={NOOP} />
          : <Button key={pressKey(card, q, i)} label={b.label} onPress={NOOP} />)}
    </Box>
  )
}

/** The card in full. A card of several items (a feature card) lists them; Show all gives each
 * its own buttons. */
export function CardView(ui: Ui, card: PlumbCard, opts: { isOpen: boolean; showAll: boolean }) {
  const { Box, Button, Text } = ui
  const several = card.offers.length > 1
  const parts = [nowReads(ui, card), changed(ui, card, opts.isOpen), words(ui, card),
    options(ui, card), why(ui, card)].filter(p => p !== null)
  const answer: any[] = []
  if (several && !opts.showAll) {
    answer.push(line(ui, T.items(card.offers.length), { dimColor: true }))
    for (const q of card.questions) answer.push(line(ui, `• ${q.text}`))
    answer.push(<Button key={`items:${card.id}`} label={T.showAll} onPress={NOOP} />)
  } else {
    card.offers.forEach((offer, q) => {
      if (several) answer.push(line(ui, card.questions[q]?.text ?? offer.question, { bold: true }))
      answer.push(buttons(ui, card, offer, q))
    })
  }
  return (
    <Box key={`card:${card.id}`} flexDirection="column" borderStyle="round" paddingX={1} marginTop={1}>
      <Text bold>{card.topic}</Text>
      <Text>{card.issue}</Text>
      {parts}
      {answer}
    </Box>
  )
}

/** "merge check (2), reminders": the cards awaiting, per feature (DEC-029). */
export function perFeature(cards: PlumbCard[]): string {
  const counts = new Map<string, number>()
  for (const card of cards) {
    const name = card.feature || card.topic
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return [...counts].map(([name, n]) => (n > 1 ? `${name} (${n})` : name)).join(', ')
}
