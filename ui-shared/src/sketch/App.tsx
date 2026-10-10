// The sketch panel (DR §9). Opened by the editor in an overlay frame:
//   /ui/sketch/?case=<id>
// Draw by mouse or keyboard vectors; walls show their lengths, shapes their
// areas; labels and symbols drag in from the dock; "Save to report" writes the
// areas, levels and rooms into the units and the drawing in as the Sketch
// exhibit (engine/uad/sketch.py, POST /api/cases/{id}/sketch/report).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Line, Circle, Rect, Text, Shape, Group } from "react-konva";
import type Konva from "konva";
import type { Area, Kind, Label, Page, Pt, SketchDoc, Sym } from "./model";
import { ABOVE, BELOW, FLOOR_TITLE, KINDS, LABELS, NOT_LIVING, SYMBOLS, blankDoc, blankPage, detect, newArea, uid } from "./model";
import { arcMiddle, centroid, contains, fmtArea, fmtLen, outline, parseVectors, polygonArea, seg, snapAngle, snapTo, wallLengths, areaBounds } from "./geometry";
import type { Measure } from "./geometry";
import { drawDoor, drawSymbol, floorOrder, renderPage, SYMBOL_SIZE } from "./draw";
import { unitTable } from "./table";

type Tool = "select" | "draw" | "label" | "door" | "pan";
type Sel =
  | { kind: "area"; id: string }
  | { kind: "wall"; id: string; index: number }
  | { kind: "vertex"; id: string; index: number }
  | { kind: "label"; id: string }
  | { kind: "symbol"; id: string }
  | { kind: "door"; id: string }
  | null;
interface UnitInfo { n: number; id: string; adu: boolean }

const CASE = new URLSearchParams(location.search).get("case") || "";
const api = (path: string, init?: RequestInit) => fetch(`/api/cases/${CASE}${path}`, init);
const LS = (k: string) => `uad-sketch-${k}`;
const store = {
  get<T>(k: string, d: T): T { try { const v = localStorage.getItem(LS(k)); return v ? JSON.parse(v) as T : d; } catch { return d; } },
  set(k: string, v: unknown) { try { localStorage.setItem(LS(k), JSON.stringify(v)); } catch { /* storage off */ } },
};
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

