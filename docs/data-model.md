# Data model, field registry and mapping

## The case

A case lives in a directory under the work root (`URAR_WORK`). It holds:

- the MISMO 3.6 XML document, which is the record;
- its media (photographs, exhibits, maps);
- editor preferences;
- the sign-off state, in SQLite (WAL mode).

`engine/app/cases.py` (`Store`) owns it. `Store.bundle` packs a case into one
ZIP for backup, restore and the shared store.

## The field registry

A **Report Field ID** (e.g. `3.000`, `10.031`) is A-1's name for a place on
the report. `engine/spec/field_index.json` maps each one to:

- its section, subsection, label and order;
- its MISMO xPath and data point(s);
- its format (Amount, Numeric, Date, enumeration) and precision;
- its conditionality (R / CR / O).

`edit.field(fid)` returns the binding the editor uses.

`engine/uad/coverage.py` measures how much of the registry the editor
implements, against all twelve D-1 samples. `engine/uad/dossier.py` prints, field by field, what A-1, B-1 and C-1 say
next to what the editor does.

## UAD / MISMO mapping

`engine/uad/uadmap.py` is the single authority for what the standard calls
things:

- enumerations per data point;
- which image categories exist and where they file;
- which containers are selected by a type rather than by position.

Other modules ask it, rather than keeping their own copies.

## Writing a value (`engine/uad/edit.py`)

- Missing parent containers are created and inserted where the XSD
  `xs:sequence` puts them (`xsd_order.py`). The workbook's "XML Sort Number"
  is not the schema order.
- `choose_data_point` picks the data point a plain value goes to. For an address that is
  `AddressLineText`.
- A whole typed address (`186 8th St # 2B, Brooklyn, NY 11215`) is split by
  `split_address` into street, unit designator, unit, city, state and ZIP
  (E-076).
- Identity elements (`templates.IDENTITY`, including `PropertyOrdinalNumber`)
  are kept when a report is blanked, so comparable numbering survives (E-077).

## Typed text to stored value (`engine/uad/entry.py`)

Appraisers type `2,352 sf`, `$515k`, `1.5 acres`, `8/17/19`. The A-1 format
and precision of the data point decide the stored form: Amount, Numeric,
Date (ISO), and measures with their unit attribute.

## Data that never prints

About 450 A-1 rows are required but "Does Not Display".

- Most are filled automatically (`extra.py`): xlink labels, versions, ordinal numbers, PDF and software names.
- About 180 need the appraiser (`points.py`), for example which approaches to value were developed.
- They are edited through `/api/cases/{id}/extra/{uid}`.

## Parties and structure

- `parties.py`: an individual's name or a legal entity's name, an XSD choice, by
  `PartyRoleType`.
- `structure.py`: keeps the number of dwellings consistent (H-1 UAD1016).
