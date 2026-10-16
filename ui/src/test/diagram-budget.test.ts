import { expect, it, vi } from 'vitest';
import { parseSvg } from '../lib/diagram-mod/svg';
vi.mock('../lib/diagram-mod/svg', async (load) => ({...(await load<typeof import('../lib/diagram-mod/svg')>()),parseSvg:vi.fn(() => { throw Error('Unbounded geometric parser entered'); })}));
import { prepareDiagram } from '../lib/diagram';
it('bypasses geometric parsing of nested transforms without losing the image', () => {
  const result=prepareDiagram('<svg><rect width="20" height="20"/><text x="1" y="10">Pill</text><g transform="scale(10000)"><g transform="scale(10000)"><line x1="1" y1="0" x2="1000" y2="0"/></g></g></svg>');
  expect(parseSvg).not.toHaveBeenCalled(); expect(result.description).toContain('Pill'); expect(result.svg).toContain('scale');
});
it.each([
  '<path d="M0 0 '+ 'l100 100 '.repeat(300) +'"/>',
  '<path d="M0 0 l2000 2000"/>',
  '<polyline points="'+ '1 1 '.repeat(300) +'"/>',
])('uses label fallback for relative or excessive path geometry', shape => {
  const result=prepareDiagram('<svg><text x="1" y="1">Complex flow</text>'+shape+'</svg>');
  expect(result.description).toContain('Complex flow'); expect(parseSvg).not.toHaveBeenCalled();
});
