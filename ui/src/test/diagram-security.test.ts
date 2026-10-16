import { describe, expect, it } from 'vitest';
import { prepareDiagram } from '../lib/diagram';
describe('Repository diagrams', () => {
  it('extracts an SVG from HTML and describes its actual labels', () => {
    const result = prepareDiagram('<html><script>window.pwned=true</script><svg viewBox="0 0 300 100"><rect width="100" height="70"/><text x="10" y="30">Owner</text></svg></html>');
    expect(result.description).toContain('Owner'); expect(result.svg).toContain('xmlns='); expect(result.svg).not.toContain('<html');
  });
  it('removes executable SVG and external resources before image or download', () => {
    const result = prepareDiagram('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script><foreignObject><iframe src="https://evil.test"/></foreignObject><image href="https://evil.test/image"/><a href="javascript:alert(1)"><text x="1" y="2">Safe</text></a><style>@import "https://evil.test";rect{fill:url(https://evil.test)}</style><rect style="fill:url(https://evil.test)" width="100" height="100"/></svg>');
    expect(result.svg).not.toMatch(/script|onload|foreignObject|iframe|https:\/\/evil|javascript|@import/i); expect(result.svg).toContain('Safe'); expect((window as any).pwned).toBeUndefined();
  });
  it.each(['<html>No drawing</html>', '<svg><g></svg>', '<svg>'+ ' '.repeat(131072) +'</svg>'])('rejects missing, malformed or oversized source', source => {
    expect(() => prepareDiagram(source)).toThrow(/SVG|large|malformed/i);
  });
  it('keeps internal marker references', () => {
    const result = prepareDiagram('<svg xmlns="http://www.w3.org/2000/svg"><defs><marker id="arrow"><path d="M0 0L5 5"/></marker></defs><path d="M0 0L20 20" marker-end="url(#arrow)"/></svg>');
    expect(result.svg).toContain('url(#arrow)');
  });
});
