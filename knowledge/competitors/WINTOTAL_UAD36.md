# WinTOTAL (a la mode) UAD 3.6 — feature inventory and how we compare

Source: 36 screenshots the owner took of their own WinTOTAL during a real
4-unit assignment, plus one of a condominium grid (2026-10-08). They are in
`Competitors 3.6 software features pics/`. They hold real case data (borrower,
addresses, licence, E&O certificate). Keep them out of anything that ships.
This page is for **features and workflow only**. The official specifications
stay the authority for the form; copy nothing of their code, wording or
artwork.

Status legend:
- **have** — we already do it.
- **better** — we do it and go further.
- **built** — built in response to this inventory (with its test).
- **todo** — worth building; it is in TASKS.md.
- **skip** — deliberately not built (reason given).

| # | WinTOTAL feature (where seen) | Ours | Notes |
|---|---|---|---|
| 1 | **UAD Guidance panel**: on focus it shows the field's name, a requirement badge ("Always required" / "Required when Listing Status is Pending or Settled Sale…"), the definition, and reporting notes. Many fields say "No specific field guidance available". | **built** (2026-10-09) | Ours reads A-1 (conditionality, definition, format) and H-1 (every rule on the field) for every field, and shows each rule passing or failing **live** for the open report. `GET /api/cases/{id}/guide/{fid}`. |
| 2 | **Show All Field Validation** toggle: required-but-empty fields outlined in red on the page. | **built** | Driven by the H-1 findings for the open report: fatal in red, warning in amber, on the exact field. "Mark what is unanswered" (amber fills) stays as it was. |
| 3 | **QuickList Entries**: saved comment snippets, double-click or Alt+# to insert. | **built** | Comment library in the toolbar: save the selection or a typed snippet; Alt+1…9 or a click inserts at the caret of the focused comment. Kept per browser / desktop profile. |
| 4 | Character counters on every comment (e.g. 399 / 5000). | **built** | The limit comes from the field's own format (A-1 / XSD). The counter turns amber near it and red over it. |
| 5 | **Units and Structures Setup**: counters, plus a building → unit tree with type (Living Unit / ADU), "Include Unit in Rent Schedule", a manufactured-home flag per building, reorder and duplicate. | have, partly | Our setup asks the type and the unit count; the Structure view adds and removes units and ADUs; the rental-pairing matrix covers unit ↔ comparable. **todo** (T-1058): per-unit "Include in Rent Schedule" switch and drag-reorder. |
| 6 | **Report Settings** panel per section with "+ Add …" buttons: parcel, influence, view, feature, utility, street type, map, exhibit, lien, document, graph, listing, level, room, flooring, heating system, vehicle storage, amenity, area, site improvement, other rental income, comp property, contacts (borrower, seller, owner, lender, AMC, attorney, investor, supervisory, assistant), certifications, alternate address. | have (inline) | Ours adds rows where they print (the add-row line of each table, "+ Add Exhibit", "+ Add comparable"). **todo** (T-1056): a section "Add" list in the side panel that jumps to and opens those same controls. |
| 7 | **Show / Hide optional sections** (Disaster Mitigation, Energy Efficient, Vehicle Storage, Amenities, Sales Contract, Revision History, Client Requested Conditions, Not Used, defects). Hidden data is kept but left out of the PDF and XML. | partly | B-1's own indicators drive Rent Schedule / Income / Cost (Report setup), and sections appear by B-1 display rules. **todo** (T-1057): an explicit hide that stashes the section's data out of the MISMO document and restores it on Show (the XML must stay schema-valid both ways). |
| 8 | **Sales Comparison side-by-side grid** in the app: move a comp left/right, copy, delete, aerial view; Hide Photos; Shift+wheel horizontal scroll; "Add Comp N" card; per-group gear; net adjustment coloured; adjusted price per unit, price per GBA, comparable weight, indicated value. | **built** (T-1055) | Our grid edits in place on the page (typed cells, adjustments, add / remove comparable). The comparable menu (click its header) moves it left / right (the photos, transfer history and map follow its number) and copies it with fresh identifiers and its data-source links, schema-valid on all 12 samples (`tests/test_comparable_copy.py`). Negative adjustments and net totals read red, positive green, in the editor only. |
| 9 | **SmartAdjust**: adjustments suggested from rates. | **built** (T-1059) | Toolbar "SmartAdjust": the owner's 18 North profile (multi-family on 2-4 units), every rate editable per report. Each suggestion shows its arithmetic ("-258 sq ft × $75") beside the grid's current figure. Blanks are pre-ticked; the appraiser's own figures are not. Net / gross % per comparable, flagged past 15 % / 25 %. Nothing is written until Apply. `uad/smartadjust.py`, `tests/test_smartadjust.py` (the 18 North derivation cases; all 12 samples take every suggestion schema-valid). |
| 10 | Rental grid per subject unit, "all seven comparable columns shown by default, empty ones hidden on print". | **better** | Ours: one grid per unit from the A-1 pairing arcs, and an explicit pairing matrix. |
| 11 | Rent schedule totals. | **better** | In WinTOTAL's own screenshot the Subtotal reads **$0** under $1,600 + $1,800 + $1,600 + $1,700. Ours computes 23.01.14–25 on every save (E-148). |
| 12 | Project Information on a 4-unit (non-project) report, all fields open. | **better** | Ours prints sections by B-1 display rules; project information appears for condominium / co-op / PUD. |
| 13 | Zoom control (80–95 %). | have | The report frame scales; browser / desktop zoom works. |
| 14 | Drag-and-drop exhibit boxes ("Drag and drop image or click browse"). | have | Our exhibit boxes take a picture straight from the file dialog or a drop. |
| 15 | Legal description as Text or Photo. | todo (T-1060) | |
| 16 | Sketch page with area table; "+ Add Page (Alt+A)". | have, partly | Ours takes the sketch as an exhibit; no sketcher (WinTOTAL launches its own). |
| 17 | Grid cell pop-up for compound values (Contract Date Known + Date). | have | Our cell editor for multi-part cells. |
| 18 | Additional appraiser certifications: Add (Alt+A) / Remove (Alt+R). | **built** (T-1061) | Numbered as printed, the next number always open to type, x removes; type and indicators kept by `uad/certifications.py`. Before this they could not be saved at all (E-159). |
| 19 | Help banner, chat support, Order / Workfile / E&O / Timeline tabs. | skip | Business-office features outside the report; the owner runs those elsewhere. |
| 20 | PDF / XML delivery. | **better** | Ours validates the ZIP against the GSE subschema and B-1 package rules before export; the desktop edition prints the PDF locally. |
