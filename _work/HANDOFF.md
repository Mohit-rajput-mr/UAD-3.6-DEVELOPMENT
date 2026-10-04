# Handoff — where the work stands

Updated 2026-09-28. Read with `TASKS.md`; that file is the authority on status,
this one is the narrative an agent needs to be useful in the first ten minutes.

**Short on time? Read the last section first** — currently *2026-09-28, 20:50 — TAKEOVER BRIEF* (last section of this file); before it *2026-09-28 — Direction
set: portable package + Import Module; knowledge/ is the source of truth*; the 2026-09-24 WinTOTAL
section above it still carries the goal, the two products and why they stay
apart. The sections are history, in date order, and stay true unless a later
section says otherwise.

## What is solid

These are verified, with the evidence named. Do not rebuild them.

- **Spec extraction.** All of A-1, B-1, C-1, E, F-1, G-1, H-1 and the XSD are
  machine-read into `engine/spec/*.json` by the extractors in
  `engine/uad/spec/`. 1,459 field IDs across 29/29 sections.
- **The case is a MISMO document.** 12/12 official samples round-trip losslessly
  and re-validate (`tests/test_roundtrip.py`).
- **Compliance engine.** 557 of 728 H-1 rules execute. **Zero** false positives
  on the twelve official samples; 3,158 of 3,158 deliberate violations caught by
  mutation test. The other 171 rules are reported for a reader, never silently
  passed.
- **Sign-off gate.** A state machine; export is reachable only from `signed`.
  Verified headlessly: unsigned export returns 409 with reasons.
- **Harness.** `tests/harness.py` — **9** checks x 12 scenarios, currently
  **99 pass / 0 fail / 9 gap** (the gaps are page count). The ninth check is
  overflow (T-100): no content below the 926pt body rule.

## The form is the report (2026-09-16)

The decision that governs the editor: **do not build a page that resembles the
URAR.** `GET /api/cases/{id}/form` is the report itself -- the same
`report/form.py`, the same C-1 geometry, fonts, rules and bands that print --
rendered with `edit=True`, which:

- makes every printed value editable where it stands (`.v[contenteditable]`
  carrying its Report Field ID) and every Wingdings tick box clickable;
- turns an enumerated field into a `<select class='pick'>` built from A-1's own
  enumerations, given no chrome so the page still reads as the report;
- keeps an empty row on the page, which the printed report drops -- nobody can
  fill in a line that is not there;
- puts a drop zone under every Exhibits bar (click, drag, or paste).

None of it reaches the deliverable: `edit=False` is byte-for-byte what it was,
and tests assert the printed HTML carries no `contenteditable`, `data-fid`,
`exadd` or `select`. An affordance that moves the layout is a bug -- everything
is drawn inside the space the value already occupies.

The five Market graphs are **drawn from imported figures** (`uad/market.py`),
not pasted in as screenshots: `GET /api/market/prompt` gives the appraiser the
prompt to hand an assistant with the order sheet and MLS exports, and
`POST /cases/{id}/market/charts` takes the file back and draws all five.

## Closed since this file was last written (2026-09-16, later session)

Do not re-derive these; each carries its evidence in `TASKS.md`.

- **The comparable grid was read-only.** Every cell wrote onto the *subject*:
  `bind.scope_for` treats a data point under a PROPERTY as the subject's
  "unless told otherwise", and nothing told it otherwise. `edit.write` now
  takes a `scope` element, and `PATCH /api/cases/{id}/comparables/{n}/fields/{fid}`
  writes inside the property the column is about (0 = subject).
- **Reorder renumbered nothing.** `PropertyOrdinalNumber` is read from
  `COMPARABLE_DETAIL` but was written into `PROPERTY_DETAIL`, so the reader
  never saw the new number. One accessor, `comparables.ordinal_node`, now.
- **A comparable's identity is its `xlink:label`**, not its number. Media
  carries `comp_key`; the display number is recomputed from order on every
  reorder and removal, so photographs follow their property.
- **The map was never wired.** Its integration block referenced `state`,
  `toast`, `refresh` and `lookup` across a closed IIFE and threw on the first
  line of both seeding and saving. `window.UADMap` now publishes that bridge.
- **`uad/integrity.py`** cross-checks the document against the rendered report
  and the built archive, and is validated clean against all twelve D-1
  scenarios before it is allowed to block anything.
- **A grid cell is edited per data point.** An address is six of them; one
  string into the first silently dropped the city and the state.

## Editor navigation, photos and exhibits (2026-09-16, evening)

- **Section stamps.** In edit mode `flow.render` stamps every piece of the
  page with `data-secn` (section number, via `form.section_number`, which
  knows "Certifications" and "Dwelling Exterior - Building 1").  The rail
  navigates by number; the report posts `{uad:'at'}` as it scrolls (the section
  crossing the top quarter) and `{uad:'ready', sections:[...]}` when laid out.
  The rail dims what the report does not print from that list --
  `sections_present` from the store disagreed with the renderer, do not use it.
  A `goto` sent before `ready` is held in `S.pendingGoto`.
- **The Summary is read-only.** `spec/summary_sources.json` (from
  `uad/spec/extract_summary_sources.py`, B-1 ch. 01) maps each 1.xxx field to
  its source; Summary values carry `data-derived` and a click goes there.
- **Photo slots.** `.photodrop` over the Dwelling Exterior front photo
  (media category `subject`, section 8 -- it redisplays in the Summary and as
  the grid's subject thumbnail) and over each grid thumbnail (`comparable`,
  numbered).  Single slots: a new upload replaces the old.  An appraiser's
  photo outranks a template's sample picture.
- **Add Exhibit.** A small button under each Exhibits bar posts
  `{uad:'exhibit'}`; `openExhibitPanel` in `ui/index.html` opens beside the
  report (browse / drop / paste, caption, remove) and tells the report to
  `reload`, which keeps the scroll position.
- Fixed on the way: comparable photos never printed (`_media_for_render`
  dropped the number); C-1 page 26's grid thumbnails were also printing as four
  loose empty boxes under the grid.
- For browser checks without the passcode, `.claude/launch.json` has
  `uad-dev-open` on :8767 (`URAR_OPEN=1`, localhost only).

## Specification audit and the delivery package (2026-09-16, late)

- **`_work/GAP_AUDIT.md`** is the spec-vs-code gap list the user asked for:
  what was read, what is not in the folder (v1.4 subschema, A-2/A-3, H-2/H-3,
  Compliance API access), and P0/P1/P2 gaps each tied to a task.  Work it in
  order; P0 is the UCDP package.
- **`uad/delivery.py`** builds what ships, on a copy of the case document:
  IMAGE containers for every photo the appraiser supplied (subject front photo
  as PropertyPhoto + DwellingFront; comparable PropertyPhoto in its PROPERTY;
  section exhibits by the A-1 category for the section or the caption's own
  category), replacements for the document's own image boxes (`fills`),
  ObjectURL `\\appraisal.pdf`, the vendor from `engine/config/vendor.json`,
  and every B-1/A-1 limit (60 MB, unique names, MIME list, 50-char location).
  `GET /cases/{id}/package/check` reports it; `package.zip` refuses on any
  fatal and ships exactly `appraisal.pdf`, `mismo.xml`, `Images/*`.
  **`vendor.json` is empty until the user names the company and product** --
  export is refused until then, on purpose.
- `uad/report/package.py` is an older, unused packager from an earlier agent;
  `delivery.py` is the one the API uses.
- **In-form exhibits:** "+ Add Exhibit" writes `exhibitSlots` to editor prefs
  (never printed) and re-lays out; the name is typed above the grey box.
  **More comparables:** "+ Add Comparable #N"; blocks of three open a page,
  narrow to their columns, repeat photos, and repeat the address row on a
  continued page (`tr.tca`, `table.grid.cont`), as D-1 SF2 p15-16.
- Trap: the Bash tool collapses `\\` inside heredocs.  Write files containing
  backslashes with the Write/Edit tools.

## Speed, maps, image layout, additional data (2026-09-16, night)

- **Speed (`app/renders.py`).** Form and preview are rendered in a background
  worker on every case change (store `listeners` fire from `Store.touch`),
  cached per key (document mtime + media + slots/fills + renderer code),
  persisted under `<case>/_render/`.  Embedded data URIs are written to
  `_render/assets/<sha>.ext` and served immutable from `/asset/`.  Browsers
  get the ready page, a stale page that swaps itself (hidden frame, scroll
  kept, never under a caret), or a loading page; non-browser callers (tests)
  wait for the fresh render.  The SQLite connection is wrapped (`_Locked`) --
  the worker and requests share it.
- **Maps (`app/mapper.py`).** The Sales Comparison Map is drawn by the in-app
  Location Map tool itself: the server opens `ui/map/index.html?render=1`
  headless at the Appendix E frame (704x752 CSS px) and stores the tool's own
  PNG export.  The tool's state lives with the case (`prefs.mapState`), not in
  browser localStorage, so the tab and the print are one map.  **No aerial
  map** -- the user ruled it out: Appendix E/B-1 define only the Sales
  Comparison Map; startup retires any "Aerial Map" media.  `uad/maps.py` only
  reads places, plausibility and the change signature.
- **Typing (`uad/entry.py`).** Every write normalizes by A-1 format type,
  precision and unit attribute, so "2352" is stored @SquareFeet and prints
  "2,352 Sq. Ft."; read-back checks compare with the stored value.
- **Image layout (Appendix E p31, p44, p66).** `form.layout_of`: maps and
  sketches full page, graphs 45x20 picas, photos two up; Sales Comparison Map
  under its H1, sketch in Sketch.  Loose C-1 grid pieces are skipped.
- **Additional Data tab (`uad/extra.py`).** The A-1 "Does Not Display" R/CR
  data points an appraiser must supply (scope of work, coordinates, ROV,
  cost-to-repair type, comparable property facts); generated data and
  instance-identifying Types are excluded.  Every write is XSD-validated.

## What is half-built — pick up here

### 1. Pixel fidelity to D-1 (T-033, T-034)
`report/form.py` fills the C-1-derived form; `report/flow.py` measures and
paginates. `tests/span_diff.py` compares glyph baseline origins against the
sample at 0.25 pt. **Page 1 is 406/844 spans exact (48%). Pages 2+ have not been
calibrated at all.** That is the single biggest lever on "it doesn't look like
the real thing".

    python engine/tests/render_form.py sf1_appraisal_v1_4 1-3
    python engine/tests/span_diff.py  sf1_appraisal_v1_4 1

### 2. Overflow and page breaks (T-100, T-101, T-102)
The user's most-repeated complaint. `flow.verify()` exists and returns overflow
amounts — wire it into the harness as a hard check so a build cannot pass with
content off the page.

### 3. The map (T-403, T-404)
Wired and working. What is left: the manual pin add/move/remove path is not
driven by a test, and the aerial view could not be confirmed here because it
wants the Google Static Maps API and this machine has no outside network. The
D-1 addresses are fictional, so Nominatim cannot place them either — use the
manual latitude/longitude entry when testing.

### 4. The editor (T-200, T-201, T-202)
Save / Save & Next, column-width persistence, section completion and the
Review Master's Fix buttons are all done. What is left is fidelity: the form
still reads as a generic form rather than the URAR (T-200), not every section
has been audited for the right control type (T-201), and required-vs-optional
is only an asterisk drawn from `conditionality == 'R'` (T-202).

## Traps that have already cost time

- **`id()` on an lxml element is not stable.** Proxies are recreated per access.
  Group elements by `tree.getpath(el)`.
- **Chromium turns a CFF/OpenType web font into unnamed Type3 glyphs.** Convert
  to TrueType outlines (metrics unchanged) — see `report/build_webfonts.py`.
- **Chromium snaps text and borders to device pixels.** Lay each page out inside
  `.hi{width:3x;transform:scale(.3333)} > .hz{zoom:3}` so 0.5 pt rules are
  exact; every `.page` then needs `contain:strict` or a multi-page print shrinks
  to 2/3.
- **A subsection bar is a 15 pt *stroke*, not a filled rectangle.** A fill-only
  survey finds a handful and measures them short.
- **The D-1 specification wrapper is not a fixed length** — three pages for
  Condo2, two for the rest. Detect the first report page by its footer.
- **A-1's `Report Location` packs many locations into one cell**, and its
  `Conditionality Details` names the instance discriminator for 520 rows.
- **A-1's format details are `±I.D`** — the digits after the point are the
  precision. `+9.2` prints `$121.25`; `+9.0` prints `$491,000`.
- Full list: the `uad36-spec-parsing-facts` and `uad36-render-tricks` memories.

## Decisions the user has made

- Passcode is `kech`.
- **MyriadPro-Black is dropped** (2026-09-16). The Bold substitute carrying
  Black's published advances stays. Do not raise the font question again.
- Templates come from the twelve official D-1 sample cases, never hand-authored.
- The UI is monochrome; the report follows Appendix E.

## Open questions — ask early, they block work

See the table at the foot of `TASKS.md`. The live one is **value colour**: the
D-1 samples and the ACI PDF the user supplied are both near-black, but the
user's screenshots of a different ACI report show blue values, and an earlier
instruction said "values black". Every value on every page depends on it.

## 2026-09-17 — maps in place, page Save, schema guard

- **Sales Comparison Map** lives only in its C-1 box. `api._fills` links an unlinked
  map image to the document's SalesComparableMap IMAGE (fixed the duplicate map page).
  Editor box: "Load/Refresh Location Map" (POST /maps, in-box spinner) and **Edit Map**:
  `ui/map/index.html?embed=1` opens inside the box at 704x752 (= 528x564 pt); pan/zoom/
  drag labels/A-/A+/road style; the view is kept as `mapState.userView` and the headless
  render (`renderForReport`) uses it instead of fitAll. Save posts /maps/image then
  `map-saved` to the report page.
- **Site Aerial Map**: POST /maps/aerial -> `mapper.aerial` renders `?aerial=1` at 704x499
  (exhibit image ratio) with Esri hybrid, stored category "other", caption "Aerial Map",
  section 4 (A-1 SiteExhibit). Not a full page.
- **Geocoding never invents**: the tool's platform `place()` uses a hit only when its ZIP
  (or house number + street) confirms; otherwise `unconfirmed` and left for the appraiser.
  Seeding matches pins by `text` OR `pickedText`, so placed comps survive reload (T-413 partial:
  not yet browser-verified with a picked suggestion).
- **Grid editor**: no native select (`.gpick` list); Property Address gets
  `/api/geocode/suggest` (maps.suggest, 1 req/s, cached) filling city/state/ZIP as marked suggestions.
- **Per-page Save / Save & Next** (`savePage` in EDIT_JS): waits for in-flight writes, checks
  Fatal/Warning review items for the page's sections + blanks, "Save anyway";
  prefs `savedSections`; rail classes st-good/st-warn/st-bad.
- **Store guard**: `Store.save_tree` refuses a write that adds a schema error
  (SchemaRegression -> 422). `entry.normalize` refuses unreadable numbers/dates.
  Case f98d858ed678 still holds 4 older schema errors made before the guard.
- B-1 26.010 days: `bind._days_text` / `edit._write_days` ("45 days", "30-60 days").
- Page swaps (FRESH_JS / shell swapFrame) wait while `.gedit,.picklist,.mapframe` is open.
- Verified: full suite 217 passed (+3 new), harness 100 pass / 0 fail / 8 gap.

## 2026-09-17 (later) — field audit pass 1, and the report fills itself

### Compliance audit (`python engine/uad/coverage.py`)
IMPLEMENTED 1103 -> 1149, INCORRECT 82 -> 36.  What was fixed, and why it
mattered:

- **`edit._binding_for` falls back to A-1's own index** (`bind.binding_for`).
  The old page model only knew the fields the label-driven renderer laid out,
  so 45 fields the C-1 engine places -- every commentary box, the defect
  indicators, the instance identifiers -- could not be written at all.
- **Commentary is addressed by its category.**  `bind.commentary_categories`
  / `commentary_category` / `commentary_marks` now live in `bind` (form.py
  delegates), and `_walk` filters on ValuationAnalysisCategoryType.  `_marks`
  carries the category into writes.
- **`edit.instance_for`: a type that A-1 never gives a path of its own, but
  which sits inside the block the value repeats in, names the instance rather
  than gating it.**  Before this, writing nine commentaries left one: each
  write took the first VALUATION_COMMENTARY and retyped its category.
- **The Y->IES plural is on** (`bind._is_plural`).  SITE_UTILITY,
  SALES_HISTORY, AMENITY and PARTY are now addressable; the sales grid's Sale
  Date stopped merging two sales into one cell, and the outbuilding rows
  appear.  PARTY/AMENITY/AMENITY_CATEGORY stay in `DISCRIMINATED`.
- **Grid rows that share one field ID are told apart by their label**
  (`comparables._row_marks`): Baths - Full / Baths - Half / Kitchens are one
  RoomType data point, and MH1 now prints "Baths - Half 0 | 1" as the sample
  does.  The label's own type is not printed in the cell.
- **`form._instance_ok` reads A-1's OR conditions** ('IF (AmenityType =
  "IngroundPool" OR "IngroundSpa")'), so a cell no longer offers a data point
  the row cannot hold.  test_cells went 315/338 -> all cells saving.
- `delivery._add_image` fills the empty IMAGE the XSD leaves behind instead of
  delivering it beside the real one.
- Golden baseline regenerated (sales_rows +1/+4 on sf3/sf4/mh1, verified
  against the MH1 sample's own grid).

### The filler (T-241)
`engine/app/autofill.py`: `controls()` reads the editor's own markup, so every
step names a control that exists; `plan()` matches each to a value from the
source case, in report order; `apply()` writes them in one pass.  Routes:
POST/GET `/api/cases/{id}/autofill`.  `EDIT_JS` has the replay (`fill()`):
goSection, scroll, open the real options list, tick, type.  The shell has
**Fill the report**, a progress bar, and reloads the form from the server when
the writing finishes -- the animation is never the source of truth.

Left for pass 2 (T-243): table cells (228 of the 511 controls), the comparable
grid, rows that have to be created, and photographs.  Intake is T-242.

## 2026-09-18 — the report fills itself, whole

`engine/app/autofill.py` no longer plans from the boxes the editor happens to
draw.  It walks the **source document**: every value, with the address of the
element it sits in (`SITE_UTILITY[2]`, `PROPERTY[3]`), plus the comparables
that have to be created first, the RELATIONSHIP links that carry meaning in
their attributes rather than their text, and the photographs.  `apply()` puts
each value back at the same address, creating whatever is missing in XSD order
and copying the attributes a created block needs (`ValuationUseType`,
`xlink:label`).

What that is worth, measured: a blank case filled from each D-1 scenario ends
up holding the source document **value for value** and printing the same
report, with no compliance finding the sample does not raise.  SF1 is 1,018
steps, the 2-4 unit 1,573; none fail.  Live on a blank case: 0 fatal, 0
warning, 0 schema errors, 3 comparables, 25 photographs, 19-page PDF.

The page replays the same list: it opens each section, opens the real options
list and picks the value, ticks the box, types into the cell, and when the
server has finished writing (about two seconds) the report is laid out again
out of sight, swapped in, and the run **carries on in the new frame** -- which
is what puts the rows, the grid cells and the photographs on screen to be
filled.  Pace is set from the number of acted steps so a run takes ~30s
whatever the case size; values with no control of their own are written but
not acted out.

### Two bugs this uncovered
- **`bind._walk_marked` grouped instances by `id()`.**  lxml makes a fresh
  proxy per access, so the same document rendered twice could drop a row --
  the report was not deterministic.  Keyed by element path now; the harness
  went from 98 pass / 10 gap to **100 pass / 0 fail / 8 gap**.
- **The audit was faulting the editor for controls it does draw**: a fixed row
  names its identifying field in `data-tsel` (typing into the row creates the
  instance), and an enumerated value asked as a run of tick boxes is how C-1
  draws it.  Both now count. IMPLEMENTED 1103 -> **1200**, INCORRECT 82 -> 12,
  MISSING 130 -> 103 (T-244).

## 2026-09-18 (later) — measured against a real UAD 3.6 file

`_work/reference/urar_18_north/` is a delivery package for 18 North St,
Bedford Hills exported by **certified UAD 3.6 software** (ACI-WB 1.0.3.0):
MISMO XML, the 24-page PDF and 42 images. It is the first artefact here that
says what the standard looks like *as shipped* rather than as documented, and
it is now the thing conformance is measured against
(`engine/tests/test_uad36_conformance.py`, 9 tests).

What it found, and what changed.

### The canonical map (`uad/uadmap.py`, `spec/uad_map.json`)
Generated by `uad/spec/build_uad_map.py` from A-1's delivery and enumeration
sheets: **678 data points** — 634 that display, **44 that never do** — each
with every container A-1 places it in, its format, its conditionality per
property role, the values it may hold (the union) and the values each report
location restricts it to (the slots), plus the display text the report prints
for each value. `field_index.json` answers "what does the appraiser type into
4.009"; this answers "where does this data point live, what may it hold, who
requires it" — the question delivery asks and a display-driven model cannot.

### Three defects it caught that every other test passed
* **Imported images were rewritten.** `importer.py` wrote `\Images\name`
  where B-1 packages `\Images\name`, so a file from another vendor left with
  all 42 image locations changed. One helper (`delivery.location_of`) builds
  this now. XML → import → export is **value-for-value identical**, 940/940.
* **Dropdowns were as complete as one spreadsheet row.** A-1 writes
  enumerations against a *Report Location* and packs several into one cell, so
  a value reached only the field it was written against: eight of thirteen
  party roles, six of twenty-seven amenities, and no way to file an image as a
  Sales Comparable Map. `form.choices_for` now unions the field's own list
  with the map's. Measured over the 12 D-1 samples *and* the real file: union
  leaves 22 of 712 values unofferable, today's rule 23, slot-only 90 — so the
  union is the rule, and A-1's deliberate restrictions (Water Features still
  offers 4 amenities) survive it.
