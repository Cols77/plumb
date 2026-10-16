// Pure: finds the <svg> in a page, reads the skill's boxes, groups, arrows and labels out of it,
// and prepares it for the Svg element. No XML library: the skill's SVG is flat and regular.
import type { Box, Diagram, Edge, Group, Label, Point, Rect } from './model'

const NEAR = 24 // units within which an arrow end belongs to a box
const GROUP_TOP = 30 // units from a group's top in which its label sits
const SKIPPED = /<(defs|marker|pattern|style|script|title|desc)\b[\s\S]*?<\/\1\s*>/gi
const NUM = /[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g

export function extractSvg(text: string): string | null {
  // Every top-level <svg>...</svg> (nesting counted); the one with most rects wins, then the longest.
  const found: string[] = []
  const tag = /<(\/?)svg(?=[\s>/])[^>]*>/gi
  let depth = 0
  let start = -1
  for (const m of text.matchAll(tag)) {
    if (m[1]) {
      if (depth > 0 && --depth === 0) found.push(text.slice(start, m.index + m[0].length))
    } else if (!m[0].endsWith('/>')) {
      if (depth++ === 0) start = m.index
    } else if (depth === 0) found.push(m[0])
  }
  if (found.length === 0) return null
  const rects = (v: string) => (v.match(/<rect\b/gi) ?? []).length
  return found.reduce((a, b) => (rects(b) > rects(a) || (rects(b) === rects(a) && b.length > a.length) ? b : a))
}

type Inherit = { dash?: string; start?: string; end?: string }

/** Simple `.name{declarations}` rules of the page's <style> elements, by class name. */
function classRules(svg: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const st of svg.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style\s*>/gi))
    for (const r of st[1]!.matchAll(/\.([\w-]+)\s*\{([^}]*)\}/g)) out[r[1]!] = (out[r[1]!] ? out[r[1]!] + ';' : '') + r[2]
  return out
}

function attrs(tag: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const m of tag.matchAll(/([A-Za-z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) out[m[1]!.toLowerCase()] = m[2] ?? m[3] ?? ''
  return out
}

/** An attribute, or the same property in the style attribute. */
function prop(a: Record<string, string>, name: string): string | undefined {
  if (a[name] !== undefined) return a[name]
  const m = (a.style ?? '').match(new RegExp(`(?:^|;)\\s*${name}\\s*:\\s*([^;]+)`))
  return m ? m[1]!.trim() : undefined
}

/** A number attribute: the fallback when missing, null when a percentage or not a number. */
function num(v: string | undefined, fallback: number | null): number | null {
  if (v === undefined) return fallback
  if (v.includes('%')) return null
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : fallback
}

// The HTML named entities an HTML page may use in its SVG text; XML knows only the first five.
const XML_ENTITIES = new Set(['lt', 'gt', 'quot', 'apos', 'amp'])
const NAMED: Record<string, number> = {
  nbsp: 160, rarr: 8594, larr: 8592, uarr: 8593, darr: 8595, harr: 8596, middot: 183, mdash: 8212, ndash: 8211,
  bull: 8226, hellip: 8230, times: 215, copy: 169, reg: 174, trade: 8482, laquo: 171, raquo: 187, lsquo: 8216,
  rsquo: 8217, ldquo: 8220, rdquo: 8221, deg: 176, plusmn: 177, rArr: 8658, lArr: 8656, hArr: 8660, check: 10003,
}

function decode(s: string): string {
  return s
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => cp(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => cp(parseInt(d, 10)))
    .replace(/&([A-Za-z][A-Za-z0-9]*);/g, (m, n) => (n in NAMED ? cp(NAMED[n]!) : m))
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&')
}
function cp(n: number): string {
  try {
    return String.fromCodePoint(n)
  } catch {
    return ''
  }
}

type Mat = [number, number, number, number, number, number] // a b c d e f, as in SVG
const IDENT: Mat = [1, 0, 0, 1, 0, 0]
function mul(m: Mat, n: Mat): Mat {
  return [
    m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1],
    m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
    m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5],
  ]
}
/** translate, scale and matrix; rotate and skew are not read (the terminal drawing is then approximate). */
function parseTransform(v: string | undefined): Mat {
  let m = IDENT
  for (const t of (v ?? '').matchAll(/(translate|scale|matrix)\s*\(([^)]*)\)/gi)) {
    const n = (t[2]!.match(NUM) ?? []).map(Number)
    const k = t[1]!.toLowerCase()
    if (k === 'translate') m = mul(m, [1, 0, 0, 1, n[0] ?? 0, n[1] ?? 0])
    else if (k === 'scale') m = mul(m, [n[0] ?? 1, 0, 0, n[1] ?? n[0] ?? 1, 0, 0])
    else if (n.length === 6) m = mul(m, n as Mat)
  }
  return m
}
function pt(m: Mat, x: number, y: number): Point {
  return { x: m[0] * x + m[2] * y + m[4], y: m[1] * x + m[3] * y + m[5] }
}

