// One card as the panel draws it (SR-129, SR-145): a read-back or a choice, each readable cold:
// the diagram when the agent drew one, the topic and the question, the context, what plumb
// assumed and the one thing it won't do, each option with what it does (the recommended one
// first), then the card's buttons.
//
// Every Button's own handler is a no-op: the panel's `ui.press` hook does the work, by the
// Button's key (pressKey), where its `$` calls are spelled.
import type { PlumbCard, PlumbOffer } from '../types'
import { T } from './text'

/** The surface's element table, as `$.ui.resolve(e)` answers it. */
export type Ui = { Box: any; Text: any; Button: any; Svg?: any }

export const NOOP = () => {}

/** A button's key names the offer it answers, never its position: a press on a card drawn
 * before a redraw cannot land on another record (plumb answers the offer it names). */
export function pressKey(offer: PlumbOffer, b: number): string {
  return `press:${b}:${offer.offer_id}`
}

/** The card, offer and button a press key names (`pressKey`): found by the offer's id, so a
 * key from an earlier draw names that offer or nothing, never another record's. */
export function findPress(cards: PlumbCard[], key: string) {
  const rest = key.slice('press:'.length)
  const cut = rest.indexOf(':')
  if (cut < 1) return null
  const b = Number(rest.slice(0, cut))
  const offerId = rest.slice(cut + 1)
  for (const card of cards) {
    const offer = card.offers.find(o => o.offer_id === offerId)
    const button = Number.isInteger(b) ? offer?.buttons[b] : undefined
    if (offer && button) return { card, offer, button }
  }
  return null
}

/** What changes a card's content: its id, status and the versions it shows. */
export function contentKey(card: PlumbCard): string {
  return [card.id, card.status, ...card.offers.map(o => o.hash)].join('|')
}

function line(ui: Ui, text: string, props: Record<string, unknown> = {}) {
  const { Text } = ui
  return <Text {...props}>{text}</Text>
}

/** The diagram above the question (INT-041): the drawn rows on the terminal, the file's SVG
 * where the surface has an Svg, else one line naming the file (also when `room` cells are too
 * few for the drawing). */
function diagram(ui: Ui, card: PlumbCard, room: number) {
  if (!card.diagram) return null
  const { Svg, Text } = ui
  const drawn = card.drawn
  if (Svg && drawn?.svg) return <Svg key="diagram" source={drawn.svg} alt={`diagram ${card.diagram}`} />
  if (!Svg && drawn?.rows.length && drawn.rows.every(r => r.length <= room)) { // never a cut drawing
    return drawn.rows.map((row, i) => <Text key={`diagram:${i}`} wrap="truncate-end">{row}</Text>)
  }
  return line(ui, T.diagramLine(card.diagram), { dimColor: true })
}

/** The card: a read-back (what plumb will do, what it assumed, the one thing it won't) or a
 * choice (one question, its options each with what it does), then the buttons. */
export function CardView(ui: Ui, card: PlumbCard, room = Infinity) {
  const { Box, Button, Text } = ui
  const c = card.content
  const offer = card.offers[0]
  return (
    <Box key={`card:${card.id}`} flexDirection="column" borderStyle="round" paddingX={1} marginTop={1}>
      {diagram(ui, card, room)}
      <Text bold>{c?.topic ?? card.topic}</Text>
      <Text>{c?.issue ?? card.issue}</Text>
      {(c?.context ?? []).map(t => line(ui, t, { dimColor: true }))}
      {(c?.assumptions ?? []).map(t => line(ui, T.assumed + t))}
      {c?.wont ? line(ui, T.wont + c.wont) : null}
      {(c?.options ?? []).map(o => (
        <Box key={`option:${o.n}`} flexDirection="column">
          <Text>{`${o.n}. ${o.text}${o.recommended ? T.recommended : ''}`}</Text>
          {o.consequence ? <Text dimColor>{`   ${o.consequence}`}</Text> : null}
        </Box>
      ))}
      {offer ? (
        <Box key={`buttons:${card.id}`} flexDirection="row" flexWrap="wrap" gap={1} marginTop={1}>
          {offer.buttons.map((b, i) =>
            i === 0 && b.answer === 'accepted'
              ? <Button key={pressKey(offer, i)} label={b.label} variant="primary" onPress={NOOP} />
              : <Button key={pressKey(offer, i)} label={b.label} onPress={NOOP} />)}
        </Box>
      ) : null}
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
