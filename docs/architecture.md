# Architecture

## One document, every output derived from it

A case **is** its MISMO 3.6 document. The editor writes into it, and every
output is drawn from it:

```
editor (browser) ──REST──► case document (MISMO XML on disk / shared store)
                              ├─ compliance engine ─► Review Master
                              ├─ report renderer   ─► galley ─► pages ─► PDF
                              ├─ XML               ─► mismo.xml / portable.xml
                              └─ media             ─► Images/
                                                        └─► delivery ZIP
```

The file the appraiser edits is the file that ships, and it can be checked
against the schema at every moment in between (`engine/app/cases.py`).

## Specifications drive the code

Everything a specification defines is extracted at build time into
`engine/spec/*.json` by `engine/uad/spec/` extractors. Nothing is hand-typed.

| Source | Extract | Used by |
|---|---|---|
| A-1 delivery spec | `delivery_spec.json`, `field_index.json`, `enumerations.json` | `bind`, `edit`, `entry`, `delivery` |
| B-1 implementation guide | `display_rules.json`, `comparable_grids.json`, `supplements.json` | `report/rules`, `report/comparables`, `report/dashes` |
| C-1 layout | `c1_form.json` | `report/form` |
| E style guide | `layout.json`, `tables.json`, `typography.json`, `page_geometry.json` | `report/form`, `report/flow`, `report/page` |
| D-1 samples | templates, `d1_kerning.json`, `d1_font_widths.json` | `templates`, fonts, the harness |
| H-1 compliance rules | `compliance_rules.json` | `compliance` |
| GSE XSD | `xsd_order.json`, `xsd_required.json`, `xsd_choices.json` | `edit`, `xsd_order`, `schema` |

## Modules

- `engine/app/`: the web server.
  - `main.py`: FastAPI app and passcode gate.
  - `api.py`: REST API; the UI is one client of it.
  - `cases.py`: case store and sign-off state machine.
  - `durable.py`: shared store for many server copies.
  - `renders.py`: background render cache.
  - `mapper.py`: map drawing.
  - `ui/`: the editor.
- `engine/uad/`: the domain.
  - `bind.py`: label to field to value.
  - `edit.py`: writes a value in XSD order.
  - `entry.py`: typed text to the stored form.
  - `compliance.py`: H-1.
  - `review.py`: Review Master.
  - `importer.py`: import.
  - `delivery.py`: UCDP ZIP.
  - `templates.py`: D-1 starting templates.
- `engine/uad/report/`: the form.
  - `form.py`: the form, from C-1.
  - `flow.py`: measure, paginate, and the in-frame editing script.
  - `comparables.py`: the grids.
  - Fonts: `fonts.py`, `kerned_fonts.py`, `substitute_fonts.py`.

## A request, end to end (editing one field)

1. The report frame (`flow.EDIT_JS`) shows the typed value at once. This is an optimistic update: the user never waits.
2. It sends `PATCH /api/cases/{id}/fields/{field_id}`.
3. `edit.py` resolves the field's A-1 data point, normalises the text (`entry.py`), creates missing containers in XSD order and writes the value.
4. The document is saved. With a shared store, the new bundle is pushed (`durable.py`).
5. The render key changes. On a host with Chromium the server re-lays the report in the background (`renders.py`). Without one, the browser lays it out and posts the pages back (`/layout/{kind}/pages`).
6. The editor caches the laid-out pages in IndexedDB, so a reload shows the last report instantly and revalidates in the background.