export default function App() {
  const [doc, setDoc] = useState<SketchDoc>(blankDoc());
  const [pageIdx, setPageIdx] = useState(0);
  const [tool, setTool] = useState<Tool>("draw");
  const [sel, setSel] = useState<Sel>(null);
  const [drawing, setDrawing] = useState<Pt[]>([]);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [view, setView] = useState({ scale: 14, x: 120, y: 90 });
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [measure, setMeasure] = useState<Measure>(store.get("measure", "standard"));
  const [precision, setPrecision] = useState<"feet" | "inches">(store.get("precision", "inches"));
  const [angleSnap, setAngleSnap] = useState<number>(store.get("angle", 45));
  const [grid, setGrid] = useState<boolean>(store.get("grid", true));
  const [snapOn, setSnapOn] = useState<boolean>(store.get("snap", true));
  const [floor, setFloor] = useState("LevelOne");
  const [unitNo, setUnitNo] = useState(1);
  const [units, setUnits] = useState<UnitInfo[]>([{ n: 1, id: "Unit 1", adu: false }]);
  const [signed, setSigned] = useState(false);
  const [vec, setVec] = useState("");
  const [vecErr, setVecErr] = useState("");
  const [dockTab, setDockTab] = useState<"props" | "labels" | "symbols">("props");
  const [pendingLabel, setPendingLabel] = useState("Bedroom");
  const [customLabels, setCustomLabels] = useState<string[]>(store.get("labels", []));
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [help, setHelp] = useState(false);
  const [report, setReport] = useState<null | { changes: { where: string; what: string; old: string; new: string }[]; skipped: string[]; kept: string[] }>(null);
  const [space, setSpace] = useState(false);
  const history = useRef<{ undo: SketchDoc[]; redo: SketchDoc[] }>({ undo: [], redo: [] });
  const wrap = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const clipboard = useRef<Area | null>(null);
  const panFrom = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  const page: Page = doc.pages[Math.min(pageIdx, doc.pages.length - 1)];
  const step = !snapOn ? 0 : precision === "feet" ? 1 : 1 / 12;

  // ------------------------------------------------------------------ load
  useEffect(() => {
    (async () => {
      const backup = store.get<SketchDoc | null>(`backup-${CASE}`, null);
      try {
        const r = await api("/sketch");
        if (!r.ok) throw new Error(`the sketch could not be read (${r.status})`);
        const d = await r.json();
        setUnits(d.units?.length ? d.units : [{ n: 1, id: "Unit 1", adu: false }]);
        setSigned(!!d.signed);
        let sk: SketchDoc = d.sketch?.pages?.length ? d.sketch : blankDoc();
        if (backup && JSON.stringify(backup.pages) !== JSON.stringify(sk.pages) && backup.pages.some((p) => p.areas.length)) {
          if (confirm("This browser kept a newer, unsaved copy of the sketch (it was not saved before the window closed). Restore it?")) { sk = backup; setDirty(true); }
        }
        setDoc(sk);
        setTimeout(() => fit(sk.pages[0]), 30);
      } catch (e) { setStatus(String((e as Error).message)); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // the window size
  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); return () => ro.disconnect();
  }, []);

  // crash safety: the unsaved drawing is kept in this browser until saved
  useEffect(() => { if (dirty) store.set(`backup-${CASE}`, doc); }, [doc, dirty]);
  useEffect(() => { store.set("measure", measure); store.set("precision", precision); store.set("angle", angleSnap); store.set("grid", grid); store.set("snap", snapOn); },
    [measure, precision, angleSnap, grid, snapOn]);

  // ------------------------------------------------------------ edit helpers
  const commit = useCallback((fn: (d: SketchDoc) => void) => {
    setDoc((cur) => {
      history.current.undo.push(clone(cur)); if (history.current.undo.length > 120) history.current.undo.shift();
      history.current.redo = [];
      const next = clone(cur); fn(next); return next;
    });
    setDirty(true);
  }, []);
  const live = useCallback((fn: (d: SketchDoc) => void) => { setDoc((cur) => { const n = clone(cur); fn(n); return n; }); setDirty(true); }, []);
  const mark = useCallback(() => { setDoc((cur) => { history.current.undo.push(clone(cur)); history.current.redo = []; return cur; }); }, []);
  const undo = () => { const h = history.current; const prev = h.undo.pop(); if (!prev) return; h.redo.push(clone(doc)); setDoc(prev); setSel(null); setDirty(true); };
  const redo = () => { const h = history.current; const nx = h.redo.pop(); if (!nx) return; h.undo.push(clone(doc)); setDoc(nx); setSel(null); setDirty(true); };
  const pg = (d: SketchDoc) => d.pages[Math.min(pageIdx, d.pages.length - 1)];
  const areaOf = (id: string) => page.areas.find((a) => a.id === id);

  // screen <-> feet
  const toFeet = (sx: number, sy: number) => ({ x: (sx - view.x) / view.scale, y: (sy - view.y) / view.scale });
  const snapPt = (p: { x: number; y: number }, from?: Pt) => {
    let q = from && angleSnap ? snapAngle(from, p, angleSnap) : p;
    if (step) q = from && angleSnap ? snapLen(from, q, step) : { x: snapTo(q.x, step), y: snapTo(q.y, step) };
    return q;
  };
  function snapLen(from: Pt, q: { x: number; y: number }, s: number) {
    const dx = q.x - from.x, dy = q.y - from.y, len = Math.hypot(dx, dy);
    if (!len) return q;
    const L = snapTo(len, s);
    return { x: from.x + (dx / len) * L, y: from.y + (dy / len) * L };
  }

  const fitRef = useRef<() => void>(() => {});
  useEffect(() => { fitRef.current = () => fit(); });
  function fit(p: Page = page) {
    const el = wrap.current; if (!el) return;
    if (!p.areas.length) { setView({ scale: 14, x: el.clientWidth / 2 - 20 * 14, y: el.clientHeight / 2 - 15 * 14 }); return; }
    const bb = areaBounds(p.areas);
    const w = bb.x1 - bb.x0 || 10, h = bb.y1 - bb.y0 || 10;
    const scale = Math.min((el.clientWidth - 120) / w, (el.clientHeight - 120) / h, 60);
    setView({ scale, x: el.clientWidth / 2 - ((bb.x0 + bb.x1) / 2) * scale, y: el.clientHeight / 2 - ((bb.y0 + bb.y1) / 2) * scale });
  }

  // --------------------------------------------------------------- drawing
  function finishShape(points: Pt[]) {
    if (points.length < 3) { setDrawing([]); return; }
    const n = page.areas.filter((a) => a.floor === floor).length + 1;
    const a = newArea(points.map((p) => ({ x: +p.x.toFixed(4), y: +p.y.toFixed(4) })), floor, unitNo, n);
    if (BELOW.includes(floor)) a.grade = "FullyBelowGrade";
    commit((d) => { pg(d).areas.push(a); if (!pg(d).floorTitles[floor]) pg(d).floorTitles[floor] = FLOOR_TITLE[floor]; });
    setDrawing([]); setSel({ kind: "area", id: a.id }); setDockTab("props");
    setStatus(`${a.name}: ${fmtArea(polygonArea(a.points))}`);
  }

  function applyVectors() {
    const res = parseVectors(vec);
    if (res.error) { setVecErr(res.error); return; }
    setVecErr("");
    let pts = drawing.slice();
    if (!pts.length) {
      // start beside what is drawn already, or at the origin
      let start = { x: 0, y: 0 };
      const others = page.areas.filter((a) => a.floor === floor);
      if (others.length) { const bb = areaBounds(others); start = { x: bb.x1 + 10, y: bb.y0 }; }
      else if (page.areas.length) { const bb = areaBounds(page.areas); start = { x: bb.x0, y: bb.y1 + 12 }; }
      pts = [{ x: start.x, y: start.y }];
    }
    for (const m of res.moves) { const l = pts[pts.length - 1]; pts.push({ x: l.x + m.dx, y: l.y + m.dy }); }
    const first = pts[0], last = pts[pts.length - 1];
    const closesItself = pts.length > 3 && Math.hypot(first.x - last.x, first.y - last.y) < 0.05;
    if (closesItself) pts.pop();
    setVec("");
    if (res.close || closesItself) { finishShape(pts); setTimeout(() => fitRef.current(), 30); }
    else { setDrawing(pts); setTool("draw"); }
  }

  // -------------------------------------------------------------- the mouse
  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const st = stageRef.current!; const p = st.getPointerPosition()!;
    const k = e.evt.deltaY < 0 ? 1.12 : 1 / 1.12;
    const scale = Math.max(2, Math.min(200, view.scale * k));
    const f = toFeet(p.x, p.y);
    setView({ scale, x: p.x - f.x * scale, y: p.y - f.y * scale });
  };
  const pointer = () => { const p = stageRef.current!.getPointerPosition()!; return toFeet(p.x, p.y); };

  function hitWall(f: { x: number; y: number }, tol: number) {
    for (const a of [...page.areas].reverse()) {
      for (let i = 0; i < a.points.length; i++) {
        const p = a.points[i], q = a.points[(i + 1) % a.points.length];
        const m = arcMiddle(p, q);
        // distance to the chord (or near the arc's middle for a curved wall)
        const dx = q.x - p.x, dy = q.y - p.y, L2 = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((f.x - p.x) * dx + (f.y - p.y) * dy) / L2));
        const d = p.b ? Math.min(Math.hypot(f.x - m.x, f.y - m.y), Math.hypot(f.x - (p.x + t * dx), f.y - (p.y + t * dy)))
          : Math.hypot(f.x - (p.x + t * dx), f.y - (p.y + t * dy));
        if (d < tol) return { area: a, index: i, t };
      }
    }
    return null;
  }

  const onDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const btn = e.evt.button;
    if (btn === 1 || btn === 2 || tool === "pan" || space) {
      const p = stageRef.current!.getPointerPosition()!;
      panFrom.current = { x: p.x, y: p.y, vx: view.x, vy: view.y }; return;
    }
    if (signed) return;
    const f = pointer();
    if (tool === "draw") {
      const prev = drawing[drawing.length - 1];
      const q = snapPt(f, prev);
      if (drawing.length >= 3) {
        const first = drawing[0];
        if (Math.hypot(q.x - first.x, q.y - first.y) * view.scale < 10) { finishShape(drawing); return; }
      }
      if (prev && Math.hypot(q.x - prev.x, q.y - prev.y) < 1e-6) return;
      setDrawing([...drawing, { x: q.x, y: q.y }]);
      return;
    }
    if (tool === "label") {
      const l: Label = { id: uid("l"), text: pendingLabel, x: snapTo(f.x, 0.5), y: snapTo(f.y, 0.5) };
      commit((d) => { pg(d).labels.push(l); smartFromLabel(d, l); });
      setSel({ kind: "label", id: l.id }); setTool("select"); return;
    }
    if (tool === "door") {
      const hit = hitWall(f, 8 / view.scale);
      if (!hit) { setStatus("Click on a wall to put a door in it."); return; }
      const door = { id: uid("d"), area: hit.area.id, wall: hit.index, t: hit.t, width: 3, flip: false };
      commit((d) => pg(d).doors.push(door)); setSel({ kind: "door", id: door.id }); return;
    }
    // select: what is under the pointer (a wall first, then the smallest shape)
    if (e.target !== stageRef.current && e.target.name() && !["grid"].includes(e.target.name())) return;
    const wall = hitWall(f, 6 / view.scale);
    if (wall) { setSel({ kind: "wall", id: wall.area.id, index: wall.index }); setDockTab("props"); return; }
    const inside = page.areas.filter((a) => contains(a.points, f.x, f.y));
    if (inside.length) {
      const a = inside.reduce((m, x) => (polygonArea(x.points) < polygonArea(m.points) ? x : m));
      setSel({ kind: "area", id: a.id }); setDockTab("props"); return;
    }
    setSel(null);
  };
  const onMove = () => {
    const p = stageRef.current!.getPointerPosition(); if (!p) return;
    if (panFrom.current) { const s = panFrom.current; setView((v) => ({ ...v, x: s.vx + p.x - s.x, y: s.vy + p.y - s.y })); return; }
    setCursor(toFeet(p.x, p.y));
  };
  const onUp = () => { panFrom.current = null; };
  const onDbl = () => { if (tool === "draw" && drawing.length >= 3) finishShape(drawing); };

  // labels say what a shape is: "Unit 2", "Second Floor", "Garage" ...
  function smartFromLabel(d: SketchDoc, l: Label) {
    const det = detect(l.text);
    if (!Object.keys(det).length) return;
    const p = pg(d);
    const hosts = p.areas.filter((a) => contains(a.points, l.x, l.y));
    if (!hosts.length) return;
    const a = hosts.reduce((m, x) => (polygonArea(x.points) < polygonArea(m.points) ? x : m));
    if (det.unit) a.unit = det.unit;
    if (det.floor) a.floor = det.floor;
    if (det.kind) { a.kind = det.kind; a.gla = false; a.finished = false; }
    if (det.floor && BELOW.includes(det.floor) && !a.grade) a.grade = "FullyBelowGrade";
    setStatus(`${a.name}: ${[det.unit && `Unit ${det.unit}`, det.floor && FLOOR_TITLE[det.floor], det.kind].filter(Boolean).join(", ")} (from the label "${l.text}")`);
  }

  // ------------------------------------------------------------- keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest("input,textarea,select");
      if (e.key === " " && !typing) { setSpace(e.type === "keydown"); e.preventDefault(); return; }
      if (e.type !== "keydown") return;
      const ctrl = e.ctrlKey || e.metaKey;
      if (ctrl && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); undo(); return; }
      if (ctrl && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) { e.preventDefault(); redo(); return; }
      if (ctrl && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
      if (typing) return;
      if (ctrl && e.key.toLowerCase() === "c" && sel?.kind === "area") { clipboard.current = clone(areaOf(sel.id)!); setStatus("Shape copied"); return; }
      if (ctrl && e.key.toLowerCase() === "v" && clipboard.current) {
        const a = clone(clipboard.current); a.id = uid("a"); a.points = a.points.map((p) => ({ ...p, x: p.x + 2, y: p.y + 2 }));
        commit((d) => pg(d).areas.push(a)); setSel({ kind: "area", id: a.id }); return;
      }
      if (e.key === "Escape") { setDrawing([]); setSel(null); setHelp(false); return; }
      if (e.key === "Enter" && tool === "draw" && drawing.length >= 3) { finishShape(drawing); return; }
      if (e.key === "Backspace" && tool === "draw" && drawing.length) { setDrawing(drawing.slice(0, -1)); return; }
      if (e.key === "Delete" || e.key === "Backspace") { removeSel(); return; }
      if (e.key === "?") { setHelp((h) => !h); return; }
      const k = e.key.toLowerCase();
      if (k === "v") setTool("select"); else if (k === "a") setTool("draw"); else if (k === "l") setTool("label");
      else if (k === "d") setTool("door"); else if (k === "h") setTool("pan"); else if (k === "f") fit();
      else if (k === "r" && sel) rotateSel(e.shiftKey ? -90 : 90);
      else if (k === "m" && sel?.kind === "area") mirrorSel();
      else if (k === "g") setGrid((g) => !g);
    };
    window.addEventListener("keydown", onKey); window.addEventListener("keyup", onKey);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("keyup", onKey); };
  });

  function removeSel() {
    if (!sel || signed) return;
    commit((d) => {
      const p = pg(d);
      if (sel.kind === "area" || sel.kind === "wall") { p.areas = p.areas.filter((a) => a.id !== sel.id); p.doors = p.doors.filter((x) => x.area !== sel.id); }
      if (sel.kind === "vertex") { const a = p.areas.find((x) => x.id === sel.id); if (a && a.points.length > 3) a.points.splice(sel.index, 1); }
      if (sel.kind === "label") p.labels = p.labels.filter((l) => l.id !== sel.id);
      if (sel.kind === "symbol") p.symbols = p.symbols.filter((s) => s.id !== sel.id);
      if (sel.kind === "door") p.doors = p.doors.filter((x) => x.id !== sel.id);
    });
    setSel(null);
  }
  function rotateSel(deg: number) {
    if (!sel) return;
    if (sel.kind === "symbol") { commit((d) => { const s = pg(d).symbols.find((x) => x.id === sel.id); if (s) s.rot = (s.rot + deg + 360) % 360; }); return; }
    if (sel.kind !== "area") return;
    commit((d) => {
      const a = pg(d).areas.find((x) => x.id === sel.id); if (!a) return;
      const c = centroid(a.points), r = (deg * Math.PI) / 180, cos = Math.cos(r), sin = Math.sin(r);
      a.points = a.points.map((p) => ({ ...p, x: +(c.x + (p.x - c.x) * cos - (p.y - c.y) * sin).toFixed(4), y: +(c.y + (p.x - c.x) * sin + (p.y - c.y) * cos).toFixed(4) }));
    });
  }
  function mirrorSel() {
    if (sel?.kind !== "area") return;
    commit((d) => {
      const a = pg(d).areas.find((x) => x.id === sel.id); if (!a) return;
      const c = centroid(a.points);
      // mirrored left-right: the walls run the other way, so every bulge flips
      const pts = a.points.map((p) => ({ x: 2 * c.x - p.x, y: p.y, b: p.b }));
      const rev = pts.slice().reverse();
      a.points = rev.map((p, i) => ({ x: p.x, y: p.y, b: rev[(i + 1) % rev.length].b ? rev[(i + 1) % rev.length].b : 0 }));
    });
  }

  // --------------------------------------------------------------- saving
  async function save(): Promise<boolean> {
    setBusy(true);
    try {
      const r = await api("/sketch", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sketch: doc }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `not saved (${r.status})`);
      setDirty(false); store.set(`backup-${CASE}`, null); setStatus("Sketch saved"); return true;
    } catch (e) { setStatus(`The sketch was not saved: ${(e as Error).message}`); return false; } finally { setBusy(false); }
  }
  async function saveToReport() {
    if (signed) return;
    if (!doc.pages.some((p) => p.areas.length)) { setStatus("Draw at least one area first."); return; }
    setBusy(true); setStatus("Saving to the report...");
    try {
      const fd = new FormData();
      fd.append("sketch", JSON.stringify(doc));
      for (const p of doc.pages) {
        if (!p.areas.length) continue;
        const cv = renderPage(p, { measure, width: 1620, height: 1728 });       // the full-page exhibit box, 3x
        const blob: Blob = await new Promise((res) => cv.toBlob((b) => res(b!), "image/png"));
        fd.append(`page_${p.id}`, blob, `${p.id}.png`);
      }
      const r = await fetch(`/api/cases/${CASE}/sketch/report`, { method: "POST", body: fd });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || d.detail || `not saved (${r.status})`);
      setDirty(false); store.set(`backup-${CASE}`, null);
      setReport({ changes: d.changes || [], skipped: d.skipped || [], kept: d.kept || [] });
      setStatus("Saved to the report: the sketch exhibit and the unit areas, levels and rooms");
      try { window.parent !== window && window.parent.postMessage({ uad: "sketch-saved" }, "*"); } catch { /* standalone */ }
    } catch (e) { setStatus(`Not saved to the report: ${(e as Error).message}`); } finally { setBusy(false); }
  }
  const close = async () => {
    if (dirty && !signed && confirm("Keep the changes to the sketch before closing?")) { if (!(await save())) return; }
    try { window.parent !== window ? window.parent.postMessage({ uad: "sketch-close" }, "*") : window.history.back(); } catch { /* standalone */ }
  };

  // ------------------------------------------------------------- the view
  const sc = view.scale;
  const px = (n: number) => n / sc;        // screen pixels -> feet (for sizes that should not scale)
  const units4 = useMemo(() => unitTable(doc), [doc]);
  const selArea = sel && (sel.kind === "area" || sel.kind === "wall" || sel.kind === "vertex") ? areaOf(sel.id) : undefined;
  const floorsUsed = [...new Set(page.areas.map((a) => a.floor))].sort((a, b) => floorOrder(a) - floorOrder(b));

  const gridShape = (
    <Shape name="grid" listening={false} sceneFunc={(ctx) => {
      if (!grid) return;
      const c = (ctx as unknown as { _context: CanvasRenderingContext2D })._context;
      const x0 = -view.x / sc, y0 = -view.y / sc, x1 = x0 + size.w / sc, y1 = y0 + size.h / sc;
      const minor = sc >= 10 ? 1 : sc >= 4 ? 5 : 10;
      c.save();
      for (const [stp, col] of [[minor, "#eceef1"], [minor * 5 >= 5 ? 10 : 50, "#d6dae0"]] as [number, string][]) {
        c.beginPath(); c.strokeStyle = col; c.lineWidth = 1 / sc;
        for (let x = Math.floor(x0 / stp) * stp; x < x1; x += stp) { c.moveTo(x, y0); c.lineTo(x, y1); }
        for (let y = Math.floor(y0 / stp) * stp; y < y1; y += stp) { c.moveTo(x0, y); c.lineTo(x1, y); }
        c.stroke();
      }
      c.restore();
    }} />
  );

  return (
    <div className="app">
      <header className="top">
        <div className="brand"><b>Sketch</b><span>{page.name}</span></div>
        <nav className="tabs">
          {doc.pages.map((p, i) => (
            <button key={p.id} className={i === pageIdx ? "on" : ""} onClick={() => { setPageIdx(i); setSel(null); setDrawing([]); setTimeout(() => fit(p), 0); }}
              onDoubleClick={() => { const n = prompt("Name this sketch page", p.name); if (n) commit((d) => { d.pages[i].name = n; }); }}>
              {p.name}{dirty && i === pageIdx ? " *" : ""}</button>))}
          <button title="A new sketch page (e.g. an outbuilding)" onClick={() => { commit((d) => d.pages.push(blankPage(d.pages.length + 1))); setPageIdx(doc.pages.length); }}>+</button>
          {doc.pages.length > 1 && <button title="Remove this sketch page" onClick={() => { if (confirm(`Remove ${page.name}?`)) { commit((d) => d.pages.splice(pageIdx, 1)); setPageIdx(0); } }}>−</button>}
        </nav>
        <div className="tools">
          {([["select", "Select", "V"], ["draw", "Draw area", "A"], ["label", "Label", "L"], ["door", "Door", "D"], ["pan", "Pan", "H"]] as [Tool, string, string][]).map(([t, n, k]) => (
            <button key={t} className={tool === t ? "on" : ""} title={`${n} (${k})`} onClick={() => { setTool(t); if (t !== "draw") setDrawing([]); }}>{n}</button>))}
          <span className="sep" />
          <button title="Undo (Ctrl+Z)" onClick={undo}>Undo</button>
          <button title="Redo (Ctrl+Y)" onClick={redo}>Redo</button>
          <button title="Rotate the selection 90° (R)" onClick={() => rotateSel(90)} disabled={!sel}>Rotate</button>
          <button title="Mirror the selected shape (M)" onClick={mirrorSel} disabled={sel?.kind !== "area"}>Mirror</button>
          <button title="Delete the selection (Del)" onClick={removeSel} disabled={!sel}>Delete</button>
          <button title="Fit the drawing (F)" onClick={() => fit()}>Fit</button>
          <button title="Keyboard shortcuts (?)" onClick={() => setHelp(true)}>?</button>
        </div>
        <div className="act">
          <button onClick={save} disabled={busy || signed}>Save</button>
          <button className="primary" onClick={saveToReport} disabled={busy || signed} title="The sketch exhibit, and the unit areas, levels and rooms">Save to report</button>
          <button onClick={close}>Close</button>
        </div>
      </header>

      <div className="mid">
        <div className="canvasCol">
          <div className="vecbar">
            <label>Floor<select value={floor} onChange={(e) => setFloor(e.target.value)}>
              {[...ABOVE.slice(0, 4), ...BELOW.slice(0, 2)].map((f) => <option key={f} value={f}>{FLOOR_TITLE[f]}</option>)}</select></label>
            <label>Unit<select value={unitNo} onChange={(e) => setUnitNo(+e.target.value)}>
              {units.map((u) => <option key={u.n} value={u.n}>{u.id}{u.adu ? " (ADU)" : ""}</option>)}</select></label>
            <form onSubmit={(e) => { e.preventDefault(); applyVectors(); }}>
              <input value={vec} onChange={(e) => setVec(e.target.value)} placeholder={drawing.length ? "Continue: R12 D8 … C closes" : "Draw by keys: R20 U15 L20 D15  (UR10 = 45°, A30 12 = angle, C = close)"} aria-label="Keyboard vectors" />
              <button type="submit">Draw</button>
            </form>
            {vecErr && <span className="err">{vecErr}</span>}
          </div>
          <div className={`stagewrap tool-${tool}${space ? " panning" : ""}`} ref={wrap}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const raw = e.dataTransfer.getData("text/uad-sketch"); if (!raw || signed) return;
              const it = JSON.parse(raw) as { label?: string; symbol?: string };
              const r = wrap.current!.getBoundingClientRect();
              const f = toFeet(e.clientX - r.left, e.clientY - r.top);
              if (it.label) { const l: Label = { id: uid("l"), text: it.label, x: snapTo(f.x, 0.5), y: snapTo(f.y, 0.5) }; commit((d) => { pg(d).labels.push(l); smartFromLabel(d, l); }); setSel({ kind: "label", id: l.id }); }
              if (it.symbol) { const s: Sym = { id: uid("s"), type: it.symbol, x: snapTo(f.x, 0.5), y: snapTo(f.y, 0.5), rot: 0, scale: 1 }; commit((d) => pg(d).symbols.push(s)); setSel({ kind: "symbol", id: s.id }); }
            }}>
            <Stage ref={stageRef} width={size.w} height={size.h} scaleX={sc} scaleY={sc} x={view.x} y={view.y}
              onWheel={onWheel} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onDblClick={onDbl}
              onContextMenu={(e) => e.evt.preventDefault()}>
              <Layer listening={false}>{gridShape}</Layer>
              <Layer>
                {page.areas.map((a) => {
                  const selected = selArea?.id === a.id;
                  const living = !NOT_LIVING.includes(a.kind);
                  return (
                    <Line key={a.id} name="area" points={outline(a.points)} closed
                      fill={a.subtract ? "rgba(220,38,38,.05)" : living ? (selected ? "rgba(37,99,235,.08)" : "rgba(37,99,235,.03)") : "rgba(120,120,120,.06)"}
                      stroke={selected ? "#2563eb" : "#111"} strokeWidth={selected ? 2.5 : 2} strokeScaleEnabled={false}
                      dash={a.subtract ? [8, 6] : undefined} listening={tool === "select"}
                      draggable={tool === "select" && selected && !signed}
                      onMouseDown={(e) => { if (tool !== "select") return; e.cancelBubble = true; const f = pointer(); const w = hitWall(f, 6 / sc);
                        if (w && w.area.id === a.id) setSel({ kind: "wall", id: a.id, index: w.index }); else setSel({ kind: "area", id: a.id }); setDockTab("props"); }}
                      onDragStart={mark}
                      onDragEnd={(e) => {
                        const n = e.target; const dx = n.x(), dy = n.y(); n.position({ x: 0, y: 0 });
                        const sx = step ? snapTo(dx, step) : dx, sy = step ? snapTo(dy, step) : dy;
                        live((d) => { const t = pg(d).areas.find((x) => x.id === a.id); if (t) t.points = t.points.map((p) => ({ ...p, x: +(p.x + sx).toFixed(4), y: +(p.y + sy).toFixed(4) })); });
                      }} />
                  );
                })}
                {/* wall lengths and shape areas */}
                {page.areas.map((a) => {
                  const c = centroid(a.points);
                  const lens = wallLengths(a.points);
                  return (
                    <Group key={`t${a.id}`} listening={false}>
                      {a.points.map((p, i) => {
                        const q = a.points[(i + 1) % a.points.length]; const m = arcMiddle(p, q);
                        let nx = -(q.y - p.y), ny = q.x - p.x; const L = Math.hypot(nx, ny) || 1; nx /= L; ny /= L;
                        if ((m.x - c.x) * nx + (m.y - c.y) * ny < 0) { nx = -nx; ny = -ny; }
                        let ang = (Math.atan2(q.y - p.y, q.x - p.x) * 180) / Math.PI; if (ang > 90) ang -= 180; if (ang < -90) ang += 180;
                        if (lens[i] * sc < 26) return null;
                        const t = fmtLen(lens[i], measure, precision);
                        return <Text key={i} x={m.x + nx * px(12)} y={m.y + ny * px(12)} text={t} fontSize={px(11)} fill={a.subtract ? "#b91c1c" : "#1f2937"}
                          rotation={ang} offsetX={(t.length * px(11) * 0.55) / 2} offsetY={px(6)} fontFamily="Geist, Segoe UI, sans-serif" />;
                      })}
                      <Text x={c.x} y={c.y} text={`${a.name}\n[Area: ${a.subtract ? "-" : ""}${fmtArea(polygonArea(a.points))}]`} align="center"
                        fontSize={px(12)} lineHeight={1.25} fill={a.subtract ? "#b91c1c" : "#111"} fontStyle="bold"
                        offsetX={px(70)} width={px(140)} offsetY={px(14)} fontFamily="Geist, Segoe UI, sans-serif" />
                    </Group>
                  );
                })}
                {page.doors.map((d) => {
                  const a = areaOf(d.area); if (!a) return null;
                  return <Shape key={d.id} sceneFunc={(ctx) => { const c = (ctx as unknown as { _context: CanvasRenderingContext2D })._context; c.save(); drawDoor(c, a, d.wall, d.t, d.width, d.flip, 1, 1.6 / sc); c.restore(); }}
                    hitFunc={(ctx, shape) => { const p = a.points[d.wall], q = a.points[(d.wall + 1) % a.points.length]; if (!p || !q) return; const x = p.x + (q.x - p.x) * d.t, y = p.y + (q.y - p.y) * d.t; ctx.beginPath(); ctx.arc(x, y, d.width, 0, Math.PI * 2); ctx.fillStrokeShape(shape); }}
                    onMouseDown={(e) => { if (tool === "select") { e.cancelBubble = true; setSel({ kind: "door", id: d.id }); setDockTab("props"); } }}
                    stroke={sel?.kind === "door" && sel.id === d.id ? "#2563eb" : undefined} />;
                })}
                {page.symbols.map((s) => {
                  const [w, h] = SYMBOL_SIZE(s.type); const on = sel?.kind === "symbol" && sel.id === s.id;
                  return <Shape key={s.id} x={s.x} y={s.y} rotation={s.rot} draggable={tool === "select" && !signed}
                    sceneFunc={(ctx, shape) => { const c = (ctx as unknown as { _context: CanvasRenderingContext2D })._context; c.save(); c.strokeStyle = on ? "#2563eb" : "#222"; c.lineWidth = 1.3 / sc; c.translate(-w / 2 * s.scale, -h / 2 * s.scale); c.scale(s.scale, s.scale); drawSymbol(c, s.type, w, h); c.restore(); void shape; }}
                    hitFunc={(ctx, shape) => { ctx.beginPath(); ctx.rect(-w / 2 * s.scale, -h / 2 * s.scale, w * s.scale, h * s.scale); ctx.fillStrokeShape(shape); }}
                    onMouseDown={(e) => { if (tool === "select") { e.cancelBubble = true; setSel({ kind: "symbol", id: s.id }); setDockTab("props"); } }}
                    onDragStart={mark}
                    onDragEnd={(e) => { const x = snapTo(e.target.x(), 0.25), y = snapTo(e.target.y(), 0.25); live((d) => { const t = pg(d).symbols.find((v) => v.id === s.id); if (t) { t.x = x; t.y = y; } }); }} />;
                })}
                {page.labels.map((l) => {
                  const on = sel?.kind === "label" && sel.id === l.id;
                  return <Text key={l.id} x={l.x} y={l.y} text={l.text} fontSize={px(13)} fill={on ? "#2563eb" : "#111"} fontFamily="Geist, Segoe UI, sans-serif"
                    offsetX={(l.text.length * px(13) * 0.55) / 2} offsetY={px(7)} draggable={tool === "select" && !signed}
                    onMouseDown={(e) => { if (tool === "select") { e.cancelBubble = true; setSel({ kind: "label", id: l.id }); setDockTab("props"); } }}
                    onDblClick={() => { const t = prompt("Label", l.text); if (t) commit((d) => { const x = pg(d).labels.find((v) => v.id === l.id); if (x) { x.text = t; smartFromLabel(d, x); } }); }}
                    onDragStart={mark}
                    onDragEnd={(e) => { const x = snapTo(e.target.x(), 0.25), y = snapTo(e.target.y(), 0.25); live((d) => { const t = pg(d).labels.find((v) => v.id === l.id); if (t) { t.x = x; t.y = y; smartFromLabel(d, t); } }); }} />;
                })}
              </Layer>
              <Layer>
                {/* handles of the selected shape: red corners, blue wall middles, orange arc handle */}
                {selArea && tool === "select" && !signed && selArea.points.map((p, i) => {
                  const q = selArea.points[(i + 1) % selArea.points.length]; const m = arcMiddle(p, q);
                  const wallOn = sel?.kind === "wall" && sel.index === i;
                  return (
                    <Group key={`h${i}`}>
                      <Rect x={m.x} y={m.y} width={px(9)} height={px(9)} offsetX={px(4.5)} offsetY={px(4.5)} fill={wallOn ? "#f59e0b" : "#2563eb"} stroke="#fff" strokeWidth={1} strokeScaleEnabled={false}
                        draggable onDragStart={mark}
                        onClick={(e) => { e.cancelBubble = true; setSel({ kind: "wall", id: selArea.id, index: i }); }}
                        onDblClick={() => commit((d) => { const a = pg(d).areas.find((x) => x.id === selArea.id); if (!a) return; const mm = arcMiddle(a.points[i], a.points[(i + 1) % a.points.length]); a.points.splice(i + 1, 0, { x: +mm.x.toFixed(4), y: +mm.y.toFixed(4) }); a.points[i].b = 0; })}
                        onDragMove={(e) => {
                          // a straight wall moves parallel to itself; a curved one changes its bulge
                          const n = e.target; const nx = n.x(), ny = n.y();
                          live((d) => {
                            const a = pg(d).areas.find((x) => x.id === selArea.id); if (!a) return;
                            const P = a.points[i], Q = a.points[(i + 1) % a.points.length];
                            const dx = Q.x - P.x, dy = Q.y - P.y, c = Math.hypot(dx, dy) || 1;
                            if (P.b) {
                              const mx = (P.x + Q.x) / 2, my = (P.y + Q.y) / 2;
                              const s = ((nx - mx) * -dy + (ny - my) * dx) / c;        // signed sagitta along (-dy, dx)
                              P.b = Math.max(-1.5, Math.min(1.5, (2 * s) / c));
                            } else {
                              const cur = arcMiddle(P, Q); let ox = nx - cur.x, oy = ny - cur.y;
                              const ux = -dy / c, uy = dx / c; const along = ox * ux + oy * uy; ox = ux * along; oy = uy * along;
                              const k = step ? snapTo(along, step) / (along || 1) : 1;
                              P.x += ox * k; P.y += oy * k; Q.x += ox * k; Q.y += oy * k;
                            }
                          });
                        }}
                        onDragEnd={(e) => { const mm = arcMiddle(selArea.points[i], selArea.points[(i + 1) % selArea.points.length]); e.target.position(mm); }} />
                      <Circle x={p.x} y={p.y} radius={px(5)} fill={sel?.kind === "vertex" && sel.index === i ? "#f59e0b" : "#dc2626"} stroke="#fff" strokeWidth={1} strokeScaleEnabled={false}
                        draggable onDragStart={() => { mark(); setSel({ kind: "vertex", id: selArea.id, index: i }); }}
                        onClick={(e) => { e.cancelBubble = true; setSel({ kind: "vertex", id: selArea.id, index: i }); }}
                        onDragMove={(e) => {
                          const f = { x: e.target.x(), y: e.target.y() };
                          const prev = selArea.points[(i - 1 + selArea.points.length) % selArea.points.length];
                          const q2 = snapPt(f, angleSnap ? prev : undefined);
                          e.target.position(q2);
                          live((d) => { const a = pg(d).areas.find((x) => x.id === selArea.id); if (a) { a.points[i].x = +q2.x.toFixed(4); a.points[i].y = +q2.y.toFixed(4); } });
                        }} />
                    </Group>
                  );
                })}
                {/* the shape being drawn, with its next wall following the pointer */}
                {drawing.length > 0 && (() => {
                  const last = drawing[drawing.length - 1];
                  const nxt = cursor ? snapPt(cursor, last) : last;
                  const pts = [...drawing, nxt];
                  const len = Math.hypot(nxt.x - last.x, nxt.y - last.y);
                  return (
                    <Group listening={false}>
                      <Line points={pts.flatMap((p) => [p.x, p.y])} stroke="#2563eb" strokeWidth={2} strokeScaleEnabled={false} dash={[6, 4]} />
                      {drawing.map((p, i) => <Circle key={i} x={p.x} y={p.y} radius={px(i === 0 ? 6 : 4)} fill={i === 0 ? "#16a34a" : "#2563eb"} />)}
                      <Text x={(last.x + nxt.x) / 2} y={(last.y + nxt.y) / 2 - px(18)} text={fmtLen(len, measure, precision)} fontSize={px(12)} fill="#2563eb" fontStyle="bold" />
                    </Group>
                  );
                })()}
              </Layer>
            </Stage>
            {help && <Help onClose={() => setHelp(false)} />}
            {report && <Report r={report} onClose={() => setReport(null)} />}
          </div>
          <AreaTable doc={doc} page={page} units={units4} />
        </div>

        <aside className="dock">
          <nav className="docktabs">
            {(["props", "labels", "symbols"] as const).map((t) => <button key={t} className={dockTab === t ? "on" : ""} onClick={() => setDockTab(t)}>{t === "props" ? "Properties" : t === "labels" ? "Labels" : "Symbols"}</button>)}
          </nav>
          {dockTab === "props" && <Props sel={sel} page={page} units={units} measure={measure} precision={precision} signed={signed}
            commit={commit} floorsUsed={floorsUsed} pg={pg} setSel={setSel} />}
          {dockTab === "labels" && (
            <div className="list">
              <p className="hint">Drag a label onto the plan, or pick one and click where it goes. "Unit 2", "Second Floor" or "Garage" also tell the shape what it is.</p>
              {[...LABELS, ...customLabels].map((t) => (
                <div key={t} className={`item${pendingLabel === t && tool === "label" ? " on" : ""}`} draggable
                  onDragStart={(e) => e.dataTransfer.setData("text/uad-sketch", JSON.stringify({ label: t }))}
                  onClick={() => { setPendingLabel(t); setTool("label"); }}>{t}</div>))}
              <button className="new" onClick={() => { const t = prompt("New label"); if (t) { const n = [...customLabels, t]; setCustomLabels(n); store.set("labels", n); } }}>+ New label</button>
            </div>
          )}
          {dockTab === "symbols" && (
            <div className="list">
              <p className="hint">Drag a symbol onto the plan. R turns it; Delete removes it.</p>
              {[...new Set(SYMBOLS.map((s) => s.group))].map((g) => (
                <div key={g}><h4>{g}</h4>
                  <div className="syms">{SYMBOLS.filter((s) => s.group === g).map((s) => (
                    <div key={s.type} className="sym" draggable onDragStart={(e) => e.dataTransfer.setData("text/uad-sketch", JSON.stringify({ symbol: s.type }))} title={s.name}>
                      <SymbolIcon type={s.type} /><span>{s.name}</span></div>))}</div></div>))}
            </div>
          )}
        </aside>
      </div>

      <footer className="status">
        <label>Measurement<select value={measure} onChange={(e) => setMeasure(e.target.value as Measure)}><option value="standard">Standard (feet/inches)</option><option value="decimal">Decimal feet</option></select></label>
        <label>Precision<select value={precision} onChange={(e) => setPrecision(e.target.value as "feet" | "inches")}><option value="inches">Inches</option><option value="feet">Feet</option></select></label>
        <label>Angle snap<select value={angleSnap} onChange={(e) => setAngleSnap(+e.target.value)}>{[0, 5, 15, 45, 90].map((v) => <option key={v} value={v}>{v ? `${v}°` : "Off"}</option>)}</select></label>
        <label><input type="checkbox" checked={snapOn} onChange={(e) => setSnapOn(e.target.checked)} />Snap</label>
        <label><input type="checkbox" checked={grid} onChange={(e) => setGrid(e.target.checked)} />Grid</label>
        <span className="pos">{cursor ? `${fmtLen(cursor.x, measure, precision)}, ${fmtLen(cursor.y, measure, precision)}` : ""}</span>
        <span className="zoom">{Math.round(sc * 10) / 10} px/ft</span>
        <span className="msg">{signed ? "Signed report: the sketch is shown, not changed." : status}</span>
      </footer>
    </div>
  );
}

