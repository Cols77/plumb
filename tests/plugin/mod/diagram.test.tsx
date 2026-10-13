// A card can carry a block diagram above its question (SR-145, INT-041). The diagram mod's noun
// is drawn when the snapshot is taken, at 85 columns, and the card shows what it gave: rows on
// the terminal, the Svg elsewhere; without the noun one line names the file. The test engine's
// $ has no nouns but its own, so the snapshot is run over a stand-in noun and the card is drawn
// by CardView over plain tags.
import { describe, expect, test } from 'claude-code/testing'

import { CardView } from '../../../plugin/hooks/cards'
import { snapshot } from '../../../plugin/hooks/plumb'
import type { Io } from '../../../plugin/hooks/plumb'
import { DRAW, PYTHON, ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, world } from './harness'

const PATH = '.plumb/diagrams/hooks.html'
const ROWS = ['┌────┐', '│ A  │', '└─┬──┘', '  │', '┌─┴──┐', '│ B  │']
const CARD = { ...JSON.parse(JSON.stringify(DRAW.cards[1])), diagram: PATH }
const LINK = { session: SESSION, root: ROOT, python: PYTHON, key: 'k'.repeat(64) }
const EMPTY = { cards: [], present: null, status: null, line: '' }

/** The Io a snapshot reads through: plumb's draw answering the card, the diagram file, `noun`. */
function io(noun?: Io['diagram']): Io {
  return {
    exists: async () => false,
    read: async p => {
      if (p !== `${ROOT}/${PATH}`) throw new Error(`no such file ${p}`)
      return '<svg>hooks</svg>'
    },
    write: async () => {},
    run: async () => ({ exitCode: 0, stdout: JSON.stringify({ session: SESSION, cards: [CARD] }), stderr: '', isStdoutTruncated: false, isStderrTruncated: false }),
    root: async () => ROOT,
    id: async () => SESSION,
    now: async () => 0,
    env: async () => ({}),
    diagram: noun,
  }
}

describe('a card diagram, as the snapshot draws it', () => {
  test('is the file drawn at 85 columns by the noun', async () => {
    const seen: [string, number][] = []
    const noun: Io['diagram'] = async (text, columns) => { seen.push([text, columns]); return { rows: ROWS, svg: '<svg/>' } }
    const { view: v } = await snapshot(io(noun), LINK, EMPTY, [], false)
    expect(seen).toEqual([['<svg>hooks</svg>', 85]])
    expect(v.cards[0]?.drawn).toEqual({ rows: ROWS, svg: '<svg/>' })
  })

  test('is nothing when the noun or the file fails', async () => {
    const broken: Io['diagram'] = async () => { throw new Error('no diagram noun') }
    expect((await snapshot(io(broken), LINK, EMPTY, [], false)).view.cards[0]?.drawn).toBeNull()
  })
})

/** Every text and Svg of a drawn card, in order, over an element table of plain tags. */
function drawnBy(surface: string, drawn: { rows: string[]; svg: string } | null, room?: number) {
  const table = { Box: 'Box', Text: 'Text', Button: 'Button', Svg: surface === 'terminal' ? undefined : 'Svg' }
  const out: string[] = []
  const walk = (node: any): void => {
    if (Array.isArray(node)) return node.forEach(walk)
    if (node === null || typeof node !== 'object') return void (typeof node === 'string' && out.push(node))
    if (node.type === 'Svg') out.push(`Svg ${node.props.alt}: ${node.props.source}`)
    walk(node.children)
  }


  walk(CardView(table, { ...CARD, drawn }, room))
  return out
}

test('a drawing wider than the pane is not cut: the file line shows instead', () => {
  const shown = drawnBy('terminal', { rows: ROWS, svg: '<svg/>' }, 5)
  expect(shown).toContain(`Diagram: ${PATH} (open it to see it)`)
  expect(shown).not.toContain(ROWS[0])
})

for (const surface of SURFACES) {
  describe(`a card diagram on the ${surface}`, () => {
    test('is drawn above the question', () => {
      const shown = drawnBy(surface, { rows: ROWS, svg: '<svg>hooks</svg>' })
      expect(shown.indexOf('Confirm button')).toBeGreaterThan(0)
      const above = shown.slice(0, shown.indexOf('Confirm button'))
      expect(above).toEqual(surface === 'terminal' ? ROWS : [`Svg diagram ${PATH}: <svg>hooks</svg>`])
    })

    test('without the diagram mod one line names the file, and the buttons still press', async ($, on) => {
      const w = world({ answer: (action, argv) => action === 'draw' ? { exitCode: 0, data: { session: SESSION, cards: [CARD] } } : world().answer(action, argv) })
      install(on, w)
      await $.session.start(START)
      const ui = await $.ui.mount({ plugin: 'plumb', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: `Diagram: ${PATH} (open it to see it)` })).toBeDefined()
      expect(await ui.find({ type: 'Svg' })).toBeUndefined()
      expect(await ui.find({ type: 'Text', text: 'Confirm button' })).toBeDefined()
      await ui.press({ key: 'press:0:sha256:bbbb' })
      expect(w.runs.filter(r => r.argv[4] === 'press')).toHaveLength(1)
      await ui.unmount()
    })
  })
}
