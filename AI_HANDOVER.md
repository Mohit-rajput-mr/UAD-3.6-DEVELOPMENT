# AI HANDOVER — read this first, every session, every agent

Several AI agents (Claude sessions, other assistants) work on this repository
one after another. A session can end at any moment — a credit limit, a
timeout, a closed tab. **This file is how the next agent continues exactly
where the last one stopped, with the same goal, the same approach and the same
behaviour.** If you are a new agent: read this whole file before doing
anything, then follow §7 ("How to take over").

If you finish a piece of work, update §4 and §5 of this file **in the same
commit** as the work. If you stop mid-task, write what you were doing in §5
before you stop. An agent that leaves this file stale breaks the chain.

---

## 1. The owner's aim (in their words, condensed)

The owner is a working appraiser. They want a **live, working UAD 3.6 report
form filler** on the web:

- It must **look the same as the official UAD 3.6 URAR report** from the GSE
  documentation (Appendix C-1 layout, D-1 samples, E style guide).
- An appraiser opens it, starts a report (blank or from a template/XML), fills
  every section, adds photos, exhibits (maps, market charts), comparables and
  adjustments, and gets out a **valid UAD 3.6 deliverable**: `appraisal.pdf` +
  `mismo.xml` + `Images/` in a ZIP — one canonical document, so the editor,
  preview, validation, PDF and XML never disagree.
- It must be **deployed and working live** on Vercel, with continuous
  deployment, protected by the passcode **`uad3.6`**.
- **No "Kech" branding anywhere** (owner, 2026-10-04). The software names
  itself "UAD 3.6 Form Filler".
- Wanted after the core works: a professional, modern, appraiser-friendly UI
  (glassmorphism card / admin-dashboard style), complete permanent
  documentation, a forensic audit of every section and field, regression
  tests, a second audit, and a final report.

## 2. What we (the AI) are trying to achieve — the main goal

**Make the live site do the whole appraisal job correctly, end to end, without
glitches**, and keep every claim provable:

1. Every page renders exactly like the official report (fidelity to D-1).
2. Every field saves, re-reads and validates (MISMO XML against the GSE
   subschema; H-1 compliance rules).
3. Photos, exhibits, comparables, maps, market charts all land in the report.
4. The deliverable ZIP is valid.
5. Nothing is invented: the official specifications are the authority
   (A-1, B-1, C-1, D-1, E, F-1, G-1, H-1, GSE subschema — under
   `specs/official/`). Never claim "Fannie Mae approved" or compliance without
   a test that shows it.

## 3. Where things are live

| What | Where |
|---|---|
| Live site | https://uad36-form-filler.vercel.app — passcode `uad3.6` |
| GitHub | `Mohit-rajput-mr/UAD-3.6-DEVELOPMENT` — **`main` auto-deploys to Vercel production** on every push |
| Working branch | `claude/keen-turing-3r26sh` (fast-forwarded into `main` after each verified fix) |
| Vercel | team `team_yLARSrJxmy8eba17j9vCfKRT`, project `prj_DAFzsrP7CsyJX3tG838oglSyqQ3l` (`uad36-form-filler`), region iad1 |
| Shared case store | Vercel Blob store `uad36-cases` (private); `BLOB_READ_WRITE_TOKEN` is injected by Vercel — never print or copy it |
| Entry point on Vercel | `api/index.py` → `engine/app/main.py` |

**Deploy = commit, run the checks, push to the branch, fast-forward `main`.**
No Vercel tool calls are needed to deploy. Use the Vercel connector only to
read build state and runtime logs (`get_runtime_logs`, `get_runtime_errors`,
`list_deployments`). This container cannot open vercel.app directly.

