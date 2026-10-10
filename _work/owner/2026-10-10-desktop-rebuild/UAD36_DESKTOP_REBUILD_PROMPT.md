# UAD 3.6 Form Filler — Desktop Rebuild & Operator-Experience Overhaul

> **Who this is for:** the AI engineering agent working in `Mohit-rajput-mr/UAD-3.6-DEVELOPMENT`.
> **Who wrote the requirements:** the owner, after reviewing the current Windows build section by section from an operator's chair.
> **Read first:** `AI_HANDOVER.md`, `CLAUDE.md`, `_work/GOAL.md`, `TASKS.md`, last section of `_work/HANDOFF.md`. Every non-negotiable in `CLAUDE.md` still applies (specs are the authority, generate from spec files, validate validators against the 12 D-1 samples, no fake controls, no compliance claim without a test).
> **Register every item below** with `python engine/tasks.py add ... --area <area>` before starting, and close each with evidence.

---

## 0. The goal in one paragraph

The current Windows app is the web editor inside an Edge app-mode window. It *looks and feels like a website*: panels eat the screen, the report is a thin strip in the middle, actions take 2–3 seconds, dropdowns must be clicked one by one, sections that do not apply still show, and several "save to report" actions silently do nothing. Rebuild it into a **fast, native-feeling, operator-first desktop application** that an appraiser can fill in a fraction of the time — **while every output (preview, `appraisal.pdf`, `mismo.xml`, `Images/`, ZIP) stays 100 % faithful to UAD 3.6 / URAR (C-1 layout, D-1 samples, H-1 rules, GSE subschema).**

Key principle: **the editor is a form filler, not a photocopy of the printed page.** Editing views may be laid out for speed (e.g. all comparables side by side). The *preview, PDF and ZIP* must follow the official layout exactly.

Think like an appraiser filling 5 reports a day **and** like a senior software architect. Fix what is listed, then **apply each fix to every similar place in the app**, and **predict and fix the problems the owner has not hit yet**. Do not do only the literal list.

---

## 1. Technology decision (2026)

| Layer | Use | Notes |
|---|---|---|
| Desktop shell | **Tauri 2** (Rust, WebView2) | Replace the Edge app-mode launcher (`desktop/launcher.py`). Small, instant start, native window, menus, tray, file drag-drop, auto-updater. |
| Desktop UI | **React + TypeScript + Vite** | **Not Next.js** for desktop (Tauri only supports static export; no benefit). |
| Web UI | Next.js may be used for the web edition. | Put form components, ribbon, panels, sketch, worksheet in a **shared package** used by both editions — write each screen once. |
| Local data | **Local-first**: SQLite (or the case MISMO XML on disk, as today) with in-memory edits and background persistence | Every keystroke updates the UI instantly; persistence, compliance and layout run asynchronously. Optional background sync to the cloud store. |
| Report engine | **Existing Python engine** (`engine/`) as a bundled **Tauri sidecar** | Keep the proven MISMO/H-1/C-1 work. Move hot paths to Rust later, only with tests proving identical output. |
| Sketch | Canvas engine (**Konva** or **PixiJS**) | See §9. |
| Offline document intelligence | **PaddleOCR + ONNX Runtime** + rule-based parsers; optional **small local LLM via llama.cpp** (Qwen — Apache 2.0, or Phi — MIT) | No API key, runs on the PC, free. Do **not** use models with restrictive licences (e.g. Llama). See §10. |
| Updates | Tauri updater | Signed releases. Note: a code-signing certificate (~$200–400/yr) removes the "Windows protected your PC" warning — flag to owner, do not block on it. |

All components above are free for commercial use (MIT / Apache / public domain). Keep it that way; check licence before adding any dependency.

### Performance budget (measure and record in HANDOFF)
- App cold start < 2 s; open a report < 1 s.
- Keystroke → visible < 16 ms. **No server round trip on edit.**
- Add exhibit/photo → thumbnail visible **instantly** (local object URL); resize/hash/store in background. Today it takes 2–3 s — unacceptable.
- Switching sections, opening units side-by-side, opening comparables: < 150 ms.
- Re-layout only the page/section that changed, never the whole report.
- Long actions (map render, PDF, ZIP, OCR) show progress and never freeze the UI.

---

## 2. Branding

Use the assets in `brand/` (shipped with this prompt):
- `app-icon.ico` (16–256 px) → window, taskbar, Start menu, shortcut, installer.
- `app-icon-*.png` (16–1024) → Tauri bundle icons, updater.
- `logo-black.png` / `logo-white.png` (transparent) → ribbon header, splash, sign-in, light/dark themes.
- Replace the current "U" mark everywhere. Product name stays **"UAD 3.6 Form Filler"**. No "Kech" branding.