function inside(r: Rect, p: Point): boolean {
  return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h
}
function holds(outer: Rect, r: Rect): boolean {
  return r.x >= outer.x && r.y >= outer.y && r.x + r.w <= outer.x + outer.w && r.y + r.h <= outer.y + outer.h
}
function dist(r: Rect, p: Point): number {
  return Math.hypot(Math.max(r.x - p.x, 0, p.x - (r.x + r.w)), Math.max(r.y - p.y, 0, p.y - (r.y + r.h)))
}
function smallest<T extends Rect>(list: T[]): T | undefined {
  let best: T | undefined
  for (const r of list) if (!best || r.w * r.h < best.w * best.h) best = r
  return best
}

/** The end point of each segment of a path's d, control points ignored. */
function pathPoints(d: string): Point[] {
  const pts: Point[] = []
  const arity: Record<string, number> = { m: 2, l: 2, h: 1, v: 1, c: 6, s: 4, q: 4, t: 2, a: 7, z: 0 }
  let cur: Point = { x: 0, y: 0 }
  let start: Point = cur
  for (const seg of d.matchAll(/([MmLlHhVvCcSsQqTtAaZz])([^A-Za-z]*)/g)) {
    const cmd = seg[1]
    const n = arity[cmd!.toLowerCase()!]
    const args = (seg[2]!.match(NUM) ?? []).map(Number)
    const rel = cmd !== cmd!.toUpperCase()!
    const up = cmd!.toUpperCase()!
    if (up === 'Z') {
      cur = start
      pts.push(cur)
      continue
    }
    for (let i = 0; i + n! <= args.length; i += n!) {
      const a = args.slice(i, i + n!)
      const ox = rel ? cur.x : 0
      const oy = rel ? cur.y : 0
      if (up === 'H') cur = { x: a[0]! + ox, y: cur.y }
      else if (up === 'V') cur = { x: cur.x, y: a[0]! + oy }
      else cur = { x: a[n! - 2]! + ox, y: a[n! - 1]! + oy }
      if (up === 'M' && i === 0) start = cur
      pts.push(cur)
    }
  }
  return pts
}

function dedupe(pts: Point[]): Point[] {
  return pts.filter((p, i) => i === 0 || p.x !== pts[i - 1]!.x || p.y !== pts[i - 1]!.y)
}

