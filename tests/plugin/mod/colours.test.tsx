// plumb's own colours in the band (SR-290): plum for its name and state, the darker shade on a
// light theme, and never a colour of Claude Code's own (its orange, lavender, cyan or green, or
// a theme key that paints the host's prompts). Each case runs on the terminal and the desktop.
import { describe, expect, test } from 'claude-code/testing'

import { BRASS, PLUM, plumbColor } from '../../../plugin/hooks/text'
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
