# Comparables, images, maps and market graphs

## Comparable grids (`engine/uad/report/comparables.py`, `grid.py`)

- **Source.** The grid is read from B-1's "Comparable Grids" workbook
  (`engine/spec/comparable_grids.json`, 167 rows). Each row records:
  - its label;
  - whether it always shows;
  - the subject field ID, the comparable field ID and the adjustment field ID;
  - the MISMO data point.
- **Geometry**, measured from the D-1 PDFs:
  - the grid spans the full 45-pica width;
  - the row label is 106 pt wide; the subject column and each comparable column are 108.5 pt;
  - a comparable column splits into a 66 pt description and a 42.5 pt adjustment.
- **Empty cells.** An empty cell prints an em-dash only when B-1's per-row
  dash sentence holds (`report/dashes.py`).
- **Numbering.** Any number of comparables (4, 6, 10) are kept in order by
  `PropertyOrdinalNumber`. API:
  - `POST /comparables` to add one;
  - `DELETE /comparables/{n}` to remove one;
  - `POST /comparables/order` to reorder;
  - `PATCH /comparables/{n}/fields/{fid}` to edit a field;
  - `PUT /comparables/lineitems` for adjustment line items.
- **Negative adjustments** print as `$(10,000)` (B-1 Figure 22-5; all D-1 PDFs).

## Photographs and exhibits

- **Filing.** A picture's `ImageCategoryType` decides its section, using A-1's
  Report Location (`engine/uad/filing.py`). The section number is derived from
  that table and never typed in.
- **Rotation.** `report/images.py` rotates phone photos by EXIF, so they are
  never sideways in the PDF.
- **API.** Upload with `POST /media`; replace with `PUT /media/{id}/file`; set the caption or category with `PATCH /media/{id}`. Image boxes on the report are set with `PATCH /images`.
- **Optimistic display.** In the editor, a chosen photo shows in its slot at
  once (`showLocal` in `flow.EDIT_JS`), before the upload finishes.

## Maps (`engine/uad/maps.py`, `engine/app/mapper.py`, `engine/app/ui/map/`)

- A-1 requires a latitude and longitude for the subject (0100.0015 / 0100.0016) and for each comparable.
- `maps.py` reads the places, checks that coordinates are plausible, and gives distance and direction.
- The printed **Sales Comparison Map** (`SalesComparableMap`) is drawn by the
  in-app Location Map tool itself:
  - the tool runs headless at the Appendix E frame, 704 x 752 CSS px;
  - it restores the appraiser's pins, callouts and layer;
  - so what the appraiser arranges is what prints.
- No aerial map is drawn; B-1 defines one map.
- Without a browser (Vercel), the tool's own "Save to the report" button
  exports the PNG from the user's browser (`POST /maps/image`).

## Market graphs (`engine/uad/market.py`)

The five B-1 Market image categories are drawn from figures in the D-1
samples' chart style:

- PriceTrend;
- AbsorptionRate;
- MedianDaysOnMarket;
- PercentOfDistressedSales;
- YearBuiltOfSales.

The appraiser imports one data file (`GET /market/prompt` explains its format) instead of pasting screenshots.