// --------------------------------------------------------------- panels
function Props(p: { sel: Sel; page: Page; units: UnitInfo[]; measure: Measure; precision: "feet" | "inches"; signed: boolean;
  commit: (fn: (d: SketchDoc) => void) => void; floorsUsed: string[]; pg: (d: SketchDoc) => Page; setSel: (s: Sel) => void }) {
  const { sel, page, commit, pg } = p;
  if (!sel) return (
    <div className="props"><p className="hint">Draw an area (A): click each corner and click the green first point to close, or type vectors above.
      Select a shape (V) to name it and say what it is; a wall to set its length or curve it.</p>
      {p.floorsUsed.length > 0 && <><h4>Floor titles</h4>{p.floorsUsed.map((f) => (
        <label key={f} className="row">{FLOOR_TITLE[f]}<input defaultValue={page.floorTitles[f] || FLOOR_TITLE[f]} onBlur={(e) => commit((d) => { pg(d).floorTitles[f] = e.target.value; })} /></label>))}</>}
    </div>);
  if (sel.kind === "label") {
    const l = page.labels.find((x) => x.id === sel.id); if (!l) return null;
    return <div className="props"><h4>Label</h4><label className="row">Text<input value={l.text} disabled={p.signed} onChange={(e) => commit((d) => { const x = pg(d).labels.find((v) => v.id === l.id); if (x) x.text = e.target.value; })} /></label></div>;
  }
  if (sel.kind === "symbol") {
    const s = page.symbols.find((x) => x.id === sel.id); if (!s) return null;
    return <div className="props"><h4>{SYMBOLS.find((x) => x.type === s.type)?.name}</h4>
      <label className="row">Rotation<input type="number" step={15} value={s.rot} onChange={(e) => commit((d) => { const x = pg(d).symbols.find((v) => v.id === s.id); if (x) x.rot = +e.target.value; })} /></label>
      <label className="row">Size ×<input type="number" step={0.1} min={0.3} value={s.scale} onChange={(e) => commit((d) => { const x = pg(d).symbols.find((v) => v.id === s.id); if (x) x.scale = Math.max(0.3, +e.target.value || 1); })} /></label></div>;
  }
  if (sel.kind === "door") {
    const dd = page.doors.find((x) => x.id === sel.id); if (!dd) return null;
    return <div className="props"><h4>Door</h4>
      <label className="row">Width (ft)<input type="number" step={0.5} min={1} value={dd.width} onChange={(e) => commit((d) => { const x = pg(d).doors.find((v) => v.id === dd.id); if (x) x.width = Math.max(1, +e.target.value || 3); })} /></label>
      <label className="row">Swing<button onClick={() => commit((d) => { const x = pg(d).doors.find((v) => v.id === dd.id); if (x) x.flip = !x.flip; })}>Flip</button></label></div>;
  }
  const a = page.areas.find((x) => x.id === sel.id); if (!a) return null;
  const set = (fn: (t: Area) => void) => commit((d) => { const t = pg(d).areas.find((x) => x.id === a.id); if (t) fn(t); });
  const living = !NOT_LIVING.includes(a.kind);
  const walls = wallLengths(a.points);
  return (
    <div className="props">
      <h4>Shape</h4>
      <label className="row">Name<input value={a.name} disabled={p.signed} onChange={(e) => set((t) => { t.name = e.target.value; })}
        onBlur={(e) => set((t) => { const det = detect(e.target.value); if (det.unit) t.unit = det.unit; if (det.floor) t.floor = det.floor; if (det.kind) { t.kind = det.kind; t.gla = false; t.finished = false; } if (det.subtract) t.subtract = true; })} /></label>
      <label className="row">Floor<select value={a.floor} onChange={(e) => set((t) => { t.floor = e.target.value; if (BELOW.includes(t.floor) && !t.grade) t.grade = "FullyBelowGrade"; })}>
        {[...ABOVE, ...BELOW].map((f) => <option key={f} value={f}>{FLOOR_TITLE[f]}</option>)}</select></label>
      <label className="row">Unit<select value={a.unit} onChange={(e) => set((t) => { t.unit = +e.target.value; })}>
        {p.units.map((u) => <option key={u.n} value={u.n}>{u.id}</option>)}</select></label>
      <label className="row">What it is<select value={a.kind} onChange={(e) => set((t) => { t.kind = e.target.value as Kind; const lv = !NOT_LIVING.includes(t.kind); t.gla = lv; t.finished = lv; })}>
        {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</select></label>
      {living && <>
        <label className="chk"><input type="checkbox" checked={a.finished} onChange={(e) => set((t) => { t.finished = e.target.checked; })} />Finished</label>
        {!BELOW.includes(a.floor) && <label className="chk"><input type="checkbox" checked={a.gla && !a.nonstandard} onChange={(e) => set((t) => { t.gla = e.target.checked; if (e.target.checked) t.nonstandard = false; })} />Counts in GLA (standard finished area above grade)</label>}
        <label className="chk"><input type="checkbox" checked={a.nonstandard} onChange={(e) => set((t) => { t.nonstandard = e.target.checked; if (e.target.checked) t.gla = false; })} />Nonstandard finished area</label>
        {BELOW.includes(a.floor) && <label className="row">Below grade<select value={a.grade || "FullyBelowGrade"} onChange={(e) => set((t) => { t.grade = e.target.value as Area["grade"]; })}>
          <option value="FullyBelowGrade">Fully below grade</option><option value="PartiallyBelowGrade">Partially below grade</option></select></label>}
      </>}
      <label className="chk"><input type="checkbox" checked={a.subtract} onChange={(e) => set((t) => { t.subtract = e.target.checked; })} />Deduction (open to below, atrium): comes off the shape it sits in</label>
      <p className="area">{a.subtract ? "−" : ""}{fmtArea(polygonArea(a.points))}{!living && !a.subtract ? " · not living area" : ""}</p>
      <h4>Walls</h4>
      <div className="walls">{walls.map((w, i) => {
        const on = sel.kind === "wall" && sel.index === i;
        const P = a.points[i];
        return (
          <div key={i} className={`wall${on ? " on" : ""}`} onClick={() => p.setSel({ kind: "wall", id: a.id, index: i })}>
            <span>{i + 1}</span>
            <input defaultValue={w.toFixed(2)} key={`${a.id}-${i}-${w.toFixed(3)}`} disabled={p.signed || !!P.b} title={P.b ? "A curved wall's length follows its curve" : "Type a length: the wall's end moves along the wall"}
              onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
              onBlur={(e) => {
                const L = parseFloat(e.target.value); if (!(L > 0) || Math.abs(L - w) < 1e-6) return;
                set((t) => { const A = t.points[i], B = t.points[(i + 1) % t.points.length]; const dx = B.x - A.x, dy = B.y - A.y, c = Math.hypot(dx, dy) || 1;
                  B.x = +(A.x + (dx / c) * L).toFixed(4); B.y = +(A.y + (dy / c) * L).toFixed(4); });
              }} />
            <em>{fmtLen(w, p.measure, p.precision)}</em>
            <button title={P.b ? "Make the wall straight" : "Curve the wall (a bay or a rounded end); drag its handle to shape it"}
              onClick={(e) => { e.stopPropagation(); set((t) => { t.points[i].b = t.points[i].b ? 0 : -0.4142; }); }}>{P.b ? "Straight" : "Curve"}</button>
          </div>);
      })}</div>
    </div>
  );
}

function AreaTable({ doc, page, units }: { doc: SketchDoc; page: Page; units: ReturnType<typeof unitTable> }) {
  const rows = [...page.areas].sort((a, b) => floorOrder(a.floor) - floorOrder(b.floor));
  const n = (v: number) => Math.round(v).toLocaleString("en-US");
  return (
    <div className="table">
      <table>
        <thead><tr><th>Shape</th><th>Floor</th><th>Unit</th><th>What</th><th>GLA</th><th>Finished</th><th className="num">Area ft²</th><th>Walls</th></tr></thead>
        <tbody>{rows.map((a) => (
          <tr key={a.id} className={a.subtract ? "ded" : ""}><td>{a.name}</td><td>{page.floorTitles[a.floor] || FLOOR_TITLE[a.floor]}</td><td>{a.unit}</td>
            <td>{a.subtract ? "deduction" : KINDS.find((k) => k.value === a.kind)?.label}</td>
            <td>{!NOT_LIVING.includes(a.kind) && a.gla && !a.nonstandard && !BELOW.includes(a.floor) ? "Yes" : "No"}</td>
            <td>{a.finished ? "Yes" : "No"}</td><td className="num">{a.subtract ? "−" : ""}{n(polygonArea(a.points))}</td>
            <td className="walls">{a.points.map((pp, i) => seg(pp, a.points[(i + 1) % a.points.length]).length.toFixed(1)).join(" · ")}</td></tr>))}</tbody>
      </table>
      <div className="totals">{units.map((u) => (
        <div key={u.unit}><b>Unit {u.unit}</b>
          <span>GLA {n(u.standardAbove)}</span>
          {u.nonstandardAbove ? <span>Nonstandard above {n(u.nonstandardAbove)}</span> : null}
          {u.unfinishedAbove ? <span>Unfinished above {n(u.unfinishedAbove)}</span> : null}
          <span>Below grade finished {n(u.standardBelow + u.nonstandardBelow)} · unfinished {n(u.unfinishedBelow)}</span>
          <span>Bedrooms {u.bedrooms} · Baths {u.fullBaths} full, {u.halfBaths} half</span>
        </div>))}
        {doc.pages.length > 1 && <em>All sketch pages count.</em>}
      </div>
    </div>
  );
}

function SymbolIcon({ type }: { type: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current!.getContext("2d")!; const [w, h] = SYMBOL_SIZE(type);
    c.clearRect(0, 0, 44, 44); const k = 32 / Math.max(w, h);
    c.save(); c.translate(22 - (w * k) / 2, 22 - (h * k) / 2); c.scale(k, k); c.lineWidth = 1.4 / k; c.strokeStyle = "#222"; drawSymbol(c, type, w, h); c.restore();
  }, [type]);
  return <canvas ref={ref} width={44} height={44} />;
}

