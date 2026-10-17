// plumb's own colours in the band (SR-290): plum for its name and state, the darker shade on a
// light theme, and never a colour of Claude Code's own (its orange, lavender, cyan or green, or
// a theme key that paints the host's prompts). Each case runs on the terminal and the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { BRASS, BRASS_LIGHT, brassColor, PLUM, plumbColor } from '../../../plugin/hooks/text'
import { ROOT, SESSION } from './fixtures'
import { BAND, install, START, SURFACES, world } from './harness'

// Claude Code's own: its orange and lavender, the named colours it draws in, the theme keys
const HOST = ['#d77757', '#b1b9f9', 'cyan', 'cyanbright', 'green', 'greenbright', 'claude',
  'permission', 'suggestion', 'success', 'planmode', 'autoaccept', 'remember']

function painted(found: { props: Record<string, unknown> }[]): string[] {
  return found.flatMap(f => ['color', 'backgroundColor', 'borderColor']
    .map(k => f.props[k]).filter((c): c is string => typeof c === 'string'))
}

async function bandOn($: any, on: any, surface: (typeof SURFACES)[number], theme?: string) {
  const w = world()
  w.files[`${ROOT}/.plumb/session/${SESSION}/progress`] = JSON.stringify({ state: 'running', step: 'judging the backlog', done: 10, total: 160 })
  install(on, w)
  // the host's /config rows: the theme the owner chose (none: a surface that does not say)
  if (theme !== undefined) on('config.list', () => ({ value: [{ key: 'theme', label: 'Theme', kind: 'choice', value: theme }] }))
  await $.session.start(START)
  return $.ui.mount({ plugin: 'plumb', surface, ...BAND })
}

for (const surface of SURFACES) {
  describe(`plumb's colours on the ${surface}`, () => {
    test('SR-290 EX-1: plumb\'s name and state are plum; nothing is cyan or Claude orange', async ($, on) => {
      const ui = await bandOn($, on, surface, 'dark')
      const head = await ui.find({ type: 'Text', text: /^plumb / })
      expect(head?.props.color).toBe(PLUM.dark)
      const colours = painted(await ui.findAll({}))
      expect(colours.length).toBeGreaterThan(0)
      for (const c of colours) expect(HOST).not.toContain(c.toLowerCase())
      await ui.unmount()
    })

    test('SR-290 EX-3: on a light theme the plum is the darker shade', async ($, on) => {
      const ui = await bandOn($, on, surface, 'light')
      expect((await ui.find({ type: 'Text', text: /^plumb / }))?.props.color).toBe(PLUM.light)
      await ui.unmount()
    })

    test('SR-290 EX-4: no colour of the band is one Claude Code\'s permission prompt draws in', async ($, on) => {
      const ui = await bandOn($, on, surface)
      const colours = painted(await ui.findAll({}))
      for (const c of colours) {
        expect(HOST).not.toContain(c.toLowerCase())
        expect([PLUM.dark, PLUM.light, BRASS]).toContain(c)
      }
      await ui.unmount()
    })
  })
}

test('SR-290: the theme picks the shade; an unknown or absent theme is dark', () => {
  expect(plumbColor('light-daltonized')).toBe(PLUM.light)
  expect(plumbColor('dark-ansi')).toBe(PLUM.dark)
  expect(plumbColor(undefined)).toBe(PLUM.dark)
})

test('SR-290 EX-3: on a light theme the brass is the darker one, readable on white', async ($, on) => {
  const w = world()
  w.files[`${ROOT}/.plumb/session/${SESSION}/intent/aaaaaaaaaaaa.json`] = JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64),
    intent: 'INT-001', opened_at: '2026-10-11T11:00:00Z', step: 'plan', stopped: null, stages: {},
    tasks: { label: 'writing the plan', done: 3, total: 7, started_at: '2026-10-11T11:59:00Z' } })
  install(on, w)
  on('config.list', () => ({ value: [{ key: 'theme', label: 'Theme', kind: 'choice', value: 'light' }] }))
  await $.session.start(START)
  const ui = await $.ui.mount({ plugin: 'plumb', surface: 'terminal', ...BAND })
  expect((await ui.find({ type: 'Text', text: /^[█░]+$/ }))?.props.color).toBe(BRASS_LIGHT)
  await ui.unmount()
})

// WCAG contrast of a #RRGGBB text colour on white
function onWhite(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 1.05 / (0.2126 * r! + 0.7152 * g! + 0.0722 * b! + 0.05)
}

test('SR-290 EX-3: the light brass reads at 4.5:1 or more on white, the dark one would not', () => {
  expect(brassColor('light')).toBe(BRASS_LIGHT)
  expect(brassColor('dark')).toBe(BRASS)
  expect(onWhite(BRASS_LIGHT)).toBeGreaterThanOrEqual(4.5)
  expect(onWhite(BRASS)).toBeLessThan(3)
})
