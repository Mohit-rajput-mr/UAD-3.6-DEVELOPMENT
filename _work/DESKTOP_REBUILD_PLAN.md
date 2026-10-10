# Desktop rebuild & operator-experience overhaul: the plan

Owner's brief, 2026-10-10: `_work/owner/2026-10-10-desktop-rebuild/UAD36_DESKTOP_REBUILD_PROMPT.md`.
Their screenshots sit beside it in `screenshots/`. The brand assets are in `brand/` at the repo root.
**More owner chunks will follow.** Append each as a new section at the end of
this file, copy it into `_work/owner/<date>-<topic>/`, and register its items.
Never rewrite a completed section.

This file is the map for that brief:

- what the owner wants;
- what already exists;
- the decisions taken, and why;
- the order of work;
- the live status of every item.

`TASKS.md` holds the evidence for each item. `AI_HANDOVER.md` §5 names the
item in progress.

## 1. The situation in plain words

The owner is a working appraiser who fills several UAD 3.6 reports a day.

**What exists today.** The platform is a web editor plus an engine:

- `engine/` holds MISMO XML, the 728 H-1 rules, C-1 layout and B-1 display
  rules. It produces `appraisal.pdf` + `mismo.xml` + `Images/` in a ZIP that
  is faithful to the 12 D-1 samples.
- It runs live on Vercel. The appraiser's browser lays the report out, and
  since T-1033 it also draws the PDF.
- It also runs as a Windows "desktop edition": the same web editor inside an
  Edge app-mode window (`desktop/launcher.py`), installed by
  `desktop/build.py`.

**What the owner found**, filling a 2-4 unit report on the Windows build:

- It feels like a website. Panels eat the screen and the report is a thin
  strip.
- Actions take 2-3 s.
- Every dropdown has to be clicked separately.
- Sections that do not apply still show. 143 fatal findings show on an
  almost empty report.
- Several "save to report" actions do nothing: the location map, the garage,
  the listing data source.
- Rows spawn by themselves in the grid ("Name this row").
- A supervisor appears that nobody added.
- Checkbox outlines are off-centre.
- There is an XSD error in the amenities.

They want a fast, native-feeling, operator-first desktop application. It must:

- fill reports quickly: smart inputs, learned defaults, templates, repeating
  groups, an adjustment worksheet, a built-in sketch, offline document reading;
- keep every output exactly as UAD 3.6 defines it.

The guiding principle: **the editor is a form filler, not a photocopy of the
printed page; the preview, PDF and ZIP follow the official layout exactly.**

The owner also asked that every WinTOTAL feature they rely on be present. The
inventory is `knowledge/competitors/WINTOTAL_UAD36.md`: all rows are built,
have or skip, with reasons. This brief adds the items WinTOTAL has that we do
not:

- ribbon;
- sketch;
- worksheet per grid row;
- QuickList-style learned values;
- templates;
- split view.

## 2. Decisions (reversible; recorded so nobody re-derives them)