export function parseSvg(svg: string): Diagram {
  const css = classRules(svg)
  const body = svg.replace(/<!--[\s\S]*?-->/g, '').replace(SKIPPED, '').replace(/<text\b[^>]*\/>/gi, '')
  const root = attrs(body.match(/<svg\b[^>]*>/i)?.[0] ?? '')

  const rects: (Rect & { dashed: boolean })[] = []
  const texts: { p: Point; text: string; anchor: Label['anchor']; badge: boolean }[] = []
  const lines: { points: Point[]; start: boolean; end: boolean }[] = []

  const token = /<text\b([^>]*)>([\s\S]*?)<\/text\s*>|<(rect|line|polyline|path)\b([^>]*?)\/?>|<g\b([^>]*?)(\/?)>|<\/g\s*>/gi
  const stack: Mat[] = [IDENT]
  const inherited: Inherit[] = [{}]
  const withClass = (a: Record<string, string>) => {
    const rules = (a.class ?? '').split(/\s+/).map((c) => css[c]).filter(Boolean).join(';')
    return rules ? { ...a, style: rules + ';' + (a.style ?? '') } : a
  }
  for (const m of body.matchAll(token)) {
    if (/^<\/g/i.test(m[0])) {
      if (stack.length > 1) {
        stack.pop()
        inherited.pop()
      }
      continue
    }
    if (/^<g\b/i.test(m[0])) {
      if (!m[6]) {
        const g = withClass(attrs(m[5]!))
        const up = inherited[inherited.length - 1]
        stack.push(mul(stack[stack.length - 1]!, parseTransform(g.transform)))
        inherited.push({
          dash: prop(g, 'stroke-dasharray') ?? up!.dash!,
          start: prop(g, 'marker-start') ?? up!.start!,
          end: prop(g, 'marker-end') ?? up!.end!,
        })
      }
      continue
    }
    const top = stack[stack.length - 1]
    if (m[3] === undefined) {
      const a = attrs(m[1]!)
      const fs = num(prop(a, 'font-size'), 12) ?? 12
      const anchor = prop(a, 'text-anchor')
      const mat = mul(top!, parseTransform(a.transform))
      // A <tspan> that sets x, y or dy starts a new line; other tags are dropped.
      let seg = { x: num(a.x, 0) ?? 0, y: num(a.y, 0) ?? 0, text: '' }
      const segs = [seg]
      for (const part of m[2]!.split(/(<tspan[^>]*>)/i)) {
        if (/^<tspan/i.test(part)) {
          const t = attrs(part)
          if (t.x !== undefined || t.y !== undefined || t.dy !== undefined) {
            const dy = t.dy === undefined ? 0 : (num(t.dy, 0) ?? 0) * (/em/.test(t.dy) ? fs : 1)
            seg = { x: num(t.x, seg.x) ?? seg.x, y: (num(t.y, seg.y) ?? seg.y) + dy, text: '' }
            segs.push(seg)
          }
        } else seg.text += decode(part.replace(/<[^>]*>/g, ''))
      }
      for (const g of segs) {
        const text = g.text.replace(/\s+/g, ' ').trim()
        if (text) texts.push({ p: pt(mat, g.x, g.y - 0.35 * fs), text, anchor: anchor === 'middle' || anchor === 'end' ? anchor : 'start', badge: false })
      }
      continue
    }
    const a = withClass(attrs(m[4]!))
    const inh = inherited[inherited.length - 1]
    const kind = m[3].toLowerCase()
    const mat = mul(top!, parseTransform(a.transform))
    if (kind === 'rect') {
      const x = num(a.x, 0), y = num(a.y, 0), w = num(a.width, null), h = num(a.height, null)
      if (x === null || y === null || w === null || h === null || w <= 0 || h <= 0) continue
      const p0 = pt(mat, x, y)
      const p1 = pt(mat, x + w, y + h)
      const rx = Math.min(p0.x, p1.x), ry = Math.min(p0.y, p1.y)
      const rw = Math.abs(p1.x - p0.x), rh = Math.abs(p1.y - p0.y)
      if (rw <= 0 || rh <= 0) continue
      const dash = prop(a, 'stroke-dasharray') ?? inh!.dash!
      const dashed = dash !== undefined && dash !== 'none' && !/^[0\s,]*$/.test(dash)
      const twin = rects.find((r) => r.x === rx && r.y === ry && r.w === rw && r.h === rh)
      if (twin) twin.dashed ||= dashed
      else rects.push({ x: rx, y: ry, w: rw, h: rh, dashed })
      continue
    }
    let points: Point[] = []
    if (kind === 'line') {
      points = [
        { x: num(a.x1, 0) ?? 0, y: num(a.y1, 0) ?? 0 },
        { x: num(a.x2, 0) ?? 0, y: num(a.y2, 0) ?? 0 },
      ]
    } else if (kind === 'polyline') {
      const n = (a.points ?? '').match(NUM)?.map(Number) ?? []
      for (let i = 0; i + 1 < n.length; i += 2) points.push({ x: n[i]!, y: n[i + 1]! })
    } else points = pathPoints(a.d ?? '')
    points = dedupe(points.map((p) => pt(mat, p.x, p.y)))
    if (points.length < 2) continue
    const marked = (v: string | undefined) => v !== undefined && v !== 'none' && v !== ''
    lines.push({ points, end: marked(prop(a, 'marker-end') ?? inh!.end!), start: marked(prop(a, 'marker-start') ?? inh!.start!) })
  }

  // Dashed rects are groups. A solid rect is a group when it encloses a labelled rect that is a quarter of it
  // or more, or when its own text sits at the top, not centred; labelled rects that are all small and inside
  // a box whose text is centred are badges (pills, version tags) of that box, however many there are.
  const vbox = viewBoxOf(root, rects)
  // A small labelled rect that an arrow runs through, with no arrow ending at it, is the background of that
  // arrow's label, not a component: its text stays a free label.
  const ends0 = lines.flatMap((l) => [l.points[0], l.points[l.points.length - 1]])
  const crosses = (r: Rect) =>
    lines.some((l) =>
      l.points.some((a, i) => {
        const b = l.points[i + 1]
        if (!b) return false
        const n = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 2))
        for (let k = 0; k <= n; k++) {
          const q = { x: a.x + ((b.x - a.x) * k) / n, y: a.y + ((b.y - a.y) * k) / n }
          if (q.x > r.x + 1 && q.x < r.x + r.w - 1 && q.y > r.y + 1 && q.y < r.y + r.h - 1) return true
        }
        return false
      }))
  const isPill = (r: Rect) =>
    r.h <= 30 && texts.some((t) => inside(r, t.p)) && !rects.some((o) => o !== r && holds(r, o)) &&
    !ends0.some((p) => dist(r, p!) <= NEAR) && crosses(r)
  const solid = rects.filter((r) => !r.dashed && !isPill(r))
  const labelled = (r: Rect) => texts.some((t) => inside(r, t.p))
  const inner = (r: Rect) => solid.filter((o) => o !== r && holds(r, o) && labelled(o))
  const isGroup = (r: Rect) => {
    const i = inner(r)
    if (i.length === 0) return false
    if (i.some((o) => o.w * o.h * 4 >= r.w * r.h)) return true
    // a rect that covers most of the canvas, or holds a rect that arrows end at (away from its own border), is a container
    if (r.w * r.h * 2 >= vbox.w * vbox.h) return true
    const margin = { x: r.x + NEAR, y: r.y + NEAR, w: r.w - 2 * NEAR, h: r.h - 2 * NEAR }
    const ends = lines.flatMap((l) => [l.points[0], l.points[l.points.length - 1]]).filter((p) => inside(margin, p!))
    if (i.some((o) => ends.some((p) => dist(o, p!) <= NEAR))) return true
    return texts.some((t) => inside(r, t.p) && !i.some((o) => inside(o, t.p)) && t.anchor !== 'middle' && t.p.y - r.y <= GROUP_TOP)
  }
  const grouped = new Set(solid.filter(isGroup))
  const badges = solid.filter((r) => !grouped.has(r) && labelled(r) && solid.some((o) => o !== r && !grouped.has(o) && holds(o, r)))
  const boxes: Box[] = solid.filter((r) => !grouped.has(r) && !badges.includes(r)).map((r) => ({ x: r.x, y: r.y, w: r.w, h: r.h, lines: [] }))
  const groups: Group[] = rects.filter((r) => r.dashed || grouped.has(r)).map((r) => ({ x: r.x, y: r.y, w: r.w, h: r.h, label: null }))
  for (const t of texts) t.badge = badges.some((r) => inside(r, t.p))

  const labels: Label[] = []
  const placed = boxes.map(() => [] as { y: number; text: string; badge: boolean }[])
  for (const t of texts) {
    const b = smallest(boxes.filter((c) => inside(c, t.p)))
    if (b) {
      placed[boxes.indexOf(b)]!.push({ y: t.p.y, text: t.text, badge: t.badge })
      continue
    }
    const g = smallest(groups.filter((c) => c.label === null && inside(c, t.p) && t.p.y - c.y <= GROUP_TOP))
    if (g) g.label = t.text
    else labels.push({ x: t.p.x, y: t.p.y, text: t.text, anchor: t.anchor })
  }
  boxes.forEach((b, i) => {
    b.lines = placed[i]!.sort((p, q) => Number(p.badge) - Number(q.badge) || p.y - q.y).map((p) => p.text)
  })

  const keptBoxes = boxes.filter((b) => b.lines.length > 0)
  const keptGroups = groups.filter((g) => g.label !== null || keptBoxes.some((b) => holds(g, b)))

  const nearest = (p: Point): number | null => {
    let best: number | null = null
    let bd = Infinity
    keptBoxes.forEach((b, i) => {
      const d = dist(b, p)
      if (d <= NEAR && d < bd) {
        bd = d
        best = i
      }
    })
    return best
  }
  const edges: Edge[] = []
  for (const l of lines) {
    const from = nearest(l.points[0]!)
    const to = nearest(l.points[l.points.length - 1]!)
    const head = l.start && l.end ? 'both' : l.end ? 'end' : l.start ? 'start' : 'none'
    if (from !== null && from === to) continue
    if (head === 'none' && (from === null || to === null || from === to)) continue
    edges.push({ points: l.points, from, to, head })
  }

  return { viewBox: vbox, boxes: keptBoxes, groups: keptGroups, edges, labels }
}

