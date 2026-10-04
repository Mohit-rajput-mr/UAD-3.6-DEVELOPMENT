# TOTAL import profile — what the package must be for WinTOTAL to rebuild it

The generator's rules **beyond** the UAD specification, learned from WinTOTAL
(web engine 0.0.1.3848). Each rule names its evidence (`errors/CATALOG.md`)
and how sure we are: **[C]** confirmed by code or a controlled test, **[O]**
observed on real cases, **[I]** inferred, awaiting its test. A rule becomes an
executable generator gate as the Import Module is rebuilt (TASKS phase 3).

Read with `templates/` (per-configuration fill sheets) and
`builds/<build>/validation_profile.json` (every TOTAL validation rule joined to
the data points it guards).

## File shape

| # | Rule | Evidence |
|---|---|---|
| P1 | **No `xsi:schemaLocation`** (or any other prefixed attribute besides xlink) on any element. TOTAL's importer puts every ancestor's attributes into each element's XPath, cannot resolve `xsi:`, and silently skips the value. | E-028 [C] |
| P2 | Build from a clean skeleton, **never a blanked official sample**: no `SIGNATORY`, `RELATIONSHIP` or certification pointing at a party or role that is not in the file; TOTAL makes one signature block per signatory, in order. | E-003 [C] |
| P3 | No empty containers and no typeless rows (adjustments without a type/amount, utilities without type and ownership, amenities without a type). | E-004, E-021, E-023 [O] |
| P4 | Utilities: one `SITE_UTILITY` per utility type, each with `UtilityType` **and** `SiteUtilityOwnershipType` (TOTAL reads a missing ownership as private). | E-004 [O] |

## Structure