---

## 3. Window layout — give the report the screen

Reference: `screenshots/01-layout-panels-take-space.jpg`.

Problems: left Sections list, top tab bar + toolbar rows, and right Field Guidance / Sign-off / Delivery panels together leave the report as a narrow strip.

Build:
1. **Ribbon** at the top (Office-style, collapsible to one row with Ctrl+F1): tabs **Home · Report · Comparables · Sketch · Location Map · Exhibits · Worksheets · Review · Deliver**. Every current toolbar button moves into the ribbon. Remove the duplicate tab row and toolbar row.
2. **Dockable, collapsible side panels** (left: Sections/navigator; right: Problems, Field Guidance, Sign-off). Each panel: collapse to an icon rail, slide away like a shutter, resize by drag, pin/unpin, remember state per user.
3. **Focus mode** (F11): hide everything except the report.
4. **Split view / clones of the same report**: open the *same* report in 2+ panes (side by side or stacked, or a floating window on a second monitor). Every pane is **fully editable** and live-synced (one model, many views). Use case: keep page 1 visible while filling page 20; compare subject to comps; check earlier answers without scrolling.
5. **Header always shows** report type (e.g. **2–4 Unit**, highlighted chip), borrower/client name, subject address, status (Draft/Signed), and live problem counts.
6. Status bar: save state ("Saved · 2 s ago"), problem counts, current section, zoom.
7. Keyboard: Ctrl+S save, Ctrl+G go to field, F8/Shift+F8 next/previous problem, Ctrl+Tab next section, Ctrl+K command palette (search any field/section/action).

---

## 4. Review Master & problems — fix while you see the report

Reference: `screenshots/04-review-master-covers-report.png`.

- Problems live in a **side panel next to the report**, never a full screen covering it.
- Clicking a problem **scrolls to and highlights the exact field** (and opens the right unit/comp column).
- Keep an "All problems" view: filter by Fatal/Warning/Info/Schema, group by section, search.
- **Live**: the list updates as fields change.
- **Only applicable rules count.** A rule on a field that is hidden/not applicable for this report type must not count. (Today 143 fatal on an almost empty 2–4 unit report — most are fields that should not exist.)
- Every field with a problem shows a red/amber marker inline with a **plain-English explanation** and the H-1 rule id.
- **"Fix this" must be real**: either an automatic correction (format, date, computed value, obvious typo with a suggested value the user confirms) or a jump to the field. Never a no-op.
- **Real bug seen in screenshot:** XSD fatal — `AMENITY_CATEGORY_DETAIL` "not expected, expected AMENITIES" (lines 683, 1110). The XML writer emits amenity elements in the wrong order/parent. Fix in `engine/uad/edit.py` (schema-order writing), add a regression test, and scan for the same class of error in every repeating group.

---

## 5. Show only what applies — dynamic sections

Owner saw: **Project Information** on a two-family report with blank Yes/No answers and no way to remove it; dwelling style questions that don't apply; Subject Listing fields still shown after choosing **None**; renewable energy rows shown when there is none; "reasons illegal" asked when zoning is legal.

Rule: **visibility is generated from B-1 display rules and C-1 conditions** (`engine/uad/report/rules.py`), never hand-coded per field.

- Report type (SF, Condo, Co-op, MH, 2–4 unit, etc.) and earlier answers drive which sections/fields appear.
- Examples to verify: Project Information only for condo/co-op/PUD where required; Subject Listing "None" → hide status/type/ID/data-source details; Zoning "Legal" → hide reasons-illegal; No renewable energy → hide component/ownership/financing rows **and the matching comparable-grid rows**; same for wind, solar, building certifications, efficiency rating.
- Each section header shows **Required / Optional / Not applicable** for this report.
- Changing report type re-evaluates the **whole** report; hidden values are kept (not deleted) but excluded from output and from problem counts, with an undo.
- Section navigator: N/A sections greyed with a "skip" tick.
- Test against all 12 D-1 samples: nothing a sample needs may be hidden.

---

## 6. Smart, fast data entry (rules-based, not AI)

### 6.1 Inputs
- **Dates**: type `11112026` → `11/11/2026`; slash auto-inserted after MM and DD; also accept `11/11/26`, `t` = today. Validate real dates.
- Phone, ZIP, APN, currency (`$`, thousands), sq ft, percentages: auto-format as you type.
- Every Yes/No = one keystroke (Y/N). Every dropdown = **type-ahead combobox** (type 2 letters, Enter). Tab order follows the visual order.

