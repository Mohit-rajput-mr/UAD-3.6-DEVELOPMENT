# AI AGENTS UPDATES — read this first

Any AI agent taking over this project reads this file **before doing anything
else**, then `CLAUDE.md`, `TASKS.md`, `_work/HANDOFF.md` and `_work/WORK_QUEUE.md`.
Keep this file current: at the end of every batch, update "Status" and
"Next task", in the same style.

## Rules from the owner (every session)

1. **On start: restart the server and give the owner the link.**
   - http://localhost:8766 (passcode: the owner's, verifier in engine/app/access.json) — Claude desktop launch config `uad-app`
   - http://localhost:8767 (no passcode, for testing) — `uad-dev-open`
   - Without the desktop app: `python engine/app/main.py` (port from `URAR_PORT`).
   - Restart again after every Python change (modules load once), and say so.
2. The official documentation is the authority: A-1, B-1, C-1, D-1, E, H-1 and the
   GSE XSD, in the `3.6 DEVELOPMENT, BLUEPRINT, DOCUMENTATION` folder. Never guess.
3. Fix classes of problems, not single fields. Verify in the real UI, not only tests.
4. Do not stop after a few fixes; work the queue until it is empty.
5. Never claim "UCDP approved" or "compliant" without a test that shows it.
6. The owner wants to watch progress visually on localhost:8766 (the autofill run
   fills the report on screen).

## What the owner has asked for (in order)

- A production UAD 3.6 appraisal report editor to compete with ACI / WinTotal,
  "powered by Kech"; the editor is the printed report itself, editable in place.
- Summary is never editable (it redisplays other sections).
- Photos insertable everywhere; "+ Add Exhibit" boxes in every exhibits area;
  comps 4, 5… like WinTotal; UAD pagination with no overflow; fast, never glitching.
- Sales Comparison Map: real map in its official box only (no extra pages),
  "Load Location Map" in the box, and edit in place (drag, zoom, labels).
  Site Exhibits: "Aerial Map" button at exhibit photo size.
- Dropdowns compact, official values only; address autocomplete in the comp grid.
- Auto units ("200" → "200 Sq. Ft.").
- Per-page **Save / Save & Next** beside each page; lists UAD errors (red), warnings
  (orange), blanks; "Save anyway"; sidebar sections turn green / orange / red.
- Full audit of every field against the documentation; fix every field A–Z so the
  MISMO XML is right; field-by-field.
- An **autofill** that fills a blank report visibly on screen (opens lists, ticks
  boxes, types, adds rows/comps/photos) while the server writes it.
- "Fix ALL remaining issues, do not stop after a few; audit, fix, test, re-audit
  until zero known defects" (see `_work/WORK_QUEUE.md`).

## Done so far (both agents)

Agent A (map / editor / field-by-field session):
- Sales Comparison Map: single map linked to the document's own box (`api._fills`),
  Load/Refresh control, **Edit Map** in place (`ui/map/index.html?embed=1`, view saved
  as `mapState.userView`), headless render uses the saved view.
- Site Aerial Map (`POST /maps/aerial`, `mapper.aerial`), exhibit photo size.
- Geocoder never invents a location (ZIP / street must confirm); comp pins survive reload.
- Grid editor: compact in-page list instead of `<select>`; address autocomplete
  (`/api/geocode/suggest`) filling city/state/ZIP as marked suggestions.
- Per-page Save / Save & Next + sidebar green/orange/red (`savedSections` prefs).
- Store guard: no write may add a schema error (`Store.save_tree`, 422);
  unreadable numbers/dates refused (`entry.normalize`).
- B-1 26.010 days ("45 days", "30-60 days").
- Field-by-field tool: `python engine/uad/dossier.py <section> --json`
  (A-1 / B-1 / H-1 per field + live save/read/print/schema test through the API).
- **Section 2 (Assignment Information) done: 60/61 fields pass** (2.010 is the fixed
  "Client" role). Engine fixes that apply everywhere:
  - `edit.instance_for`: A-1 conditions (`IF PartyRoleType = …`) pick or create the
    right PARTY / ROLE / PROVIDED_SERVICE in schema order; gates (indicator = true)
    are set; XSD required children (`xsd_order.required`) and choice groups
    (`xsd_order.rivals`: a ROLE is APPRAISER *or* SERVICE_PROVIDER) respected.
  - Inspection links via `INSPECTION_CompletedBy_ROLE` relationships (supervisor).
  - Property Data Report lives in its own SERVICE (ServiceType Inspection).
  - `uad/parties.py`: Borrower / Seller / Owner / appraiser names — person
    (First/Middle/Last/Suffix) or company (FullName), several borrowers, B-1 owner
    Case A/B/C; editor Person/Company switch. Summary writes refused (422).
  - "Other" in any list asks for its description (…OtherDescription).
  - Client/[Role] heading is a picker (`PATCH /cases/{id}/client-role`).

