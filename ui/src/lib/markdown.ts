// A study's body drawn as Markdown, its ```mermaid blocks as diagrams (SR-293). The HTML is
// sanitized; mermaid is loaded only when a study has a diagram, and a diagram that fails to draw
// keeps its source with a short note, never a blank.
import DOMPurify from 'dompurify';
import { marked } from 'marked';

export const DIAGRAM_FAILED = 'This diagram could not be drawn; its source is below.';

export function studyHtml(body: string): string {
  return DOMPurify.sanitize(marked.parse(body, { async: false, gfm: true }));
}

let loaded: Promise<typeof import('mermaid').default> | null = null;
function mermaid() {
  loaded ??= import('mermaid').then(({ default: m }) => {
    // the room's dark theme, plum boxes and brass lines (SR-290); SVG labels, so the SVG
    // profile below keeps them (no foreignObject HTML)
    m.initialize({
      startOnLoad: false, securityLevel: 'strict', theme: 'base', htmlLabels: false,
      flowchart: { htmlLabels: false },
      themeVariables: {
        darkMode: true, background: '#1b1917', fontFamily: 'Hanken Grotesk, system-ui, sans-serif',
        primaryColor: '#3a2338', primaryBorderColor: '#b05fb0', primaryTextColor: '#ede7df',
        secondaryColor: '#2a2724', secondaryBorderColor: '#c9a227', tertiaryColor: '#211f1c',
        lineColor: '#c9a227', textColor: '#ede7df', noteBkgColor: '#2a2724', noteTextColor: '#ede7df',
        noteBorderColor: '#c9a227', actorBkg: '#3a2338', actorBorder: '#b05fb0', actorTextColor: '#ede7df',
        signalColor: '#c9a227', signalTextColor: '#ede7df', edgeLabelBackground: '#211f1c',
      },
    });
    return m;
  });
  return loaded;
}

/** A diagram keeps its natural size (from its viewBox) so the figure scrolls instead of shrinking it unreadably. */
function keepNaturalSize(svg: SVGElement | null): void {
  const box = svg?.getAttribute('viewBox')?.trim().split(/[\s,]+/).map(Number);
  if (!svg || !box || box.length !== 4 || !(box[2] > 0)) return;
  svg.setAttribute('width', String(Math.round(box[2])));
  svg.style.maxWidth = 'none';
  svg.style.width = `${Math.round(box[2])}px`;
}

let seq = 0;
/** Draw each mermaid block under `root` in place; a failure keeps the source and adds the note. */
export async function drawDiagrams(root: HTMLElement): Promise<void> {
  const blocks = Array.from(root.querySelectorAll<HTMLElement>('pre > code.language-mermaid'));
  if (!blocks.length) return;
  let m: Awaited<ReturnType<typeof mermaid>> | null = null;
  try { m = await mermaid(); } catch { /* every block keeps its source, with the note */ }
  for (const code of blocks) {
    const pre = code.parentElement!;
    try {
      if (!m) throw Error('mermaid did not load');
      const { svg } = await m.render(`study-diagram-${++seq}`, code.textContent ?? '');
      const figure = document.createElement('figure');
      figure.className = 'study-diagram';
      figure.setAttribute('role', 'img');
      figure.setAttribute('aria-label', 'Diagram');
      figure.innerHTML = DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true }, ADD_TAGS: ['style'] });
      keepNaturalSize(figure.querySelector('svg'));
      pre.replaceWith(figure);
    } catch {
      document.getElementById(`dstudy-diagram-${seq}`)?.remove(); // mermaid's leftover error box
      const note = document.createElement('p');
      note.className = 'study-diagram-note';
      note.textContent = DIAGRAM_FAILED;
      pre.before(note);
    }
  }
}