### 6.2 Dropdown fatigue
- **Learns per appraiser**: preselects the most-used value for each field (local frequency stats), shown as a suggestion (light grey) that Enter/Tab accepts.
- **Defaults from template** override learned values.
- **Bulk-apply**: set one value across a row (e.g. all units, all comps).

### 6.3 Templates
- Appraiser saves any report (or chosen sections) as a **template**: appraiser/company info, license, typical commentary (Highest & Best Use, market, scope, conditions), common defaults.
- New report → choose template → those fields prefilled; rest blank.
- Template manager: create, rename, duplicate, delete, export/import (share in firm).
- **Comment library**: reusable paragraphs per section, insertable with a shortcut; recurring commentary stays until the user changes it.

### 6.4 Enter once, flow everywhere
- A fact entered once fills every place that needs it (subject address → map, grid, exhibits labels; units → grid; contract price/date → sales contract and grid; market data → market section and comps).
- Show a small "linked" icon so the user knows where a value is used.

### 6.5 Validation as you type
- Inline warnings (not blocking) for: name mismatch between borrower / owner of public record / seller, impossible dates (signature before inspection), GLA total not matching unit sum, comps sold after effective date, etc.
- Each warning: what is wrong, why (rule id), suggested fix, one-click apply.

---

## 7. Repeating groups — add / delete everywhere

Owner saw: only one borrower, one seller, one owner of public record; utilities have one extra placeholder with no add/delete; influences (e.g. Busy Road) lack proximity / impact / comment; "Name this row" rows spawn by themselves in the comparable grid (`screenshots/02-name-this-row-spawning.jpg`, `03-units-grid.jpg`).

- **Every** repeating group defined by the schema gets **+ Add** and **× Delete** (with undo), up to the schema maximum: borrowers, sellers, owners of public record, intended users, utilities (electric/gas/water/sewer/other), site influences, view factors, renewable energy components, building certifications, units, comparables, rentals, exhibits, custom grid rows.
- Each may also be **empty** when the property has none (e.g. no borrower on a purchase listing, seller only).
- **Influences** include all spec fields: type, **proximity**, **impact (beneficial/neutral/adverse)**, **detail/comment**.
- **Custom grid rows**: only created by an explicit + button; never auto-spawn a blank "Name this row". Row name field must look editable (proper text box with placeholder), delete button on hover.
- Audit every group against the GSE subschema cardinality.

---

## 8. Specific section fixes (each one → check all similar sections)

| Area | Problem | Required |
|---|---|---|
| Vehicle storage / Garage | Garage does not save; no **garage size (sq ft)** | Fix persistence; add size and spaces per spec; test round-trip. |
| Subject Listing | Data Source dropdown does not select | Fix; then **test every dropdown and Yes/No in the app saves and reloads** (automated). |
| Exhibits | Adding takes 2–3 s; title is a plain label | Instant add (§1); title is a real editable text box with placeholder ("Type exhibit title…"), category dropdown, drag to reorder, multi-file drop. |
| Location Map | "Generate map" → "unknown error"; **Save to report does nothing** | Find root cause (see `engine/app/ui/map/`); show real error messages; after Save the map appears immediately in the report and survives reload, PDF and ZIP. Add an end-to-end test. |
| Sales comparison map | No confirm on remove; no side list | Side list of subject + comps (add/edit/remove listing, drag order), confirm before remove, Save to report. |
| Units side by side | Slow to render | Virtualise the grid; render < 150 ms. |
| Rentals / Income | Confusing; asks for fields not in UAD 3.6 | Rebuild strictly from spec (B-1/C-1/A-1) — only the fields 3.6 defines, in its order. |
| Signature | Shows **Supervisory** appraiser although not chosen | Supervisory fields appear only when the user adds a supervisor. Audit similar "appears without being chosen" cases. |
| Signature quality | Pixelated | Pressure/velocity-sensitive smooth strokes (e.g. perfect-freehand style), vector (SVG) storage, crisp at any zoom and in PDF. Saved signatures per appraiser profile. **Cryptographic signing**: sign the delivered package/XML hash with the appraiser's key, show verification status. |
| Quality/condition checkboxes | Not centered (`screenshots/05-checkbox-misaligned.png`) | Pixel-check every checkbox in editor, preview and PDF; add a visual regression test. |
| SmartAdjust | Owner does not want it as is | Replace with the Adjustment Worksheet (§11). |
| "Property Data Report" etc. | Owner unsure why some sections exist | **Cross-verify every section/field against C-1 and B-1.** Remove anything not in UAD 3.6; list removals in HANDOFF with the spec reference. |
| Market section | Manual typing of metrics | Auto-fill sales/listing metrics (median price, DOM, absorption, list-to-sale) from uploaded MLS/market files and comps; field to describe market area boundary. |