| # | Decision | Why |
|---|---|---|
| D1 | The new shell (ribbon, dockable panels, focus mode, problems side panel, shortcuts, split view) is built **into the shared editor** (`engine/app/ui`), so the web edition and the desktop edition get it in the same commit. | Both editions already run the same editor. Building the shell once is the brief's own "write each screen once". |
| D2 | **React + TypeScript + Vite** come in as a shared package (`ui-shared/`) for the **new large screens** first: Sketch panel, Adjustment Worksheet. Existing screens migrate one at a time, each with tests. No big-bang rewrite. | The in-report editor (`flow.EDIT_JS`) lives inside the rendered report, which must stay the server's own HTML. The current editor carries dozens of verified fixes (CATALOG E-0xx); a rewrite would drop them. The built output is committed, so Vercel needs no build step. |
| D3 | **Tauri 2** replaces the Edge app-mode launcher. The Python engine (embedded CPython, as `desktop/build.py` packs it today) becomes the sidecar, and the Tauri window shows the local server. It is built from Linux with `cargo-xwin` + NSIS if that proves workable here; otherwise on a Windows runner. The current installer stays the shipped one until the Tauri build is verified on Windows. | Instant start, native window, menus, drag-drop and updater, without changing the engine. A code-signing certificate (~$200-400/yr) removes SmartScreen; it is flagged to the owner, not a blocker. |
| D4 | "Only applicable rules count" never silences an H-1 rule that applies. It removes findings on fields and sections B-1 does not show for this report's answers. Every D-1 sample keeps exactly its findings. | Specs are the authority; validators are validated on the 12 samples. |
| D5 | Visibility comes from B-1 display rules and C-1 conditions (`uad/report/rules.py`, `spec/section_display.json`), never per field. In edit mode a hidden gated field collapses to its gate question. Values are kept, excluded from output and counts, with undo (as T-1057 does for the optional sections). | The brief §5; the CLAUDE.md non-negotiables. |
| D6 | Offline document intelligence is **desktop-only** (PaddleOCR via ONNX, optional local Qwen/Phi via llama.cpp). Rule-based parsers (`uad/ingest/`) run on both editions. | A serverless function cannot hold the models; the owner wants no document to leave the PC. |
| D7 | The Adjustment Worksheet ports the **logic** of `total-bridge/bridge/adjust.py` (and `worksheet.py` from the owner's `kech-3.6-wintotal-mod-autofill-agent` repo), not its imports. The products stay separate (`_work/GOAL.md`). It replaces SmartAdjust (T-1059). | Owner: "SmartAdjust ... does not want it as is". |

## 3. Order of work (the brief's §16, kept)

1. **Phase 1 — the bugs the owner hit.** XSD amenities (T-509), applicable-only counts (T-506), "Name this row" (T-1070), garage (T-1071), listing data source + every dropdown/Yes-No round trip (T-1072), location map (T-416), supervisory shown unchosen (T-1074), checkbox outline (T-125), visibility cases (T-1066).
2. **Phase 2 — the shell.** Branding (T-271), ribbon (T-272), dockable panels (T-273), focus mode (T-274), header/status bar (T-276), shortcuts + command palette (T-277), problems side panel + click-to-field (T-505), inline markers (T-507), real "Fix this" (T-508), split view (T-275).
3. **Phase 3 — speed.** Local-first edits, instant exhibits (T-282), units grid virtualised (T-283), performance budget measured (T-1064).
4. **Phase 4 — what applies.** T-1066/T-1067 completed; spec cross-check, removing non-3.6 content (T-126).
5. **Phase 5 — repeating groups and section fixes.** T-1068, T-1069, rentals (T-1073), exhibits, sales map (T-417), market auto-fill (T-1075), the save-to-report pattern (T-285).
6. **Phase 6 — fast entry.** Smart inputs (T-278), learned defaults (T-279), templates (T-280), flow-everywhere (T-281), validation as you type (T-510).
7. **Phase 7 — Adjustment Worksheet.** T-1081..T-1083; comparables side-by-side view (T-1084).
8. **Phase 8 — Sketch.** T-1076..T-1078.
9. **Phase 9 — offline document intelligence.** T-1079, T-1080.
10. **Phase 10 — signature, desktop shell, polish.**
    - Signature upgrade + cryptographic signing (T-284).
    - Tauri shell (T-1063), shared package (T-1065).
    - §14: T-286..T-293.

## 4. Status

Kept current as work lands. `TASKS.md` holds the evidence.

| Task | Item | Status |
|---|---|---|
| T-1033 | PDF + ZIP on the live site (B5) | done 2026-10-10 (be14124) |
| T-509, T-506, T-1070, T-1071, T-1072, T-416, T-1074, T-125, T-1066 | Phase 1 bugs | in progress 2026-10-10 |
| everything else above | | open |