How the live site works (so you don't re-derive it):
- Vercel runs **several server copies**, each with its own `/tmp`. Cases live
  in the shared Blob store (`engine/app/durable.py`); the middleware in
  `engine/app/main.py` pulls a case before each request and pushes it after
  each change.
- Vercel has **no Chromium**, so the **appraiser's browser lays the report
  out** (client layout: `/layout/{kind}/galley` → measure →
  `/layout/{kind}/pages`). PDF export on Vercel answers 503 (needs a server
  with Chromium, e.g. Docker).
- Fonts: licensed Myriad Pro is not in the repo; open-licence substitutes with
  Myriad's published widths are used (`engine/uad/report/substitute_fonts.py`).
- Anything named by a content digest or used as a "is it current?" key must be
  **built deterministically and from content, never from file times** — every
  server copy must compute the same answer.

## 4. What the recent sessions finished (with evidence)

Most recent first. Each line: what, and how it was verified.

- **2026-10-10 — The live site makes the PDF and the ZIP (B5, T-1033;
  E-163, E-164).** `uad/report/pdfdraw.py`: the browser reports where it
  drew every glyph, rule and picture; the server writes the PDF with its own
  fonts and pictures, after checking the words against its own pages. PDF
  and ZIP download in 3.5 MB parts (Vercel answers at most 4.5 MB). On all
  12 D-1 samples it matches Chromium's PDF: same pages and characters,
  glyphs within 0.01 pt across and 0.13 pt down. `tests/test_client_pdf.py`
  passes 12 tests, including an end-to-end editor run with server layout
  off. Not yet clicked on the live site.
- **2026-10-04 — Second redesign (the one that stands).** The owner rejected
  the violet design ("shittiest") and sent new references: a dark wireframe
  with chrome/silver accents and glass cards, a bold grotesk "WEBSITE DEV"
  poster, an editorial light/dark site (white/black, "+ 01 / LABEL", two-tone
  headlines, solid ink buttons with ↗, sun/moon switch) and the Wallety dark
  dashboard. **The design language is: monochrome; Geist (SIL OFL, bundled in
  `engine/app/ui/fonts/`, served before sign-in for the gate); dark by default
  with a light theme switched in the header (localStorage `uad-theme`);
  "+"-prefixed tracked labels (`.eyebrow` — never `.lbl`, which the
  comparables grid uses for its cells); hairline rules; glass cards with a
  chrome edge; colour only for status (green/amber/red, with the word).**
  Tokens: CSS variables at the top of `index.html` (`[data-theme=dark|light]`).
  The report frame paints its stage in the theme colour (a transparent frame
  is drawn white by Chrome when colour schemes differ). Do not reintroduce a
  coloured accent. Screenshots: `_work/ui/redesign-*.png`.
- **2026-10-04 — Typed addresses save** (owner's property 186 8th St # 2B,
  Brooklyn, NY 11215 at 40.671292, -73.989409): `edit.split_address`;
  catalog E-076; `engine/tests/test_address_entry.py`.
- **2026-10-04 — First UI redesign (superseded the same day by the second, below the line above)** (owner: "entire design should be changed";
  references: glassmorphism card, admin dashboards, content-list UI). Only the
  application shell changed; the report pages are untouched. Passcode gate:
  frosted glass on navy with violet light (`engine/app/access.py` GATE). Home:
  dark navigation, four live status cards, searchable report list, import
  card, template cards (`showLaunch` in `engine/app/ui/index.html`). Editor:
  dark section rail, underline tabs, chip header with fatal/warning counts,
  card inspector; editor controls inside the report frame (Save / Save & Next)
  restyled from `flow.EDIT_JS`, not from `form.py`. Design tokens are the CSS
  variables at the top of `index.html` (accent `#6d5dfc`). Screenshots:
  `_work/ui/redesign-*.png`. Every element id the JavaScript uses is kept.
- **2026-10-04 — Instant updates and fast reload** (owner: "all updates should
  show instantly"). (1) The report frame's start-up script keeps the last
  layout per case in IndexedDB (`uad36-layout`) and shows it at once; when the
  case changed it shows the kept one and the editor lays the current one out
  behind it (`engine/app/api.py` CLIENT_LAYOUT_HTML). (2) A chosen/dropped
  photo is shown from the local file in 50 ms (`showLocal` in
  `flow.EDIT_JS`); removals fade at once; a slim moving line marks what is
  still being saved. (3) A change that arrives while a layout is in flight is
  remembered (`S.again` in `index.html`), never dropped. (4) `Renderer.key`
  uses media file *names*, not paths — two copies with different folders
  computed different keys and swapped forever. (5) `/fields` and the galley
  are cached per content version. Measured in Chromium against two server
  copies + shared store: reopen 0.02 s (was ~5 s), browser reload 0.27 s,
  photo visible 52 ms, saved photo laid out 2.7 s behind; 121 tests pass.
- **2026-10-04 — Audit branch merged with main's "Instant updates" work.** Pending the owner's merge of PR #1, `main` was not yet carrying slices 1-2; after the merge Vercel builds them. The Roof detail composer (T-124) is in as well.
- **2026-10-04 — Audit slice 2: grid fidelity** (E-073, E-074, E-075).
  (a) Grid cells compose as B-1 says (`Local Road | Asphalt`, `3 Miles SE`,
  `Driveway | 4 | Pavers` + a Garage line, enumeration order, address on two lines).
  (b) The Supervisory Appraiser certifications print only with a supervisory
  appraiser (B-1 p396; extractor fixed, regenerated specs; matches 12/12 official
  PDFs). (c) An empty grid cell prints an em-dash only where B-1's per-row
  sentence says so (`report/dashes.py`; exact dash count on 4 samples, was 2-6x
  over); Contract Price / Date subject values and the all-comparables row
  visibility fixed. Whole-report word diff vs D-1: 21411 -> 17706. Harness 87 pass
  / 0 fail; `test_report_rows.py` 27 pass. Golden baseline regenerated (+2 grid
  rows per sample: Contract Price / Date).
- **2026-10-04 — Audit slice 1: wrong data in repeated-row tables fixed** (E-071,
  E-072). Laying our SF1/MH1 pages beside the official PDFs showed the Exterior
  Features table printing the wall's comment on every row, and the Utilities
  table printing the water comment against Electricity and Gas. Cause: rows told
  apart by a label read only the first block. Fix: `form._label_blocks` /
  `row_instances`; C-1's clipped IDs (4.06 for 4.069, 4.05, 4.00, 20.00) repaired
  at load (`form._complete_clipped_ids`), which also removes two duplicate prints.
  Tests: `engine/tests/test_report_rows.py` (5/7 fail on the old code). Harness
  87 pass / 0 fail / 21 gap. New audit tools: `_work/audit/render_all.py`,
  `linediff.py` (whole-report word diff vs the D-1 PDFs; total is the number to
  drive down).
- **2026-10-05 — Owner's section-test bugs B1, B4, B7-B13 fixed** (E-079..E-083):
  sales contract saves (XSD maxOccurs, not plural names), alternate address
  (element/type alias), signature date (schema arcrole, orphan SIGNATORY reuse),
  Yes/No answers read as answered, grid totals computed from A-1 on every save,
  grid limits 3-24 / 1-24 / 3-24, report and section in the URL, package check
  agrees with export, adjustment type taken from the B-1 grid. Tests:
  `test_blank_writes.py`, `test_grid_math.py`, `test_comparable_limits.py`.
- **2026-10-05 — T-119 Level and Room Detail** (E-078): every level, B-1 rules,
  checked against all 12 published PDFs (`test_level_table.py`).
- **2026-10-04 — `docs/` reference set** (architecture, data model, rules and
  validation, report and PDF, comps/images/maps, import/export, persistence and
  deployment, testing, GSE vendor-recognition note), written from the code.
- **2026-10-04 — Docker image: server-side layout and PDF** (`Dockerfile`,
  `.dockerignore`, `DEPLOY_DOCKER.md`). Built and run here: `/healthz` 200,
  sign-in 303, sf1 case `report.pdf` 200, 6 pages, 8.0 s cold. A proxy CA
  goes in as a BuildKit secret, never into the image.
- **2026-10-04 — In-app dialogs replace the browser's alert/confirm/prompt**
  (`engine/app/ui/dialog.js`, `UADDialog`); 19 call sites converted in the
  editor, report frame and map tool. Guarded by
  `engine/tests/test_browser_scripts.py::test_no_browser_dialogs_in_the_editor`.
- **2026-10-04 — Blank reports no longer blocked by comparable numbering**
  (E-077: `PropertyOrdinalNumber` kept in `templates.IDENTITY`); all 12 blank
  templates: 0 schema errors. **Typed whole addresses split into A-1 parts**
  (E-076, `edit.split_address`; `engine/tests/test_address_entry.py` 9/9).
- **2026-10-04 — Second UI redesign (monochrome editorial)** is the one that
  stands: Geist fonts, dark/light theme, glass cards; the violet v1 was rejected.
- **2026-10-04 — Negative dollar amounts print as `$(10,000)`** (bind.py
  `format_value`, kind "amount"). Authority: B-1 Figure 22-5 (page 297 of B-1
  v1.4) and all 12 D-1 PDFs (121 x `$(n)`, 0 x `-$n`). Harness 87 pass / 0 fail.
- **2026-10-04 — Audit: no character falls back to a system font.** The MH2
  sample's "®" printed in a system font because the kerned fonts were subset
  to a hand-typed list; the set is now derived from the WinAnsi (cp1252)
  encoding, and the font cache key includes the build code. Harness over the
  12 official samples: **87 pass · 0 fail** · 21 gap (was 1 fail).
- **2026-10-04 — This handover file (`AI_HANDOVER.md`)** created at the
  owner's request and linked from `START_HERE.md`, `README.md`, `CLAUDE.md`,
  `_work/HANDOFF.md`.
- **2026-10-04 — Saves/photos/exhibits update the live report** (7d77174).
  The endless "Updating the report…" spinner is gone. Verified in Chromium
  against two server copies with one shared store: edit shown in 3 s, photo
  shown in 3 s; 121 tests pass. **Owner confirmed it works live.**
- **2026-10-04 — "Kech" removed everywhere** (fc16dbe, f57cd44). Vendor/product
  in exported XML is "UAD 3.6 Form Filler"; XML extension namespace is
  `urn:uad36:portable:1`; old files still import. Full scan: 0 occurrences.
- **2026-10-04 — Layout 500 on the live site fixed** (345ffb5): font-cache race
  and non-deterministic font bytes.
- **2026-10-04 — New blank report loads on the live site** (31a0cb1): shared
  durable case store. `engine/tests/test_durable.py` 9/9.
- **2026-10-04 — Continuous deployment from GitHub `main` working.**
- Earlier in the same effort: report renders without licensed fonts
  (substitutes), passcode `uad3.6` (PBKDF2 verifier in
  `engine/app/access.json`, never in client code), blank templates validate
  against the GSE subschema, case bundles (backup/restore), browser-side layout.

Full narrative and traps: last sections of `_work/HANDOFF.md`.
Task registry with evidence: `TASKS.md` (`python engine/tasks.py next`).

## 5. In progress right now / what to take over next

### 2026-10-10 (night) -- T-1085 worksheet inside the comparable grid: PARTIAL, take over here
- **Owner's addendum** (replaces DR §11):
  `_work/owner/2026-10-10-desktop-rebuild/ADDENDUM_11_WORKSHEET_IN_GRID.md`.
- **Built:**
  - green (+) on every adjustable sales-grid row and every per-unit/ADU line
    (flow.py "adjustment worksheets"); a MutationObserver re-adds it after a
    re-render;
  - Ctrl+J in a row, or the toolbar Worksheets list, opens the drawer. The
    drawer is docked where the inspector sits (index.html `worksheets()`,
    `body.ws-open`) and shows a live preview worked out in the browser
    (`wsCompute` ports `worksheet.line_amount`). OK writes, Cancel/Esc
    write nothing, manual lines have "Use worksheet", profiles plus Adjust
    all, and a signed report is read only;
  - auto-recalc: `Store.save_tree` → `worksheet.recalc`. Write routes return
    `recalculated`, and the frame relays out and flashes the moved cells.
    Hand-typed cells are marked manual (`worksheets.json`) and never
    overwritten.
- **Verified:** `tests/test_worksheet.py` passes 22/22, including recalc,
  manual, release, SF3 ADU positional amounts, and the preview, PDF,
  mismo.xml and ZIP carrying the amounts.
- **Not yet run (do next):**
  - a Chromium e2e of the icons on sf1 / condo / 2-4, including after adding
    a comp and a unit and after a relayout; Ctrl+J; drawer apply; ticked label.
    A starter script is in the session scratchpad and is not in the repo:
    write it as `tests/test_worksheet_grid.py`;
  - `python engine/tests/harness.py 12` and the full suite.
  Then `tasks.py done T-1085`.
- **Spec finding:** the UAD 3.6 rental and GRM grids define no adjustment
  rows, so the icons apply to the sales grid and its per-unit lines only.

### 2026-10-10 (evening) -- NEW OWNER BRIEF: desktop rebuild & operator experience (read this first)
- **Brief:** `_work/owner/2026-10-10-desktop-rebuild/UAD36_DESKTOP_REBUILD_PROMPT.md`,
  with screenshots beside it and the brand assets in `brand/`.
- **Plan, decisions D1-D7 and live status:** `_work/DESKTOP_REBUILD_PLAN.md`.
- **Tasks:** all 55 items are registered (titles start "DR§").
  `python engine/tasks.py list | grep DR`.
- **Order:** phase 1 = the bugs the owner hit (T-509, T-506, T-1070, T-1071,
  T-1072, T-416, T-1074, T-125, T-1066). Then the shell (ribbon, panels,
  problems side panel), speed, applicability, repeating groups, fast entry,
  Adjustment Worksheet, Sketch, offline document reading, Tauri.
- **More owner chunks will follow.** Append each to the plan as a new
  section; never rewrite completed ones.

### 2026-10-10 (later) -- the live site makes the PDF and the ZIP (T-1033 / B5; E-163, E-164)
- **Before:** `report.pdf` answered 503 on Vercel, and so did the ZIP. The
  live site could not deliver.
- **Now:**
  - Open PDF / Export ZIP lay the preview out in a hidden frame and run
    `pdfdraw.DISPLAY_JS`, then post it to `POST /api/cases/{id}/report.pdf`.
  - The server checks the words against its own pages and writes the PDF.
    It is kept per render key, locally and in the Blob store.
  - Downloads come in parts. Hosts with Chromium are unchanged.
- **Trap (E-164):** never answer a case route with `"stale": true` unless
  you mean the vault protocol. vault.js then restores the case, which wipes
  its folder.
- Work branch this session: `claude/sleepy-hypatia-e2pzcn`.
- Full suite: 851 passed, 10 skipped, 0 failed (839 before + 12 new).
- Desktop installer not rebuilt: the desktop edition prints with the system
  Edge, so nothing here changes what it does. Rebuild it with the next
  desktop-facing change.
- **Next:**
  - The owner tries Open PDF and Export ZIP on the live site.
  - Then B15 (T-258), B16, page counts vs D-1, T-120 / T-121.

### 2026-10-10 -- rent schedule units, legal description image, Add list, Show/Hide sections; eight unit rules checked (T-1058, T-1060, T-1056, T-1057; E-161, E-162)
- **T-1058:** a switch over the Rent Schedule chooses which units it lists
  (A-1 UnitIncludedInRentScheduleIndicator; H-1 UAD1159). Setup includes every unit.
- **T-1060:** the legal description can be an image (B-1 pp121-122). It prints full width under the bar
  (Appendix E p38), clears UAD1043 and is delivered as IMAGE "LegalDescription".
- **E-161 (important):** 8 required dwelling-unit rules (bedrooms, baths, quality and condition
  ratings, defects…) never fired. The H-1 tokenizer swallowed a ")" and `selects` was over-applied.
  Fixed and validated on all 12 samples (`tests/test_rule_parsing.py`).
- **T-1056:** the inspector's **Add to <section>** list names every add control in the current
  section by its table ("Row: Site Influence") and opens it (`tests/test_add_list.py`).
- **T-1057:** Show / Hide for the three sections B-1 switches on by their own question (Disaster
  Mitigation, Energy Efficient and Green Features, Sales Contract). Hiding moves their other answers
  out of the XML into `hidden.json` (case folder); showing, or answering the question, puts them back
  exactly. `uad/optional_sections.py`, `tests/test_optional_sections.py`.
- **E-162:** before this, answering No / None to one of those questions removed the whole section,
  question included, from the editor.
- Desktop installer rebuilt as **1.2.0** (`downloads/desktop/`, test_desktop 15/15). Full suite 840 passed, 9 skipped.

### 2026-10-09 (later) -- WinTOTAL-inspired editor features; a shipped CSS break fixed (T-1051..T-1054, T-270; E-155..E-157)
- The owner uploaded 36 screenshots of their WinTOTAL UAD 3.6 (`Competitors 3.6 software features pics/`;
  they hold **real case data**: keep them out of anything that ships; `.vercelignore` excludes them).
  Inventory and our status per feature: `knowledge/competitors/WINTOTAL_UAD36.md`.
- Built and verified in Chromium (create → click → type → save → XML):
  - **Field guidance** in the inspector: on focus, the field's A-1 requirement (Required / Required when
    / Optional, with its scope "for the Appraiser Supervisor"), conditions as sentences
    (`uad/conditions.py` reads all 568 A-1 conditions), definition and format, and every H-1 rule on
    the field with its live status. `GET /api/cases/{id}/guide/{fid}`. Agrees with Review Master on
    all 12 D-1 samples (`tests/test_field_guide.py`).
  - **Show problems** (toolbar): outlines every field an H-1 rule faults; clears once fixed.
  - **Comment library** (toolbar): saved snippets, click or Alt+1..9 inserts at the caret.
  - **Counter** on comments, from the field's A-1 String length.
- **E-155:** the desktop commit shipped `index.html` with an unclosed CSS rule. The report frame was
  drawn at 300 × 150 px and the inspector was unstyled on the live site. Fixed; every stylesheet is
  now brace-checked by a test.
- **Square shell:** the owner's standing preference (square, ruled, no pills or rounded cards) is
  applied shell-wide by one rule at the end of `index.html`'s style, and to the editor's own controls in
  `EDIT_CSS`. The printed form is untouched.
- Also built the same day, each tested on the 12 samples and in Chromium:
  - T-1055: comparable menu Move left / right and Copy, plus editor-only red/green adjustments.
  - T-1059: SmartAdjust panel (the owner's 18 North / multi-family rates, editable; nothing is written
    until Apply).
  - T-1061: additional certifications. They could not be saved at all before (E-159).
- **E-160 (important):** the client layout sometimes measured a half-loaded galley, so a report did
  not refresh after an edit or came out cut short. Fixed in `CLIENT_LAYOUT_HTML` `frame()`. It hit web
  and desktop alike.
- Desktop installer rebuilt as **1.1.0** (`downloads/desktop/`). Full suite 807 passed, 9 skipped.
- Next (in TASKS.md):
  - T-1056, T-1057, T-1058, T-1060: done 2026-10-10 (above).
  Rebuild the installer after shipped changes (`git add` first, then `python desktop/build.py`, then
  commit `downloads/desktop/`).

### 2026-10-09 -- faster editor; desktop edition for Windows with Download product (T-1049, T-1050)
- Opening is faster (8.6 → 5.7 s first open, 15–19 → 3.6 s reopen): E-150..E-152 in the CATALOG.
- `desktop/`: a per-user installer (24 MB) that asks for the licence key first; the app runs locally in
  an Edge window; the PDF comes from the system Edge (`uad/report/cdp.py`, output identical to Playwright).
- Download product: the header button and the public `/download` page; the key gives a ticket; the
  installer is served in parts.
- The licence key lives only as a verifier (`engine/app/license.json`); change it with
  `python engine/app/license.py set-key`.
- Next: confirm on a real Windows PC; code-signing certificate to silence SmartScreen; the competitor
  screenshots, once uploaded (the folder `Competitors 3.6 software features pics/` is still empty).

### 2026-10-08 -- setup dialog redesigned to the platform's theme (T-268)
- "What are you appraising?" now uses the shell's glass sheet, "+" labels, ink selection, icons,
  switches and a pinned footer. Same element hooks as before.

### 2026-10-07 (later) -- rentals per unit, instant adds, visibility, rent totals (E-146..E-148)
- Multi-family: the panel "Which rental comparable is compared with which subject unit"
  (uad/rentals.py, /rentals/pairs) gives each unit its own rental grid.
- Adds show at once (optimistic ghost rows); one picker open at a time; the not-used address is typed.
- Hints darker; the focused field is white with a blue ring and a blue caret.
- Rent schedule totals are calculated (uad/rent_math.py on save, flow.py rentTotals live) and read-only.
- Next: picker sweeps for single_family / cooperative / manufactured; the owner's visual review.

### 2026-10-07 -- setup page first, rental for multi-family, dropdowns, signature, typing (E-144, E-145)
- New report asks what is being appraised (5 kinds, units, approaches) and starts on that D-1
  structure. "Report setup" in the editor changes it later.
- Unit and building defect pickers save (they were refused). Fixed-row second answers save.
- Signature pad (draw / type / upload) prints on the signature line. Lists can be typed into.
- Next: fix reshape INTO condominium (schema findings); re-run the picker sweep per kind (fresh
  login each); continue the owner's visual review.

### 2026-10-06 (night) -- editor looks like a form you fill (T-260, E-140) + MH1 Site (E-139)
- Each input kind has its own look (`data-k` from `form.input_kind`, which uses F-1/B-1 data):
  - text: cream "Type…";
  - list: blue pill "Select";
  - $, # and %: green, right-aligned;
  - dates: violet "MM/DD/YYYY".
- The comparable grids look writable (hint per cell, "±$" adjustments).
- Yes/No questions carry their name and captions. Heading placeholders are named. The legend
  sits in the toolbar.
- MH1 Site differences are closed. The B-1 Site Valuation gate was dropped because D-1 MH1
  overrules it.
- Next: review the remaining editor sections for anything that looks off; continue the secdiff
  backlog listed in _work/HANDOFF.md.

### 2026-10-06 (later) -- the remaining sections against the official PDFs (E-112..E-126)
- Dwelling Exterior: rear / defect photos placed per building (`_positional_image`,
  `_defect_section`); buildings and their units interleave; "Brick | Wood" (every block in a
  component row); Room Summary "1 - Family Room"; captions "Category - Caption".
- Unit Interior: Corner Unit "No"; rules read outside the unit (`rules.values_of` climbs);
  `field_rule_hides` reads "Display checkboxes ... when" and applies to template tables --
  validated on 12/12 samples (ADU, Accessibility, Ground Rent, Foundation, Revision table).
- Amenities drawer (category from B-1 14.002, Detail composed, add / remove rows).
- Prior Sale and Transfer History drawer (subject and comparables, B-1 pp284-286).
- Rental Information: rent schedule per unit with Actual / Market income columns; the
  comparables strip; one rental grid per subject unit (A-1 pairing arcrole), scoped writes.
- Grid editor now works for rental and GRM grids (it was hard-wired to sales: dead control).
- GRM: Sale Date, "~$2,300", no all-zero ADU row; the income formula line; comparable photo
  exhibits for rental and GRM.
- Data sources tied by A-1's ArcRoles sheet (Project, Cost Approach); Land Comparables a line
  each; every revision prints; an empty Supplemental Information no longer prints.
- Evidence: tests/test_site_and_defects.py (~40), test_rooms.py (amenity, rental scoped write);
  Chromium click-through of the rental strip and per-unit grid editors.
- Sales grid (E-127/E-128): groups repeat per unit / dwelling / ADU / outbuilding and read
  inside their own block; rule-named instances (Walls and Ceiling vs Flooring); validated row
  rules. Row labels now match every official grid except rows B-1 leaves to "relevant to the
  analysis" (no A-1 data point records relevance -- see CATALOG E-128 "Known limit").
- Compliance (E-129): `uad/compliance_shapes.py` executes H-1 rules by sentence shape; 107 of
  the 171 "review" rules now run (none faults a D-1 sample; each fires on a broken copy --
  tests/test_compliance_shapes.py). The other 64 run through `uad/compliance_checks.py`
  (E-130): one function per Message ID, with inspections, signatures and unit pairs read
  through their arcs. **All 171 now execute** (T-1044 done, 78 tests).
  `rules.CLAUSE` no longer swallows a clause-joining OR. Rental analysis now prints two
  units to a line (T-1043). Harness 87/0/21: the only gaps are fonts and page counts.
- Next: page counts vs D-1 (the harness 'package' gaps); the editor's usability items
  (B15 gate hints, B16 photo category).


### 2026-10-06 -- tables read every block; Site and Reconciliation fidelity (E-102..E-111)
- K&B / Interior Features / levels drawers; "+ Add flooring" and row delete; arcrole data
  sources written with their link (`uad/sources.py`); unit defects read at property level.
- Two regexes held a raw backspace byte instead of `\b` (commentary categories, agency gate):
  Site Influence / View / Water Frontage / Sketch commentary now print.
- Template-row tables read every block of the subject; Site Influence proximity / impact print.
- Summary / Reconciliation defects grouped per structure and unit (B-1 p377), rows by Feature
  then Location; matches the official 2-4, SF1, Condo1, MH1 PDFs. Corner Unit prints "No".
- Evidence: tests/test_site_and_defects.py (8), test_rooms.py (23); suite only the 3 known
  failures; harness 87/0/21. Scorecard (scratchpad tool) missing 5364 -> ~5190.
- Next: scorecard-driven fidelity (Summary 763 missing, Market 293, Dwelling Exterior 253,
  Outbuilding 208, Amenities 193, Rental 188), then the 171 unexecuted H-1 rules (T-1034).


**Restricted Appraisal Update and Completion Report — live in the editor
(2026-10-05, E-089..E-097, T-1036).** A case's kind is its own `DocumentType`
(ValuationUpdate / ValuationCompletion); `Case.to_json()["kind"]` mirrors it
from the template marker `report:<kind>`. `uad/report_types.py` holds both
kinds from `spec/report_types/{update,completion}.json` (built by
`uad/spec/build_report_types.py` from A-2..H-2 / A-3..H-3, incl. the C-2/C-3
layouts read by the C-1 extractor, with C-3's misreads repaired). Field IDs are
namespaced `RU-01.001` / `CR-01.001`. `form.build` draws them from their own
layout with the URAR machinery (numbered, flowing certification paragraphs;
alternatives by sentence; supervisor gate; signature block; exhibits titled per
B-3); `flow.Meta` gives the header ("Restricted Appraisal Update Report  Page 1
of 3") and footer ("Update Version #1"). H-2/H-3 run in review and /fields.
**Editor:** a URAR's sign-off panel has "New Restricted Appraisal Update" /
"New Completion Report" -> `POST /api/cases/{id}/derive {kind}` (subject,
Original Appraisal, client-side parties, original repairs carried). Those cases
hide the Property / Additional Data / Comparables / Location Map tabs and the
map/market/fill buttons; structure routes answer 409. Proven by
`tests/test_report_types.py` (21 tests: AU1/CR1/CR2 text both ways, zero
H-2/H-3 findings, derive pairs SF1->AU1, SF2->CR1, SF4->CR2, API flow) and a
Chromium click-through; laid out, AU1 and CR1 are 3 pages like the official
PDFs; CR2 is 4 against 3 (the exhibit pair does not fit under the commentary).
Harness 87/0/21 unchanged. **Left:** CR repair-table editing must write
CompletionReportNewDefectIndicator = true for a newly observed item; exhibit
box height vs D-3; the URAR's own certifications still print alternatives
line by line (the kinds' paragraph/alternative logic is not yet applied to the
URAR -- needs the harness to confirm before switching it on).

**Structure engine and applicability (2026-10-05, E-086..E-088, T-1035 done).**
`uad/structure.py` holds the property as a tree (dwellings -> units, ADUs,
outbuildings); counts 3.005/3.006/3.007 are read from it; API
`/api/cases/{id}/structure` (GET/POST/DELETE, `/loss`) and the editor's
"Property" tab; typed counts run the same operations and ask before losing
answers. Which sections a report has comes from B-1's own display sentences
(`spec/section_display.json`, extractor `uad/spec/extract_section_display.py`),
checked equal to the D-1 Scenario Matrix. Shared layouts take only numbers from
the browser (`flow.trusted`). Harness 87/0/21 unchanged.

**One report, opens instantly (2026-10-05, E-084/E-085, T-1037).** There is no
template picker: `POST /api/cases` with no template starts `api.NEW_REPORT`, and
`uad/shape.py` rebuilds the report on the closest D-1 structure when an answer
changes the property type, carrying every value. Every new report has the same
content, so its layout is kept by content key (`app/layouts.py`) and served at
once; the launcher warms it (`POST /api/warm`, hidden case). Next: the structure
engine (T-1035) so unit/ADU/outbuilding counts are exact rather than "closest sample".

**Official blueprint studied, 2026-10-05: read `knowledge/blueprint/STUDY.md` before
any dynamic-form work.** The owner's repo `Mohit-rajput-mr/UAD36-Blueprint` holds the
official set; its URAR documents (A-1..H-1, XSD, 12 samples) are identical to ours. It
adds the Restricted Update (A-2..H-2) and Completion Report (A-3..H-3) report types and
the GSE job aids. STUDY.md has the section display/repeat table keyed to MISMO data
points, the dwelling/unit/ADU/outbuilding tree, and the Usability rules.

**Owner's section test, 2026-10-05 (`_work/dyn/SECTION_TEST_REPORT.md`) — the
current priority.** The owner's tester wrote ~1,060 fields on the live site and
found 16 bugs (B1-B16), then asked for the report to become *dynamic*: a generated
blank skeleton, a Property Setup step, a structure engine and spec-driven
applicability (full brief condensed in the same file; task T-1035).
Fixed and tested (E-078..E-083): B1 sales contract, B4 grid totals (A-1 formulas,
141/141 sample values), B7 Yes/No display, B8 alternate address, B9 signature
date, B10 grid limits, B11 report in the URL, B12 check = export, B13 adjustment
type, plus T-119 Level and Room Detail. **Still open, in this order:** B15 (gated
fields name their gate), B16 (photo category "DwellingFront" stored as "other",
to confirm), B5 (client-side PDF on Vercel), B2/B3 + T-1035 (structure engine,
skeleton, setup, applicability: B14), B6 (171 H-1 rules not executed).

**State of the text-fidelity audit (updated 2026-10-04, slice 2).** Method:
`python _work/audit/render_all.py` (renders the 12 samples to `_work/harness/`,
~1 min), then `python _work/audit/linediff.py [-v] [sample]` (whole-report word
diff vs the D-1 PDFs; the TOTAL is the number to drive down: 21411 at the start,
17706 now), and look at pages side by side (render with pymupdf and read the PNGs --
this found the real bugs; the text diff alone hides wrong-but-present data).
Restore the tracked PDFs afterwards: `git checkout -- _work/harness/`.

Done: E-071..E-075 (repeated-row tables read their own block, clipped C-1 IDs, grid
cell composition/units/order/dashes, supervisory gate). Known NOT a rule: the order of
data sources in a grid cell (samples disagree for identical XML).

Still wrong, found by looking at SF1 pages (each is a task in TASKS.md, T-119..T-121,
T-123): **Unit Interior** (Level and Room Detail, Kitchen and Bathroom Details, Interior
Features read only the first instance -- B-1 10.029-10.049 gives every rule; the XML
shape and the official table are in `_work/HANDOFF.md`'s last section), the Apparent
Defects tables (Dwelling Exterior, Unit Interior) and per-section Exhibits with their
captions, the Outbuilding grid rows (ADUs excluded; area/heating/utilities), roof detail
("Estimated Age:" on its own line, "(Unobservable)"), Utilities header rows that always
print, Market "Price Trend Source", Cost approach `1,568 Sq. Ft. @ $121.25` and
`45 years`, page counts differing on 9 of 12 samples.
Pre-existing failing tests (also fail on the commit before slice 1): `test_cells` sf1,
`test_autofill` condo1/mh1, `test_golden::test_the_pdf_is_text_not_a_picture`.

**Next, in priority order:**

1. The 21 harness "gap" lines: 12 are the font substitute (expected until the
   owner installs licensed Myriad Pro); 9 are **page counts that differ from the
   official samples** (e.g. 24 vs 20, 26 vs 29). Investigate page-break rules
   against Appendix E/C-1 — a mechanism, never a per-sample tweak.
2. Forensic audit of every section/field against B-1 display rules and the D-1
   PDFs (render each sample, compare text per page with the official PDF;
   suspected items still to confirm: a missing "Price Trend Source" row, a
   stray "Yes" in Highest & Best Use, manufactured-home rows (HUD Data Plate)
   showing on single-family editable pages, unit-address comma formatting, the
   Graph row listing all images, a default defects sentence). Confirm each
   against the spec before changing it; record each in
   `knowledge/errors/CATALOG.md` with its test.
3. Pre-existing test failures (fail on `main` too, not caused by recent work):
   `test_cells` sf1 (fields 4.093 / 10.031 / 10.045 not writable),
   `test_autofill` condo1/mh1 blank fill. `total-bridge/tests` fail at
   collection in this Linux container (Windows-only bridge).
4. ~~PDF export on a host with Chromium~~ — done: Docker image, see
   `DEPLOY_DOCKER.md`. On Vercel PDF stays 503 by design; to give the live
   site a PDF, host this image (any container host) and point the owner at it.
5. ~~UI redesign~~ — done (monochrome editorial v2, in-app dialogs). Keep
   new UI inside that design system (`index.html` tokens, `.eyebrow`, `UADDialog`).
6. Permanent documentation set: **written** (`docs/`, 2026-10-04; nine pages
   plus `docs/gse-vendor-recognition.md`, which separates requirements from
   inference and lists what must never be claimed). Keep the pages true when
   behaviour changes. Still to do: second audit and final report.
7. Housekeeping: `UAD_P1..UAD_P7` on the Vercel project are dead (the build
   skips the patch because `engine/app/access.json` exists) and can be deleted
   from the dashboard (Settings -> Environment Variables; the MCP tools here
   have no delete). **Keep `UAD_BUILD`**: the project's build step runs it to
   prune files the function never reads, which keeps the function under the
   225 MB limit. Checked 2026-10-04.

## 6. The approach — keep it unchanged

- **Specifications are the authority.** Generate from spec files; never
  hand-type what a spec defines. If you cannot find the source, say so.
- **Validate your validators**: every check runs against the 12 official
  samples first; a check that faults a published sample is a broken check.
- **No property-specific fixes.** A case's problem is fixed as a mechanism,
  entered in `knowledge/errors/CATALOG.md` with its test.
- **No fake controls, no sample/demo content in a real report.**
- **Prove before you push**: run the relevant tests (`python -m pytest -q
  engine/tests/...`, `python engine/tests/harness.py 12`, the
  `engine/tests/test_*.py` scripts); for a live bug, reproduce it locally
  first (two server copies behind a round-robin proxy with a shared
  `URAR_DURABLE_DIR` reproduces Vercel), show the fix, then push.
- **Record as you go**: `TASKS.md` via `python engine/tasks.py add/done`
  (done needs evidence), `_work/HANDOFF.md` new section at the end, and §4/§5
  of this file.
- Commit messages describe the mechanism and the evidence. Never put secrets,
  tokens or the passcode verifier's inputs in commits, logs or client code.

## 7. How to take over (new agent checklist)

1. Read this file, then `CLAUDE.md`, `_work/GOAL.md`, the **last** section of
   `_work/HANDOFF.md`, and run `python engine/tasks.py next`.
2. `git status` and `git log --oneline -15` — compare with §4/§5 here. If the
   tree has uncommitted changes that §5 describes, continue them; do not
   discard them.
3. Pick up §5 "In progress", then the next item in order.
4. After each verified fix: commit → push the working branch → fast-forward
   `main` (`git push origin HEAD:main`) → check the Vercel build is READY →
   ask the owner to try it live if you cannot reach vercel.app.

## 8. How to behave with the owner — this matters

- **Act, don't ask.** The owner has said, repeatedly and emphatically: continue
  with all decisions without asking, and do not ask for permission chunk by
  chunk. Make the reasonable decision, do it, verify it, report briefly.
  Ask only when something truly cannot proceed without them (a credential, a
  business choice such as a company name).
- **Keep the tool calls that trigger approval prompts to a minimum.** The owner
  finds repeated "allow once" prompts very annoying. Prefer git for deploys.
  If a safety check blocks an action, do not try to get around it; say in one
  or two lines what is blocked and the one thing the owner can do.
- **Short, plain updates.** What changed, how it was verified, the live link.
  No long surveys of options.
- **Be honest.** Say what was verified and what was not (e.g. "verified
  locally; could not open the live site from this container"). Never present
  an unverified result as done.
- Never re-introduce "Kech", never weaken the passcode, never put demo data in
  a real report, never claim GSE approval.
