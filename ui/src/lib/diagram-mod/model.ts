// The contract between svg.ts (parses the skill's SVG) and grid.ts (draws it as text).
// Every coordinate is in SVG user units in viewBox space.

export type Point = { x: number; y: number }
export type Rect = { x: number; y: number; w: number; h: number }
/** A component: a solid rect and the texts inside it, top to bottom (first = its name). */
export type Box = Rect & { lines: string[] }
/** A dashed rect (security group, region) or a rect that encloses boxes; its label is the text at its top-left. */
export type Group = Rect & { label: string | null }
/** A connection: its points in SVG order (>= 2), the boxes its ends touch (indices into boxes, null when none is near), where its arrowheads are. */
export type Edge = { points: Point[]; from: number | null; to: number | null; head: 'end' | 'start' | 'both' | 'none' }
/** A text in no box and no group label: an edge label, a legend entry. */
export type Label = Point & { text: string; anchor: 'start' | 'middle' | 'end' }
export type Diagram = { viewBox: Rect; boxes: Box[]; groups: Group[]; edges: Edge[]; labels: Label[] }
/** A box as drawn: its cell rectangle, border included. */
export type Placed = { col: number; row: number; cols: number; rows: number }
/** What grid.ts draws: rows (each <= columns code points, trailing spaces trimmed), boxes[i] placed for diagram.boxes[i], groups[i] placed for diagram.groups[i]; cutNames = boxes whose name could not be shown whole; each arrowhead drawn with the edge it ends; or problem, a plain sentence, and rows = []. */
export type Drawing = { rows: string[]; boxes: Placed[]; groups: Placed[]; cutNames: number; heads: { col: number; row: number; edge: number }[]; problem: string | null }