Agent B (autofill / defect sweep session):
- `engine/app/autofill.py`: fills a blank case from a D-1 scenario (1,018 values on
  SF1, 1,573 on 2–4 unit) visibly in the browser; 0 fatal / 0 warning / 0 schema.
- Properties Analyzed Not Used grid, Add/Remove for rental and GRM grids,
  named additional grid rows (`PUT /cases/{id}/comparables/lineitems`),
  addresses printed as D-1, certification answers, deterministic rendering.
- Details and evidence: `_work/WORK_QUEUE.md` ("Done in this job").

## Status (2026-09-18)

- Tests: 268 pass, 3 fail (golden sf3, golden sf4, bracketed-placeholder workflow
  test) — expected after Agent B's named-row change; queue item 1.
- Harness (`python engine/tests/harness.py 12`): last 99 pass / 0 fail / 9 gap.
- Coverage (`python engine/uad/coverage.py`): 1,223 IMPLEMENTED, 83 MISSING, 9 INCORRECT.

## UAD 3.6 XML Import + Portable XML (2026-09-18) — DONE, verified

Owner asked (before any rollback): full UAD 3.6 XML import, pictures included,
dynamic comps/exhibits, editable after import; then a two-part system — a
**Filing Engine** (messy project folder -> one self-contained UAD 3.6 XML) and the
**Import Engine** (that XML -> the whole editable report). **No rollback has been
done; do not roll back before the owner confirms.**

Built (Import Engine + portable file):
- `engine/uad/importer.py`: open bundle (.xml / B-1 .zip / zip of zips / XML +
  loose pictures / a folder) -> parse (no network, XXE-safe) -> normalise
  (namespace, Y/N, dates, amounts, schema-driven enumeration repair, unknown
  elements dropped *and reported*, XSD order) -> pictures (bundle by name, http(s)
  URL, data: URI, embedded base64, `IMAGE/EXTENSION/OTHER/kech:EmbeddedFile`) ->
  report. Over-long text is kept whole and flagged, never cut.
- `POST /api/import` (app/api.py): transactional — everything in memory first,
  new case only after success, deleted on failure. Pictures become media rows that
  *fill* their document IMAGE (comparable photos -> grid, front -> subject,
  SalesComparableMap -> map box, autoMaps off so an imported map is kept).
- `GET /api/cases/{id}/portable.xml`: one UAD 3.6 XML with every placed picture
  base64 inside its IMAGE (schema-valid: GSE XSD opens IMAGE/EXTENSION/OTHER to
  `##other`, lax) + editor state (`MESSAGE/EXTENSION/OTHER/kech:EditorState`).
  Namespace `urn:kech:uad36:portable:1`. UCDP delivery stays the B-1 zip.
- UI: "Import a UAD 3.6 appraisal" panel on the Cases screen (drop / files /
  folder, progress, result list, open report); "Download portable XML" in sign-off.
- Evidence: all 12 D-1 scenarios import in 0.2–1.1 s, every picture placed,
  0 invalid / 0 schema / 0 fatal; imported report text identical to the scenario
  rendered from its own XML; `tests/test_import.py` 21 pass (8 comps -> 3 grid
  blocks, 29 extra exhibits, URL/data:/embedded/missing pictures, loose values,
  unknown element, 21k-char narrative, editability, package, failed import leaves
  nothing, portable round trip identical). Full suite 289 pass, 3 known fails.
- Tools: `tests/trace_import.py`, `tests/trace_import_fidelity.py`.

### Owner correction (2026-09-18): NO Filing Engine in the software

The software only imports. **Claude (in the chat/Claude Code session) reads the
owner's property folder and writes the XML**, following
`engine/docs/CLAUDE_XML_PACKAGE.md`, then runs
`python engine/tools/pack_xml.py appraisal.xml --images "<folder>" --out x_portable.xml`
(embeds every picture, validates exactly as the importer will, lists problems).
The owner imports that one file.

Fixed in that round (all verified):
- "Preparing the case…" strip showed on every report (CSS `display:flex` beat
  the `hidden` attribute) → global `[hidden]{display:none !important}` in index.html.
- Editor ≡ Preview: new test `test_the_editor_shows_everything_the_preview_prints`
  (all 12 D-1) — every printed value is in the editor. Fixed on the way:
  company address city/state/ZIP editable (form `_party_item`); list fields with
  several values (project amenities, etc.) read **every** instance (was only the
  first — D-1 condo2 prints 6 amenities, we printed 2), one picker per value
  (`data-tk` = its block), "+ another" creates a block, clearing removes the block;
  pickers use the data point the row prints (`form.printed_point`).
- Exhibits from the XML: editable name (`PATCH /images`), replace (drop), remove
  (`DELETE /images`).
- 34 import tests pass; full suite 301 pass + 4 known (golden sf3/sf4, bracketed
  placeholder, all from the named-row queue item); harness 99/0/9 (unchanged).
- Known slow spot: first layout of a new case 10–26 s (C-1 measurement); the
  editor shows a loading page meanwhile. Next improvement candidate.