function viewBoxOf(root: Record<string, string>, rects: Rect[]): Rect {
  const v = (root.viewbox ?? '').match(NUM)?.map(Number)
  if (v && v.length === 4 && v[2]! > 0 && v[3]! > 0) return { x: v[0]!, y: v[1]!, w: v[2]!, h: v[3]! }
  const w = num(root.width, null)
  const h = num(root.height, null)
  if (w && h && w > 0 && h > 0) return { x: 0, y: 0, w, h }
  if (rects.length === 0) return { x: 0, y: 0, w: 100, h: 100 }
  const x = Math.min(...rects.map((r) => r.x))
  const y = Math.min(...rects.map((r) => r.y))
  return { x, y, w: Math.max(...rects.map((r) => r.x + r.w)) - x, h: Math.max(...rects.map((r) => r.y + r.h)) - y }
}

/** The SVG as is, plus what it loses when it leaves its page: xmlns, a size, the page's dark background. */
export function forSvgElement(svg: string, fromHtml: boolean): string {
  // An SVG image is XML: an HTML named entity becomes its numeric reference, an unknown one literal text.
  svg = svg.replace(/&([A-Za-z][A-Za-z0-9]*);/g, (m, n) => (XML_ENTITIES.has(n) ? m : n in NAMED ? `&#${NAMED[n]};` : `&amp;${n};`))
  const tag = svg.match(/<svg\b[^>]*>/i)?.[0]
  if (!tag) return svg
  const a = attrs(tag)
  let add = ''
  if (a.xmlns === undefined) add += ' xmlns="http://www.w3.org/2000/svg"'
  if (a.width === undefined && a.height === undefined && a.viewbox !== undefined) {
    const v = a.viewbox.match(NUM)?.map(Number)
    if (v && v.length === 4 && v[2]! > 0 && v[3]! > 0) add += ` width="${v[2]}" height="${v[3]}"`
  }
  if (fromHtml && a.style === undefined) add += ' style="background:#020617"'
  // The page's CSS gave the labels their monospace font; the SVG leaves the page without it.
  if (fromHtml && a['font-family'] === undefined) add += ` font-family="'JetBrains Mono', ui-monospace, monospace"`
  if (!add) return svg
  const close = tag.endsWith('/>') ? tag.length - 2 : tag.length - 1
  const next = tag.slice(0, close).replace(/\s+$/, '') + add + tag.slice(close)
  return svg.replace(tag, () => next)
}

export function describe(d: Diagram): string {
  const names = d.boxes.map((b) => b.lines[0])
  const list = names.slice(0, 12).join(', ') + (names.length > 12 ? ', ...' : '')
  const boxes = `${names.length} ${names.length === 1 ? 'box' : 'boxes'}${names.length ? ` (${list})` : ''}`
  return `Architecture diagram: ${boxes}, ${d.edges.length} ${d.edges.length === 1 ? 'arrow' : 'arrows'}.`
}
