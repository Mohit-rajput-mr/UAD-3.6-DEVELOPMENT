// Geometry of the sketch -- the same arithmetic as engine/uad/sketch.py, so the
// area the panel shows while drawing is the area the report receives.
// Coordinates are feet, y downwards. A wall's bulge b (DXF convention: tan of a
// quarter of the arc's angle) puts the arc's middle at
//   chord middle + (b / 2) * (-dy, dx)
import type { Area, Pt } from "./model";

export interface Seg { chord: number; length: number; seg: number }

export function seg(p: Pt, q: Pt): Seg {
  const dx = q.x - p.x, dy = q.y - p.y;
  const c = Math.hypot(dx, dy);
  const b = p.b || 0;
  if (!b || !c) return { chord: c, length: c, seg: 0 };
  const theta = 4 * Math.atan(Math.abs(b));
  const r = c / (2 * Math.sin(theta / 2));
  const s = (r * r) / 2 * (theta - Math.sin(theta));
  return { chord: c, length: r * theta, seg: Math.sign(b) * s };
}

export function polygonArea(points: Pt[]): number {
  const n = points.length;
  if (n < 2) return 0;
  let s = 0, arcs = 0;
  for (let i = 0; i < n; i++) {
    const p = points[i], q = points[(i + 1) % n];
    s += p.x * q.y - q.x * p.y;
    arcs += seg(p, q).seg;
  }
  return Math.abs(s / 2 - arcs);
}

export function wallLengths(points: Pt[]): number[] {
  return points.map((p, i) => seg(p, points[(i + 1) % points.length]).length);
}

export function centroid(points: Pt[]): { x: number; y: number } {
  const n = points.length || 1;
  return { x: points.reduce((t, p) => t + p.x, 0) / n, y: points.reduce((t, p) => t + p.y, 0) / n };
}

export function contains(points: Pt[], x: number, y: number): boolean {
  let inside = false;
  for (let i = 0, n = points.length; i < n; i++) {
    const a = points[i], b = points[(i + 1) % n];
    if ((a.y > y) !== (b.y > y)) {
      const xi = a.x + ((y - a.y) * (b.x - a.x)) / ((b.y - a.y) || 1e-12);
      if (x < xi) inside = !inside;
    }
  }
  return inside;
}

/** The arc's middle point (or the chord's middle for a straight wall). */
export function arcMiddle(p: Pt, q: Pt): { x: number; y: number } {
  const b = p.b || 0;
  return { x: (p.x + q.x) / 2 + (b / 2) * -(q.y - p.y), y: (p.y + q.y) / 2 + (b / 2) * (q.x - p.x) };
}

/** Points along a wall, for drawing it (an arc becomes a polyline). */
export function wallPath(p: Pt, q: Pt, steps = 24): { x: number; y: number }[] {
  const b = p.b || 0;
  if (!b) return [{ x: p.x, y: p.y }, { x: q.x, y: q.y }];
  const dx = q.x - p.x, dy = q.y - p.y, c = Math.hypot(dx, dy);
  const theta = 4 * Math.atan(Math.abs(b));
  const r = c / (2 * Math.sin(theta / 2));
  const m = arcMiddle(p, q);
  // the centre lies on the chord's normal, opposite the arc's middle
  const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2;
  const sag = Math.hypot(m.x - mx, m.y - my);
  const nx = (m.x - mx) / (sag || 1), ny = (m.y - my) / (sag || 1);
  const cx = m.x - nx * r, cy = m.y - ny * r;
  const a0 = Math.atan2(p.y - cy, p.x - cx), a1 = Math.atan2(q.y - cy, q.x - cx);
  const am = Math.atan2(m.y - cy, m.x - cx);
  // go from a0 to a1 the way that passes through the middle
  let sweep = a1 - a0;
  const norm = (a: number) => { while (a <= -Math.PI) a += 2 * Math.PI; while (a > Math.PI) a -= 2 * Math.PI; return a; };
  sweep = norm(sweep);
  const mid = norm(am - a0);
  if (Math.sign(mid) !== Math.sign(sweep) || Math.abs(mid) > Math.abs(sweep)) sweep = sweep > 0 ? sweep - 2 * Math.PI : sweep + 2 * Math.PI;
  const out = [];
  for (let i = 0; i <= steps; i++) {
    const a = a0 + (sweep * i) / steps;
    out.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  }
  return out;
}

export function outline(points: Pt[]): number[] {
  const flat: number[] = [];
  points.forEach((p, i) => {
    const path = wallPath(p, points[(i + 1) % points.length]);
    path.slice(0, -1).forEach((v) => flat.push(v.x, v.y));
  });
  return flat;
}

export function bounds(points: { x: number; y: number }[]) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of points) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); }
  return { x0, y0, x1, y1 };
}

export function areaBounds(areas: Area[]) {
  const pts: { x: number; y: number }[] = [];
  for (const a of areas) for (let i = 0; i < a.points.length; i++) pts.push(...wallPath(a.points[i], a.points[(i + 1) % a.points.length], 8));
  return bounds(pts);
}

// ------------------------------------------------------------- measurement
export type Measure = "standard" | "decimal";