NEXT (superseded — the owner does not want a Filing Engine in the software): the **Filing Engine** — folder -> canonical appraisal model
(with provenance + conflicts) -> this same UAD 3.6 document -> portable XML.
Design notes in "Filing Engine plan" below.

## Filing Engine plan (to build next)

folder walk (recursive, hash-dedupe, cache per file hash) -> per-file extractors
(PDF text via pymupdf; spreadsheets; images: EXIF date/GPS, size, perceptual hash;
MLS/CMA/public-record parsers) -> facts `{field, value, source file/page, confidence}`
-> entity resolution (subject vs each comparable by address/APN/coordinates) ->
conflict detection (same field, different values -> flagged, never auto-picked) ->
canonical model -> A-1 mapping with `uad/edit.py` / `uad/parties.py` writers into a
blank template document -> picture classification (subject / comp by GPS+address,
sketch, map, aerial, graph) -> `importer.embed` -> validate -> one portable XML.
Vision / free-text understanding needs an LLM (Claude API key, not configured yet).

## Paused (2026-09-18) — owner asked to pause for new main updates

In progress when paused (queue item 1):
- Found: SF3/SF4 grids print two blank "Wet Bar" rows (a unit-interior feature
  expanded from the "[Other Interior Feature]" template; D-1 SF3 p19-20 prints none),
  plus an outbuilding "Utilities" row that D-1 **does** print (correct).
- Edited `engine/uad/report/comparables.py` (grid row skip rule in `build`): a named
  row prints only when the subject or a comparable has a value or an adjustment.
  **Not yet verified**: golden still reports sf3 84→86, sf4 86→88. Next step: list
  which rows remain added, confirm Wet Bar rows are gone, then regenerate golden
  (`UAD_GOLDEN_UPDATE=1`) only if the rest match D-1.
- The bracketed-placeholder workflow test still fails (contract changed by Agent B).

Wait for the owner's new instructions before resuming the queue below.

## Next task (continue from here)

Work `_work/WORK_QUEUE.md` "Queue" in order, starting with item 1, and continue the
field-by-field pass with `uad/dossier.py` from **section 3** onward (section 2 done).
After each batch: tests, harness, restart servers, check in the UI, update this file.

## 2026-09-18 — 18 North St, Bedford Hills (VSA311756)
- XML: C:\18 NORTH ST BEDFORD\18_North_St_Bedford_Hills_UAD36.xml (5.5 MB, 32 pictures embedded, 4 sales comps, GSE-schema valid). Built by _work/bedford/build.py through the API.
- Platform fix: templates.load(blank=True) leaked sample facts (footer "Version #4", AA12345, Sunnyside legal, areas, lat/long). Blank now keeps only kept_elements() + IDENTITY block-type values (templates.structure_elements). Verified: 12 templates, 0 leftover answers; harness 99/0/9; test_import 34 pass.
- Open: T-919 footer IDs (HF.005-008) not editable via /fields; appraiser must set adjustments, opinion of value, year built, GLA 1,580 / bsmt 460 (sketch estimates), 3 BR, personal property, SCA map, the file number and loan number (both in the working tree, not committed -- see .gitignore).

## 2026-09-24 (evening) — 129-35 131st St + the MOD's validation engine

**Where to read the detail:** the last section of `_work/HANDOFF.md`.

### The file
`C:\Users\MOHIT\Documents\OFFICE\129-35 131st St, South Ozone Park\129-35th  131st st, south ozon - driveby\129-35_131st_St_South_Ozone_Park_UAD36_portable.xml`
414 values, 9 photographs embedded, schema 0 errors, H-1 **0 fatal**.
Credentials in (owner supplied): Mickaelle Petit, NY cert 46000042282, expires
30/01/2027; Appraiser Reference ID = the order's File ID 921557992.
No rentals: the income approach is excluded with A-1's reason
`InsufficientData`, the cost approach as `NotNecessaryForCredibleResults`.
Commentaries are each 22-57 words, in their own boxes, as the owner asked.
Adjustments are only the three the 18 North rate card supports: living area
$75/sf, site $10/sf, age $500/yr.

### The MOD
`bridge/validate.py`, `bridge/fixer.py`, `bridge/expert.py` and the commands
`check`, `fix`, `deliver`.  They drive TOTAL's own rule set
(`realTimeValidation.fieldValidators`, 1,041 checks), so they work for any 3.6
form.  A section has to be on screen before its fields can be judged.
`deliver` = import, fill, answer the validations (looping, because answers open
new questions), place the photographs, then report what TOTAL still says.

One click: `total-bridge\UAD Bridge HUD.cmd`, desktop shortcut "UAD 3.6 Bridge
HUD", pinnable.

### Still open
~35 validation errors after a full run (T-945): the project-information
section on a property that is not a project, the comparables' transfer
date/amount/source (grid controls with no fmid), and the appraiser's own
signature date.  The write path is proven -- 269 of 278 values confirmed in
TOTAL's own delivery XML.

Engine: harness 99/0, 312 of 314 tests pass; the two failures are T-941 (a
test comparing parties by position; every value is present).