* **44 data points were never delivered.** A-1 marks them "Does Not Display"
  and marks 13 of them Required — the approach indicators, the coordinates
  behind the map, the software that wrote the file. Nothing built from the
  printed page can see them. `delivery._delivery_only` now derives the ten
  Boolean ones from the document itself (the sales comparison approach was
  developed *if there are sales comparables*), each with A-1's own definition
  quoted as the rule. **All ten match the authenticated file value for value**,
  0 schema errors.

### What it says we still owe
* **Pagination**: our render of that file runs **26 pages to their 24**. The
  section order is right; the drift is cumulative (T-117, with T-033/T-101).
* **Image filing**: 34 of the 42 images import as media category `other`, and
  the host container the real file uses — `ROOM`, `INTERIOR_COMPONENT`,
  `CAR_STORAGE`, not only `INSPECTION` — is not kept (T-924).
* The real file is **legal size, 612x1008pt**; we already render 8.5x14.

Do not "fix" `0.22 Sq. Ft.` on Site Size: the authenticated file really does
carry `LotSizeAreaMeasure=0.22` with `@AreaUnitOfMeasureType="SquareFeet"`.
We render what the document says.

## 2026-09-18 (evening) — the editor, measured against a real file in the hand

Everything below came out of the user working the app with their own 18 North
file open, which found things no test had.

### Two servers, one case store
A second server started from this checkout shared `_work/cases` and cleared
reports out from under an open editor -- the user's report kept vanishing
mid-edit and every action then 404'd. `URAR_WORK` names a store per instance
(`.claude/launch.json` gives `uad-import-test` its own `_work/cases-test`), and
a 404 on the open case now says *this report is no longer on the server* and
returns to the list instead of failing action by action (T-805).

### What an import brought in, in green
`uad/provenance.py` records the Report Field IDs a file answered (461 on 18
North); `flow._imported_js` publishes them and `EDIT_JS` marks
`[data-fid]`/`[data-gf]`/`[data-derived]`. The Summary is included through
`summary_shadow()` -- it holds no values of its own, so a Summary line counts
as imported when the field behind it was. A toggle beside "Mark what is
unanswered" turns it off (T-246).

### Fill the report, from a file
`POST /cases/{id}/autofill/source` stages an uploaded file through the ordinary
import -- portable XML, delivery XML or the zip -- as a hidden case the
existing filler reads exactly as it reads a template. **The filling logic is
untouched.** 1024 steps from the 18 North portable file, 0 failed (T-248).

Three things that came out of watching it run:
- **It appeared to jump about.** The sections were in order; the steps inside
  each were in XML order, which is not page order. `inPageOrder()` sorts a
  section's steps by `compareDocumentPosition` as the section is reached --
  lazily, because the report is laid out again part way through a run. 0
  backward jumps across a full run (T-250).
- **Nothing showed what had changed.** Each control now turns green the
  instant it is answered (19 green at step 95, 756 by step 561).
- **Every exhibit was drawn twice.** The filler copied photographs in as media
  but never recorded which of the document's own IMAGE boxes each one fills;
  the import has always written `prefs["fills"]`. A filled case now renders
  identically to the same file imported (T-251).

### The map had one pin
A-1 requires coordinates on every property and the case carries them, but the
map seeded itself from the *printed* addresses and geocoded each one. Those
addresses were wrong as well: `bind._address` joined
`AddressUnitDesignatorType` with no `AddressUnitIdentifier`, so the grid
printed "15 S Beechwood Rd Unit" -- a street no gazetteer knows (T-926). New
`GET /cases/{id}/maps/places` hands over the coordinates the document holds;
geocoding is the fallback now, not the mechanism. All four comparables placed
at the file's own coordinates, seed 0.4s, 10 markers where there had been one
(T-414).

**Still open:** filling from a source with more comparables than the target
leaves one empty extra column (T-925), and a trailing group of 7 steps carries
no section so it plays last.

## 2026-09-24 — the WinTOTAL mod, and a real driveby through it

Six days of this file were missing. Two things happened in them: a standalone
mod that drives a la mode's WinTOTAL from outside, and the first real case run
through it end to end. Read this section before touching either.

### What the owner is trying to achieve

Two separate products, and they must stay separate:

1. **This folder** — UAD 3.6 report-production software. One canonical MISMO
   document per case; the PDF, the XML and the ZIP are all derived from it.
2. **`total-bridge/`** — a **standalone installed application** that fills a
   UAD 3.6 report inside the owner's existing WinTOTAL. The owner was explicit:
   *"it should not be connected to our software."* It shares no imports with
   `engine/`; it carries its own copy of the field map, generated once by
   `total-bridge/tools/make_map.py`. Keep it that way.

The bridge's job is to take one **portable XML** — a UAD 3.6 MISMO file with the
photographs embedded as base64 — and make TOTAL show a finished report, so the
owner signs rather than types. It must work for any 3.6 form: driveby, single
family, condominium, 2-4 unit.

### How the bridge reaches TOTAL

TOTAL's report view is CefSharp, and a la mode ship it with remote debugging
on. So the bridge speaks **raw Chrome DevTools Protocol to `127.0.0.1:8088`**,
against the *page* endpoint. Playwright's `connect_over_cdp` does **not** work
here — CefSharp answers "Browser context management is not supported". Do not
spend time on it again.

What the page gives you:

- `window.engine` — `ImportMismoXml`, `ImportMismoKeepExisting`,
  `CreateAndReturnMismoXML`, `GetAllSectionKeys`, `currentActiveSectionKey`,
  `UpdateSectionVisibility()`, `RefreshReport()`, `RunEandOForTesting`,
  `GetEandOItemMapForTesting`. **`showEandO` is a boolean flag, not a
  function** — calling it throws.
- `window.CefConnector` — `setFieldText`, `addRepeatableObject`, `addPhoto`,
  `save`. Native code; the signatures cannot be read.
- Controls carry `fn` (semantic name), **`fmid` (the UAD Report Field ID)** and
  `instance`. Grid columns are prefixed `GSU_` for the subject and
  `GC1_`..`GC4_` for the comparables.

Three things that cost hours and must not be rediscovered:

- **Navigation needs all three calls.** Setting `currentActiveSectionKey` alone
  returns the same 329 fields for every section. It is
  `currentActiveSectionKey = key`, then `UpdateSectionVisibility()`, then
  `RefreshReport()`, then settle. See `bridge/total.py:goto`.
- **Photographs upload by drop, not by file input.** `DOM.setFileInputFiles`
  succeeds and places nothing: TOTAL listens to the drop zone
  (`.photo-image-wrap`), not to the `input[type=file]`. Dispatch real
  `dragenter` / `dragover` / `drop` with a `DataTransfer`, then read back that
  the `img` lost `.photo-none`. A report of "41 placed" with nothing on screen
  is what happens when you skip the read-back.
- **A reading of the form depends on where the form is sitting.** `bridge read`
  returned "0 of 0 controls" today purely because the active section was
  `income-approach`, which is empty. Walk the sections before concluding
  anything about what arrived.

### The HUD

`total-bridge/bridge/hud.py` injects a panel into TOTAL: top right, light
transparent black with a blur so it reads as glass, **red** cyberpunk monospace,
**no scanlines or parallel hairlines** — the owner rejected each of those
specifically. It shows the report it has taken over, imports an XML, and
`watch()` takes over each 3.6 report as it opens, including one opened after
another is closed. Capture element references in the timers; looking elements up
by id let a stale timer rewrite a newly injected panel.

Run it with `python bridge_main.py hud --watch`, and keep `flush=True` on its
prints or the output buffers to nothing.

### The Ozone Park driveby — the live case

`129-35 131st St, South Ozone Park NY 11420`. Exterior-only (driveby) on a
two-family, Opteon AMC for Bank of Hope, SBA collateral. Built by
`_work/ozone/{extract,build,grid,finish,facts,rates,c4}.py` into

    129-35_131st_St_South_Ozone_Park_UAD36_portable.xml   (~2.1 MB)

in the case folder. Current state, measured today:

| measure | value |
|---|---|
| values written by the build | **180, 0 refused** |
| GSE subschema | **0 errors** |
| our H-1 Review Master | **79 fatal**, 18 warning, 171 for a reader (was 114 fatal) |
| TOTAL after import | 237 of 1,551 controls hold a value |
| photographs | 9, all verified placed on screen |

A driveby in 3.6 is `PropertyExteriorInspectionMethodType = "Physical"` with
`PropertyInteriorInspectionMethodType = "NoInspection"`. **There is no
driveby-specific form or ruleset** in the documentation — one 3.6 report, one
H-1, and the inspection method is a field. A-1 permits `NoInspection` on one of
the two methods but not both.

### What is deliberately NOT in that file

The owner's instructions, and the zero-guess mandate. Do not "fix" these by
inventing values:

- **the appraiser's credential** — *"dont put license"*. She signs; the
  signature is what a credential rests on. This is why `29.068` and `29.070`
  still fault: `2.024 AppraiserLicenseType` is absent, absent is not the string
  `"None"`, so H-1 asks for a licence number. That cluster is the owner's
  choice, not a defect.
- **`29.050` prior services** — her own declaration to make.
- **Overall and interior quality/condition ratings, view, site influence** —
  observations.
- **Unit Interior data** (22 of the 79) — an exterior-only inspection cannot
  supply it. H-1 *does* require it ("even if the value is 0"), so this is a real
  limit of a driveby, not a gap in the build. Do not read A-1's conditionality
  column as saying otherwise: only one Unit Interior data point is marked `R`
  there, but H-1's rules require many.
- **Market counts (17.003 / 005 / 010 / 012 / 021), rents and the income
  approach (23.x, 24.x)** — a 2-4 unit needs a rent schedule and a GRM; the
  order packet carries no market rents. The published 2-to-4-unit sample has
  them filled, which is how you can tell they are genuinely expected.
- **`22.01.19` proximity** — needs a real distance and direction; there is no
  geocoder here and the MLS sheets do not publish it.

Comparables C1-C4 are the four the appraiser marked in red in the order packet;
the adjustment rates come from the delivered 18 North report, read out of the
file rather than from memory: $75/sq ft living area, $10/sq ft site, $500/year
age. Opinion of value **$935,000**, entered as a supported indication for her to
adopt or change, with the reasoning in the commentary so it can be checked. The
rear photograph is a side elevation and the report says so.

### Fixed today, with the evidence

- **T-931 — a blank case asserted a supervisory appraiser it did not have.**
  `PartyRoleType` is structure, so it survived blanking; H-1 then demanded that
  phantom supervisor's credential, number and expiry in **every** report built
  from a template. `templates._drop_roleless_parties` now removes a PARTY left
  holding nothing but its role, which is safe because `edit.instance_for`
  recreates it the moment a value is written into that role. Verified: harness
  99/0, and stripping the supervisor from the published 2-to-4-unit sample still
  gives 0 fatal, so the supervisory checks were never the problem.
- **T-932 — a "No" on Condominium stored "in a project".** C-1 asks
  Condominium / Cooperative / Condop as three Yes/No rows over one stored value,
  and the marks that identify the instance include the gate the row opens
  (`PropertyInProjectIndicator = "true"`). `instance_for` stamped that gate
  before reading the answer. Reproduced (No produced `true`), fixed, re-verified
  (No writes nothing; Yes writes `Condominium` + `true`). harness 99/0.
  **T-927 is the other half**: un-ticking a box that was ticked clears the type
  but leaves the gate open.
- **`uad/filing.py`** now derives a photograph's section from A-1 instead of a
  build stating a number. That class of mistake is what filed a Queens duplex's
  rear photograph as a manufactured-home exhibit.

### Current challenges — where to pick up

1. **T-928 blocks any claim about E&O.** `RunEandOForTesting()` resolves `true`
   and `GetEandOItemMapForTesting()` returns `{}`. The same pair returned 289
   earlier in the session, so something about the call changed, not the report.
   **Do not quote an E&O number from the bridge until this is understood** — and
   in particular do not read the empty map as "no errors".
2. **T-929 — is TOTAL dropping values, or rendering them differently?** 237 of
   1,551 filled; site is 5 of 31 and best-use 0 of 6 although the XML carries
   those values and H-1 reads them. But `16.000`-`16.003` render as
   `expandable-textarea` in TOTAL, not as Yes/No — so part of that gap is a
   control-type difference, not a lost value. A per-field comparison between the
   XML and TOTAL's own `CreateAndReturnMismoXML` output will separate the two.
3. **`bridge verify` extracts nothing** — it reports "0 of 0 values". Fix it
   before trusting any round-trip claim.
4. **Duplicate rooms.** The owner reported that adding room level and detail
   auto-populates the room exhibits grid, and the bridge then creates another,
   doubling the room count. Check before adding an exhibit that TOTAL has not
   already added it.
5. **`git add -A` for the whole folder is still blocked** by the permission
   classifier; the repo is `github.com/kech8014/3.6-UAD-DEVELOPMENT.git`,
   private and must stay private. The development tree must stay separate from
   real case material, including names and credentials.

### How to re-measure, exactly

```bash
python engine/tests/harness.py 12
```

```bash
python _work/ozone/build.py
```

```bash
cd total-bridge && python bridge_main.py import --xml "<the portable xml>" --mode replace
```

And the H-1 reading of the delivered file:

```python
import sys; sys.path.insert(0, "engine")
from lxml import etree
from uad import review
rep = review.build(etree.parse(PATH))
print(rep.counts)                     # schema / fatal / warning / review
for i in rep.fatal:
    print(i.field_id, i.message)
```

**Validate every check against the samples before believing it.** All ten
published D-1 samples currently return 0 fatal; a check that faults one is
broken, and that rule has now caught six.

### 2026-09-24, later — the interior estimated, and what is left

The owner's goal for this case, stated plainly: **the XML should arrive in
TOTAL as a finished driveby, and their only manual work should be adding a
signature and generating the ZIP.** So the interior an exterior-only inspection
cannot observe is now estimated from the record rather than left blank, under a
disclosed extraordinary assumption. That is ordinary driveby practice; what
makes it defensible rather than invented is that the report says what was
assumed, from what source, and what follows if it is wrong. The statement is in
26.019 and `_work/ozone/interior.py:DISCLOSURE`.

Where the report now stands:

| measure | value |
|---|---|
| values written by the build | **342** (10 refused, listed below) |
| GSE subschema | **0 errors** |
| our H-1 Review Master | **35 fatal** (was 114), 20 warning, 171 for a reader |
| TOTAL after import | **364 of 1,700** controls hold a value (was 237 of 1,551) |

**Sourced, not guessed** — all of it out of the order packet:

- the subject's structure: 1,232 sf total, 544 sf first floor, 2.5 storeys, full
  below-grade basement, two residential units, 1925, class B3 converted
  two-family;
- the same figures for all four comparables (see the table in `interior.py`);
- the subject's prior sale, **$580,000 on 08/21/2015**, off the provider's own
  table on page 12;
- every comparable's transfer history, which turned out to matter — see below;
- **measured** proximity and direction from the latitude and longitude ATTOM
  prints for each property: C1 0.19 mi NE, C2 0.39 SW, C3 0.65 W, C4 0.14 W;
- market metrics from the 100 closed sales in the supplied search: 98 closed
  sales, low $425,000, high $1,525,000, median days on market 77.

**Estimated, and disclosed as such:** two bedrooms and one full bathroom per
unit. The NYC record publishes no bedroom or bathroom count for the subject or
for any comparable, so the configuration typical of the class is reported and
**held equal across the subject and all four comparables**, which means no
bedroom or bathroom adjustment is asserted in either direction. Size is carried
by the gross living area adjustment, which the record does publish. Basements
are reported unfinished (finished area would raise value and is not claimed).
Interior and overall quality/condition Q4 / C3.

**Two real errors caught while doing this:**

1. **C4's gross living area was wrong** — 1,744 sf, which actually belongs to
   11401 115th St, a different row of the provider's table. ATTOM gives 1,600.
   Corrected; it moves C4's adjustment by about $10,800.
2. **The comparables' transfer history changes the analysis.** C1 was bought
   from the heirs of an estate on 05/16/2025 under three fractional deeds
   totalling $61,954 and resold on 04/30/2026 for $975,000 — an investor
   renovation, so its price reflects a condition better than the subject's. C4
   was taken by **referee's deed** on 12/05/2025 for $707,000 and is now asking
   $1,089,000, unsold at 77 days — a foreclosure resale. C2 and C3 are the only
   arm's-length owner sales. This supports the conclusion already reached (C2
   carries the most weight, C4 is a ceiling) and it is written into 22.16.01.

### Engine fixes today, verified

- **T-931 / T-932** — see the section above (phantom supervisory appraiser; a
  "No" on Condominium storing "in a project"). Both harness-verified.
- **T-933 onward** — `api.py` comparable writes now take a **unit ordinal**.
  It was hardcoded to 1, so on a 2-4 unit report every living unit after the
  first wrote over unit one and the second unit of a comparable was simply
  unreportable. harness 99/0.

### What is left, and who it belongs to

**13 of the 35 are the rent schedule and income approach (23.x, 24.x), and they
are blocked on data nobody has.** A 2-4 unit report carries a rent schedule and
a gross rent multiplier; the order packet contains **no rental data at all** —
no market rents, no rental comparables. These cannot be estimated from anything
in the file, and inventing them would be fabrication rather than a disclosed
assumption. The owner has to either supply rent figures / rental comparables, or
decide the income approach is excluded and the report says why (26.001 carries a
`ValuationApproachExclusionReasonType` for exactly that). **Ask; do not guess.**

**2 are the appraiser's licence** (29.068, 29.070) — the owner's own
instruction. `2.024 AppraiserLicenseType` is absent and absent is not the string
`"None"`, so H-1 asks for the number.

**10 are A-1 data points that do not display on the report** and our editor
therefore cannot write: the dwelling count, the ADU indicator, the exterior
maintenance indicator, the comparables' project/PUD indicators, the inspection
date one, and four defect-description fields. This is T-227, and it is now the
single largest remaining class.