---

## 9. Sketch panel (new, built-in)

References from the owner: `screenshots/06-sketch-ref-aci-main.png`, `07-sketch-ref-angles-symbols.png`, `08-sketch-ref-report-output.png` (ACI Sketch). Match its ease of use with a modern look; also research Apex / RapidSketch conventions.

**What the references show — build all of it:**
- **Workspace**: large grid canvas; multiple sketches open as **tabs** (Untitled1, Untitled2…); right dock with **Labels** list (Atrium, Attic, Balcony, Bath, Bed, Bedroom, Boiler Room, Bonus, Breakfast, Carport, Closet, Covered Patio/Porch, Deck, Den, Dining, Driveway, Elevator, Enclosed Porch, Entrance, Exercise, Family, Finished, Fireplace, Foyer, Front Porch, Game Room, Garage, Great Room, Guest House, Gym, Half Bath, Hall, Kitchen, Living, Wet Bar, Washer/Dryer…) and **Symbols** library by category (Appliances: freezer, washer, combo W/D, stove, water heater, grill, TV, furnace, refrigerator; doors, windows, stairs, fixtures). **New Label / New Symbol** to add custom ones. Drag a label or symbol onto the plan.
- **Status bar controls**: Measurement (Standard feet/inches or Decimal), Precision (feet / inches), **Angle snap** (5°, 15°, 45°, 90°), Grid show/hide.
- **Walls**: each segment shows its **length label** on the line; red vertex handles, blue mid-point handles (drag to move a wall, click to split); **angled walls** with auto-computed length (e.g. 7.07 ft); **curved/arc walls** (bay, rounded ends) with correct area.
- **Areas**: each closed shape shows name + **[Area: N ft²]** live. Areas can **nest** (garage inside the footprint) and be **subtracted** — dashed outline = open-to-below / deduction (e.g. Atrium −337 ft² inside Second Floor).
- **Doors** drawn as swing arcs on walls.
- **Report output** (ref 08): all floors laid out on one sketch page, each with its title (First Floor, Second Floor, Attic, Basement) and area under it, room labels inside, dimensions on every wall, clean black-and-white lines; auto-fit to the page; multiple pages if needed.

**Our baseline on top of that:**
- Opens from the ribbon (Sketch tab) in its own large panel/window.
- Draw by keyboard vectors (e.g. `R20 U15 L20 D15`) **and** mouse; snap to grid/angles; edit walls, move, rotate, mirror.
- Labels: rooms, floors (1st, 2nd, basement, lower level, mezzanine), units (Unit 1, Unit 2…), garage, porch, deck.
- Symbol/furniture library (doors, windows, stairs, fixtures).
- Each area flagged **GLA / non-GLA**, **above / below grade**, **finished / unfinished**, and assigned to a **unit**.
- **Smart detection**: labels "Unit 1/Unit 2…" → multi-unit; "1st/2nd floor/basement" → single family; basement defaults to below-grade; garage/porch defaults non-GLA. User can override.
- **Area table** under the sketch (like ACI): per floor and per unit — dimensions, area, GLA included or not, totals.
- **Save to report**: inserts the sketch image into the Sketch exhibit **and** fills GLA, finished/unfinished above and below grade, room/bed/bath counts per unit in the report and grid. Re-saving updates, never duplicates.
- Shortcut keys documented in an in-app cheat sheet.

---

## 10. Offline document intelligence (no API key)

Drop zones:
- **Subject**: public record / tax card, MLS sheet, prior appraisal, engagement letter / order.
- **Contract** — asked only if assignment is a purchase; separate upload.
- **Comparable 1…N**: one drop zone per comp; accepts multiple files each. Tag each comp **Sold / Active / Pending / Rental** (auto-detected, user can change).
- Comp count is dynamic: dropping more files adds comp columns; **+ Add Comparable** after the last comp; remove with confirm; drag to reorder (grid and adjustments follow). Default 3–4 sales, but never fixed.

Pipeline (hybrid, fastest-first):
1. **Rule-based parsers** for known layouts (MLS sheets, assessor cards, common contract forms) — exact, instant (~70–80 % of fields).
2. **OCR + layout/checkbox detection** (PaddleOCR via ONNX) for scans and images; document-type classifier.
3. **Small local LLM** (Qwen/Phi via llama.cpp, 1–4B, CPU) only for leftovers: handwriting, free text, odd formats. 8 GB RAM minimum, 16 GB recommended; model is a one-time ~2–3 GB download, optional.

