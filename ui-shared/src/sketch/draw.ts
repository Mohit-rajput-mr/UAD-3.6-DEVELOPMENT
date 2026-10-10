// Drawing shared by the canvas and the report output: symbols, and the sketch
// page as the report prints it (owner's reference 08: every floor on one page,
// its title and area beneath it, a dimension on every wall, room labels inside,
// clean black lines, fitted to the page).
import type { Page, Pt, Area } from "./model";
import { ABOVE, BELOW, FLOOR_TITLE, NOT_LIVING, SYMBOLS } from "./model";
import { areaBounds, centroid, contains, fmtArea, fmtLen, polygonArea, seg, wallPath, arcMiddle } from "./geometry";
import type { Measure } from "./geometry";

type C = CanvasRenderingContext2D;

/** A symbol in its own box, w x h feet, top-left at 0,0 (already transformed). */
export function drawSymbol(c: C, type: string, w: number, h: number) {
  c.beginPath();
  const line = (pts: number[][]) => { c.moveTo(pts[0][0], pts[0][1]); for (const p of pts.slice(1)) c.lineTo(p[0], p[1]); };
  const circle = (x: number, y: number, r: number) => { c.moveTo(x + r, y); c.arc(x, y, r, 0, Math.PI * 2); };
  switch (type) {
    case "refrigerator": c.rect(0, 0, w, h); line([[0, h * 0.35], [w, h * 0.35]]); line([[w * 0.85, h * 0.1], [w * 0.85, h * 0.25]]); break;
    case "stove": c.rect(0, 0, w, h); for (const [x, y] of [[0.3, 0.3], [0.7, 0.3], [0.3, 0.7], [0.7, 0.7]]) circle(w * x, h * y, Math.min(w, h) * 0.13); break;
    case "washer": c.rect(0, 0, w, h); circle(w / 2, h / 2, Math.min(w, h) * 0.32); break;
    case "dryer": c.rect(0, 0, w, h); circle(w / 2, h / 2, Math.min(w, h) * 0.32); line([[w * 0.3, h * 0.5], [w * 0.7, h * 0.5]]); break;
    case "washerdryer": c.rect(0, 0, w, h); line([[0, h / 2], [w, h / 2]]); circle(w / 2, h / 4, Math.min(w, h / 2) * 0.32); circle(w / 2, (3 * h) / 4, Math.min(w, h / 2) * 0.32); break;
    case "waterheater": circle(w / 2, h / 2, Math.min(w, h) / 2); line([[w * 0.3, h * 0.5], [w * 0.7, h * 0.5]]); break;
    case "furnace": c.rect(0, 0, w, h); line([[0, 0], [w, h]]); line([[w, 0], [0, h]]); break;
    case "freezer": c.rect(0, 0, w, h); line([[w * 0.15, h * 0.2], [w * 0.85, h * 0.2]]); break;
    case "grill": c.rect(0, 0, w, h); for (let i = 1; i < 5; i++) line([[w * i / 5, h * 0.15], [w * i / 5, h * 0.85]]); break;
    case "tv": c.rect(0, 0, w, h); break;
    case "door": line([[0, h], [0, 0]]); c.moveTo(0, 0); c.arc(0, h, h, -Math.PI / 2, 0); break;
    case "slider": c.rect(0, 0, w / 2 + w * 0.05, h / 2); c.rect(w / 2 - w * 0.05, h / 2, w / 2 + w * 0.05, h / 2); break;
    case "window": c.rect(0, 0, w, h); line([[0, h / 2], [w, h / 2]]); break;
    case "stairs": c.rect(0, 0, w, h); for (let i = 1; i < 12; i++) line([[0, h * i / 12], [w, h * i / 12]]); line([[w / 2, h * 0.9], [w / 2, h * 0.1]]); line([[w * 0.35, h * 0.22], [w / 2, h * 0.1], [w * 0.65, h * 0.22]]); break;
    case "tub": c.rect(0, 0, w, h); c.moveTo(w * 0.12 + h * 0.35, h * 0.15); c.ellipse(w / 2, h / 2, w * 0.38, h * 0.33, 0, 0, Math.PI * 2); break;
    case "shower": c.rect(0, 0, w, h); line([[0, 0], [w, h]]); line([[w, 0], [0, h]]); circle(w / 2, h / 2, Math.min(w, h) * 0.08); break;
    case "toilet": c.rect(w * 0.1, 0, w * 0.8, h * 0.3); c.moveTo(w * 0.9, h * 0.62); c.ellipse(w / 2, h * 0.62, w * 0.4, h * 0.34, 0, 0, Math.PI * 2); break;
    case "sink": c.rect(0, 0, w, h); c.moveTo(w * 0.85, h / 2); c.ellipse(w / 2, h / 2, w * 0.35, h * 0.3, 0, 0, Math.PI * 2); break;
    case "fireplace": c.rect(0, 0, w, h); c.rect(w * 0.2, h * 0.35, w * 0.6, h * 0.65); break;
    default: c.rect(0, 0, w, h);
  }
  c.stroke();
}

