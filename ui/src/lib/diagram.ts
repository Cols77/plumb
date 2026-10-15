import DOMPurify from 'dompurify';
import { extractSvg, forSvgElement, parseSvg, describe } from './diagram-mod/svg';

/** Preparation preserves the drawing; sanitization is a separate browser boundary. */
export function prepareDiagram(source: string): {svg: string; description: string} {
  if (source.length > 131072 || new TextEncoder().encode(source).length > 524288) throw Error('Diagram is too large to display.');
  const extracted = extractSvg(source);
  if (!extracted) throw Error('No SVG drawing was found in this source.');
  const prepared = forSvgElement(extracted, /<html\b|<!doctype html/i.test(source));
  const parsed = new DOMParser().parseFromString(prepared, 'image/svg+xml');
  if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') throw Error('The SVG drawing is malformed.');
  const clean = DOMPurify.sanitize(parsed.documentElement, {
    USE_PROFILES: {svg: true, svgFilters: true},
    FORBID_TAGS: ['script', 'foreignObject', 'style', 'animate', 'animateMotion', 'animateTransform', 'set', 'image', 'feImage'],
    FORBID_ATTR: ['xml:base'],
  });
  const doc = new DOMParser().parseFromString(clean, 'image/svg+xml');
  for (const element of doc.querySelectorAll('*')) {
    for (const attr of Array.from(element.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value.trim();
      if (name.startsWith('on') || name === 'src' || (name.endsWith('href') && !/^#[\w:.-]+$/.test(value)) ||
          ((name === 'style' || /url\s*\(/i.test(value)) && (/\\|@|expression\s*\(/i.test(value) || /url\s*\((?!\s*['"]?#[\w:.-]+['"]?\s*\))/i.test(value)))) element.removeAttribute(attr.name);
    }
  }
  const svg = new XMLSerializer().serializeToString(doc.documentElement);
  // The upstream geometric parser assumes small diagrams. Bound its work on untrusted input.
  const numbers = svg.match(/[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi) ?? [];
  const relativePaths = Array.from(doc.querySelectorAll('path')).some(path => /[mlhvcsqta]/.test(path.getAttribute('d') ?? ''));
  const geometric = !relativePaths && !doc.querySelector('[transform]') && numbers.length <= 256 && doc.querySelectorAll('rect,path,line,polyline').length <= 40 && numbers.every(n => Math.abs(Number(n)) <= 2048);
  const labels = Array.from(doc.querySelectorAll('text')).map(node => node.textContent).filter(Boolean).join(', ');
  return { svg, description: geometric ? describe(parseSvg(svg)) : `Diagram: ${labels.slice(0, 1000) || 'see source for details'}.` };
}