Every auto-filled value: **confidence colour** (green/amber/red), **source** (file + page), and a "review auto-filled" list before sign-off. Nothing invented; unknown stays blank and flagged. Runs fully offline; no document leaves the PC.

---

## 11. Adjustment Worksheet (replace SmartAdjust)

Port the logic — **not the code imports** (products stay separate per `_work/GOAL.md`) — from `Mohit-rajput-mr/kech-3.6-wintotal-mod-autofill-agent`: `total-bridge/bridge/worksheet.py` and `total-bridge/bridge/adjust.py`.

- Green marker beside each adjustable grid row opens its worksheet: **$ per unit, threshold, rounding**; per comp shows difference, $ adjustment, line %, adjusted price. OK fills **all comps at once**.
- Worksheets: GLA, site, age (year built), bedrooms, baths (half = ½ rate), garage spaces (driveway/carport = 0), above-grade nonstandard & unfinished, below-grade finished/nonstandard/unfinished, basement presence, outdoor living, cooling, design, market exposure (% of list for listings/pendings). Per-unit lines on 2–4 unit reports.
- Formula: `(subject − comp) × rate`, `0` when `|diff| ≤ threshold` (the threshold gates the whole difference), rounded to step.
- **Rate profiles**: ship "Single family (18 North)" and "Multi-family" defaults from `adjust.py`; user can edit, create, switch; last used becomes default; **Adjust all** applies a profile in one click.
- Shows the math for reviewers; net/gross % and adjusted price recomputed live.
- Signed report: read-only.

---

## 12. Comparables editing view

- All comps **side by side in one horizontal row** while editing (Comp 1, 2, 3, 4, 5… with **+ Add Comparable** at the end), frozen subject column and row labels, horizontal scroll.
- Preview / PDF / ZIP still paginate comps exactly as C-1 (3 per page etc.).
- Hide grid rows not used by subject or any comp (e.g. renewable energy when none) — editing view only; output follows spec.

---

## 13. Everything that "saves to report"

Map, sales map, sketch, exhibits, photos, market charts, signature, worksheet results: one shared pattern —
1. Result visible instantly in the report.
2. Toast with ✓ and "Go to it".
3. Survives reload, appears in preview, PDF, `mismo.xml` and ZIP.
4. End-to-end automated test for each.

---

## 14. Things the owner has not hit yet — check and fix proactively

- Undo/redo across the whole report (Ctrl+Z/Y), including deletes of rows/comps.
- Crash/power-loss safety: autosave journal; reopen restores last state.
- Multi-monitor: remember window positions; clone windows on second screen.
- High-DPI and 125/150 % Windows scaling: no blurry text or misaligned boxes.
- Large reports (50+ photos, 8 comps, 4 units): still within performance budget.
- Offline: everything works except map tiles/address lookup, with clear messages.
- Accessibility: full keyboard operation, visible focus, readable contrast in light/dark themes.
- Copy/paste a whole comp or unit; duplicate a report; "start from previous report at same address".
- Version history per report with diff and restore (the History tab must be useful).
- Locale safety: currency and dates always US format in output regardless of PC settings.
- Every button wired to real state (no fake controls) — add a test that clicks each ribbon command.

---

## 15. Definition of done (per item)

- Implemented in the desktop app **and** shared with web where applicable.
- Harness passes on all 12 D-1 samples (`python engine/tests/harness.py 12`), 0 XSD errors on samples.
- New tests added (round-trip, visibility, save-to-report, performance timings).
- `TASKS.md` closed with evidence; `AI_HANDOVER.md` §4–5 and `_work/HANDOFF.md` updated in the same commit.
- Screenshots before/after saved under `_work/ui/` for the owner.

## 16. Suggested order

1. Tauri shell + sidecar + ribbon + dockable panels + split view (biggest visible win).
2. Local-first edits + instant exhibits (speed).
3. Review side panel + click-to-field + applicable-only counting + XSD amenity fix.
4. Dynamic sections/visibility from B-1; spec cross-check; remove non-3.6 content.
5. Repeating groups add/delete; section fixes table (§8); save-to-report pattern (§13).
6. Smart inputs, learned defaults, templates, comment library.
7. Adjustment Worksheet.
8. Sketch panel.
9. Offline document intelligence.
10. Signature upgrade + cryptographic signing; polish (§14).

Ask the owner only when a choice is irreversible or the spec is silent. Otherwise decide, record the decision and reason in HANDOFF, and continue.

---
*Assets in this pack:* `brand/` (icons, logos), `screenshots/` (owner's review captures).
*More owner chunks may follow (sketch references, further section reviews) — append them as new sections, do not rewrite completed ones.*
