// The room draws in the band's plum and brass (SR-290 EX-2): its tokens hold the mod's values.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// vitest runs from ui/
const css = readFileSync(resolve('src/app.css'), 'utf8');
// read as text: the mod lies outside the room's root and is no module of the room's
const mod = readFileSync(resolve('../plugin/hooks/text.ts'), 'utf8');

const PLUM = { dark: mod.match(/dark: '(#[0-9A-Fa-f]{6})'/)?.[1] ?? '', light: mod.match(/light: '(#[0-9A-Fa-f]{6})'/)?.[1] ?? '' };
const BRASS = mod.match(/BRASS = '(#[0-9A-Fa-f]{6})'/)?.[1] ?? '';

const token = (name: string) => css.match(new RegExp(`--${name}:\\s*([^;]+);`))?.[1].trim().toLowerCase();

describe('the room in iaso\'s colours', () => {
  it('SR-290 EX-2: headings and buttons use the same plum and brass as the band', () => {
    expect(token('iaso')).toBe(PLUM.dark.toLowerCase());
    expect(token('iaso-strong')).toBe(PLUM.light.toLowerCase());
    expect(token('brass')).toBe(BRASS.toLowerCase());
    // every accent of the room (headings, buttons, focus, selection) is plum; highlights brass
    expect(token('accent')).toBe('var(--iaso)');
    expect(token('wait')).toBe('var(--brass)');
    expect(css).toMatch(/button\.primary \{ background:var\(--iaso-strong\)/);
  });
});
