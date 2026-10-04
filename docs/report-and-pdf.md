# The report and the PDF

## The form (C-1)

`engine/spec/c1_form.json` is the form as Appendix C-1 draws it: every tab,
bar, subheading, row, checkbox, table and photo slot, in page order, with the
Report Field IDs that fill each one. `report/form.py` walks it against a case
and emits only what the case needs.

Section choice comes from the property's own data (`report/profiles.py`). UAD 3.6 has no form numbers.

## Style (Appendix E)

- `report/style_spec.py`: type, sizes and rules, each value with its page citation.
- `report/page.py`: Legal page geometry, measured off the D-1 PDFs
  (`page_geometry.json`, `page_rules.json`).
- 41 in-section tables come from Appendix E Part 2 (`extract_tables.py`), with their heads and widths.

## Layout and pagination (`report/flow.py`)

The blocks are laid out once as a galley at the 45-pica measure. Each block's
real height is read back from a browser. Page breaks follow Appendix E:

- tabs, bars and subheadings never end a page;
- a continued section reopens with its tab and "(continued)";
- Assignment Information, Sales Comparison and Scope of Work start a page;
- tables break only where they must, and repeat their heads.

**Where the browser runs:**

- **Server with Chromium** (local, Docker): Playwright lays out and prints.
  `renders.py` keeps results under a content key: document, media names,
  state and renderer code.
- **Vercel** (no browser): the server sends the galley
  (`GET /layout/{kind}/galley`, `X-Render-Key` header). The user's browser
  measures it and posts the pages back (`POST /layout/{kind}/pages`). Pages are
  cached in IndexedDB (`uad36-layout`) for instant reloads. `report.pdf`
  answers 503 there by design.

## Fonts

- Appendix E names **Myriad Pro**, with **Calibri** as the substitute. Myriad Pro is licensed and is not in the repository. `fonts.py` uses a local Adobe install when there is one.
- Without it, `substitute_fonts.py` builds metric-matched faces, so the report still renders. The harness reports this as an expected "gap".
- `kerned_fonts.py` writes the D-1 samples' optical kerning into a kern feature, one copy per point size. Its character set is cp1252 (WinAnsi), so no glyph falls back to a system font.
- Fonts are built deterministically (`recalcTimestamp=False`) and written atomically.

## PDF

- Endpoint: `GET /api/cases/{id}/report.pdf`. It needs Chromium: run locally or with the Docker image.
- Fonts are embedded as TrueType, not Type3 (`build_webfonts.py`).
- Verified 2026-10-04 in Docker: the sf1 sample printed 6 pages in 8.0 s, cold.
- Open: page counts differ from the official samples on 9 of 12 (`AI_HANDOVER.md` §5).