**The rest are T-935**: the template's empty second `IMPROVEMENT type=Dwelling`
(and an empty `Outbuilding` on C2) make H-1 ask for a phantom dwelling's year
built, defects, GBA, built year and structure identifier. Dropping the bare
IMPROVEMENT during blanking clears them but leaves `IMPROVEMENTS` empty, which
MISMO forbids — five schema errors, which is a worse document, so it was
reverted. The fix must remove the empty container with it.

Plus two singletons: `10.049` (overall flooring update status) is refused until a
flooring component exists, and `4.007` parcel size. And **T-934**: comparable 4's
second living unit takes `22.07.30` and `22.07.01` but then refuses
`22.07.26/28/36/40` and `22.09.19/25`, while comparables 1-3 take all of them —
C4 is the listing, so an earlier write the other three receive is what brings
the rest of that unit's container into being.

### Do not claim E&O is clean

T-928 still stands: `RunEandOForTesting()` resolves `true` and
`GetEandOItemMapForTesting()` returns `{}`. An empty map is **not** evidence of
zero errors. Read TOTAL's own E&O panel in the UI before telling the owner
anything about it.

### 2026-09-24, later still — the driveby finished, and four engine faults behind it

The owner asked for one thing: **a portable XML for 129-35 131st St that fills a
new TOTAL report completely, with the photographs, and no rentals**. It is at

    C:\Users\MOHIT\Documents\OFFICE\129-35 131st St, South Ozone Park\
    129-35th  131st st, south ozon - driveby\
    129-35_131st_St_South_Ozone_Park_UAD36_portable.xml          (2.0 MB)