| # | Rule | Evidence |
|---|---|---|
| P5 | Import only into a **new or freshly reset** report: a replace-import keeps whatever it does not overwrite. | E-029 [C] |
| P6 | Every unit carries `UnitIdentifier` "Unit n" (subject and comparables); TOTAL lines comparable unit rows up by it. | E-013 [O] |
| P7 | One `INSPECTION` per inspecting role, linked to the role (`INSPECTION_CompletedBy_ROLE`). | E-014 [O] |
| P8 | One `SALES_HISTORY` per GRM comparable holding both price and date. | E-015 [O] |
| P9 | Building identifiers are set on TOTAL's section, not a field: the Import Module sets them after import. | E-006 [C] |
| P10 | Label each subject unit's `RENTAL_INFORMATION` with a label ending `_I<unit number>` and relate every rental comparable's comparison detail to it (`RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION`): TOTAL maps rental comparables to subject units only through that suffix, and otherwise drops the unit data of every comparable past the unit count. The Import Module relabels any file on the way in. | E-032 [C] |
| P16 | Label comparables `PROPERTY_<Role>_P<n>` and subject unit areas `PROPERTY_UNIT_AREA_SubjectProperty_P<unit>` (TOTAL's own convention): its data-source importer finds rental, GRM and land comparables and unit areas only by those label patterns. The Import Module relabels any file on the way in. | E-036 [C] |
| P11 | Pictures are not imported from embedded base64: every picture is placed in its slot by category and caption after import, and read back. Interior pictures sit under their unit's `ROOM/IMAGES`. | E-019, E-020 [C/O] |
| P22 | **The subject's `PropertyPhoto` is the same picture as the first building's `DwellingFront`; one `DwellingFront` per building, in building order.** TOTAL's importer makes the n-th DwellingFront building n's front photo (`DE<n>_PHOTO1`), and TOTAL copies building 1's front photo into every subject photo field — `GSU_PHOTO`, `RSU_PHOTO`, `GRU_PHOTO` and `GSU_PHOTO_SUMMARY`, which its XML delivers as the subject `PropertyPhoto` — one second after any front photo changes (dwelling-exterior calcs, `handlePhotoSummaryChange`). A different subject photo is not delivered. 11 of the 12 D-1 samples already comply (the 2-4 unit sample does not). | E-039 [C] |

## Values TOTAL validates that UAD does not require

| # | Rule | Evidence |
|---|---|---|
| P12 | For **every sales comparable**, carry what TOTAL validates even though H-1 requires it only for the subject (or warns): financing type (`MortgageType` / `NoFinancingTransactionIndicator`), `LevelCount`, functional issues, street access / surface, zoning compliance, primary entry/exit, project amenities (PUD/project), non-standard below-grade area, rights included. The full list per configuration is generated in `templates/*.json` → `total_flagged_on_example` (measured) and `total_validates_beyond_example` (possible). | E-030 [C] |
| P13 | Wherever subject and comparable **differ**, write an adjustment amount — `0` when none was made. Where they are **equal**, write none. | E-031 [C], E-017 [O] |
| P14 | "Other" income rows: with no other income the description is "None" (a blank row fails). | E-008 [C] |
| P15 | Values go in the field's own format and pick-list text (`builds/<build>/datafields.json`): no unit inside a value whose field has a separate unit field. | E-026 [O] |
| P25 | **State every switch TOTAL's writer reads** (`builds/<build>/configuration.json`: approaches, amenities / defects exist, homeowner maintenance, units, ADUs, prior sales, reconsideration …) explicitly — a new report already holds TOTAL's defaults for them (amenities exist, sketch, Itemized, 1 unit, Traditional …) and an import keeps what it does not overwrite. `bridge diagnose --xml` lists the unstated ones. | E-042 [C/I] |
| P26 | Never let a Yes/No pair end up with both boxes marked: TOTAL then delivers no value for it. `bridge diagnose --report` finds them. | E-041 [C] |
| P27 | **Every defect picture carries a caption** (`ImageCaptionCommentDescription`), built from its defect record: TOTAL turns it into the exhibit description its field validation requires. Preflight checks it. | E-044 [C] |

## After import (the Import Module, not the file)

| # | Rule | Evidence |
|---|---|---|
| P17 | Place every picture into the slot TOTAL's import already made for it, by file name (TOTAL creates one per picture, captioned, and never loads the bytes); then the rest by category; re-read linked exhibits before calling a slot missing. | E-033 [C] |
| P18 | After the grid has rendered, show every sales-grid row that holds a comparable value: TOTAL's writer omits values in hidden rows, and rendering hides rows that hold data. | E-037 [C] |
| P19 | With no supervisor in the report, set `HIDDEN_SUPERVISOR_COUNT` back to 0: opening the Order page makes TOTAL deliver a phantom supervisor role. Re-check before signing. | E-034 [C] |
| P20 | Run E&O from a neutral section (Assignment): with Sales Comparison open TOTAL does not report the grid's field-validation findings. | E-035 [C] |
| P21 | Never trust "UAD Errors: 0" unless field validation and schema passed first — otherwise the UAD rules did not run. | E-012 [C] |
| P23 | After P18, have TOTAL re-sum every sales comparable (a value-changed event on its `NETADJ_ADJ` addressed to the sales-comparison calcs): the net adjustment counts only rows visible when it sums, and it summed during import. Then compare every adjustment, net and adjusted price with the package; any difference is value-affecting. | E-038 [C] |
| P24 | Picture slots are found by the pattern `PHOTO\d*$` — building front photos are `DE<n>_PHOTO1` — and a placement by category never replaces a picture of the same category. Verify by the round trip (each slot's file), not by counting drops. | E-039 [C] |

## Values TOTAL owns (expected differences in a round trip)

Software vendor, product, version and identifier; `AboutVersionIdentifier`;
the PDF `ObjectURL`; `ValuationReportContentIdentifier` (TOTAL writes
"URAR Delivery Specification v1.3"); defect pictures move from
`PROPERTY_DEFECT/…/IMAGES` to the inspection's images; the subject
`PropertyPhoto` is building 1's front photo (P22).

## Measured fidelity

`roundtrip/<build>/SUMMARY.md` — the twelve D-1 samples, each imported into a
fresh blank report with P1 applied, serialized back by TOTAL and compared.