/** 39.79 -> 39' 9 ½" (standard) or 39.79' (decimal). */
export function fmtLen(ft: number, measure: Measure, precision: "feet" | "inches" = "inches"): string {
  const neg = ft < 0; ft = Math.abs(ft);
  if (measure === "decimal") return `${neg ? "-" : ""}${ft.toFixed(2).replace(/\.?0+$/, "")}'`;
  if (precision === "feet") return `${neg ? "-" : ""}${Math.round(ft)}'`;
  let whole = Math.floor(ft), inches = (ft - whole) * 12;
  let quarters = Math.round(inches * 4);            // to the quarter inch
  if (quarters === 48) { whole += 1; quarters = 0; }
  const ins = Math.floor(quarters / 4), frac = quarters % 4;
  const f = ["", " ¼", " ½", " ¾"][frac];
  if (!ins && !frac) return `${neg ? "-" : ""}${whole}'`;
  return `${neg ? "-" : ""}${whole}' ${ins}${f}"`;
}

export function fmtArea(a: number): string {
  return `${Math.round(a).toLocaleString("en-US")} ft²`;
}

/** "12" "12.5" "12'6" "12' 6\"" "12-6" -> feet. */
export function parseLen(s: string): number | null {
  s = s.trim();
  let m = /^(-?\d+(?:\.\d+)?)\s*(?:'|ft)?\s*(?:-|\s)?\s*(\d+(?:\.\d+)?)\s*(?:"|in)?$/i.exec(s);
  if (m && /['\-\s]|ft/i.test(s)) return parseFloat(m[1]) + parseFloat(m[2]) / 12;
  m = /^(-?\d+(?:\.\d+)?)\s*(?:'|ft)?$/i.exec(s);
  if (m) return parseFloat(m[1]);
  m = /^(\d+(?:\.\d+)?)\s*(?:"|in)$/i.exec(s);
  if (m) return parseFloat(m[1]) / 12;
  return null;
}

/** Keyboard vectors: "R20 U15 L20 D15", "R20U15", "UR10" (45°), "A30 12"
 *  (angle from the right, counter-clockwise, then length), "C" closes the shape.
 *  Lengths in feet or feet-inches (12'6", 12-6). Returns the moves in feet. */
export function parseVectors(text: string): { moves: { dx: number; dy: number }[]; close: boolean; error?: string } {
  const moves: { dx: number; dy: number }[] = [];
  let close = false;
  const norm = text.toUpperCase().replace(/,/g, " ")
    .replace(/([UDLRAC])(?=[-\d.])/g, "$1 ")
    .replace(/(\d|["'])(?=[UDLRAC])/g, "$1 ");
  const toks = norm.split(/\s+/).filter(Boolean);
  const length = (i: number): [number | null, number] => {
    let t = toks[i] || "";
    let used = 1;
    if (toks[i + 1] && /^\d+(\.\d+)?"$/.test(toks[i + 1]) && /'$/.test(t)) { t += toks[i + 1]; used = 2; }
    return [parseLen(t), used];
  };
  for (let i = 0; i < toks.length;) {
    const t = toks[i];
    if (t === "C") { close = true; i++; continue; }
    if (t === "A") {
      const ang = parseFloat(toks[i + 1]);
      const [len, used] = length(i + 2);
      if (!isFinite(ang) || len == null) return { moves, close, error: `Cannot read the angle move at "${toks.slice(i, i + 3).join(" ")}"` };
      const a = (ang * Math.PI) / 180;
      moves.push({ dx: Math.cos(a) * len, dy: -Math.sin(a) * len });    // 0 = right, 90 = up
      i += 2 + used;
      continue;
    }
    if (/^[UDLR]{1,2}$/.test(t)) {
      const [len, used] = length(i + 1);
      if (len == null) return { moves, close, error: `"${t}" needs a length, e.g. ${t}12 or ${t}12'6"` };
      let dx = 0, dy = 0;
      for (const ch of t) { if (ch === "R") dx += 1; if (ch === "L") dx -= 1; if (ch === "U") dy -= 1; if (ch === "D") dy += 1; }
      const k = t.length === 2 ? len / Math.SQRT2 : len;
      moves.push({ dx: dx * k, dy: dy * k });
      i += 1 + used;
      continue;
    }
    return { moves, close, error: `Cannot read "${t}": use R, L, U, D (or UR, DL ...), A<angle> <length>, C` };
  }
  return { moves, close };
}

// ---------------------------------------------------------------- snapping
export function snapTo(v: number, step: number): number { return step ? Math.round(v / step) * step : v; }

/** Snap the next point's direction from `from` to the angle step (degrees). */
export function snapAngle(from: { x: number; y: number }, to: { x: number; y: number }, stepDeg: number) {
  if (!stepDeg) return to;
  const dx = to.x - from.x, dy = to.y - from.y, len = Math.hypot(dx, dy);
  if (!len) return to;
  const step = (stepDeg * Math.PI) / 180;
  const a = Math.round(Math.atan2(dy, dx) / step) * step;
  return { x: from.x + Math.cos(a) * len, y: from.y + Math.sin(a) * len };
}