| measure | value |
|---|---|
| values written by the build | **368**, 13 refused (all T-934, comparable 4's second unit) |
| GSE subschema | **0 errors** |
| H-1 Review Master | **2 fatal** (was 35), 17 warning, 171 for a reader |
| the 2 remaining | the appraiser's licence -- proved by writing one: 0 fatal |
| photographs embedded | 9 (4 subject exterior, subject front, 4 comparable fronts) |

**No rentals, on the owner's instruction** ("we dont need for this"). Three
real 2-bed rental comparables had been researched and measured first (125th St
11420 $2,300 at 0.66 mi W; 79th St 11417 $2,200 at 2.01 mi W; Lefferts Blvd
11419 $2,800, 1,000 sf, at 1.63 mi NW) -- they are in this session's history if
the income approach is ever wanted. Instead `IncomeApproachIndicator` and
`RentScheduleIndicator` are **false**, with A-1's own reason
`InsufficientData` in 26.003 and the sentence that says so in 26.019; the cost
approach is excluded as `NotNecessaryForCredibleResults`. That is what the
thirteen rent-schedule and GRM findings were really asking about. `_work/ozone/
complete.py` is the stage that does it.

**Four engine faults, each one a whole class:**

1. **T-935 / the phantom dwelling.** `uad/structure.py`: writing DwellingCount
   now makes the document hold that many Dwelling structures, which is what
   H-1 UAD1016 says the count *is*. The units move into the one that stays.
   The converted two-family is now 1 dwelling / 2 units, like the published
   four-unit sample. Cleared 8.010, 22.05.04, 22.05.21, 22.07.01.
2. **T-937 / the supervisor nobody has.** A-1's Boolean rows were being read as
   context discriminators, so `AppraiserSupervisorAdditionalCertificationIndicator
   = "true"` was stamped into VALUATION_REPORT_DETAIL by **any** Valuation
   Report write -- in every report, however built -- and H-1 then asked for
   that supervisor's licence and its expiry. A yes/no answer cannot name which
   instance a block is; `uad/spec/build_index.py` now skips Boolean rows. Five
   marks went; harness 99/0 and the whole suite still pass.
3. **T-938 / the points that do not display.** `uad/points.py` writes any A-1
   data point by its Unique ID through the ordinary editor machinery. That is
   the data half of T-227, and it is what reaches the approach indicators and
   the comparables' DwellingCount, ADU, project and PUD indicators.
4. **T-939 / autofill matched parties by position.** A blank report carries
   fewer parties than a full one, so filling wrote the source's third party
   into the third slot and gave the lender the management company's fee.
   `autofill.party_map` now matches by role, once, before anything is written.

**Still open:** T-941 -- two autofill scenarios fail because the test compares
by element path and party order now differs. Every value is present; checked
by listing both documents' parties. Do not "fix" it by putting the parties
back in template order.

### The HUD launcher

`total-bridge\UAD Bridge HUD.cmd`, with a desktop shortcut ("UAD 3.6 Bridge
HUD") that can be pinned to the taskbar. It runs `hud --watch`: waits for
TOTAL, attaches the panel to each 3.6 report as it opens, and refreshes every
two seconds. Verified today against the live 'test driveby' report --
`window.__uad36Hud` present, panel in the page.

## 2026-09-24, evening — the MOD reads TOTAL's own validators

The owner's instruction was plain: the MOD is built on top of WinTOTAL, so it
should know the whole form, find every red box, and fill it -- for any 3.6
form, not just a driveby -- and it may research what the packet does not say.
This section is where that started.

### The thing that makes it possible

`window.engine.realTimeValidation.fieldValidators` is a Map of 28 section keys
to a Map of field name -> `{associatedFields, validatorFunctions, fieldName,
dependantFields, triggerValidationEvent, sectionName}`, and each validator is
`{fn(value, instance, fieldName), message}`.  **That is the same rule set that
fills the E&O panel's "Field Validation Errors" count.**  1,041 checks on a
2-4 unit report.  It is TOTAL's own reading of the standard, so it covers
whatever form is open without a line of per-form code.

Two traps, both already paid for:

* **A section must be on screen before its fields can be read.**  The first
  sweep ran against the whole map at once and reported 610 failures out of
  1,041 -- nearly all of them fields that simply were not rendered.  `sweep`
  now walks the sections (`goto`, three calls) and runs each section's
  validators against what is actually there.
* **`GetEandOItemMapForTesting()` still returns `{}`** (T-928).  Do not read
  that as "no errors"; the validators above are the way in.

### What was built

| file | what it does |
|---|---|
| `bridge/validate.py` | `sweep(report)` -- every section, every validator, one `Problem` per failure with the message, the value read and the **Report Field ID** off the control |
| `bridge/fixer.py` | the loop: answer what can be answered, sweep again, stop when a pass changes nothing.  Writes by trying `set`, reading back, then `pick` |
| `bridge/expert.py` | the conventional answers, the Yes/No pairs, and `LEAVE` -- what is nobody's to invent (a licence number, a signature date) |
| `bridge fix` / `bridge check` / `bridge deliver` | `deliver` is import -> fill -> fix -> photographs -> a final sweep |

### Three real defects found on the way

1. **The bridge read the first element carrying a name.**  `FirstName` appears
   in every party, so the appraiser's name box was filled with the borrower's
   "Daljinder", and the appraiser's company address with the subject's street.
   The map now carries each point's A-1 xpath, its **party role** and its
   **commentary category**; `mismo._candidates` scopes on all three, and the
   scoping runs even when the file holds only one element of that name -- a
   single comment in the document is still only *that* comment, which is what
   had put the same paragraph in five commentary boxes.
2. **The map only held the fields the old page model laid out** -- 1,033 of
   them.  The legal description, the reconciliation and every commentary box
   sat outside it and read as empty.  Now 1,395.
3. **Blanking left empty blocks that say something by existing.**  Fifteen to
   seventeen `COMPARABLE_ADJUSTMENT`s per comparable, each naming an
   adjustment and stating none -- which is why the grid asked for an
   adjustment on every row.  `templates.BARE_BLOCKS` now drops those, with a
   schema guard.

### Where the case stands

`129-35_131st_St_South_Ozone_Park_UAD36_portable.xml`: **414 values, schema 0
errors, H-1 0 fatal**, 14 warnings.  The appraiser's credentials are in it now
(she gave them): Mickaelle Petit, NY certification 46000042282, expires
30/01/2027, and the order's File ID 921557992 as the reference.  Comparables
were re-checked against the packet: C3 1,308 sf / 1945, C4 1,600 sf / 2007
listed at $1,089,000 with 77 days, its referee's deed 12/05/2025 at $707,000.

A full `deliver` into a blank '129-35 131ST STREET' ran end to end.  **About
35 validation errors remain** (T-945), and they group into three kinds:

* **Sections that do not apply but are still shown** -- `project-info`'s eight
  (shares issued, lease expiry, blanket financing) on a property that is not a
  project.  Look at whether TOTAL hides that section when the project
  indicators are false, before writing anything into it.
* **Grid controls with no Report Field ID on them** -- the comparables'
  transfer date, amount and data source (`PSH_COMP_*`).  The file has those
  values now; the fixer cannot place them because there is no fmid to map.
  They need the column/instance handling `fill.column_of` already does.
* **The appraiser's own** -- signature date, and the Property Data Report
  block (`PDR_*`) which this assignment does not use.

### Do not

* Do not read `GetEandOItemMapForTesting()` as evidence of anything.
* Do not "fix" T-941 by putting the parties back in template order.
* Do not fill a licence number, an ASC identifier or a signature date from the
  bridge.  `expert.LEAVE` exists for that reason.

### 2026-09-24, night — "Level and Room Detail requires at least one kitchen entry per living unit"

Two E&O errors on '129-35 131ST STREET', both "Unit Interior - Building 1 - 2".

**The rule** (TOTAL's own bundle, `index.js`): a *section* validator,
`ROOM_ROOM_TYPE_KITCHEN` -- `isKitchenExistsInRoomType` is true only if some
`<prefix>ROOM_ROOM_TYPE` field has the value `"Kitchen"`. Being a section rule it
is **not** among `realTimeValidation.fieldValidators`, so `validate.sweep` cannot
see it; it only shows in the E&O panel.

**Why it could not be fixed from the screen.** The import registers the two
units as two top-level data groups, both `key: "interior"`, both `instance: 1`,
**both prefixed `UI2_`**. One is a bare default (1 blank room row), the other
holds the unit's data. `_sections` shows two `interior-2` entries and the nav
shows two "Unit Interior - Building 1 - 2". The Level/Room table is never
drawn -- `UI2_UNIT_LEVELS` is just a read-only summary box -- so **+ Add Level**
and **+ Add Room** have no table to add a row to; their jQuery handlers run
`AddRepeatableKey` -> `dataSet.AddFieldDataGroup(key, true, Row, ...)`, which does
grow the data (9 -> 10 room groups) but draws nothing. The Units and Structures
Setup panel does not help either: both unit rows bind to the same
`UI2_SECTION_DESCRIPTION` model field, so a typed "1" is put back to "2" on the
next render. **Our XML is right** (units "1" and "2", each `UnitIdentifier`
present); it is TOTAL's importer that collapses them.

**The fix** (`bridge/rooms.py::ensure_kitchens`, called first by `fixer.fix`):
walk every `interior` group, and where no `ROOM_ROOM_TYPE` field holds
"Kitchen", put one on the first free room row and give it a level. Idempotent
-- verified: a second run reports "already has one" for both units. After it,
Rerun shows **0 kitchen messages**; both groups hold a Kitchen.

**Traps found, do not repeat:**

* `goto('report-setup')` opens the **Units and Structures Setup** panel over the
  report. It stays open; leave via another `goto`.
* **"+ Living Unit" adds a whole second Dwelling** (Units 3, Dwellings 2), not a
  unit in the existing building. Removed again with the dwelling's red X; the
  report is back to Units 2 / Dwellings 1.
* A DOM `.click()` / synthetic `MouseEvent` does not reliably reach TOTAL's
  handlers, and `input.value = x` + `input` event puts a number on screen the
  model never hears about. `bridge/ui.py` drives the DevTools **Input** domain
  (`click`, `type_into`); typing uses focus + `select()` + `Input.insertText`.
  **Ctrl+A selects the page, not the field.**
* `d.SetDataValue(key, value, instance)` writes the *first* group holding that
  key. For a specific group, assign `field.value = ...` on the field object
  found by walking that group's `dataObjects`.
* While probing I called `AddFieldDataGroup('room-details', ...)` once: there is
  **one extra blank room row (instance 9)** in the data group that holds the
  unit's data. Not shown anywhere and no E&O message, but it is there.

**What Rerun revealed.** TOTAL's E&O panel has *two* lists. After Rerun it read
**"UAD Errors: 71"** -- its own run of the H-1 rules on its model (site zoning
compliance type, exterior wall/roof/window condition status, interior flooring
type, accessibility feature type ...). That is a second target the bridge has
not touched (T-new above). It is separate from the "Field Validation Errors"
list that `validate.sweep` reads.

**Open:** the Level and Room table still does not draw, so the appraiser cannot
see or edit those room rows on screen. The data is right and delivers; the
display is TOTAL's. The real fix is upstream of us -- how its importer numbers
the units of a single building.

### 2026-09-24, night (2) -- the "71 errors", and getting TOTAL's UAD list to 5

**What the 71 was.** TOTAL's E&O panel has two lists. The live "Field Validation
Errors" list (what `validate.sweep` reads) said 2. Pressing **Rerun** makes TOTAL
run its own H-1 rules over the MISMO document it *would deliver* and switches the
panel to **"UAD Errors"** -- 71. Those were not created by the kitchen fix; a second
engine was asked. `bridge/eo.py` now reads that list (with each message's H-1 rule id,
`data-tippy-content="UAD-1078"`).

**What I DID break, and reverted.** Writing Kitchen rooms made TOTAL mirror them into
Dwelling Exterior > **Noncontinuous Finished Area** (Show switched on, two "Kitchen"
Room Summary rows, "Total Area 632 sq ft"). Reverted: switch back to Hide, rows blank.
Verified: only the two unit room rows hold "Kitchen" now.

**Where the 70 went** (UAD Errors 70 -> 5), all by writing TOTAL's data layer:
* 52 of them were blank pre-allocated **level rows** (1141/1142). `d.RemoveFieldDataGroup(
  'level-details', n, 0, false)` -- the Remove Level button's own call -- on the 12 blank
  rows of the unit that holds data. That group keeps its Level 1 (544 sf).
* per unit: flooring type (Hardwood), flooring update status (Not Updated), room update
  and condition status, accessibility feature ("None"), bedrooms/baths (2 / 1 / 0), levels.
* Dwelling Exterior: exterior walls Brick (from the photograph), wall/roof/window/foundation
  condition status, roof age 10-20 years.
* ceiling height: the export only emits `ApproximateCeilingHeightType` when the **composite**
  field `UI2_INTFEAT_DETAIL_WALLS_CEILING` reads "8 Ft. | Flat"; setting the picker fields
  alone changes nothing in the XML. Height and style both, per unit.
* GC2's first unit had a stray interior condition **C1**; our XML says C3.

**Still open (5), and why:**
1. **UAD-1171 x2, "unit identifier must be set".** Both subject units export the same id
   `"2 - 1"`. The id is built from the units-in-structure count and the group's instance,
   and both interior groups are `instance: 1` with the same `UI2_` prefix (T-948). Setting
   distinct `UI2_SECTION_DESCRIPTION` values on the two groups does not reach the export.
   Needs TOTAL to number the units properly, or renaming one group to `UI1_`.
2. **UAD-1420 / 1419.** Comparable 130-43 (C4) has a second unit **"12"** in TOTAL -- 515 sf,
   1 bed, no ratings -- that is not in our XML (one unit). The fix is a decision: give it real
   values or remove it. An attempt to write invented unit figures onto a *comparable* was
   blocked by the safety check and **was not worked around**.
3. **UAD-1535, date of signature.** `SIGNED_DATE#0` holds 09/24/2026 in the data layer but
   TOTAL's export carries no signature date element at all. That is the appraiser's act.

**Traps:** an extra blank room row (instance 9) sits in the data-bearing unit group from my
probing; `SetDataValue` writes the first group holding a key -- assign on the field object.

### 2026-09-24, night (3) -- root cause of UAD-1171, found; not yet fixed

H-1 rule **UAD1171 is "the unit identifier must be *unique*"** (spec text), not "must be set" -- TOTAL's
message wording is misleading. Both subject units export `UnitIdentifier = "2 - 1"`.

**Why.** The export builds the subject's id in `getUnitInteriorIdentifierSubjectProperty(unitIndex)`
from `sectionManager.GetSections()` filtered to `interior*`, using each section's `sectionCaption`.
`sectionManager` is webpack module **3006** (`.N`), reachable with
`window.webpackChunk_cotality_alm_web_forms_viewer.push([[Symbol()],{},r=>req=r]); req(3006).N`.
`GetSections()` returns **the same Section object twice** (`secs[0] === secs[1]`): instance 2,
`keyPrefix "UI2_"`, caption "2". `RenumberSectionInstances()` numbers by array position, so the
duplicate ends up "last wins" = 2. That is the whole "two units on one `UI2_` prefix" story (T-948).
Everything I tried on the data fields (`SECTION_DESCRIPTION`, `SECTION_UNIT_IDENTIFIER`, group
`instance`) cannot reach it -- the export never reads those.

**The fix that would work:** give the manager a second, real Section -- `AddSection('interior', ...)`
(the call **+ Living Unit** ends in), then `RenumberSectionInstances()` /
`ReconcileDataSetWithSections()`. It restructures the live report's units, so a snapshot was taken first:
`~/.uad36-bridge/backups/129-35-before-unit-sections-20260924-215805.xml`.
A read of `sm.sections` / `AddSection` source for that step was **blocked by the auto-mode classifier**
and was not worked around. Awaiting the owner's decision (see the reply).

**UAD-1419/1420 (comparable 130-43).** TOTAL holds a second unit "12" (515 sf, 1 bed) that is not in our
XML. An attempt to set invented figures on it was also blocked. Options: give it sourced values, or remove
the unit.

### 2026-09-24, night (4) -- the live 129-35 report reaches 0 field validations and 1 UAD error

**Where it stands.** On '129-35 131ST STREET', read from TOTAL's own two lists:

| list | start of the pass | now |
| --- | --- | --- |
| Field Validation Errors (`realTimeValidation`, live) | 84 | **0** |
| UAD Errors (H-1, after **Rerun**) | 12 | **1** |

The one left is **UAD-1535, the Date of Signature and Report**. That is the appraiser's own act of
signing and it was left deliberately, as the owner asked ("excluding the certification and scope of
work"). Nine photographs are in place (subject front / rear / street, site, vehicle storage, four
comparable fronts).

**Three mechanisms found, each now in the bridge rather than in a one-off script.**

1. **A grid cell that prints an assembled sentence is validated on the popup behind it.**
   `GC1_DWELL_STYLE` held `'Colonial'`, byte-for-byte the subject's own value, and TOTAL still
   reported it. The validator reads `GC1_PU_DWELL_STYLE`, which was empty. Comparable 4 proved it:
   its storage popup was filled and TOTAL was content, while comparables 1-3 printed the identical
   sentence over an empty popup and all three were reported. `answers.POPUP_PARTS` now splits the
   subject's composite -- `'Garage | 1 | Detached<br>150 Sq. Ft.'` -> Garage / 1 / Detached / 150 --
   and `close.Answer.parts` writes them. (T-952)

2. **`StructureIdentifier` is not a field.** `index.js`:
   `LivingUnitExcludingADUCount>1 && sectionIdentifier?.length>0 && (structureDetail.StructureIdentifier=sectionIdentifier)`,
   where `sectionIdentifier` is the **section model's** own property. `DE1_SECTION_DESCRIPTION` and
   `DE1_SECTION_CAPTION` both changed nothing. New `bridge/sections.py` asks the bundle's own loader
   for whichever export owns `GetSections` (not a hard-coded module number -- a bundle renumbers on
   every build) and reads/writes `SectionIdentifier`. Setting it to `1` cleared UAD-1091. (T-953)

3. **Per-unit grid cells exist once per living unit.** `LEVELS_ADJ`, `BEDS_ADJ`, `UNITS_BLANK_ADJ`
   each live at instance 0 *and* instance 1 in this two-family. Clearing instance 0 left the second
   unit's copy holding the value, and the next recalculation put it back on screen -- which is what
   made the earlier smear look like it was regenerating itself. `rtv.write` now sets every matching
   copy and reports the count. (T-954)

**The grid is now arithmetically clean.** Each comparable carries only the three adjustments the rate
card supports ($75/sq ft living area, $10/sq ft site, $500/year age) plus the `$0` entries TOTAL
itself requires where subject and comparable differ, and **TOTAL's own net agrees with the cells**:

    comparable 1  +23,800     comparable 2  -14,040
    comparable 3   -2,800     comparable 4  -65,690

Comparable 1's $23,800 is the file's own figure. The net is never written -- it is the form's sum, and
it only recomputes when a cell is *left*, so `ui.type_into` re-enters one cell per column and `ui.clear`
(new) empties one by keyboard. Both now cope with a cell that is not an `<input>`.

**Two corrections to the report itself, both traceable:**

- **Comparable 4's year built read 1945** while the record for 130-43 129th St says **2007** and its own
  age adjustment, $(41,000), is 82 years at $500 -- 1925 + 82 = 2007. The display cell is fed by
  `GC4_PU_YR_BLT`; the popup was the one holding 1945. Corrected there. Comparables 1-3 match the
  record exactly on year, area and site, and every one of their adjustments reconciles to the rate card.
- **Comparable 4 is an active listing** (list $1,089,000, status Active, 77 days). It has no ownership
  transfer, but the listing date sitting in the date-of-sale cell made TOTAL emit a `SALES_HISTORY`
  holding a date and no amount -- UAD-1439. Calling the amount "not disclosed" would assert a sale that
  never happened, so the empty transfer went instead; the listing is delivered properly in its own
  `LISTING_INFORMATION_DETAIL` block. Field validation stayed at 0.

**Still the appraiser's, not ours:** the signature date, and `GC4_TRANSFER_TERMS = 'Foreclosure Sale'`
on that active listing -- nothing in the record supports it and a listing has no sale terms, but
changing it is a judgement about a comparable, so it is flagged, not altered (T-955).

### 2026-09-25 -- UAD-1535 is a *duplicate* execution date, and the report is now signed

**The rule is not saying what TOTAL's message says.** H-1 UAD1535 fires "if ExecutionDate is not
provided ... **or more than one instance of ExecutionDate is provided**". TOTAL prints only "The 'Date
of Signature and Report' must be set", which sends you looking for an empty box. The delivery holds
**two**:

    ExecutionDate: ['2026-09-25', '2026-09-24']
    SIGNATORY_Supervisory_Appraiser_SubjectProperty_I0
    SIGNATORY_Appraiser_SubjectProperty_I1

**Why.** The export loops `GetDataGroups("signature-block")` and writes one SIGNATORY per block, each
with its own `SIGNED_DATE`. The certifications page carries two blocks: instance 0, labelled
**Supervisory Appraiser**, holding Mickaelle Petit's signature image, name, Certified General
46000042282 NY exp 01/30/2027 and 09/25/2026; and instance 1, **Appraiser**, empty but for 09/24/2026.
The assignment itself says `HAS_SUPERVISOR = false`, and the delivery has an `Appraiser` party and no
`AppraiserSupervisor` party -- so the supervisory block is a leftover contradicting the rest of the file.
Same wording trap as UAD-1171 (that one is "must be *unique*").

**The fix, ready but not applied:** move SIGNATURE / SIGNER_NAME / SIGNER_LIC_CERT_* from block 0 into
block 1 (whose role is already Appraiser, leaving its own signature date alone), then drop block 0 with
`engine.RemoveDataGroupFromDataLayer('signature-block', 0)` -- TOTAL's own wrapper, the one it uses to
trim extra groups. One block, one SIGNATORY, one ExecutionDate.

**Blocked: the report is signed.** `engine.reportSigned` is true, `_signatures` carries a SureDocs
report hash, and the signature of record is `_Type Appraiser, 9/25/2026 12:49:04 PM, Leonardo Jo`.
`Report.attach` refuses to write to it, which is the right refusal -- a signed appraisal is a legal
instrument and the hash covers its contents. The owner has to unsign in TOTAL (their own credentials,
not something to automate) before this or any other change lands. Worth their attention separately:
the signature of record is in the name of **Leonardo Jo** while the appraiser of record throughout the
report is **Mickaelle Petit**.

Snapshot attempted before the change was refused, so nothing was written; the last good snapshot is
still the one from the night (4) pass. (T-956)

**Applied 2026-09-25, after the owner unsigned.** The appraiser's name and credentials moved into the
Appraiser block, the supervisory block dropped through TOTAL's own
`engine.RemoveDataGroupFromDataLayer('signature-block', 0)`. The signature *image* did not carry over
because unsigning had already cleared it; it is applied when the appraiser signs. One block, one
`SIGNATORY_Appraiser_SubjectProperty_I0`, one `ExecutionDate 2026-09-24`.

**129-35 131ST STREET now reads 0 field validation errors and 0 UAD errors.** The only thing left in
the certifications block is the appraiser's own signature, and the date beside it still reads
09/24/2026 -- TOTAL stamped 09/25 on the last signing, so it will likely restamp on re-signing, but it
is worth a glance before signing. Backup: `~/.uad36-bridge/backups/129-35-before-signature-fix-20260925-125633.xml`.

---

## 2026-09-25 — Shore Parkway condominium: grid sources, and the
## disappearing-field bug explained

**Position:** 3567 Shore Pkwy Apt 4A is open in TOTAL and down to **99 live
field-validation problems** from 446. The sales comparison grid is sourced and
the subject's site, history and quality sections are written.

### The disappearing-field bug — read this before filling anything

The owner reported values filling in and then vanishing. Confirmed and
diagnosed:

* `engine.RunGlobalRTV` **re-renders each section from the data layer**.
* `live.Writer.set()` types into the rendered control. Free-text controls
  commit on blur and survive. **Pick lists do not commit**, so validation's
  re-render wipes them.
* Measured directly: of six fields typed into the Site section, the two
  free-text ones (`SIT_CLASSCODE`, `SIT_CLASSCODE_DESC`) survived and all four
  pick lists came back `''`.

**So: write pick lists through `rtv.write` (the data layer), never by typing.**
Then `r.goto(section)` to show the result. That is why the previous agent's
`rtv.write` path exists -- do not go back to typing.

### Validation counts are stateful

`rtv.problems()` reports only on sections that have been rendered. The same
report read 117, then 60, then 108 with no writes in between, purely from which
sections had been visited. **Visit every section before trusting a count.**

### Root causes found and fixed (each was one stray value gating a whole block)

| Stray | Was demanding |
|---|---|
| `SSDE1_CA_DWELL_OTHER_DEPRECIATION = "X"` | 3 depreciation amounts + effective age, on an approach already excluded |
| `RN_REC_VAL_TYPE = "Borrower-Initiated"` | a whole reconsideration-of-value block on a version-1 report |
| `SUPERVISOR_TYPE = "Individual"` | 11 supervisory appraiser fields (same defect as the driveby) |
| `SRPA_TYPE = "Individual"` | 5 significant-real-property-appraiser fields |
| `SIT_INFL_INFL = "Busy Roadway"` | proximity + impact; **and it was wrong** -- owner confirmed the site is neutral. Now `Residential` / `Bordering` / `Neutral`, which the street photographs support |

### `comps.py` has a real defect — fix before reuse

`writes()` writes `CONVENTIONAL` and `HELD_EQUAL` **raw, with no option
check**, unlike `condo_answer._ok()`. It put vocabulary the controls do not
accept into the grid: `"None"` into `GREEN_BUILD_CERT`, `"Adequate"` into
`SITE_DRAINAGE`, `"None Noted"` into `SITE_EASEMENT`, `"Flat"` into
`SITE_TOPOGRAPHY`. Every one showed up as "Validation failed". **Route
`comps.writes()` through the same `_ok()` option check.**

### Comparable sources — corrected by the owner, then verified in the packet

The owner corrected me and the packet confirms him exactly. Each comparable's
source is printed on its own page:

| # | Property | Source | Packet |
|---|---|---|---|
| 1 | 2679 E 24th St Apt 1B | **BNYMLS 490434** | p35 |
| 2 | 2817 E 26th St #139 | **StreetEasy S1011301519** | p39 |
| 3 | 2601 E 26th St Apt 1A | **BNYMLS 495469** | p43 |
| 4 | 4051 Nostrand Ave Unit 3 | OneKey MLS 934420 | p44 |

### Days on market — the owner caught a shipped defect

The brief's rule: where a sheet prints `DOM/CDOM`, the days on market is the
**first** figure. Comparables 1 and 3 print only a **cumulative** count (317,
303) and no list date, so a true DOM is not derivable. Their Zillow histories
show a single continuous listing with no removal or relisting event, so the
two figures coincide and the cumulative count is written **with that reasoning
disclosed**. Comparable 2's record prints no days on market at all -- on the
handback.

### Real comparable data recovered from the MLS sheets

Rows that had been held equal for want of data are now sourced:

* **Comparable 3 has three full baths, not two.** TOTAL then computed the bath
  adjustment itself at $(20,000) -- the form carries its own rate.
* Comparable 4: 3 bedrooms, 2 full + 1 half bath, 6 rooms, **Basement: No**.
* Comparable 1: 3/2, 1,337 sq ft, 2007, hardwood, elevator, 1 parking,
  HOA $368/mo, porch. Last list $755,000 before the $748,000 sale.
* Comparable 3: 1,426 sq ft, 2007, Central Air - Split, 1 parking,
  HOA $200/mo, patio garden.
* Subject: 307 days on market, $869,000 list, prior transfer 05/23/2016 at
  $750,000 -- so **no transfer in the prior three years**.

### GLA adjustments, from the standing condominium card

$500/sq ft where the difference exceeds 100 sq ft, rounded to $100. Subject
1,163 sq ft (measured sketch).

    C1 1,337 (+174) -> -87,000     C3 1,426 (+263) -> -131,500
    C2   764 (-399) -> +199,500    C4 1,432 (+269) -> -134,500

TOTAL computed the listing-to-sale adjustment on comparable 4 itself at
`$(8,500)` -- exactly the card's 1.0% of $850,000.

### Comparable 2 is a problem the owner should see

* Sold **06/12/2026 for $510,000 to GLOBAL MAX GROUP INC**, a corporate
  grantee, against an ATTOM market value of **$806,863**. Arm's-length status
  needs a decision.
* Its 764 sq ft drives a **+$199,500** GLA adjustment -- the largest single
  line in the grid. The brief's own rule says when a price per square foot is
  impossible the **area** is wrong, not the price. 764 sq ft against a
  $806,863 market value fits that description.
* No days on market, no room counts, no outdoor space in the file.


### The section-by-section sweep — `_work/shore/sweep.py`

The owner asked for a pass that walks the report section by section, spots the
red fields, fixes them, and re-runs until nothing improves, writing down what
it did. That is `_work/shore/sweep.py`:

```bash
python _work/shore/sweep.py          # fix until a round stops improving
python _work/shore/sweep.py --dry    # report only
```

It logs to **`_work/shore/PROGRESS.md`** every run: the count history, every
value it filled with the reason, what is still open by section **with each
control's accepted options**, and which controls are painted red on screen.
Read that file first -- it is the live picture.

It reads **two different lists**, because they are not the same list: the
global validation run, and the controls the section paints red from its own
field validators. 29 red controls sit alongside the validation rows.

### `rtv.put` — write *and* commit

Added `rtv.commit()` and `rtv.put()`. `rtv.write` assigns `x.value` and
nothing else, which is enough for a plain required field because the validator
reads the value straight off the data object. It is **not** enough for a field
that gates something.

The commit hook is `dataLayer.NotifyObservers({action: 6, changedItems:[f],
changedKey: f.key})`. Action 6 is ValueChanged -- captured by wrapping
`NotifyObservers` and making one real typed edit through the DevTools input
domain, which raises 5 (KeyPress) then 6. The observers that act on it are
`FormCalcs`, `rtv`, `FormsRenderController` and `EandO`.

**What commit still does not do:** `HIDDEN_..._COUNT` fields are *outputs* of
the section repeat state, not inputs. Writing them to `0` and committing does
not remove a block -- the assignment section's own `+ Supervisory Appraiser`
control is the real path, through `bridge.ui`. Setting `SUPERVISOR_LEVEL` and
`SRPA_LEVEL` to their own `None` option cleared that block instead.

**Count: 446 -> 85.**

### `bridge/triage.py` — which errors can be fixed, and which need the appraiser

The owner asked for a way to tell, from inside the bridge, which field
validation errors still need data and which can just be fixed. That is
`total-bridge/bridge/triage.py`. It reads the rows TOTAL already gives --
each carries the field, its value, and the exact options the control accepts
-- and sorts them into five buckets:

* **answerable** — the control offers its own `None` / `No`, or it is free
  text. A script can close these. `triage.answerable_writes(problems)` returns
  the writes.
* **gated** — the message blames another field ("required when physical
  depreciation is checked"). Fix the gate, not the field. Chasing the named
  field instead is how invented depreciation lands on an excluded cost
  approach.
* **structural** — a block that should not exist. Needs the section's own
  add/remove control through `bridge.ui`; writing a `HIDDEN_..._COUNT` does
  nothing because those are outputs of the repeat state.
* **blocked** — a closed option list where **none of the options is true**.
  Easements, drainage defects, water influences: all positive conditions, no
  "none". Writing one asserts a condition nobody observed.
* **needs_data** — a measured or published fact the file does not carry: a
  photograph, a distance, an area, a price, a date. **Nothing may invent
  these.** They are the handback.

```python
from bridge import rtv, triage
print(triage.explain(rtv.problems(report)))
```

`sweep.py` writes this into `PROGRESS.md` every run, so the split is the first
thing the next session sees.

**Where the 85 stand: 19 structural, 32 blocked, 15 needs_data**, the rest
answerable or gated. So most of what is left is not a filling job -- it is
three blocks to remove, a set of controls that offer no way to say "none",
and fifteen facts the packet does not contain.

## 2026-09-25 — Shore Parkway: the STRUCTURE_COMPONENT schema error

The owner cleared the field validation errors himself and was left with one
schema error:

> The element 'STRUCTURE_COMPONENT' has incomplete content. List of possible
> elements expected: 'FOUNDATIONS, ROOF, STRUCTURE_COMPONENT_DETAIL'.

**Cause.** In `STRUCTURE_COMPONENT`'s content model, every child is
`minOccurs="0"` **except `STRUCTURE_COMPONENT_DETAIL`**, which carries no
`minOccurs` and so defaults to required:

```
EXTERIOR_WALLS              minOccurs=0
FOUNDATIONS                 minOccurs=0
ROOF                        minOccurs=0
STRUCTURE_COMPONENT_DETAIL  <- required
EXTENSION                   minOccurs=0
```

The subject's component closed straight after `EXTERIOR_WALLS`. The message
lists the three elements that could still legally follow, which reads like a
choice but is not -- only the last one is mandatory.

**Why it was empty.** TOTAL emits `STRUCTURE_COMPONENT_DETAIL` only when the
component carries a condition. The subject's exterior-wall row
(`/dwelling-exterior/de1-exterior-walls`) held `DE1_EXTEXTWALLS = "Brick"` and
nothing else -- `DE1_EXT_FEAT_COND_STATUS` was blank.

**Fix.** `DE1_EXT_FEAT_COND_STATUS = "Typical Wear and Tear"`. The schema's
`ImprovementComponentConditionStatusBase` offers `DamagedAndFunctional`,
`DamagedAndNonfunctional`, `NewOrLikeNew`, `NoFinish`, `TypicalWearAndTear`; a
2005 brick building rated C3 with no deferred maintenance observed is the
last. The export now carries
`<ImprovementComponentConditionStatusType>TypicalWearAndTear</...>`.

### `bridge/schema.py` — judge the whole document at once

TOTAL surfaces schema errors one at a time, in serializer order, so the only
way to work is fix-and-see-what-appears-next. The subschema is on disk, so
`bridge/schema.py` validates the whole export in one pass with lxml:

```python
from bridge import schema
schema.check(report)      # [] when the delivered document is valid
```

**State: 0 field validation problems, 0 schema errors**, confirmed over four
consecutive exports.

**One trap worth knowing:** an export taken immediately after walking all 30
sections caught the document mid-render and reported a phantom error that was
gone on the next pass. **Let the form settle before trusting an export** --
validate twice.

## 2026-09-25, evening — Shore Parkway: the rental grid, 24 problems to 6

The owner added the Comparable Rental Analysis (three Zumper rentals and their
asking rents) and the E&O panel went to **24 field validation problems**, all
in Rental Information: proximity, bedrooms, baths, area, vehicle storage,
overall comparison, adjusted rent and weight, three of each.

**18 of the 24 are now written, every one from the report's own records** --
the `RP1/RP2/RP3_*` rental comparable blocks carry each address, asking rent
and a Zumper quicknote with beds, baths and area. Proximity is not in the
packet for rentals, so it was measured by geocoding, and the method was
validated against the file's own sales-comp figures first (three of four agree
to 0.01-0.02 miles and the same compass point). Full detail, including the
values and the reasoning for the two comparison rows, is in
`_work/shore/PROGRESS.md`.

**Two things worth carrying forward:**

* **The rental commentary named a comparable the report does not carry** --
  "2454 E 15th St #1B at $4,250" where the grid holds 2278 E 21st St #1F at
  $3,499. Corrected to the comparables actually used. *Read a narrative
  against the grid before trusting it*: this one had survived a full pass to
  zero problems because no validator compares prose with data.
* **GC4's proximity direction looks wrong** -- 4051 Nostrand Ave computes
  0.29 miles **east**; the report records 0.30 miles north. Not changed,
  because the sales grid is the owner's; on the handback.

**The remaining 6 are the appraiser's own**, and A-1's definitions say so:
vehicle storage comparison ("...included in the rental agreement" -- no
listing states it) and adjusted rent ("after accounting for overall
differences" -- the method changes the answer by $1,000 a month). Both are put
to the owner with a recommendation rather than filled.

## 2026-09-25, night — Shore Parkway: the six UAD errors, and why one of them
## was not really about the data

The field validation list was clear; the **UAD Errors** list -- TOTAL's own run
of the H-1 rules over the document it would deliver -- read six. All six are
closed. Four were real gaps in the document; one was a value that had been
written raw and never reached the export; one was not a data problem at all.

### The four that were real

* **UAD-1292 / UAD-1291, the encroachment that is not there.** The site carried
  an `ENCUMBRANCE` of type `Encroachment` with no type and no direction, so the
  rules asked for both. The file says the opposite: `SIT_FEAT_ENCROACH_DTL`
  read *"None observed at inspection"*, and writing that into an encroachment
  row is what created the record. The row is gone and the statement now sits in
  `SIT_FEATURE_COMMENTARY`, where it is a disclosure rather than a record of an
  encroachment of unknown kind. `ENCUMBRANCE` blocks: 1 -> 0.
* **UAD-1195 / UAD-1192 / UAD-1202, the subject's own prior sale.** The subject
  carried `PriorSalesOrTransfersIndicator = true` and no `SALES_HISTORY` at all.
  `PSH_SUB_ANALYSIS` already stated the facts -- *"last transferred on
  05/23/2016 for $750,000 (ACRIS document 2016052700740001)"* -- but the whole
  Prior Sale section is `div label="true"`, **read-only labels**. The values are
  entered in the sales grid's subject column: `GSU_TRANSFER_HISTORY_DATE`,
  `GSU_DFE_TRANSFER_HISTORY_AMOUNT_VALUE` and `GSU_TRANSFER_HISTORY_TERMS`
  (*Typically Motivated*, as each comparable's own transfer is written, which
  is what produces `OwnershipTransferTransactionType = Sale`). The subject now
  exports `2016-05-23 / 750000 / Sale / TypicallyMotivated`.

### The one that was a formatting habit

* **UAD-1643, the highest closed price.** `MKT_HIGHEST_SALE_PRICE` held
  `1050000` -- written raw, where every sibling holds `$290,000`,
  `$1,699,000`. The raw value never reached the export. Written as
  `$1,050,000`, it exports.

  **The rule this teaches: write an amount the way the form writes it.** A raw
  number sits in the data layer looking correct and is silently absent from the
  delivered XML. The same was true of the transfer amount, which only exported
  from `GSU_DFE_TRANSFER_HISTORY_AMOUNT_VALUE`.

### The one that was not about the data at all

**UAD-1542, "a party role type of 'Client' must be set", is a render artifact.**
Measured directly, with **nothing in the data layer changing between the two**
(a full snapshot diff: 0 fields changed):

| last section rendered | parties in `CreateAndReturnMismoXML()` |
|---|---|
| `assignment` | Borrower/PropertyOwner, **Lender/Client**, Appraiser |
| `report-setup` | Borrower/PropertyOwner, **Lender/Client**, Appraiser |
| `order-1` | Borrower/PropertyOwner, Appraiser |

The Order section replaces the assignment's contact controls in the DOM and the
exporter builds the party list from what is rendered. Filling the Order
section's own `ORD_CONTACT_*` copies does not change it.

**So: leave the form on a settled section before exporting, signing or
zipping -- not on Order.** A sweep that walks all 30 sections ends on `order-1`,
which is exactly how a clean report reads "1 UAD error".

### Where it stands

Visited all 30 sections, settled on `assignment`, then:
**0 field validation problems - 0 UAD errors (twice) - 0 schema errors.**

## 2026-09-26 — 1062 Woodycrest Ave (2-4 unit): UAD 2.6 carried into 3.6

Case material: `_work/woodycrest/` (source files in `source/`, pictures in
`images/`, converter `convert26.py` + `convert_extras.py` + `convert_post.py` +
`convert_facts2.py`).

* **Pictures.** The 2.6 XML's embedded PDF is empty (`<DOCUMENT></DOCUMENT>`);
  the `.aci` is ACI's sealed RAPID! compound file (streams encrypted; its
  RAPIDFILEX library carries a no-reverse-engineering notice -- do not decode
  it). The owner then supplied the printed report PDF; `extract_images.py`
  lifts all 37 pictures from it (raw JPEGs for photos, rendered strips for the
  sketch, maps, licence, E&O) named by their printed captions.
* **Converter.** `convert26.py` builds a blank 2-4 unit case in the platform
  and writes every 2.6 value by Report Field ID through the API (300 fields,
  383 grid cells), reshapes the template's duplex comparable shells to one
  building of three units, writes per-unit adjustments with UnitIdentifier
  (the grid API cannot), rebuilds the data-source graph (the template's was
  cross-linked: one source absorbed the cost source and GEODATA), uploads the
  pictures, and exports `Woodycrest_UAD36_portable.xml` (8.6 MB, 39 pictures).
* **Judgements made, for the owner to confirm:** condition "Average" -> C4,
  "Good" -> C3 (the appraiser printed words, not C-ratings); subject
  RowhouseTownhouse, not an end unit (attached, vs the semi-D the grid adjusts
  $30,000 for); roof "Shingle" -> Asphalt; baths "remodeled 11-15 years ago" ->
  FullyUpdated / TenOrMoreYears; subject listing from the appraiser's own MLS
  workfile (One Key #997805, PND $1,100,000, 106 DOM); pending sales 12 (PND in
  that search). Licence number fields left for TOTAL's signature (standing rule).
* **Gaps no source fills:** contract date (blank on the 1025), comparables'
  per-unit finished areas (only building GBA is reported).
* Trap: `edit.insert_ordered` creates XSD-required children (ROOM ->
  ROOM_DETAIL); inserting the child again yields a schema error.

Next: import into the open TOTAL report through the MOD, fill, place photos,
validation loop to zero.

### 2026-09-26, later — Woodycrest in TOTAL: 334 -> 13 field validation, 0 UAD errors

Run order that works (`_work/woodycrest/run_in_total.py "<report>"`): TOTAL import
(replace) -> `total_fix.py` (targeted writes, then cost total via real keystrokes)
-> `place_photos.py` (55 of 56 slots, by caption/column) -> `eo.py`.

**Do not run the MOD's generic `bridge fill` on a 2-4 unit report**: it read the
GRM/rental columns from the wrong properties (subject address, $0 sale) and its
comparable-number writes raised 19 "Clear Comparable Data" prompts (all
cancelled). TOTAL's own import also smears a *listing's* SaleToListPriceRatio
adjustment across every adjustment cell of that column, and copied comp 1's
rent into unused rental columns 6-7; `total_fix.py` resets both.

TOTAL facts learned here: comparable unit rows line up only when each
comparable PROPERTY_UNIT carries UnitIdentifier "Unit n"; the appraiser's
inspection must be ONE INSPECTION linked to ROLE_Appraiser; GRM price+date must be
one SALES_HISTORY; Dwelling Style applies only to detached (comps) but the
subject still wants DE1_STYLE; an adjustment where subject = comp must be blank,
not $0; TOTAL's cost calculator uses whole-number percents (use total
depreciation to reproduce a 1025's dollars); TOTAL recomputes cost totals only
on real keystrokes (`bridge.ui.type_into`), not data-layer commits.

Left (13): comps' per-unit finished area (12) and the porch area (1) -- no source
in the 1025, the 2.6 XML or the MLS sheets. Asked the owner. Owner-confirm list
is in the chat summary of this date (condition words -> C-ratings, rowhouse,
roof age, contract date 08/03/2026, MLS conflicts on comps 2 and 3).

* 2026-09-26 18:00 — owner supplied clean licence and E&O declaration images;
  placed as Assignment exhibits "License" / "Insurance" (TOTAL and the portable
  XML; `images/License.jpg`, `images/Insurance.jpg`). The licence scan's ID reads
  ambiguously (45000046484 vs the 2.6's 46000046484) -- 2.6 value kept, owner
  asked to confirm. TOTAL shows appraiser Designation "MAI", which no file or
  script here wrote -- left alone, owner asked.

### 2026-09-26, evening — Woodycrest in TOTAL: 0 field validation, 0 UAD errors

Live report verified with TOTAL's own check (`RunEandOForTesting` item map empty,
panel "UAD Errors: 0", "Show All Field Validation" on): screenshot
`_work/woodycrest/pages/total_signature_eo_clean.png`. Figures unchanged (adjusted
1,117,700 / 820,300 / 1,035,000 / 1,078,100; cost 1,030,127). Owner still signs
and **saves in TOTAL**. The fresh-import path was not re-run end to end (T-971):
re-importing the live report would have wiped the owner's own edits.

Why each UAD error happened, and where it is now fixed:

* **Our file** (fixed in `convert_post3.py`, runs after post2 in `convert26.py`):
  - UAD-1350/1355 sewer "Non Public": the blanked template (official 2-4 unit
    sample) left its cesspool sewer row with no ownership, and the engine's
    4.076 write made an ownership-only row with no UtilityType -> TOTAL read
    sewer as private and made an "Other" utility row. Now one SITE_UTILITY per
    utility, type + ownership, Scenario 2's pattern (2.6: all four public).
  - UAD-1008/1009/1429/1430 coordinates: the 2.6 has LOCATION lat/long for every
    property; the converter never carried them. Now on 12 properties.
  - Comparable unit GLA (UnitStandardAboveGradeFinishedAreaMeasure) from the
    owner-approved split `comp_unit_gla.json`; porch 100 sq ft, concrete, under
    Outdoor Living, no empty amenity rows.
  - **Supervisor that does not exist**: the template's SIGNATORY_AppraiserSupervisor,
    its link to a ROLE that blanking removed, and an empty "by
    AppraiserSupervisor" additional certification. TOTAL made a "Supervisory
    Appraiser" signature block, put Leonardo Jo in it, left an empty Appraiser
    block, and fired UAD-1535 on it. Removed; the file has no "Supervisor" left.
  - Engine H-1 on the portable file: before 15 fatal / 10 warning, after 14 / 6,
    nothing new. The remaining engine fatals are mostly "Does Not Display" items
    TOTAL writes itself on delivery.
* **TOTAL's importer drops values the file does carry** (fixed after import in
  `total_fix.py`): SIT_COMPLIANCE Legal + SIT_CLASSCODE R7-1 + SIT_CLASSCODE_DESC;
  SKT_MEASURE_STD "ANSI" (list: ANSI, AMS); DE1_UNIT_NUMS 3;
  CA_COST_SERVICE_SOURCE_TYPE "Marshall & Swift" (a fixed list; it becomes the
  CostService DataSourceName -- CA_COST_DATA_SOURCE is not it); GC4_DWELL_CONST_METHOD
  (the grid cell, separate from GC4_PU_DWELL_CONST_METHOD).
* **Only reachable through TOTAL's own code paths** (in `total_fix.py`):
  - UAD-1091 StructureIdentifier is read off the dwelling *section*, not a
    field: `structure_identifier()` sets identifier/caption/description and calls
    SaveSections, as TOTAL's importer does.
  - the empty "Other" utility row fails EXT_SIT_UTIL not-empty: `remove_other_utility()`
    runs TOTAL's Remove Utility button with that row as engine.curField.
  - unit GLA "required" although filled: the check runs on LeaveField, so
    `typed_gla()` types each value and tabs out.
  - other rental income: rule passes only with description "None" (or a non-$0
    amount); blank fails.
  - signature blocks: `one_signer()` relabels/removes a "Supervisory Appraiser"
    block with TOTAL's own RemoveRepeatableKey (found via the webpack loader,
    like `bridge/sections.py`) when HAS_SUPERVISOR is false.

Traps: `review.run` misreads the item map once field validation is clean (the
map then holds UAD rule items: RuleId/MessageText/Severity, not fieldName) --
read `GetEandOItemMapForTesting()` directly. The engine's schema guard rejects
an empty AMENITY_CATEGORIES *and* an empty PROPERTY_AMENITY; prune empties only
where a real amenity remains. Engine-level fix for the blanking leftovers and
the utility-row writes is T-970.

### 2026-09-28 — Direction set: portable package + Import Module; knowledge/ is the source of truth

The owner chose the portable UAD 3.6 XML package imported by the Import Module
over field-by-field filling, asked for one generalized system (no per-case
fixes) that learns from every case, and moved the project's memory into the
repository. Done this session (read-only toward TOTAL):

* **`knowledge/`** created and made the first read in CLAUDE.md: `README.md`
  (rules, order of authority), `ARCHITECTURE.md` (decision, pipeline, gates,
  diagnostics schema, phases 0-6), `total/FINDINGS.md` (investigation of the
  blank report — confirmed / observed / inferred / untested), `errors/CATALOG.md`
  (E-001..E-027 from the rowhouse case, each with mechanism and state —
  most still *case-only*), `memory/` (agent memory copied in), `cases/`.
* **`total-bridge/tools/form_model.py`** — extracts TOTAL's form model from an
  open report + its bundle into `knowledge/total/builds/<build>/`. Run on
  "sample blank", build 0.0.1.3848: 4,482 controls (1,139 only in templates,
  568 in popups), 759 validators, 642 data points → 2,002 field placements
  keyed by the spec's UIDs, 42 WinTOTAL actions.
* Key confirmed facts (details in FINDINGS): the E&O check is three gates
  (field validation → schema → a la mode server rules + Fannie Mae findings) and
  skips the UAD rules when an earlier gate fails; nothing *inside the form*
  blocks sign/XML/PDF/ZIP on missing data (WinTOTAL decides from
  `geteandowarningcount`, untested); 583 of 728 H-1 rules map to a TOTAL field,
  145 do not (they need a driver table for clickable diagnostics).

Next: phases 1-6 are T-973..T-978; T-979 observes WinTOTAL's own blocking.
Phase 1 and 2 need the owner (a scratch report; permission to change the
blank). Not committed yet — the owner is asked before committing/pushing.

### 2026-09-28, later — xsi:schemaLocation was the import killer; D-1 round trips; new repo staged

* **E-028 (confirmed by experiment):** TOTAL's importer puts every ancestor's
  attributes into each element's XPath and cannot resolve `xsi:`; with the
  root's `xsi:schemaLocation` present it silently skips ~25 subject values
  (zoning, ANSI, ratings, parcel, commentaries...). SF1: 938/986 kept with it,
  964-972/985 without. Fixed generally: `engine/uad/delivery.py build()` strips
  it (delivery XML + portable XML); `total-bridge/bridge/total.py import_mismo`
  strips it from any file before TOTAL sees it.
* **E-029:** a replace-import does not reset a report; a first batch of the 12
  samples into one report was contaminated and is kept only under
  `knowledge/total/roundtrip/0.0.1.3848/_discarded_contaminated_batch/`.
  `tools/roundtrip.py reset_blank()` reopens a blank report file through
  TOTAL's `OpenReportXml` (a file with zero fields breaks the form — it was
  restored from a backup of the same file; the blank needs the building-1 /
  unit-1 / order structure fields).
