// SR-293 EX-1 (a study with a diagram of the dispatcher, a page in plain words with its
// diagram): the study's Markdown is drawn as HTML, sanitized, and its mermaid block as a diagram;
// mermaid loads only for a study with a diagram; a broken diagram keeps its source with a note.
import { describe, expect, it, vi, beforeEach } from 'vitest';

const render = vi.fn();
const initialize = vi.fn();
vi.mock('mermaid', () => ({ default: { initialize, render } }));

import { DIAGRAM_FAILED, drawDiagrams, studyHtml } from '../lib/markdown';

const BODY = [
  '# How plumb\'s background jobs run', '',
  'A **dispatcher** hands each job to a *worker*.', '',
  '- one job at a time', '- retried once', '',
  '| | plumb | cron |', '|---|---|---|', '| runs | **6** | 5 |', '',
  'Run `plumb jobs`.', '',
  '```mermaid', 'flowchart LR', '  D[dispatcher] --> W[worker]', '```', '',
  '<img src=x onerror="alert(1)"><script>alert(2)</script>',
].join('\n');

function mount(body: string) {
  const el = document.createElement('div');
  el.innerHTML = studyHtml(body);
  document.body.replaceChildren(el);
  return el;
}

beforeEach(() => { render.mockReset(); initialize.mockReset(); });

describe('a study page (SR-293 EX-1)', () => {
  it('draws headings, emphasis, lists, tables and code, not raw Markdown', () => {
    const el = mount(BODY);
    expect(el.querySelector('h1')?.textContent).toBe("How plumb's background jobs run");
    expect(el.querySelector('strong')?.textContent).toBe('dispatcher');
    expect(el.querySelector('em')?.textContent).toBe('worker');
    expect(el.querySelectorAll('ul > li')).toHaveLength(2);
    expect(el.querySelectorAll('table td')).toHaveLength(3);
    expect(el.querySelector('p code')?.textContent).toBe('plumb jobs');
    expect(el.textContent).not.toContain('**');
    expect(el.textContent).not.toContain('|---|');
  });

  it('sanitizes the HTML: no script, no event handler', () => {
    const el = mount(BODY);
    expect(el.querySelector('script')).toBeNull();
    expect(el.innerHTML).not.toMatch(/onerror/i);
  });

  it('draws the mermaid block as a diagram in plum and brass', async () => {
    render.mockResolvedValue({ svg: '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><g><text>dispatcher</text></g></svg>' });
    const el = mount(BODY);
    await drawDiagrams(el);
    expect(render).toHaveBeenCalledWith(expect.any(String), 'flowchart LR\n  D[dispatcher] --> W[worker]\n');
    const figure = el.querySelector('figure.study-diagram');
    expect(figure?.querySelector('svg text')?.textContent).toBe('dispatcher');
    expect(figure?.innerHTML).not.toMatch(/onload/i);
    expect(el.querySelector('code.language-mermaid')).toBeNull();
    const vars = initialize.mock.calls[0]?.[0]?.themeVariables;
    expect(vars.primaryBorderColor).toBe('#b05fb0');
    expect(vars.lineColor).toBe('#c9a227');
  });

  it('keeps a large diagram at its natural width so the figure scrolls', async () => {
    render.mockResolvedValue({ svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1796 1864" style="max-width: 1796px;" width="100%"><g><text>x</text></g></svg>' });
    const el = mount(BODY);
    await drawDiagrams(el);
    const svg = el.querySelector('figure.study-diagram svg') as SVGElement;
    expect(svg.getAttribute('width')).toBe('1796');
    expect(svg.style.width).toBe('1796px');
    expect(svg.style.maxWidth).toBe('none');
  });

  it('shows a broken diagram as its source with a short note, never a blank', async () => {
    render.mockRejectedValue(new Error('Parse error on line 2'));
    const el = mount(BODY);
    await drawDiagrams(el);
    expect(el.querySelector('.study-diagram-note')?.textContent).toBe(DIAGRAM_FAILED);
    expect(el.querySelector('code.language-mermaid')?.textContent).toContain('D[dispatcher] --> W[worker]');
  });

  it('does not load mermaid for a study without a diagram', async () => {
    const el = mount('# Plain\n\nNo diagram here.');
    await drawDiagrams(el);
    expect(render).not.toHaveBeenCalled();
  });
});