function Help({ onClose }: { onClose: () => void }) {
  const rows: [string, string][] = [
    ["A", "Draw an area: click corners, click the green first point (or Enter / double-click) to close"], ["Backspace", "While drawing: take back the last corner"],
    ["R20 U15 L20 D15", "Draw by keys (Right, Up, Left, Down, in feet; 12'6\" works); UR10 = 45°; A30 12 = 30° for 12 ft; C closes"],
    ["V", "Select: a shape, a wall, a label, a symbol, a door"], ["Red corner", "Drag to move a corner"],
    ["Blue square", "Drag to move a straight wall (or to bend a curved one); double-click to split the wall"],
    ["L", "Label (or drag one from the Labels tab)"], ["D", "Door: click on a wall"], ["H / Space+drag / right-drag", "Pan"],
    ["Wheel", "Zoom"], ["F", "Fit the drawing"], ["R / Shift+R", "Rotate the selection 90°"], ["M", "Mirror the selected shape"],
    ["Ctrl+C / Ctrl+V", "Copy and paste a shape"], ["Del", "Delete the selection"], ["Ctrl+Z / Ctrl+Y", "Undo / redo"],
    ["Ctrl+S", "Save the sketch"], ["G", "Grid on / off"], ["Esc", "Cancel"]];
  return <div className="overlay" onClick={onClose}><div className="card" onClick={(e) => e.stopPropagation()}>
    <h3>Sketch keys</h3><table><tbody>{rows.map(([k, v]) => <tr key={k}><td><kbd>{k}</kbd></td><td>{v}</td></tr>)}</tbody></table>
    <button onClick={onClose}>Close</button></div></div>;
}

