// The area table, live while drawing: the same rules as engine/uad/sketch.py
// table() (which the report receives on Save to report).
import type { Area, Page, SketchDoc } from "./model";
import { BELOW, NOT_LIVING } from "./model";
import { centroid, contains, polygonArea } from "./geometry";

export interface UnitRow {
  unit: number; standardAbove: number; nonstandardAbove: number; unfinishedAbove: number;
  standardBelow: number; nonstandardBelow: number; unfinishedBelow: number;
  levels: Record<string, { finished: number; unfinished: number }>;
  bedrooms: number; fullBaths: number; halfBaths: number;
}

const ROOMS: [string[], string][] = [
  [["half bath", "half-bath", "powder", "1/2 bath", "½ bath"], "HalfBathroom"],
  [["bath", "bathroom"], "FullBathroom"], [["bed", "bedroom", "br"], "Bedroom"],
];
export function roomType(text: string): string | null {
  const t = " " + text.toLowerCase().replace(/\./g, " ").split(/\s+/).join(" ") + " ";
  for (const [words, kind] of ROOMS) for (const w of words) if (t.includes(` ${w} `) || t.trim().startsWith(w + " ") || t.trim() === w) return kind;
  return null;
}

function host(a: Area, areas: Area[]): Area | null {
  const c = centroid(a.points);
  let best: Area | null = null;
  for (const h of areas) {
    if (h === a || h.subtract || h.floor !== a.floor) continue;
    if (contains(h.points, c.x, c.y) && (!best || polygonArea(h.points) < polygonArea(best.points))) best = h;
  }
  return best;
}

export function unitTable(doc: SketchDoc): UnitRow[] {
  const units = new Map<number, UnitRow>();
  const row = (n: number) => {
    if (!units.has(n)) units.set(n, { unit: n, standardAbove: 0, nonstandardAbove: 0, unfinishedAbove: 0, standardBelow: 0,
      nonstandardBelow: 0, unfinishedBelow: 0, levels: {}, bedrooms: 0, fullBaths: 0, halfBaths: 0 });
    return units.get(n)!;
  };
  for (const page of doc.pages) {
    const areas = page.areas.filter((a) => a.points.length >= 3);
    for (const a of areas) {
      let v = polygonArea(a.points), f: Area = a;
      if (a.subtract) { f = host(a, areas) || a; v = -v; }
      if (NOT_LIVING.includes(f.kind) && !a.subtract) {
        const h = host(a, areas);
        if (!h || NOT_LIVING.includes(h.kind)) continue;
        f = h; v = -v;
      } else if (NOT_LIVING.includes(f.kind)) continue;
      const u = row(f.unit || 1), below = BELOW.includes(a.floor);
      const lv = (u.levels[a.floor] ||= { finished: 0, unfinished: 0 });
      if (f.finished) {
        lv.finished += v;
        if (below) { if (f.nonstandard) u.nonstandardBelow += v; else u.standardBelow += v; }
        else if (f.nonstandard || !f.gla) u.nonstandardAbove += v; else u.standardAbove += v;
      } else { lv.unfinished += v; if (below) u.unfinishedBelow += v; else u.unfinishedAbove += v; }
    }
    countRooms(page, areas, row);
  }
  return [...units.values()].sort((a, b) => a.unit - b.unit);
}

function countRooms(page: Page, areas: Area[], row: (n: number) => UnitRow) {
  const living = areas.filter((a) => !a.subtract && !NOT_LIVING.includes(a.kind));
  for (const l of page.labels) {
    const kind = roomType(l.text); if (!kind) continue;
    const hosts = living.filter((a) => contains(a.points, l.x, l.y));
    if (!hosts.length) continue;
    const h = hosts.reduce((m, a) => (polygonArea(a.points) < polygonArea(m.points) ? a : m));
    const u = row(h.unit || 1);
    if (kind === "Bedroom") u.bedrooms++; else if (kind === "FullBathroom") u.fullBaths++; else u.halfBaths++;
  }
}