export function floorOrder(f: string): number {
  const a = ABOVE.indexOf(f); if (a >= 0) return a;
  const b = BELOW.indexOf(f); return b >= 0 ? 100 + b : 50;
}

/** The living area a floor's title states: finished living shapes, deductions taken. */
export function floorArea(areas: Area[]): number {
  let total = 0;
  for (const a of areas) {
    const living = !NOT_LIVING.includes(a.kind);
    const v = polygonArea(a.points);
    if (a.subtract) total -= v;
    else if (living && a.finished) total += v;
    else if (!living) {
      // a garage drawn inside a living outline comes off it
      const c = centroid(a.points);
      if (areas.some((h) => h !== a && !h.subtract && !NOT_LIVING.includes(h.kind) && contains(h.points, c.x, c.y))) total -= v;
    }
  }
  return total;
}

/** A wall's length written beside it, outside the shape, along the wall. */
function wallLabel(c: C, p: Pt, q: Pt, inside: { x: number; y: number }, text: string, px: number, off: number) {
  const m = arcMiddle(p, q);
  let nx = -(q.y - p.y), ny = q.x - p.x;
  const len = Math.hypot(nx, ny) || 1; nx /= len; ny /= len;
  // point the normal away from the shape's centre
  if ((m.x - inside.x) * nx + (m.y - inside.y) * ny < 0) { nx = -nx; ny = -ny; }
  let ang = Math.atan2(q.y - p.y, q.x - p.x);
  if (ang > Math.PI / 2) ang -= Math.PI; if (ang < -Math.PI / 2) ang += Math.PI;
  c.save();
  c.translate((m.x + nx * off) * px, (m.y + ny * off) * px);
  c.rotate(ang);
  c.fillText(text, 0, 0);
  c.restore();
}

export interface OutputOpts { measure: Measure; width: number; height: number; title?: string }

/** One sketch page as the report prints it, on a canvas of width x height px. */
export function renderPage(page: Page, opts: OutputOpts): HTMLCanvasElement {
  const cv = document.createElement("canvas");
  cv.width = opts.width; cv.height = opts.height;
  const c = cv.getContext("2d")!;
  c.fillStyle = "#fff"; c.fillRect(0, 0, cv.width, cv.height);
  const floors = [...new Set(page.areas.map((a) => a.floor))].sort((a, b) => floorOrder(a) - floorOrder(b));
  if (!floors.length) return cv;
  // each floor's drawing, in feet, with room for wall dimensions and its title
  const groups = floors.map((f) => {
    const areas = page.areas.filter((a) => a.floor === f);
    const bb = areaBounds(areas);
    return { floor: f, areas, bb, w: bb.x1 - bb.x0, h: bb.y1 - bb.y0 };
  });
  const pad = 4, titleH = 6;            // feet around each drawing; feet under it for the title
  // try every number of rows; keep the arrangement that draws biggest
  let best = { scale: 0, rows: [] as typeof groups[] };
  for (let r = 1; r <= groups.length; r++) {
    const per = Math.ceil(groups.length / r);
    const rows: typeof groups[] = [];
    for (let i = 0; i < groups.length; i += per) rows.push(groups.slice(i, i + per));
    const rowW = rows.map((row) => row.reduce((t, g) => t + g.w + pad * 2, 0));
    const rowH = rows.map((row) => Math.max(...row.map((g) => g.h + pad * 2 + titleH)));
    const W = Math.max(...rowW), H = rowH.reduce((t, h) => t + h, 0);
    const margin = 0.04;
    const scale = Math.min((cv.width * (1 - 2 * margin)) / W, (cv.height * (1 - 2 * margin)) / H);
    if (scale > best.scale) best = { scale, rows };
  }
  const px = best.scale;
  const rowsH = best.rows.map((row) => Math.max(...row.map((g) => g.h + pad * 2 + titleH)));
  const totalH = rowsH.reduce((t, h) => t + h, 0) * px;
  let y = (cv.height - totalH) / 2;
  const lineW = Math.max(1.5, px * 0.09);
  const font = (pt: number, bold = false) => `${bold ? "700 " : ""}${Math.max(8, pt)}px Helvetica, Arial, sans-serif`;
  best.rows.forEach((row, ri) => {
    const rowW = row.reduce((t, g) => t + g.w + pad * 2, 0) * px;
    let x = (cv.width - rowW) / 2;
    for (const g of row) {
      c.save();
      c.translate(x + (pad - g.bb.x0) * px, y + (pad - g.bb.y0) * px);
      for (const a of g.areas) {
        c.beginPath();
        a.points.forEach((p, i) => {
          const path = wallPath(p, a.points[(i + 1) % a.points.length]);
          path.forEach((v, k) => (i === 0 && k === 0 ? c.moveTo(v.x * px, v.y * px) : c.lineTo(v.x * px, v.y * px)));
        });
        c.closePath();
        c.setLineDash(a.subtract ? [lineW * 4, lineW * 3] : []);
        c.lineWidth = NOT_LIVING.includes(a.kind) ? lineW * 0.8 : lineW;
        c.strokeStyle = "#000"; c.stroke();
        c.setLineDash([]);
        // dimensions on every wall
        c.fillStyle = "#000"; c.font = font(px * 1.15); c.textAlign = "center"; c.textBaseline = "middle";
        const ctr = centroid(a.points);
        a.points.forEach((p, i) => {
          const q = a.points[(i + 1) % a.points.length];
          const s = seg(p, q);
          if (s.length < 1.5) return;
          wallLabel(c, p, q, ctr, fmtLen(s.length, opts.measure), px, 1.3);
        });
        // a shape that is not the floor itself: its name and area inside it
        if (g.areas.length > 1 && (a.subtract || NOT_LIVING.includes(a.kind) || a.name)) {
          const own = a.name && a.name !== FLOOR_TITLE[a.floor];
          if (own) {
            c.font = font(px * 1.3, true);
            c.fillText(a.name, ctr.x * px, (ctr.y - 0.9) * px);
            c.font = font(px * 1.1);
            c.fillText(`[Area: ${a.subtract ? "-" : ""}${fmtArea(polygonArea(a.points))}]`, ctr.x * px, (ctr.y + 0.9) * px);
          }
        }
      }
      // room labels and symbols in this floor's shapes
      c.font = font(px * 1.35); c.fillStyle = "#000"; c.textAlign = "center"; c.textBaseline = "middle";
      for (const l of page.labels) if (g.areas.some((a) => contains(a.points, l.x, l.y))) c.fillText(l.text, l.x * px, l.y * px);
      c.lineWidth = Math.max(1, lineW * 0.5);
      for (const s of page.symbols) {
        if (!g.areas.some((a) => contains(a.points, s.x, s.y))) continue;
        const def = SYMBOL_SIZE(s.type);
        c.save(); c.translate(s.x * px, s.y * px); c.rotate((s.rot * Math.PI) / 180);
        c.scale(px * s.scale, px * s.scale); c.lineWidth = Math.max(1, lineW * 0.5) / (px * s.scale);
        c.translate(-def[0] / 2, -def[1] / 2);
        drawSymbol(c, s.type, def[0], def[1]); c.restore();
      }
      // doors: a swing arc on its wall
      for (const d of page.doors) {
        const a = g.areas.find((x) => x.id === d.area); if (!a) continue;
        drawDoor(c, a, d.wall, d.t, d.width, d.flip, px, lineW);
      }
      c.restore();
      // the floor's title and area beneath it
      const cx = x + (g.w / 2 + pad) * px, ty = y + (g.h + pad * 2) * px + titleH * 0.25 * px;
      c.fillStyle = "#000"; c.textAlign = "center"; c.textBaseline = "top";
      c.font = font(px * 1.9, true);
      c.fillText(page.floorTitles[g.floor] || FLOOR_TITLE[g.floor] || g.floor, cx, ty);
      c.font = font(px * 1.4);
      c.fillText(`[Area: ${fmtArea(floorArea(g.areas))}]`, cx, ty + px * 2.3);
      x += (g.w + pad * 2) * px;
    }
    y += rowsH[ri] * px;
  });
  return cv;
}