function Report({ r, onClose }: { r: { changes: { where: string; what: string; old: string; new: string }[]; skipped: string[]; kept: string[] }; onClose: () => void }) {
  const nice = (w: string) => w.replace(/^Unit/, "").replace(/AreaMeasure$/, "").replace(/([a-z])([A-Z])/g, "$1 $2");
  return <div className="overlay" onClick={onClose}><div className="card wide" onClick={(e) => e.stopPropagation()}>
    <h3>Saved to the report</h3>
    <p>The sketch is the Sketch exhibit. {r.changes.length ? `${r.changes.length} value(s) changed:` : "No unit values needed changing."}</p>
    {r.changes.length > 0 && <table className="chg"><thead><tr><th>Where</th><th>What</th><th>Was</th><th>Now</th></tr></thead>
      <tbody>{r.changes.map((c, i) => <tr key={i}><td>{c.where}</td><td>{nice(c.what)}</td><td>{c.old || "—"}</td><td>{c.new}</td></tr>)}</tbody></table>}
    {r.kept.length > 0 && <><h4>Kept as the report had them (the sketch does not draw these floors)</h4><ul>{r.kept.map((k) => <li key={k}>{k}</li>)}</ul></>}
    {r.skipped.length > 0 && <><h4>Not written</h4><ul>{r.skipped.map((k) => <li key={k}>{k}</li>)}</ul></>}
    <button onClick={onClose}>OK</button></div></div>;
}