* Round trips of all 12 D-1 samples, each from a fresh blank, write to
  `knowledge/total/roundtrip/0.0.1.3848/d1/`. 2-4 unit sample: rental
  comparables 3-5 lose all unit data in TOTAL (real, not ordinal noise).
* `templates/make_templates.py` generates one fill sheet per configuration
  (D-1 example × spec × H-1 rules × TOTAL fields × import status).
* `total-bridge/tools/observe.py` records WinTOTAL↔form calls for the owner's
  sign/ZIP test (T-979/T-982).
* New repo staged at `C:\UAD 3.6 PORTABLE-XML` (no history, no case material,
  identifiers redacted, spec paths repo-relative via `UAD36_SPECS`); **not
  pushed: GitHub shows it PUBLIC** — owner to make it private (T-981).
* **Results (12/12 D-1 samples, fresh blank each):** kept SF 97.8-99.3 %, MH
  98.6-98.7 %, co-op 99.2 %, condo 93.5-96.2 %, 2-4 91.3-93.0 %
  (`knowledge/total/roundtrip/0.0.1.3848/d1/SUMMARY.md`). New catalog entries:
  E-030 (TOTAL validates comparable data UAD does not require — financing,
  levels, zoning, street, functional issues...), E-031 (explicit $0 adjustment
  wherever subject and comparable differ), E-032 (rental comparables beyond the
  grid's columns lose unit data — widen grid first, untested).
  `knowledge/total/IMPORT_PROFILE.md` collects the generator's TOTAL rules P1-P15.
* `form_model.py --derive` writes `validation_profile.json` (759 TOTAL rules
  joined to data points); `templates/make_templates.py` now adds per sheet
  `total_flagged_on_example` (measured) and `total_validates_beyond_example`.
* Observer running on "sample blank" (T-979) for the owner's sign/ZIP test.
* New repo re-staged and committed **locally only** at `C:\UAD 3.6 PORTABLE-XML`
  (commit 6795087): real case config (`engine/config/appraiser.json`,
  `contract.json`, `inspection.json`, `images.json`) found and excluded, commit
  rewritten before any push; T-983 notes those files are tracked in the old repo.
  Push waits for the owner to make the GitHub repo private (T-981).
* Not re-run after today's `delivery.py` change: the full engine harness.

### 2026-09-28, evening — end-to-end on the 12 D-1 samples with pictures

* Engine harness re-run after the delivery change: **99 pass / 0 fail / 9 gap**
  (gaps = PDF page counts vs the samples; schema valid and H-1 0 fatal / 0
  warning on all 12).
* `engine/tools/d1_portable.py`: D-1 ZIP → `POST /api/import` → portable XML;
  all 12 exported with every picture embedded (19-52 each, 0 missing), engine
  review schema 0 / fatal 0 / warning 0.
* MOD: `place.py place_by_file()` (E-033) — SF1 28/28 pictures, 2-4 unit all 53
  slots. `prepare_for_total()` now relabels to TOTAL's xlink conventions
  (E-032 rental comp→unit, E-036 data sources) — 5 tests in
  `total-bridge/tests/test_prepare.py`.
* E&O depends on the open section (E-035): Sales Comparison hides 48 grid
  findings. Opening sections invents a supervisor (E-034: count min 1 → writer
  emits the role). Multi-unit comps lose per-unit rows after rendering (E-037,
  experiment pending).
* `tools/classify_findings.py` sorts field validation into pipeline defect /
  data gap / adjustment rule; on the raw D-1 samples most findings are data
  gaps the official samples do not carry (comparable details TOTAL demands).
* Batch running (started ~15:12): all 12 engine exports through TOTAL with
  pictures → `knowledge/total/e2e/0.0.1.3848/total/` (loaded the code *before*
  the relabel fix: re-run 2-4 ×2 and Condo2 afterwards to prove E-032/E-036).

### 2026-09-28, late — stopped on a usage limit; where the D-1 end-to-end stands

* New MOD pieces (all in `total-bridge/`): `bridge/reconcile.py`
  (`show_rows_with_data` E-037, `recalculate`, `clear_phantom_supervisor`
  E-034, `set_identifiers` E-006), `prepare_for_total` general relabel
  (E-032/E-036, 5 tests pass), `place_by_file` (E-033), `tools/classify_findings.py`.
* 2-4 unit sample with all fixes: kept 1490/1535 (97.1%), 53/53 photos, rows
  re-shown 20, identifiers correct, real supervisor untouched, field validation
  63. **Open and value-affecting: E-038** — TOTAL's net adjustment omits
  site-characteristic / hazard-zone / disaster-mitigation adjustments; next step
  is the NETADJ calc's field list in the bundle.
* The full 12-sample batch was stopped twice to pick up fixes; **re-run it**:
  `cd total-bridge; python tools/roundtrip.py --report "sample blank" --photos
  --out ../knowledge/total/e2e/0.0.1.3848/total ../knowledge/total/e2e/0.0.1.3848/*_Appraisal/portable.xml`
  then `--summarize` and `tools/classify_findings.py --run …`.
* Scratch report free. Observer (`tools/observe.py`, pid 1152) expires ~16:18;
  restart it before the owner's sign/ZIP test.
* New repo still unpushed (public on GitHub); re-stage before pushing
  (`scratchpad/stage_portable_repo.py` — copy into the repo's tools if kept).

### 2026-09-28, night — E-038 solved (TOTAL's nets), 12-sample batch re-running

* **E-038 cause, from TOTAL's bundle** (module `SalesCompCalcs`, build
  0.0.1.3848): `ApplySummaryCalculations(comp)` adds an adjustment only if its
  grid row is visible *when it sums*; it sums during import while rows are still
  hidden (E-037). Re-showing rows does not re-sum; `ExecuteAllCalcs` does not
  either (`ApplyFormCalculations` returns when `changedKey` is empty); and a calc
  event without `fieldSectionKey` runs the **open section's** calcs only
  (`FormCalcs.ExecuteCalcsForSection`). The catalog's earlier "not a visibility
  effect" was wrong, and so was `recalculate()`'s docstring claiming it fixed it.
* **Fix** `bridge/reconcile.py recalculate()`: after ExecuteAllCalcs, one
  `ValueChanged` per sales comparable on its `NETADJ_ADJ` field with
  `fieldSectionKey` "sales-comp" (what editing an adjustment raises; hits no
  per-field case, so only the summary runs). Returns nets before/after.
  Verified on the 2-4 unit sample left in the scratch report: −84,200 / −4,600 /
  −50,500 = the package; serialization diff before/after = exactly the 12 value
  figures; stable through re-rendering SxS, Sales Comparison, Assignment.
* `tools/roundtrip.py` now writes `recalc.json` and `value_diffs.json` (every
  difference in adjustments, nets, adjusted prices/rents, GRM, approach
  indications, the opinion) and reports `nets_corrected` and
  `value_affecting_diffs` per case; SUMMARY.md has a Value-affecting column.
* Batch re-run started 16:27 (all 12, `--photos`, ~5 min each) →
  `knowledge/total/e2e/0.0.1.3848/total/`, log `total_run.log`. Then
  `--summarize` and `tools/classify_findings.py --run …`; close T-986 on the
  result.
* Bridge tests 5/5 pass.
* Batch sample 1 (2-4 unit, fresh blank, old in-memory code + the fix):
  `nets_corrected` 3, **value-affecting diffs 0** (were 12), kept 1502/1535,
  53/53 pictures, field validation 63.
* **T-984 built — `bridge deliver` is now the Import Module.** `bridge/deliver.py`
  runs: import (`prepare_for_total`) → pictures (by file, then category) →
  `show_rows_with_data` → `recalculate` → phantom supervisor → identifiers →
  TOTAL XML vs package (`bridge/compare.py`, value-affecting rows first) → E&O
  from a neutral section (`bridge/review.py eando()`, E-035). Old fill/fixer
  path only with `--fill`. Results go to `<file>_TOTAL_check/`. `tools/roundtrip.py`
  now calls the same `deliver.run` (after `reset_blank`), so the D-1 batch
  measures the owner's path. `compare` moved to the bridge: identical output on
  12 saved pairs. `review.run` parses UAD-rule items (E-027 closed). `--as-is`
  removed from roundtrip: `import_mismo` always strips xsi, so it only skewed
  the baseline. Tests 9/9. **Not yet run live** through `bridge deliver` — do it
  on the scratch report once the batch finishes (reset_blank first).
* `tools/classify_findings.py` was a broken check: it called a finding a
  pipeline defect when *any* of the field's data points was in the package, so
  comparables' "street type and surface" (package: surface only, TOTAL kept it)
  counted as ours. Now: pipeline defect only when TOTAL's own XML lacks a value
  the package has, matched by street address. 2-4 unit: 3 → 0 pipeline
  defects (51 data gap, 10 adjustment rule, 2 untraced).
* **New E-039 (open, value of the report's first photo):** on the 2-4 unit
  sample building 2's front photo ended up as building 1's front *and* the
  subject photo; Dwelling1Front and SubjectProperty gone. `place.py` BY_ROLE
  sends every DwellingFront to `DE1_PHOTO1` and picks the slot without
  checking it is empty. Needs the live experiment in the catalog entry once the
  batch frees the report. Untraced finding `DE<n>_EXTERIOR_EXHIBIT_DESCRIPTION`
  (roof-defect exhibits without a description) to look at in the same session.
* **Batch aborted (E-040, T-987):** 16:34:59 WinTOTAL's report renderer
  (`CefSharp.Alm.BrowserSubprocess`) died out of memory (0xe0000008) importing
  sample 2 (Scenario 2); the owner saw the report pane white; the batch hung and
  was stopped at ~16:45. Only sample 1 of this run is valid (its results in
  `e2e/.../total/2- to 4-unit_Appraisal/`). `Page.alive()` now stops a batch
  when the page vanishes. **Re-run the batch on a freshly started TOTAL**, then
  run `scratchpad`-style E-039 experiment (steps in the catalog entry).
* Trap: in this shell, backslashes inside a Bash heredoc reach Python already
  unescaped once (`\\n` became a real newline inside JS/f-strings twice). Edit
  files with backslashes through the Edit/Write tools.

### 2026-09-28, evening (2) — new scratch report "sample"; E-039 fixed; preflight; blueprint

* Owner's rules this session: **no desktop control** — work in WinTOTAL only
  through the MOD (now in `_work/GOAL.md`). Scratch report is now **"sample"**
  (new, created 17:12; "sample blank" died with the renderer and was never
  saved). T-988 = owner's instruction: learn the whole 3.6-in-WinTOTAL
  blueprint by reverse engineering and remove every blocker for an
  AI-generated portable XML.
* **E-039 fixed and verified live** (2-4 unit via `bridge deliver`): slots
  matched `PHOTO\d*$` (building fronts are `DE<n>_PHOTO1`), no same-category
  overwrite, subject photo left to TOTAL (it copies DE1_PHOTO1 into
  GSU/RSU/GRU_PHOTO and GSU_PHOTO_SUMMARY, which the writer delivers). New
  profile rules P22 (subject photo = building 1 front; one front per building),
  P23 (re-sum nets), P24 (slot pattern / no overwrite).
* `bridge deliver` ran live end to end: 0 value-affecting differences, 55 slots
  naming a file, 0 empty, E&O at field validation (60, all data the sample
  lacks + E-031 rule).
* **`tools/preflight.py`** — the package against the profile before TOTAL
  (P1-P4, P8, P11, P22, P23). 0 errors on all 12 D-1 samples after 3 broken
  checks were caught by them; 8 tests (`tests/test_preflight.py`, 17 total
  pass). `knowledge/total/preflight/README.md`.
* **Blueprint**: `tools/dump_bundle.py` keeps TOTAL's form-engine code outside
  the repo (`%LOCALAPPDATA%괶-bridge\bundle\0.0.1.3848`, 281 modules);
  `tools/blueprint.py` writes `builds/<build>/blueprint.json` (1,291 classes:
  40 importer, 7 writer, 58 calcs, 30 validators) and `transfers.json` (99
  groups / 388 fields — all single facts or composites, no cross-fact
  equality; plus the code copy of the front photo). Narrative:
  `knowledge/total/BLUEPRINT.md`.
* Found in the bundle, not yet used: a la mode's own round-trip test; the
  importer's narration (`MISMODeserializerHelpers`, switch unreachable).
* **12-sample batch running** since 17:47 on "sample" with every fix, heap
  recorded per sample (86 MB after sample 1). Sample 1: kept 1503/1535, value
  diffs 0, photos 0 empty, FV 60. When it ends: `--summarize`,
  `classify_findings.py --run`, then learn P12/P13 from the data-gap findings
  and add them to preflight, checked against the measured findings.

### 2026-09-28, late evening (3) — the MOD recognises the report; one diagnostics list, clickable inside TOTAL

Owner's instruction (T-989/T-990/T-991): the MOD must recognise whichever report
is open (not a hard-coded 1004/1025/1073/2090/2055 list), give each open report
its own HUD, run diagnostics before and after import pointing at the exact
field, and be ready for a real **multi-family** case the owner will supply.
Scratch report is now **"SAMPLE BLANK"** (new 19:08, web engine **0.0.1.3855** —
TOTAL updated itself; diff: `knowledge/total/builds/0.0.1.3855/DIFF_FROM_0.0.1.3848.md`,
vehicle storage only). The 3848 batch on "sample" stopped after 8 of 12
(SF2 interrupted, SF3–5 never ran, no summary) when that report was closed.

Built, tested, live-verified on SAMPLE BLANK (read-only except navigation):

* **`engine/uad/spec/extract_legacy_forms.py` → `engine/spec/legacy_forms.json`**
  from the GSEs' *Functioning without Form Numbers* v1.1 (PDF fetched from
  Freddie Mac, now beside the other official files and in the repo root): six
  driver data points → 12 legacy forms, atypical kinds and examples. The note
  "does not apply for high/mid/low-rise" resolves from A-1 to
  StructuralDesignType.
* **`total-bridge/bridge/detect.py`, `bridge detect [--xml]`**: TOTAL form code
  and family (URAR / Completion / Restricted Update / mobile — TOTAL's own
  literals), TOTAL's 22 writer switches (its `SharedDataCommonInfo`, generated
  into `builds/<build>/configuration.json` by `tools/blueprint.py`, evaluated
  with TOTAL's own `Indicator` helper), section structure (buildings / units /
  ADUs / outbuildings / manufactured, TOTAL's multi-family test), grids, the six
  drivers (live via uid_map, or from any MISMO file) → legacy form or atypical,
  active report among several (visible/focused page). 12/12 D-1 samples agree
  with their names (`tests/test_detect.py`); TOTAL's XML keeps the drivers on
  8/8 batch samples.
* **HUD**: new rows REPORT (e.g. "URAR · 1025 (72) · Traditional") and CONFIG
  ("2 bldg · 4 unit · 0 ADU · Sales+Incom"), per report page; `bridge hud
  --watch` refreshes each open report every 30 s.
* **`total-bridge/bridge/diagnose.py`, `bridge diagnose`**: one Diagnostic shape
  (ARCHITECTURE §6). `--xml` alone = before import: preflight + what the package
  is + writer switches it leaves to TOTAL's defaults (E-042). `--report` = after:
  detection, mirror/source disagreements, both-marked Yes/No pairs anywhere
  (E-041), TOTAL field validation, UAD rules (only when FV is clear — else
  "not run", P21), round trip when `--xml` is also given. `--hud` puts the list
  in the panel; **clicking an item opens its section and outlines the field**
  (verified: SPA_AMENITY_CATEGORY → Subject Property Amenities). 58 tests pass.
* Knowledge: FINDINGS §9 (recognition) and §10 (WinTOTAL on disk: MajorForms
  has no 3.6 entry; `<Proj2000ID>-<guid>.oz_` per open report; `.zap`/
  `ReportData` encrypted — we stopped there; delivery trace log empty — no ZIP
  built on this machine yet). CATALOG E-041, E-042, E-043. PROFILE P25, P26.

Traps: a blank TOTAL report is **not** empty (557 defaults: amenities exist,
sketch, Itemized, 1 unit, Traditional …) — the package must state every switch
(P25). The HUD's own "inject" button bypasses the Import Module (E-043, T-992):
use `bridge deliver`. Never write Python containing backslashes through a bash
heredoc — use the Edit tool (hit twice again today).

Next, in order: (1) the owner's multi-family case → `bridge diagnose --xml`
before import, `bridge deliver` on SAMPLE BLANK, `bridge diagnose --report
"SAMPLE BLANK" --xml <package> --hud` after; (2) re-run the 12-sample batch on
3855 (`tools/roundtrip.py`), then `--summarize` and learn P12/P13 into preflight;
(3) T-992; (4) T-979 sign/ZIP observation to fill in "blocking".

**Later the same evening.** The panel's >> inject button now goes through the
Import Module (`bridge hud --watch` must be running; `hud.serve_request`):
verified live with the SF1 portable package on SAMPLE BLANK (3855) — preflight
clean, import 52 s, pictures, reconcile, verify, then the diagnostics list in
the panel: 60 field-validation items (the known E-030/E-031 sales-grid data the
D-1 sample lacks), **0 value-affecting round-trip differences**. Round-trip rows
TOTAL owns (vendor, version, spec v1.3, PDF name, defect pictures under the
inspection) are labelled expected from `knowledge/total/expected_differences.json`.
Trap met on the way (CATALOG E-043): a panel installed by older bridge code kept
its bare-import button; panels now carry a code version and are replaced.
Freshness (P5): `tools/new_report.py` fingerprints what a new report holds
(`builds/0.0.1.3855/new_report.json`, 634 fields incl. the reset observation);
`detect.freshness` flags anything else (it saw the stray import's 1,179 values).
AMC party (E-029 open note): TOTAL's importer drops any value whose row does not
exist; which new-report field makes it add the second contact row is still [U]
— the owner's first freshly created report (the multi-family case) will show it.
State at hand-over: SAMPLE BLANK reset to blank (fresh); a `bridge hud --watch`
started by this session may still be running.

## 2026-09-28, 20:50 — TAKEOVER BRIEF (read this first; the session that wrote it hit its usage limit)

### What the owner wants (condensed)
A system where the owner hands over one appraisal case folder/ZIP and gets back
**one portable UAD 3.6 MISMO XML** (pictures embedded, every section filled)
that the **Import Module** (`total-bridge/`, "the MOD") imports into a **new
WinTOTAL report**, rebuilt through TOTAL's own structures, so the report has
**zero actionable errors, visible or hidden, except the appraiser's
signature**. Every error met is fixed as a *mechanism* (never a per-property
hack), recorded in `knowledge/errors/CATALOG.md` with its test, so each case
improves the next. The MOD recognises whatever report is open (URAR /
Completion / Update; property type and its legacy-form equivalent; buildings,
units, ADUs, grids) and shows a HUD plus a clickable diagnostics list inside
TOTAL.

**Next job: a real MULTI-FAMILY case.** The owner will attach a folder.
Deliver: portable XML, `bridge diagnose --xml` clean, import into a NEW
WinTOTAL report the owner creates, `bridge diagnose --report <name> --xml
<package> --hud`, fix every new error generally, regenerate, re-import, until
only the signature is left.

### Owner's standing rules (full list: `_work/GOAL.md`)
* **No blank fields; fill gaps by online research, never demo data** (decided
  2026-09-28, T-994). Facts the folder lacks come from county assessor /
  records, listing portals, FEMA flood, census tract, zoning, rent and market
  data; keep the source per value (UAD's data-source fields need it); list
  every researched or estimated value for the appraiser to confirm; derive the
  value opinion from the comparables with the arithmetic shown. Never log in to
  or get around a site; owner and borrower names come from the folder.
* No desktop control of the owner's PC: WinTOTAL only through the MOD (CDP
  127.0.0.1:8088). Only the owner opens, creates or reopens reports.
* Scratch report = **"SAMPLE BLANK"**. Real cases go into a **new** report.
* No licence number in the report (signing adds it). Never bypass or silence
  validation. Specs are the authority; generate from them. Validate every
  validator against the 12 D-1 samples.
* Keep TASKS.md, HANDOFF.md and knowledge/ current as work lands.

### How the system works now (run from `total-bridge/`)
| Step | Command | What it does |
|---|---|---|
| Recognise | `python -m bridge.cli detect [--xml f]` | form, TOTAL's config switches, structure, six GSE drivers to legacy form (FINDINGS §9) |
| Before import | `python -m bridge.cli diagnose --xml PACKAGE` | preflight (profile P1-P26), engine XSD + executed H-1, package config, switches left to TOTAL defaults |
| Import | `python -m bridge.cli deliver --xml PACKAGE --report "<new report>"` | TOTAL's importer (xsi strip, label conventions), pictures, hidden grid rows re-shown, nets re-summed, phantom supervisor cleared, verify |
| After import | `python -m bridge.cli diagnose --report "<name>" --xml PACKAGE --hud` | TOTAL field validation, UAD rules (only once FV = 0), Yes/No conflicts, mirrors, round trip; list in the panel, click goes to the field |
| Panel | `python -m bridge.cli hud --watch` | panel on every open report; its inject button runs the same Import Module (refuses signed / not-new / bad packages) |
| Batch | `python tools/roundtrip.py --report "SAMPLE BLANK" --photos --out ../knowledge/total/e2e/<build>/total ../knowledge/total/e2e/0.0.1.3848/*_Appraisal/portable.xml` | the 12 D-1 samples end to end; `python tools/batch_summary.py <log>` summarises |
| Causes | `python tools/classify_findings.py --run ../knowledge/total/e2e/<build>/total --build <build>` | each FV finding: pipeline-defect / data-gap / adjustment-rule / untraced |
| New TOTAL build | `tools/form_model.py`, `tools/dump_bundle.py`, `tools/blueprint.py --build B`, `tools/diff_builds.py OLD NEW` | re-extract and diff (now also compares code class sizes) |
| Tests | `python -m pytest tests -q` | 58 pass |

### Where things stand at hand-over (20:50)
* **12-sample batch on web engine 0.0.1.3855** was running in the background
  (log `knowledge/total/e2e/0.0.1.3855.batch.log`, results in
  `knowledge/total/e2e/0.0.1.3855/total/`). Done: 2-4, 2-4 S2, Condo1, Condo2,
  Coop1, MH1, MH2 (21:00), all with **0 value-affecting differences, 0 empty
  picture slots, 96-99 % of values kept**; heap climbs ~15 MB per sample
  (133.5 MB after MH2) -- if the report pane goes white (E-040) the owner must
  reopen SAMPLE BLANK, then re-run only the missing SF samples. It may have stopped with the session: check the
  log and re-run only the missing samples (MH1, MH2, SF1-SF5) with the batch
  command, then `--summarize` and `classify_findings.py`. So far **0 pipeline
  defects** in 479 FV findings (411 data gaps, 65 $0-adjustment rule, 3
  untraced exhibit descriptions). Watch the page heap (E-040: the renderer died
  once; 102 MB after sample 5).
* **T-995, the key open proof**: does TOTAL's importer place the extra
  comparable facts TOTAL validates (financing, levels, street/surface, zoning
  compliance, functional issues, cooling, topography, project amenities) and
  the $0 adjustments when a package *has* them? Never observed, because the
  samples lack them. Built: `tools/fill_test.py`, output
  `knowledge/total/e2e/0.0.1.3855/SF1_TEST_NOT_A_REPORT.xml` (stand-in values,
  **never a deliverable**). Next: after the batch, `roundtrip.reset_blank`
  SAMPLE BLANK, `bridge deliver` that file, `bridge diagnose --report "SAMPLE
  BLANK" --xml <it> --hud`; expect FV to reach 0 and the UAD rules to run;
  whatever fails is a mechanism to fix. Rebuild the test from the **3855** SF1
  findings once that sample has run. **Warning sign**: on 3848 SF1, TOTAL
  flagged kitchen / bath / walls quality and window condition as required for
  subject and comparables although the package carries them. Check with
  classify_findings on 3855 SF1; if TOTAL lost them, that is a pipeline defect.
* **T-996, silent drops still open** (round trip): the AMC party and its fee
  (E-029 note: the importer drops any value whose row does not exist; new and
  reset reports differ in `ORD_CONTACT_PARTY_ROLE` / `ORD_REPORT_TYPE`; test on
  the owner's new report), report-level DATA_SOURCES (2-4), unit
  FloorIdentifier, picture metadata (date, GPS, category, caption) on Condo1.
* **Multi-family generator readiness**: intake is not general yet (T-977).
  Woodycrest (2-4 unit) was built with case scripts in `_work/woodycrest/`
  (convert26.py etc.) and reached 0 FV / 0 UAD only with post-import fixes.
  For the new case: read the folder, build facts with provenance, research the
  gaps online, generate the package through the engine (`engine/uad/edit.py`
  `write(tree, field_id, value, scope=comparable)` writes any field in schema
  order; `engine/uad/report/comparables.py write_adjustment` for adjustments);
  include everything TOTAL validates beyond UAD (P12; `fill_test.py` shows the
  join TOTAL field to Report Field ID to data point) and $0 adjustments where
  subject and comparable differ (P13; list them for the appraiser); state every
  writer switch (P25); never both Yes and No (P26); subject photo = building 1
  front, one DwellingFront per building (P22).
* Nothing else running: no watcher, no observer. SAMPLE BLANK is in use by the
  batch; afterwards reset it with `tools/roundtrip.py reset_blank` before any
  test.
* The new GitHub repo (T-981) is still unpushed: it is PUBLIC, and the owner
  must make it private first.

### OWNER PRIORITY (21:05): MULTI-FAMILY ONLY (T-997)
Fix every blocker that affects a **2-4 unit** report so the owner's
multi-family case passes; single-family / condo / co-op / MH errors wait for a
later session. The batch was stopped after MH2 for this reason (SF1-SF5 not run
on 3855 — not needed now).

Multi-family work done at 21:05-21:20:
* **E-044 / P27** — defect pictures without a caption become exhibits TOTAL's
  field validation rejects (the 2-4 sample's DE1/DE2 exterior exhibit findings;
  also Condo1, MH1). Preflight P27 flags them; generator must caption every
  defect picture from its defect record. Test in `tests/test_preflight.py`.
* `tools/fill_test.py` now covers every grid (sales GC, GRM GR, rental property
  RP, rental unit RC), per-unit rows (instance = unit; per-unit adjustments with
  UnitIdentifier) and P27 captions. Built
  `knowledge/total/e2e/0.0.1.3855/2-4S2_TEST_NOT_A_REPORT.xml` (212 stand-ins).
* **Suspected multi-family import losses** (package carries the value, TOTAL
  still flags it): GR#_GBFA (GRM comparables' gross building finished area,
  income approach), RC1.2/RC2.2 rows (units of rental comparable 2: furnished,
  market area, rent concessions, rent control, utilities, overall comparison),
  GC#_UNITS_SF_GLA_BELOW_GRD_NONSTD per unit. `tools/run_test_package.py
  --report "SAMPLE BLANK" <test package>` was run on the 2-4 S2 test at 21:20
  (log `knowledge/total/e2e/0.0.1.3855/2-4S2_TEST.log`, result
  `2-4S2_TEST_NOT_A_REPORT_result.json`): whatever TOTAL still flags there is an
  import mechanism to fix (compare package vs `total.xml` for those rows; E-032
  / P10 is the rental-unit labelling precedent). Then do the same for the other
  2-4 sample, then run the owner's multi-family case.

**RESULT of the 2-4 S2 test (21:35, `2-4S2_TEST_NOT_A_REPORT_result.json`)**:
field validation 225 -> **99** with stand-ins, 0 value-affecting diffs; UAD
rules still not run (FV not clear). What is left, by cause:
* **Confirmed import losses (round trip shows package value dropped)** — fix as
  mechanisms, these block every multi-family case:
  1. `FunctionalIssueType` = None on sales comparables: dropped, then FV
     "complete all required functional issues fields" (3). Read how
     `MISMODeserializerURARImporterSalesComp` imports FUNCTIONAL_ISSUES for a
     comparable (bundle snapshot) and emit that shape.
  2. Per-unit `RoomUpdateStatusType` (kitchen) and `OverallFlooringUpdateStatusType`
     on sales comparables' PROPERTY_UNITs: dropped, FV INT_COND_KITCHEN /
     INT_COND_FLOORS (12 + 12). Compare the path fill_test/edit.write used with
     the subject's path for the same facts and with the importer's reader.
  3. `UnitNonStandardBelowGradeFinishedAreaMeasure` per comparable unit: TOTAL
     adds its own 0 and then fails its own validator ("Validation failed", 12)
     — find what the validator wants (validation_profile.json / bundle).
* **Test builder gaps, not TOTAL's** (TEST1 had a scoping bug — fixed in
  `fill_test.py` `held()`; rebuilt as `2-4S2_v2_TEST_NOT_A_REPORT.xml`, not yet
  imported): rental comparable unit rows RC#_FURNISHED / MARKETAREA / RENT_CONC
  / RENT_CONTROL / UTILS_INCLUDED / SMRY_OVRL_COMP_TO_SUB (48), GR#_GBFA (3),
  EXT_QUAL_ROOF, SITE_TOPOGRAPHY; and DWELL_STYLE_ADJ (3) is the test writing a
  $0 adjustment although its own stand-in made subject and comparable equal
  (P13: equal -> no adjustment). **Next: import TEST2** (`python
  tools/run_test_package.py --report "SAMPLE BLANK"
  ../knowledge/total/e2e/0.0.1.3855/2-4S2_v2_TEST_NOT_A_REPORT.xml`), check
  whether the rental-unit rows then clear (if not: rental comparable units are
  an import mechanism too — E-032 / P10 labels), fix 1-3 above, repeat until FV
  = 0 and TOTAL's UAD rules run; then the same on the 2-unit sample.

### Traps that cost time this session
* Python edits containing backslashes (or long text) through a bash heredoc
  get mangled or rejected: use the Edit / Write tools.
* A HUD installed by older code keeps its old handlers: panels are versioned now.
* "Fresh" is not "empty": a new report holds ~630 values (557 TOTAL defaults).
* Grid rows hidden when P18 runs escape both the writer and field validation,
  so counts vary with render state.
* Never decrypt `.zap` / ReportData or patch TOTAL's code (the importer's log
  switch is unexported; use the round trip instead).

## 2026-09-28, late — TAKEOVER: the next case is SINGLE FAMILY, not multi-family

The owner reversed the priority in the previous brief: **"i will give you
single family .. not the multi"**. T-997 ("MULTI-FAMILY ONLY for now") is
superseded — that is why the 12-sample batch was stopped after MH2, and it is
now the wrong place to stop.

### State verified on takeover, not assumed

* `python -m pytest tests -q` in `total-bridge/` — **60 passed**.
* TOTAL is running (`alamode.WinTOTAL`, window "sample"), but **no report is
  open**: the CDP endpoint on 127.0.0.1:8088 answers with **0 targets**. Every
  live step (batch, import, diagnose `--report`) is blocked until the owner
  opens a report, since only the owner opens reports.
* 12-sample batch on 0.0.1.3855: **7 of 12 done** (2-4, 2-4 S2, Condo1,
  Condo2, Coop1, MH1, MH2), each with 0 value-affecting differences and 0
  empty picture slots. `SF1_Appraisal/` in the results directory is **empty** —
  the run stopped before it. **SF1–SF5 have never run on 3855.**
* `classify_findings` has only been run over the first four samples: 479 FV
  findings, **0 pipeline defects**, 411 data gaps, 65 $0-adjustment rule, 3
  untraced exhibit descriptions.

### What single family needs, and what is already there

The proof package for T-995 was already built and is single-family:
`knowledge/total/e2e/0.0.1.3855/SF1_TEST_NOT_A_REPORT.xml` (3.8 MB, 20:49).
Diagnosed offline on takeover:

```
configuration info 1, generator-h1 info 171, profile warning 1
[warning/profile]  SubjectProperty  2 DwellingFront picture(s) for 1 building(s)
```

**0 errors.** The one warning is P22 / E-039 territory — two front pictures for
a single building — and it must be resolved before a real single-family case
runs that path, because E-039 is exactly the defect where a second building's
front photo replaces the first's.

### The order of work, once a report is open

1. Owner opens **SAMPLE BLANK**.
2. Run the five missing SF samples through the batch, then `--summarize` and
   `classify_findings.py`. That is the single-family evidence base, and it is
   what the owner's case will be measured against.
3. Run the SF1 proof package (T-995): `reset_blank`, `bridge deliver`,
   `bridge diagnose --report "SAMPLE BLANK" --xml <it> --hud`. Expect FV to
   reach 0 and the UAD rules to run; whatever fails is a mechanism to fix.
4. Resolve the P22 DwellingFront warning above.

### Which open blockers actually touch single family

Most of T-998 is per-unit and rental-unit work that a one-unit report never
exercises. The ones that **do** reach a single-family report:

* **E-045** — a comparable's `FunctionalIssueType` is read by TOTAL inside
  `IMPROVEMENT` while A-1 puts it on `PROPERTY`. Sales comparables exist on
  every report, so this is not multi-family-specific. `prepare_for_total`
  copies it; **live confirmation still pending**.
* **E-030 / E-031** — the comparable facts TOTAL validates beyond UAD, and the
  $0 adjustment wherever subject and comparable differ. Both are per-comparable
  and apply to single family unchanged.
* **T-996** — the AMC party and its fee, and picture metadata. Not
  unit-count-specific.

The rental-unit losses (per-unit kitchen/flooring update status, per-unit
non-standard below-grade area, rental comparable unit rows) stay open but are
**not** on the critical path for a single-family case.

## 2026-09-28, late — 89 Rockland Ave, Yonkers (SINGLE FAMILY): case in progress

Owner attached `C:\Users\MOHIT\Documents\OFFICE\89 ROCKLAND` and opened the
report **"89 Rockland Ave"** in TOTAL (UAD 3.6 URAR, web engine 0.0.1.3855,
1 building / 1 unit, sales comparison only). Case model with a source for
every value: **`_work/rockland/facts.py`** — read it before touching the
report.

### The one judgement that moves the value

The measured sketch totals **1,764 sq ft "Total Living Area"** by adding the
764 sq ft lower level to the 1,000 sq ft upper level. Four things say the
lower level is **below grade**:

* IMG_7198 — a window set hard against the ceiling (ground outside at head
  height) and a suspended drop ceiling.
* IMG_7180 / IMG_7184 — the site rises to the rear; the garage and lower level
  are at grade only on the driveway side.
* ATTOM — **1 story, 800 sq ft, "Garage, Basement"**.
* The appraiser's own folder is named **"lower mezz as basement"**.

Entered as **Level B1 = Partially Below Grade, 764 sq ft finished** and
**Level 1 = Above Grade, 1,000 sq ft finished**, which is also what makes
ATTOM's square footage and story count agree. **On the handback — it is the
appraiser's call and it changes the grid.**

### Case facts worth carrying

* Reverse-mortgage refinance, **Longbridge Financial** through **Atlas VMS**
  (NY AMC licence AMC-23-1104); borrower [BORROWER]; order [ORDER NUMBER].
* Raised ranch, 1981, detached, C3, hot water baseboard on **gas** (sheet)
  against ATTOM's forced air on **oil** — the sheet is the appraiser's own
  observation and is written; the conflict is on the handback.
* Built-in 1-car garage 156 sq ft, deck 72 sq ft, both non-living.
* **Comparable 4 (72 Gibson Pl) is a PENDING sale, not closed** — accepted
  contract, coded and adjusted as such. Comparables 1-3 are the three closed
  sales the engagement requires.
* **Comparable 1 has no GEO sheet** and no published parcel coordinate; 0.84
  miles south is a *street-level* geocode of Courter Avenue (OpenStreetMap
  Nominatim), recorded as street-level, not parcel-precise. Comparables 2-4
  are measured from ATTOM coordinates (1.03 E, 1.27 E, 0.85 S).
* ATTOM prints **"listing statistics are currently unavailable for historic
  1004MC's"**, so active listings, months of supply, median list price and
  sale-to-list ratio have no source in the folder.

### Mechanism confirmed again

**Adding level and room rows works only through the section's own controls.**
`rtv.put` cannot create a row. `ui.click(page, ".button-guidance-add",
"+ Add Level")` through the DevTools input domain added the level and nine
rooms first time — the same finding as E-024 / the "+ Add Level" note in
`ui.py`, now confirmed on a single-family report.

### Where it stands

Field validation **501 -> 494**, but the subject sections are the part that
moved: assignment 43 -> 25, site 30 -> 17, interior 20 -> 10,
dwelling-exterior 10 -> 3, best-use 6 -> 0. **sales-comp went 339 -> 393**,
because giving the subject its levels and rooms means every comparable must
now mirror them — E-030 / E-031 exactly. The grid carries **3 columns and the
folder has 4 comparables**, so a fourth column has to be added before it is
filled.

**Next:** add the fourth comparable column, fill all four from
`_work/rockland/facts.py` COMPS, write the $0 adjustments where subject and
comparable differ (P13/E-031), then the photographs (24 in four folders) and
the sketch.

### Rockland, continued — the grid, and a new blocker (E-046)

Field validation **501 -> 441**. Subject sections are substantially filled;
the three closed comparables are written (69 of 72 values landed through the
data layer).

**E-046, recorded**: the fourth comparable column cannot be added from the
screen. `Add Comp #4` exists but its ancestor `guidance-entry-container` is
`display:none`, and the sales grid is virtualised -- with the section open
only **20** controls render and no `GC*` cell exists to focus -- so the
guidance panel cannot be raised either. `HIDDEN_SALESCOMP_COUNT` is an output,
so writing it does nothing. The columns that *do* exist are fully writable
through the data layer regardless of rendering.

Consequence for this case: comparables 1-3 (the three **closed** sales the
engagement requires) are in the grid. Comparable 4, 72 Gibson Pl, is a
**pending** sale and is supporting evidence rather than a required sale -- it
has no column yet.

Still open on this case: the $0 adjustments where subject and comparable
differ (P13/E-031), `SITSITEAREA` is the wrong key for a comparable's site
area (3 misses -- find the grid's own key), the 24 photographs and the sketch,
reconciliation and the value opinion, and the items in
`_work/rockland/facts.py` OPEN.

### Rockland progress: 501 -> 49 field validation, 0 schema errors

Filled: assignment and parties (incl. the **AMC block added through
`+ AMC`** -- Atlas VMS, Miami), subject property, site, dwelling exterior,
two interior levels with **Level B1 = Partially Below Grade 764 sq ft** and
**Level 1 = Above Grade 1,000 sq ft**, ten rooms, vehicle storage, the deck
amenity, highest and best use, market (ATTOM 1004MC), subject listing
history, prior transfers, the three closed comparables end to end, the value
opinion (**$650,000**, inside the $615,000-$675,000 range of the closed
sales, arithmetic in the reconciliation), and the cost and income approach
exclusions.

**Photographs: 13 placed** -- subject front (DE1_PHOTO1), the measured
sketch, subject/site/rear/garage/deck exhibits, two interior exhibits, and
the three comparable photographs **extracted from the MLS PDFs**
(`_work/rockland/comp_photos/`). All captioned (E-044).

**15 photographs could not be placed: there are no slots for them.**
`+ Add Exhibit` is hidden in every section for the same reason as E-046 --
it lives in a `guidance-entry-container` with `display:none`. So a
screen-driven report is capped at the exhibit rows it was created with.
This is the strongest argument yet for the import route: `bridge deliver`
creates the rows from the package.

Values **researched, not from the folder** (all on the handback):
appraiser's firm address and Certified General level (ASC federal registry),
Atlas VMS address, comparable 1's street-level geocode, 68 active listings
(Zillow, Sept 2026) and 25 pending derived from the 24.75/month absorption
rate -- ATTOM prints "listing statistics are currently unavailable for
historic 1004MC's".

## 2026-09-29 — 89 Rockland Ave: owner's review fixed; FV 3 (licence, at signing), schema 0

The owner reviewed the report and found: assignment photo missing, interior
photos wrong (a living room as the kitchen, basement rooms under Level 1),
most photos missing, **the AC condenser placed as the deck**, comparable 4
missing, and GLA to be 1,000 with the 764 sq ft lower level as basement.
All fixed. The root cause of the photo errors is the lesson: **I placed
pictures by folder and free slot without looking at them** (CATALOG E-047).

**E-046 is solved for both halves** (catalog updated):
* comparable column: `dataSet.CompManagers.get("sales").AddComp(1,false)`,
  the method TOTAL's own button calls;
* exhibit rows: focus a cell of that exhibit table, then click the guidance
  button that appears -- description cell for most sections, caption cell
  for Vehicle Storage, and Site's label has no "+".

**E-048** new: a Pending comparable must carry no sale price or transfer
terms; a Driveway needs its surface material in `PU_VEHICLE_STORAGE_DETAILS`
(the validator fires on HidePopup, action 17).

Once comparable 4 and every photo were in, the 19 structural and 21 "no-none"
rows that had looked stuck all resolved -- they were cascades of incomplete
rows, not true blocks. **Field validation 46 -> 3**; the 3 are the licence
fields signing fills. Schema 0 twice. Handback:
`_work/rockland/HANDBACK.md`. Tools: `_work/rockland/photos.py` (manifest +
row adding), `grid.py`, `facts.py`.

## 2026-09-29, later — 89 Rockland Ave: **FV 0 · schema 0 · UAD errors 0**

Owner asked for the adjustments on "our 18 North file, same parameters", the
credential fields fixed, designation MAI, and licence + E&O in the assignment
exhibits. Done except the last (files not on disk -- see below).

* **Adjustments** read out of the 18 North grid (no rate paragraph exists
  there; each rate = amount / difference): $75/sf GLA, $10/sf site (>1,000 sf),
  $250/yr age (>5 yr), $10k bedroom, $5k half bath, $10k finished basement,
  $10k garage space, $10k outdoor living, 2% of list for exposure. Applied by
  `_work/rockland/adjust.py`. Nets re-summed with `reconcile.show_rows_with_data`
  + `recalculate` (E-038: TOTAL's net had left out outdoor living and the
  exposure line). Adjusted: 581,170 / 701,780 / 684,150 / 713,850; value
  **$665,000** (weights 25/25/40/10, arithmetic in the reconciliation).
* **Credentials**: MAI; NY 46000046484 exp 03/12/2028 (owner's signature
  block); AMC Atlas VMS NY AMC-23-1104 exp 03/29/2027 (engagement).
* Field validation 0 exposed **18 UAD errors** (E-051); all fixed: hazard
  zone half-of-pair (E-049), unlisted subject, exposure-days gate, pending
  comparable sale date (E-050), living unit count, parcel area, zoning
  compliance/description, estate type, ANSI measurement standard,
  kitchen/bath condition + update + timeframe, and the SCA boundary map
  (drawn from OpenStreetMap tiles, `_work/rockland/map.py`).
* **Map finding for the owner**: comps 2 and 3 are east of the Saw Mill River
  Parkway / Tibbetts Brook Park (Central Park Ave, near the Raceway); the
  subject and comps 1 and 4 are in Park Hill. No location rate in 18 North,
  so no adjustment taken.
* **Open**: assignment exhibits must be the licence + E&O declaration. The
  owner pasted both as images mid-message; pasted images are not saved to
  disk and no file by those names exists on the machine. The engagement
  letter stays in the slot until the files are dropped into the case folder.

## 2026-09-30 — THE FOLDER TRAVELS: portable, self-installing, one command per case (READ THIS FIRST)

The owner is handing this folder to other appraisers' devices. On a new device
an agent is told only **"refresh your memory"**, then given a case folder. It
must install the MOD into *that* WinTOTAL, confirm the right report is open,
fill ~100% with the same adjustments, and hit none of the errors met here.

**Entry point: `START_HERE.md`** (CLAUDE.md now says so first). Then
`knowledge/PLAYBOOK.md` (the case runbook + traps checklist).

### What changed

* **Portable.** The official specs are now inside the folder at
  `specs/official/` (copied from `C:\3.6 uad zips\_UNZIPPED_ALL`, 873 files,
  220 MB). Every hard-coded path to this PC was replaced (`bridge/schema.py`,
  four engine spec scripts, three engine tests) with `UAD36_SPECS` →
  `specs/official` → old path. The D-1 zips were already in the root.
* **Setup:** `setup/install.ps1` (Python check → packages → memory seed →
  `check.py --tests`), `setup/check.py` (one PASS/WARN/FAIL line per
  requirement, each FAIL says the fix; warns when TOTAL's web-engine build
  differs from the extracted model), `setup/seed_memory.ps1` (copies
  `knowledge/memory/` into the agent's memory for this folder path),
  `setup/requirements.txt`, `setup/export_for_device.py`.
* **The case kit (the MOD), one command per case:**
  `python -m bridge.cli case --json case.json [--dry-run]`,
  `bridge certify --report`, `bridge sheets --folder --out`. Modules
  `casekit.py`, `formkit.py`, `adjust.py`, `exhibits.py`, `locmap.py`,
  `certify.py` encode everything proven on 89 Rockland: 876 field writes and
  12 structural moves in the proven order. `case_template.json`, worked example
  `knowledge/cases/worked_example_sf/case.json` (anonymised).
* **Tests:** `total-bridge/tests/test_casekit.py` — every key the plan writes
  exists in TOTAL's model (caught one real bug on its first run: a note key
  would have been written as field `GC1__about`), the adjustment engine
  reproduces TOTAL's own nets on the finished report exactly (−33,830 /
  +26,780 / +9,150 / −36,150), the 18 North rates re-derive from its grid,
  pick-list and format rules. Suite: **68 passed**.
* **Profiles:** `profiles/appraiser.json` (Leonardo Jo, MAI, NY 46000046484),
  `profiles/advent.json` (Howard F. Jackson Jr., Advent, NY 46000004840, read
  from `MATERIALS/APPRASER INFO AND MATERIALS`, licence + insurance copied to
  `profiles/documents/advent/`; designation not stated — ask). The kit places
  the profile's licence + E&O in Assignment Information itself.
* **Memory in the folder:** `knowledge/memory/uad36-appraiser-defaults.md`,
  `uad36-casekit.md` added to the shared index.

### Honest status

* Every write and structural move in the kit was executed on the live 89
  Rockland report (FV 0 / schema 0 / UAD 0). **The kit itself has not yet run
  end to end in one pass on a blank report**, and its `--dry-run` against the
  finished report is still to do — TOTAL was closed when this was built.
  First job when TOTAL is open: `bridge case --json _work/rockland/case.json
  --dry-run` (expect only free-text and format differences), then the first
  real case with `--dry-run` before the fill.
* **Missing:** Leonardo Jo's licence and E&O images
  (`profiles/documents/licence.png`, `eo_insurance.png`) — the owner pasted
  them into chat; pasted images are not saved. The 89 Rockland report still
  carries the engagement letter in Assignment until they arrive.
* Not covered by the kit: condo, co-op, 2–4 unit, manufactured, ADUs,
  multiple buildings; listed-subject and subject-prior-transfer paths untested
  through the kit (PLAYBOOK §9).

### Export

`python setup/export_for_device.py` → `Documents\UAD36_for_device_<date>.zip`
(~1.4 GB before compression). Leaves out `.git`, caches, a la mode's cached
bundle, and **real client case material** (borrower names, loan numbers,
delivered reports, photos of real homes); `--include-case-material` /
`--include-git` bring them. Everything left out is listed in
`EXPORT_MANIFEST.txt` inside the zip.

Built and verified 2026-09-30: `Documents\UAD36_for_device_20260930.zip`,
1,102 MB, 3,691 entries, `testzip` OK. Client identifiers listed in
`setup/redact_terms.txt` (itself never shipped) are replaced in every shipped
text file -- 1 file needed it (this handoff); a scan of all shipped text for
the known names and loan/order numbers found none left. **For every new case,
add its identifiers to `setup/redact_terms.txt`** (PLAYBOOK §8).

## 2026-10-01 — TOTAL updated to web engine 0.0.1.3886; next case is a 3-family

* `setup/check.py` caught it: TOTAL now runs **0.0.1.3886** (was 3855).
  Re-extracted with `tools/form_model.py` → `knowledge/total/builds/0.0.1.3886/`;
  `tools/diff_builds.py 0.0.1.3855 0.0.1.3886`: **0 validators, 0 controls,
  0 pick lists, 0 MISMO placements, 0 repeatables, 0 templates changed.** One
  validation message added: sales-comp `DWELL_CONST_METHOD`
  `constructionmethodcountmatchesyearbuilt` — "Number of buildings defined by
  number of year built values provided" (matters for multi-building
  comparables). The 1282 "removed classes" lines are an artifact: the 3886
  bundle has not been dumped (`tools/dump_bundle.py`), so there are no class
  sizes to compare — not a code change.
* Open report at the time: "1965 20th DR". Next case per the owner: a
  **3-family (2-4 unit)** — not yet covered by the case kit (PLAYBOOK §9);
  the open multi-family losses are T-997 / T-998 (per-unit kitchen/flooring
  update status and per-unit non-standard below-grade area on comparable
  units; rental grids E-032/E-036).

## 2026-10-01 (evening) — 1965 20th Dr 3-family: in progress (T-1011)

Case notes: `_work/bathbeach/OWNER_NOTES.md` (owner facts, sketch + inspection
sheet transcription, order, public record, DOB research, comps, photo
manifest); case file `_work/bathbeach/case.json`; run logs `run*.log`.

**Done**
* Report set to **1 building / 3 units** through TOTAL's own Report Setup:
  Multi-Family toggle → copy icon on a unit row → identifiers 1/2/3 → rent
  schedule ticks → Save (CATALOG **E-053**, incl. the 90 % zoom click trap,
  now handled in `bridge/ui.py::where`).
* Order is Opteon AMC for Bank of Hope, appraiser named **Mickaelle Petit**
  (MAI Appraisal LLC) → `profiles/petit.json` + `profiles/documents/petit/`.
  The insurance image is a GENERAL LIABILITY certificate, not E&O.
  Designation/phone/e-mail unknown (handback).
* **Legal 3-family confirmed**: DOB NOW final C of O 03/19/2025, 3 units
  (job B00805490). ATTOM/PLUTO building data are stale (2-family, 1945).
* Kit extended for 2-4 units (`bridge/casekit.py`): `units()`, per-unit
  interiors `UI<n>_`, Units in Structure = unit count (was hard-coded "1"),
  `rent_schedule()`, amenity list, income gates honour a developed income
  approach, per-comparable data source + attachment; `exhibits.py`: unit 2-4
  tables + labelled exhibits with no picture (`missing_photos`).

**Open / traps**
* Rental comparables: none in the folder; researched Zillow 11214 asking
  rents (OWNER_NOTES). GRM grid (min 3 sales with known rents) has no data →
  income approach marked "Insufficient Data" for now; Bank of Hope requires
  it → handback.
* Bank of Hope wants 5 sales incl. 2 listings; folder has 3 sales + 1
  listing. Candidate: 2062 Bath Ave (ACT $1,999,000, 0.2 mi).
* Lease start / month-to-month unknown (owner gave rents only).
* `tests/test_diagnose.py::test_an_unstated_switch_is_reported` fails on
  3886 (unrelated to the kit; spun off as a separate task).

## 2026-10-01 (night) — 1965 20th Dr: took over the paused session; rental grid 286 -> 4

Picked up where the previous agent paused (case.json edited 20:37, after run2).
The live report had already reached **0 field validation outside Rental
Information**; the rent grid held **286**.

**Cause** (CATALOG **E-060**): the kit wrote each unit's lease but had no step
for the rental comparables -- and `case.json` had no place for them; the rent
research existed only as prose (three addresses and a range).

**Fixed as a mechanism**: `casekit.rental_comps` (records RP<k>, then a
comparison grid RC<u>.<k> per unit), plus subject-unit rows in
`rent_schedule` (grade level, floor, view, car storage). Tests:
`total-bridge/tests/test_rental_comps.py`. Ran only these steps on the live
report (`_work/bathbeach/run_rental_comps.py`) -- the full `bridge case` run
would re-drop 54 photographs.

**Research corrected** (`_work/bathbeach/add_rental_comps.py`, case.json
backed up as `case.before-rental-comps.json`):
* 248 Bay 23rd St #1A **dropped** -- no listing found; record shows a 3-bed /
  1-bath house.
* 8728 Bay 16th St #1B is **3 baths**, not 2 (StreetEasy).
* 65 Bay 23rd St #3 **added** (renovated 2-bed, 1910 three-family) -- unit 2
  is a 2-bedroom.
* Areas: 42 Bay 25th #1 1,300 sf (listing); 65 Bay 23rd 980 sf and 8728 Bay
  16th 1,281 sf are PLUTO building averages (handback).
* Adjusted rents on one stated basis ($250/bed, $150/full bath, $250
  renovation, $100 private outdoor space, rounded $50). Every unit's contract
  rent sits inside its adjusted range. **Basis is the appraiser's to confirm.**

**Left (4)**
* `RENT_SCH_MONTH_TO_MONTH` x3 -- whether each lease is month-to-month: owner fact.
* `RP1_PHOTO` (42 Bay 25th St #1): the listing has been removed; Zillow,
  HotPads, Redfin and StreetEasy all answer with human-verification checks,
  which are not bypassed. Owner/appraiser can supply it from MLS access.
* Photos placed: RP2 (65 Bay 23rd, listing lead photo -- interior; no exterior
  published), RP3 (8728 Bay 16th, building front). Files in
  `_work/bathbeach/rental_photos/`.

## 2026-10-02 — 1965 20th Dr: multi-family adjustments; report had reverted overnight

**State: field validation 0 · schema 0 · UAD 1 (UAD-1428, comp 2 DOM).**
Not ready to sign until the owner settles comp 2 (below) and SAVES in WinTOTAL.

* **Lost writes (CATALOG E-064).** This morning TOTAL held last evening's
  older values. The bridge cannot save -- `SaveReport` only serializes for the
  host. Re-applied with `_work/bathbeach/run_reapply.py`. **The owner must save
  in WinTOTAL after each session.**
* **Adjustments (E-063)**: owner's multi-family rates now the kit default for
  2-4 units. Adjusted: C1 $1,812,100 (net +12,100), C2 $1,699,600 (-125,400),
  C3 $1,934,580 (-65,420), C4 $2,047,240 (-240,760); weights .30/.35/.25/.10
  -> $1,826,859 -> **$1,825,000** (unchanged). TOTAL's re-sum matches.
  Assumptions for the owner: the rate list names the finished basement twice
  ($20k and $40k) -- read as $40k full finished, $20k partial (no partials
  here); thresholds gate the whole difference (35-yr gap -> 35 x $250).
* **Reconciliation**: short weighting summary + value + "Adjustments:" line
  (case `reconciliation.summary`).
* **Wall material (E-062)**: Brick, rear ground floor stucco, from the photos.
* **Photos**: unit 1 bedroom (3) placed (owner's photo, viewed). Unit 1 bath
  (2) caption corrected (owner pasted that picture in TOTAL; not on disk).
  **Unit 3 roof-level bedroom photo the owner sent was NOT placed**: it shows
  a staged home gym with signs of being AI-generated / a stock render; held
  until the owner confirms it was taken at the property.
* **UAD-1428 (comp 2, 1557 76th St)**: sale known only from deed/ATTOM; no
  listing found (StreetEasy 403). DOM is Fatal-required; not invented. Owner
  options: supply DOM from MLS access, or replace comp 2.
* Rooms: live unit rooms match the sketch and owner table exactly; the owner
  said "some unit rooms are incorrect" -- awaiting which.

### 2026-10-02 (later) — value consistency; certify 0 / 0 / 0
* $1,825,000 everywhere: OpinionOfValue, ValueIndicatedBySalesComparison,
  GSU_SCMINDVALUE2, REC_OPINION_MKT_VAL, both comments. REC_MARKET_VALUE now a
  written final comment (E-065) instead of the bare amount.
* Exported adjusted prices = kit nets (1,812,100 / 1,699,600 / 1,934,580 /
  2,047,240) after zeroing ATT_DET_ADJ, which held ±$20,000 written by
  someone else (not the kit) -- double-counted the design adjustment.
* **GC2_EX_DOM = 104 was written by someone other than this session** (no
  source on file; comp 2 has no listing in ATTOM/StreetEasy). It is what
  cleared UAD-1428. Owner to confirm its source before signing.
* Income approach still "not developed (insufficient data)" although 3 rental
  comps exist and the lender asks for GRM on 2-4 units -- owner/appraiser call.
* OWNER MUST SAVE IN WINTOTAL (E-064).

## 2026-10-02 (close) — 1965 20th Dr DELIVERED; how the next case goes faster

Owner: "no mistakes, no UAD blockers, ZIP generated". Report signed (by the
owner). Handback: `_work/bathbeach/HANDBACK.md`.

**What changed for every future case (read PLAYBOOK top + §0, §2, §4, §6):**
* `bridge audit --json case.json` after certify — the delivered XML vs the case
  (E-065). Certify READY is not enough.
* Rate profile by report type (`casekit.profile`): 18 North for 1 unit,
  multi-family for 2-4 (owner rates). Short reconciliation from
  `reconciliation.summary`; `REC_MARKET_VALUE` is prose (`final_comment`).
* The owner must SAVE in WinTOTAL (E-064); someone else may be editing the
  same report — a value you did not write is put to the owner.
* 2-4 unit case-file section in PLAYBOOK §4; re-run pattern `run_reapply.py`.
* Open tasks: T-1015 (full `bridge case` run on the next 2-4), T-1016 (condo
  kit), T-1017 (pre-existing diagnose test failure).

## 2026-10-02 (evening) — condo 146 W 57th St Unit 44C (T-1018) — PAUSED: WinTOTAL closed

* Case folder (owner): `C:\Users\MOHIT\Documents\OFFICE\146 w 57th st\146 WEST 57TH ST APT 44C -`.
  Case file `_work/w57/case.json` built by `_work/w57/build_case.py` (sources in
  its docstring). Owner decisions: GLA **802** from the sketch only; comps 1-4 as
  given; **18 North** rates; inspected 10/01/2026; corner unit; building fan-coil.
* TOTAL updated to 0.0.1.3894: re-extracted, diff = no form changes.
* Kit extended for condos (E-066, tests/test_condo.py). Live run: steps 1-11
  written, step 12 (sales contract) hung TOTAL; WinTOTAL then closed (E-067).
  Fix in the kit; nothing was saved -- re-run the whole case after the owner
  reopens the report.
* OPEN: contract date (blank in the contract -- owner to supply); heat fuel of
  the building plant unverified; units rented unknown (no questionnaire);
  measurement basis differs (802 measured vs comps' offering-plan sizes).
* (later) Report reopened via `WinTOTAL.exe "<.zap>"` (no desktop control).
  Contract toggle CLICKED fine; step 13 (contract fields via commit) froze the
  page a THIRD time. Cause read from TOTAL code (E-067): change on SC_CONTRACT_NO
  -> resetContractData + toggles, transfers listen to the same keys. Kit now:
  contract filled one rendered control at a time, "_YES" boxes only, liveness
  check after each field and before every step. Page 88050798 still frozen at
  hand-off; owner to close it / restart WinTOTAL (Woodycrest is open alongside).
* (night) 146 W 57th St: FV 501 -> **1** (SC_CONTRACT_DATE, owner), schema 0,
  `bridge audit` clean. Contract filled one control at a time (no freeze).
  E-069 lists the condo mechanisms. Value by the kit: weighted 1,488,279 ->
  1,490,000 vs contract 1,380,000 -- the lender requires the variance to be
  explained in the reconciliation (appraiser's call; handback).

## 2026-10-02 (late) — Woodycrest [AMC ORDER NO]: AMC revision request (28 QA items)
Scripts + evidence in `_work/woodycrest/qa/` (fix1-3, fix5_revision, make_graphs, before/after exports).
Fixed live: AMC block (NY AMC-19-0008), licence expiry 03/12/2028, utility comments, site-value ratio
comments, predominant value, StreetEasy figures removed, 3 market graphs (absorption, DOM, price trend),
separate sales / rental / GRM maps, comp 4 bedroom sign (-$20,000), comp 4 disaster mitigation, SCA value
= opinion $1,030,000, adjustment commentary, income-approach narrative, listing dates, driveway photo,
10 dated Revision History rows. Not fixable by the bridge: sketch (porch, utility room), % distressed and
year-built graphs (no data), signature date (owner re-signs). FV 330 found -- the cells were ALREADY empty
before the QA work (snapshot qa/before_values.json); not caused by these fixes; owner to decide.
New learnings: MKT_GRAPH stores "a<br>b<br>c" and only builds its exhibit rows on SelectClosed.

## 2026-10-02 (night) — 601 Euclid Ave, Brooklyn 11208: 4-family (T-new) — IN PROGRESS
Notes `_work/euclid/OWNER_NOTES.md`; case built by `_work/euclid/build_case.py` (values not in the folder
are tagged ASSUMED there); logs `run*.log`. Signs: Leonardo Jo (licence + Aspen E&O from the folder ->
`profiles/documents/licence.png`, `eo_insurance.png` -- the profile's missing exhibits now exist).
* NEW kit step `bridge/units_setup.set_units(report, n)` (E-053 encoded). Traps met building it (E-070):
  `offsetParent` is null inside the fixed setup panel (made 8 units; Cancel froze the page until the owner
  dismissed WinTOTAL's dialog); class names were truncated in my dump (use placeholders); click points =
  rect x cumulative zoom ALWAYS (elementFromPoint shares the rect's space; measured at 90 % and 110 %).
* `casekit.design_of`: a rowhouse is ranked by its attachment (semi-detached comps were getting $0).
* Comparable unit areas restated on the subject's NET basis (sketch units 2,648 of a 3,360 sf building):
  gross/4 x 0.788 -- otherwise $80-170k phantom GLA deductions per comp.
* Comp 2 GEO "photo" was a map strip: never take an image wider than ~2.5:1 as a front photo.
* OPEN for the owner: lender / borrower / order no. / purpose (no engagement letter); actual rents, leases
  and which unit the owner occupies; comp 4 = 6-unit mixed use with a medical office (kept, support weight).
* (later) Owner supplied the order (PDF p.1 is an IMAGE -- render it: pymupdf get_pixmap), inspection
  10/01/2026, all units owner occupied, rental photos from Google Maps. New `tools/streetview.py` (headless
  Edge over CDP, consent "Reject all", re-attach after cross-site navigation; view every capture -- the
  first ones faced down the street). Rental-property columns now added by the kit (`add_comparables(grid=
  "rentalprop")`); RP photos via manifest `slot: RP<k>_PHOTO`; Rowhouse design asks 3 townhouse fields.
* **RESULT: certify READY (FV 0 / schema 0 / UAD 0), audit clean, $1,375,000. Owner must SAVE.**
* (final) Reviewer pass on the narrative -- fixed: unit 4 "vacant" left in the QC comment after the owner
  said all units owner occupied; rental comment still said "tenants pay"; wall-comment date; marketing time
  vs 55-day median DOM; income approach exclusion now explained in the reconciliation. New kit step
  `casekit.comments` (case `"comments": {..._COMMENTARY: text}` only): assignment (order "Investment" vs
  owner-occupied), dwelling (smoke/CO, mechanicals, bars), sketch (2,649 net vs 3,360 gross public record),
  unit 4. Re-certified READY 0/0/0, audit clean. LESSON: after any owner correction, grep every narrative
  for the old fact (vacant/tenant/date) -- validators never see prose.

## 2026-10-04 — live Vercel: blank report not loading; shared case store (branch claude/keen-turing-3r26sh)

**Cause.** Vercel runs several server copies, each with its own /tmp disk. A case created on one
copy is unknown to the next, so "New blank" opened a report the next request could not find.

**Fix (committed 31a0cb1, 2nd commit logs failures; NOT pushed, NOT deployed).**
`engine/app/durable.py` keeps each case's bundle in one shared store: Vercel Blob (private)
when `BLOB_READ_WRITE_TOKEN` is set, or a shared folder with `URAR_DURABLE_DIR` (Docker volume,
tests). `main.py` middleware pulls the case before any `/api/cases/<id>` request, `pull_all` on the
case list, pushes after every successful change, forgets on delete; a store failure answers 503
with the reason (and logs it), never a silent guess. Verified: `engine/tests/test_durable.py`
(9/9), and two real server processes behind a round-robin proxy — "New blank" renders 26 pages,
an edit on one copy is read on the other.

**Vercel state.** Blob store `uad36-cases` (store_2X950Muudm6XvK2n, private, iad1) created and
connected; `BLOB_READ_WRITE_TOKEN` injected. Live production is still the older deployment
dpl_EZpEn7HaqFKoWqe6pWmSeaSDKWit (no shared store). **Env chunks are inconsistent:** `UAD_P1` holds
chunk 1 of the NEW patch, `UAD_P2..P7` the OLD one — a new build from main would fail at `git apply`
(production stays on the old deployment; nothing breaks live). The proper route is pushing the
branch and merging to main, after which the build skips the patch (access.json present) and the
`UAD_P*` vars can be deleted.

**Tests.** The fixtures signed in with the retired passcode `kech`; they now use
`app.access.sign_in(client)` (server's own token). 150 pass; 3 failures (test_cells sf1,
test_autofill condo1/mh1) fail identically on `main` — pre-existing, not from this work.

### 2026-10-04 (later) — pushed; continuous deployment from GitHub works; layout 500 fixed

GitHub write access now works: the branch is pushed and `main` fast-forwarded, and Vercel
builds production from `main` on every push (no Vercel tool calls needed). The `UAD_P*` patch
env vars are now dead weight (the build skips them because `engine/app/access.json` exists on
main) — delete them when convenient.

Live "The report could not be laid out: Internal Server Error" had two causes, both fixed (345ffb5):
1. `kerned_fonts._out_dir` probed writability with ONE shared file name; two font requests at once
   deleted each other's probe and the loser raised "no writable directory". Now a per-thread probe,
   decided once per process; fonts are written to `*.part` and `os.replace`d in.
2. fontTools stamped `head.modified = now` on every kerned font, so each server copy produced
   different bytes → different digest → a page laid out on copy A asked `/api/fontasset/<digest>`
   that copy B could never make. `TTFont(..., recalcTimestamp=False)` makes the build
   deterministic. Reproduced and verified with a cold second "copy": 48/48 fonts served (was 14/60).
LESSON: anything named by a content digest must be built deterministically on every copy.