export const SYMBOL_SIZE = (type: string): [number, number] => (SYMBOLS.find((s) => s.type === type)?.size || [2, 2]);

export function drawDoor(c: C, a: Area, wall: number, t: number, width: number, flip: boolean, px: number, lineW: number) {
  const p = a.points[wall], q = a.points[(wall + 1) % a.points.length];
  if (!p || !q) return;
  const dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const w = Math.min(width, len);
  const sx = p.x + ux * (t * len - w / 2), sy = p.y + uy * (t * len - w / 2);
  // into the shape: the side the centre is on
  const ctr = centroid(a.points);
  let nx = -uy, ny = ux;
  if ((ctr.x - sx) * nx + (ctr.y - sy) * ny < 0) { nx = -nx; ny = -ny; }
  const hinge = flip ? { x: sx + ux * w, y: sy + uy * w } : { x: sx, y: sy };
  const along = flip ? { x: -ux, y: -uy } : { x: ux, y: uy };
  c.save();
  c.strokeStyle = "#fff"; c.lineWidth = lineW * 1.6;
  c.beginPath(); c.moveTo(sx * px, sy * px); c.lineTo((sx + ux * w) * px, (sy + uy * w) * px); c.stroke();
  c.strokeStyle = "#000"; c.lineWidth = Math.max(1, lineW * 0.5);
  c.beginPath();
  c.moveTo(hinge.x * px, hinge.y * px); c.lineTo((hinge.x + nx * w) * px, (hinge.y + ny * w) * px);
  const a0 = Math.atan2(ny, nx), a1 = Math.atan2(along.y, along.x);
  let sweep = a1 - a0; while (sweep > Math.PI) sweep -= 2 * Math.PI; while (sweep < -Math.PI) sweep += 2 * Math.PI;
  c.arc(hinge.x * px, hinge.y * px, w * px, a0, a1, sweep < 0);
  c.stroke();
  c.restore();
}
