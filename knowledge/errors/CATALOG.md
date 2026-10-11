# Error catalog

Every error class met on a real case or in testing. Each entry names the
**mechanism**, not the case. Before closing a new problem, add it here, with the
check that keeps it fixed.

Layer: where the fix belongs (ARCHITECTURE.md): **intake**, **model**,
**gate** (generator gates), **profile** (TOTAL import profile check),
**import** (Import Module stage c/d/e), **diag** (diagnostics), **rule**
(standing working rule).
State: **general** (fixed by a mechanism that works for any case) ·
**case-only** (fixed so far only in one case's scripts — must be generalized) ·
**open**.

Source case: R1 = the three-unit attached rowhouse (2026-09-26/27, WinTOTAL build
0.0.1.3848).

---

### E-001 Generic field-by-field fill damages grids
- Symptom: 334 field-validation findings; GRM/rental columns read from the wrong
  properties; 19 "Clear Comparable Data" prompts.
- Cause: writing grid fields directly runs TOTAL's comparable-number handlers
  out of order and without the importer's context.
- Fix: never fill a report field by field; import the package, repair only
  differences (ARCHITECTURE decision). Layer: rule. State: general. Case: R1.

### E-002 A listing's sale-to-list adjustment spreads across its column
- Symptom: every adjustment cell of a listing comparable holds the same amount.
- Cause: TOTAL's importer, on a listing's `SaleToListPriceRatio` adjustment.
- Fix: value reconciliation (round trip finds every wrong cell and rewrites it).
  Layer: import. State: case-only (`_work/woodycrest/total_fix.py` resets the
  column). Test: TODO — D-1 sample with a listing, round trip.

### E-003 Leftover people from a blanked sample → phantom supervisor
- Symptom: signature page shows "Supervisory Appraiser: <the appraiser>" and an
  empty "Appraiser" block; UAD-1535 on both.
- Cause: the case was built on an official sample with its values blanked; the
  supervisor's `SIGNATORY`, its link to a `ROLE` that blanking removed, and an
  empty "by AppraiserSupervisor" certification remained. TOTAL makes one
  signature block per `SIGNATORY`, in order, and fills the first.
- Fix: build from a clean skeleton (model); integrity gate — no signatory,
  relationship or certification that points at a missing party/role (gate);
  import stage c — signature blocks equal the parties (import).
  State: case-only (`convert_post3.py`, `total_fix.one_signer`); engine blanking
  is T-970. Test: TODO — integrity check over all D-1 samples + R1.

### E-004 Utility rows without type or ownership
- Symptom: UAD-1350/1355 (sewer "Non Public"); field validation on
  `EXT_SIT_UTIL` (an "Other" utility row).
- Cause: the blanked sample's cesspool sewer row kept no ownership (TOTAL reads
  no ownership as private); an ownership-only `SITE_UTILITY` with no
  `UtilityType` became an "Other" row.
- Fix: integrity gate — every `SITE_UTILITY` has `UtilityType` and
  `SiteUtilityOwnershipType`, one per type (Scenario 2 sample pattern); model
  writes resolve a utility row by its type (T-970). Layer: gate, model.
  State: case-only (`convert_post3.py`; `total_fix` removes the Other row).

### E-005 Import drops values the file carries
- Symptom: UAD-1369 (zoning compliance), 1677 (measurement standard),
  1085/1086/1693 (living unit count), 1240 (cost-service name), 1774
  (a comparable's construction method); zoning code/description empty.
- Cause: **mostly E-028** (confirmed 2026-09-28 on the SF1 sample: the same
  values drop with `xsi:schemaLocation` present and import without it). Any
  residue after E-028 is measured per data point by the D-1 round trip.
- Fix: E-028 first; value reconciliation by UID for what remains.
  Layer: import. State: case-only (named writes in `total_fix.py`), superseded
  by E-028 for the xsi-caused part.

### E-028 `xsi:schemaLocation` on the root makes TOTAL's importer drop values
- Symptom: 220 console errors "Error during ConvertXPath: Cannot resolve QName
  xsi" during import; ~25 subject values silently missing (county,
  neighbourhood, parcel, legal description, attachment, overall and exterior
  quality/condition, style, construction method, special assessments,
  broadband, topography, zoning compliance/code/description, measurement
  standard, commentaries) and the highest-and-best-use indicators read false.
- Cause: [C] the importer's generic path builds an XPath for each element
  that includes a predicate for **every attribute of every ancestor**, skipping
  only `AreaUnitOfMeasureType`, `MISMOReferenceModelIdentifier` and `xmlns*`
  (`GetElementXPathWithPositionAndAttributesXLinkAware`). The root's
  `xsi:schemaLocation` therefore enters every path; its XPath library has no
  resolver for `xsi`, throws, and `ConvertXPath` swallows the error and skips
  the value.
- Proof: SF1 sample round trip — with the attribute: 938 of 986 values kept,
  31 dropped, 220 errors; without it: 972 of 985 kept, 6 "dropped" (defect
  pictures TOTAL moves under the inspection), 0 errors; every other difference
  is TOTAL's own software identity, version and PDF name.
- Fix: the generator never writes `xsi:schemaLocation` (or any other prefixed
  attribute) on elements of the package; the Import Module removes it from any
  file before handing it to TOTAL. Layer: gate + import. State: general
  (rule known; `tools/roundtrip.py` applies it; bridge import TODO).
  Test: round-trip regression over the D-1 samples (`tools/roundtrip.py`).

### E-006 Structure identifier is on the section, not a field
- Symptom: UAD-1091 although `DE1_SECTION_DESCRIPTION` holds a value.
- Cause: TOTAL serializes `StructureIdentifier` from the dwelling section's
  Description in its section manager (FINDINGS §2).
- Fix: structure reconciliation sets identifier/caption/description and saves
  the sections, as TOTAL's importer does. Layer: import. State: general
  function (`total_fix.structure_identifier`), not yet in the bridge.

### E-007 A value written without the UI event stays "required"
- Symptom: comparable unit GLA "required" with the value visibly present.
- Cause: [O] the field's validator runs on LeaveField; a data-layer write does
  not reproduce the state the typed path sets (FINDINGS §4, U3).
- Fix: validator-aware writes (type + leave for LeaveField fields). Layer:
  import. State: case-only (`typed_gla`).

### E-008 "Other rental income" row: blank description fails
- Symptom: field validation on `RI_ACT_INC_OTHER_MONTHLY_RENT` /
  `RI_OPN_INC_OTHER_MONTHLY_RENT`.
- Cause: the rule passes only when the description is "None" or the amount is
  not $0 (`otherRealPropertyRentlyTrueIsRequiredCondition`).
- Fix: profile — with no other income, the row says "None". Layer: profile.
  State: case-only (`total_fix.py`).

### E-009 Coordinates not carried over
- Symptom: UAD-1008/1009 (subject), 1429/1430 (comparables) warnings.
- Cause: the source (2.6 `LOCATION`) had them; the converter did not map them.
- Fix: intake maps every source coordinate; completeness gate. Layer: intake,
  gate. State: case-only (`convert_post3.py`).

### E-010 Source gives building area only; UAD 3.6 wants each unit's
- Symptom: comparable `UNITS_SF_GLA` required per unit.
- Cause: a data gap, not a software fault — a 1025/2.6 reports building GBA.
- Fix: intake question; owner-approved standing default "split building area
  by room count, rounded to add back exactly" and disclose it. Layer: intake.
  State: case-only (`comp_unit_gla.json`).

### E-011 Import copies a rental comparable into unused columns
- Symptom: rents in rental columns that have no property.
- Fix: structure reconciliation — columns equal the package's comparables;
  round trip. Layer: import. State: case-only.

### E-012 "UAD Errors: 0" while field validation fails
- Symptom: the UAD list looks clean; the report is not.
- Cause: [C] the E&O check stops after field validation (or schema) errors and
  never runs the UAD rules (FINDINGS §5).
- Fix: diagnostics report which stage ran; UAD counts are only trusted when
  stages 1–2 passed. Layer: diag. State: general (understood); diag TODO.

### E-013 Comparable unit rows misaligned
- Cause: TOTAL lines comparable units up by `UnitIdentifier` "Unit n".
- Fix: profile check. State: case-only (`convert_post2.py`).

### E-014 Inspection split across records
- Cause: TOTAL expects one `INSPECTION` for the appraiser, linked
  (`INSPECTION_CompletedBy_ROLE`) to the appraiser role.
- Fix: profile check. State: case-only (`convert_post2.py`).

### E-015 GRM comparable price and date in separate sale records
- Fix: profile — one `SALES_HISTORY` per GRM comparable. State: case-only.

### E-016 Dwelling style on attached dwellings
- Cause: `ArchitecturalDesignCategoryType` applies to detached dwellings; the
  subject still needs TOTAL's `DE#_STYLE`.
- Fix: profile + value reconciliation. State: case-only.

### E-017 $0 adjustment where subject equals comparable
- Symptom: adjustment cell flagged.
- Fix: rule — equal features get a blank adjustment, not $0. State: case-only.

### E-018 Cost approach does not reproduce the appraiser's figure
- Cause: TOTAL applies whole-number depreciation percentages to new cost, and
  recomputes totals only on typed input.
- Fix: reconciliation compares the indicated value; when it differs, use the
  total-depreciation path, typed. Layer: import. State: case-only
  (`total_fix.cost_total`).

### E-019 Pictures are not imported from the file
- Cause: TOTAL does not import embedded base64 pictures; each slot takes a drop.
- Fix: stage e places by A-1 category + caption; every drop read back.
  State: case-only plan (`place_photos.py` PLAN) → generalize.

### E-020 Interior pictures all land in unit 1
- Cause: pictures must sit under the unit's `ROOM/IMAGES`.
- Fix: model places each picture under its unit and room. State: case-only
  (`convert_post2.place_photos`).

### E-021 Empty or typeless adjustment rows
- Cause: template leftovers; TOTAL's import mis-assigns the next amount.
- Fix: integrity gate. State: case-only (`convert_post2.py`).

### E-022 Grid ordinals written mid-build re-sort comparables
- Fix: model assigns ordinals once, last. State: case-only.

### E-023 Empty amenity containers / wrong amenity category
- Cause: the schema forbids empty containers; a porch belongs to Outdoor
  Living (D-1 samples).
- Fix: integrity gate; model builds amenities from the samples' pattern.
  State: case-only (`convert_post3.py`).

### E-024 Engine writes create new repeated rows instead of matching
- Cause: `POST /fields` for some repeated containers (utilities) adds a row
  rather than resolving the existing one by its discriminator.
- Fix: engine `edit.py` resolves by discriminator. Layer: model. State: open
  (T-970).

### E-025 A value appears that no source provided
- Symptom: appraiser designation "MAI" with no file or script writing it.
- Cause: unknown ([I] WinTOTAL's appraiser contact profile).
- Fix: round trip flags every value not in the package; the owner confirms.
  Layer: diag. State: open.

### E-026 Doubled unit in a printed value
- Symptom: "100 Sq. Ft. Sq. Ft."
- Cause: the value carried its unit and the field has a separate unit field.
- Fix: write values in the field's format (`datafields.json` format and unit
  companions); print check. Layer: import, diag. State: case-only.

### E-029 A replace-import does not reset the report
- Symptom: importing file B into a report that held file A leaves A's extra
  sections, comparable columns and values (SF1 after a 2-4 unit file: two unit
  interiors, 83% kept instead of 98%; field-validation counts differ run to run).
- Cause: [C] `ImportMismoXml` populates what the file carries; it does not clear
  what the file does not mention.
- Fix: the Import Module imports only into a **new** report — or resets the
  report first by opening a blank report file through TOTAL's own
  `OpenReportXml` (the header of the live report plus the fields that define a
  new report's structure: building 1 with unit 1, the order page). A file with no
  fields at all leaves TOTAL without a data store and must not be used.
  `tools/roundtrip.py reset_blank()` implements and verifies it (restores the
  report if the structure is not exactly one building with one unit).
  Layer: import. State: general (tool); Import Module preflight TODO.
- Open: one party (the management company) imported into a WinTOTAL-created
  blank but not into the reset blank; [U] confirm on a report created fresh in
  WinTOTAL. 2026-09-28 (build 0.0.1.3855): [C] TOTAL's importer writes every
  value through one helper that **drops the value when its field instance
  does not exist** ("Data field not found", a warning in the import result that
  `ImportMismoXml` does not return; its narration switch is inside a module
  that exports nothing, so the Import Module cannot turn it on — the round
  trip is how drops are seen); the AMC is the second contact row, so it is lost
  unless that row exists. [O] The new and the reset report both hold exactly
  one contact row; they differ in 74 fields (`tools/new_report.py`
  observations), among them the order sheet's `ORD_CONTACT_PARTY_ROLE` and
  `ORD_REPORT_TYPE`, which only the new report holds. [U] which of them makes
  the importer add the second row — test on the first report the owner creates
  (the multi-family case), whose round trip will show the AMC kept or not.

### E-030 TOTAL's field validation requires comparable data UAD does not
- Symptom: 60 field-validation findings on the official SF1 sample after a clean
  import (fresh blank, E-028 applied) — all in the sales grid; the UAD rules
  never run (E-012).
- Cause: [C] TOTAL validates, for **every comparable**, values that H-1 requires
  only for the subject or only warns about — and that the official D-1 sample's
  comparables do not carry: financing type (`MortgageType` /
  `NoFinancingTransactionIndicator`; H-1 UAD1394 is a Warning), number of levels
  (`LevelCount`), functional issues, street access / surface, zoning
  compliance, primary entry/exit, project amenities (PUD/project), non-standard
  below-grade area, property-rights-included. Verified by reverse lookup
  through TOTAL's MISMO↔field table: absent in the file, absent in TOTAL's
  output; H-1 rules for them are subject-only (UAD1680, 1369, 1318, 1028).
- Fix: the TOTAL import profile requires these comparable values; intake
  gathers them (MLS/public record) or asks; the generator writes them. The
  list is generated from `validators.json` (grid validators) × `uid_map.json`,
  not typed. Layer: profile, intake. State: open.

### E-031 TOTAL requires an explicit adjustment wherever subject and comparable differ
- Symptom: "An adjustment entry is required when subject and comparable data
  differ" on every grid row where the values differ and no amount is present
  (10 rows × 3 comparables on SF1).
- Cause: [C] a TOTAL grid rule; UAD lets a zero adjustment be absent, and the
  D-1 samples omit them.
- Fix: the generator writes `ComparableAdjustmentAmount` 0 for every row whose
  subject and comparable values differ and no adjustment was made; and leaves it
  absent where they are equal (E-017). Layer: profile. State: open.

### E-032 Rental comparables beyond the number of subject units lose their unit data
- Symptom: after import, rental comparables past the first N keep address and
  proximity but lose every unit value (rent, bedrooms, baths, area, lease,
  condition, comparison details). Measured on the D-1 samples: N equals the
  number of subject units every time — Condo2 (1 unit, 4 comps) keeps 1; 2-4 unit
  (2 units, 5 comps) keeps 2; Scenario 2 (4 units, 6 comps) keeps 4.
- Cause: [C] TOTAL files a rental comparable into the grid of the subject unit it
  is compared with (`RC{unit}.{column}_…`) using only relationships with arcrole
  `RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION` whose **target label
  ends in `_I<unit number>`** (`BuildCompToUnitMappings`, regex `/_I(\d+)$/`).
  The GSE samples label the subject unit `RENTAL_INFORMATION_BLDG1_UNIT1`, so no
  mapping is built and TOTAL falls back to "comparable i → unit i, column 1":
  every comparable past the unit count lands on a unit that does not exist.
  TOTAL's own output uses `RENTAL_INFORMATION_SubjectProperty_I1`.
- Fix: `bridge/total.py prepare_for_total()` (run on every import) relabels each
  subject unit's `RENTAL_INFORMATION` to end in `_I<n>` (n = the unit's order in
  the subject) and every reference to it — an xlink label is only an
  identifier, no fact changes. The generator labels them this way from the start
  (IMPORT_PROFILE P10). Layer: import, profile. State: general (test:
  `total-bridge/tests/test_prepare.py`; D-1 re-measure pending).

### E-033 TOTAL makes a slot for every picture but loads none
- Symptom: only 13 of the SF1 sample's 28 pictures placed; 14 "have no section"
  (room, garage, amenity and defect pictures carry no `ImageCategoryType` — their
  container says what they are).
- Cause: [C] TOTAL's import creates a photo field for **every** picture the file
  names — under its room, defect, garage, amenity — captions it ("Level 1 -
  Kitchen", "Apparent Defects … - Roof - Damaged Flashing") and sets its value
  to the picture's file location; it never loads the bytes. A category-only
  placer cannot route the uncategorised ones.
- Fix: `bridge/place.py place_by_file()` fills every empty slot whose value
  names a file with that file's picture, then places the rest by category;
  linked exhibits (the comparable-photo exhibit mirrors the grid photo) fill
  themselves and are re-read before being reported. Role controls are looked for
  in other sections when not where expected (`GSU_MAP` lives in Sales
  Comparison, not the grid). TOTAL stores every placed picture as JPEG under its
  own name (an expected round-trip difference). Result on SF1: 28/28 placed.
  Layer: import. State: general.

### E-034 Opening sections adds a supervisor to the data
- Symptom: after merely opening every section of an imported SF1 (no edits),
  TOTAL's serialization gained `PartyRoleType` AppraiserSupervisor and
  `AppraiserSupervisorAdditionalCertificationIndicator` true — the sample has
  no supervisor.
- Cause: [C] TOTAL's XML writer emits the supervisor role, the supervisor
  additional certifications and `AppraiserSupervisorAdditionalCertificationIndicator`
  true whenever `HIDDEN_SUPERVISOR_COUNT` > 0 — regardless of whether any
  supervisor field holds a value. [C] That count defaults to 0 but its
  repeatable minimum is 1 (max 1) (`builds/…/repeatables.json`, `defaults.json`).
  [O] Rendering the section that holds the supervisor table enforces the
  minimum → count 1 → phantom supervisor in the XML. [I] So an appraiser merely
  opening that section in WinTOTAL can create it; it is also the likelier cause
  of the rowhouse case's "Supervisory Appraiser" block (E-003) alongside the
  template leftover. [C by experiment, SF1]: Summary, Assignment and
  Certifications leave the count at 0; **opening the Order page sets it to 1**
  and the XML gains the role and the indicator.
- Fix: `bridge/reconcile.py clear_phantom_supervisor()` — with no supervisor
  name, licence or `HAS_SUPERVISOR`, the count goes back to 0; measured: the XML
  is clean and stays clean when the Order page and Assignment are reopened. A
  real supervisor is never touched. Diagnostics re-check before signing.
  Layer: import, diag. State: general.

### E-035 The E&O result depends on which section is open
- Symptom: the same report, unchanged: field validation 48 from Order, the
  side-by-side grid or Assignment; **0 from Sales Comparison** (and then the
  UAD rules run and report 2 warnings). Deterministic, repeated.
- Cause: [C by experiment] with Sales Comparison open, TOTAL's global field
  validation does not report the comparable-grid findings.
- Consequence: a "clean" E&O read on that section is false; WinTOTAL's own
  delivery counts may be taken from any section.
- Fix: every E&O check runs from a neutral section (`assignment`); diagnostics
  never trust a count taken on Sales Comparison. Layer: diag. State: general —
  `bridge/review.py eando()`, used by the Import Module (`bridge/deliver.py`,
  `bridge deliver`) and by `tools/roundtrip.py`.

### E-036 Data sources of rental, GRM and land comparables and of unit areas are dropped
- Symptom: on every D-1 sample the rental and GRM comparables' MLS sources
  vanish (8 of 15 data sources on the 2-4 unit sample); unit areas of units 2+
  lose their source (field validation `UI2_AREA_DATA_SOURCE_TYPE`).
- Cause: [C] TOTAL's data-source importer (`PopulateDataSourceFields`) finds
  the target by its xlink label: a comparable's label must **contain the role**
  (`e.to.includes("Rental")`, `"LandComparable"`, `"GrossRentMultiplierComparable"`)
  and end `_P<n>`; a unit area's label must end `_P<unit>` (default unit 1). The
  GSE samples label them `PROPERTY_RENT_COMP1`, `PROPERTY_UNIT_AREA_BLDG2_UNIT2_GLA`.
  Sales comparables survive because they are resolved another way.
- Fix: `bridge/total.py prepare_for_total()` gives every element TOTAL reads by
  label TOTAL's own label (`PROPERTY_<Role>_P<n>`,
  `PROPERTY_UNIT_AREA_SubjectProperty_P<u>`, and E-032's rental labels) and
  updates every reference; nothing else changes (tests/test_prepare.py, 5
  tests on the 12 samples). Layer: import, profile. State: general; D-1
  re-measure pending.

### E-037 Displaying the grid hides rows, and TOTAL's XML then omits their values
- Symptom: 2-4 unit sample, engine export, after the picture step (which opens
  every section): each sales comparable kept only half its structure components
  (8 → 4) and fewer adjustments, plus per-unit interior quality/condition
  details; the raw-sample import without the picture step kept them. Import
  logs identical. Single-family comparables (one unit) unaffected.
- Cause: [C] TOTAL's importer adds comparable unit / quality-condition rows via
  `AddFieldDataGroup("salescomp-comp-units-section" | "salescomp-comp-quality-
  condition-(interior|exterior)-section")`, which looks up
  `HIDDEN_SALESCOMP-COMP-…_COUNT`; the form's count fields are named
  `HIDDEN_SALESCOMP-UNITS-SECTION_COUNT`, `HIDDEN_SALESCOMP-QUALITY-CONDITION-…
  -SECTION_COUNT` — the lookup fails ("HIDDEN COUNT field appears to be
  missing"). [I] The rows are written without a count behind them and rendering
  the grid trims them to the count (min 1). [U] Experiment: import, serialize,
  open only the grid, serialize, diff.
- [C by experiment] The count hypothesis was wrong (counts are 2, data-layer
  values unchanged: 1,564 grid fields identical before/after). The real
  mechanism: the writer includes a comparable value only if its grid row is
  visible for that instance (`EnableForComparisonApproach` →
  `visibilityRules.isVisible`), and rendering the grid hides rows that hold
  values (foundation, roof/window condition, kitchen/bath quality, levels,
  disaster mitigation, rights, site hazard — 20 row-instances on the sample).
- Fix: `bridge/reconcile.py show_rows_with_data()` shows every grid row that
  holds a comparable value, through TOTAL's own visibility rule. Measured: comps
  back to 8·4·15, 8·4·17, 4·4·16 (the sample's own adjustment counts) and
  unchanged after the grid is rendered again. Layer: import. State: general
  (sales grid; rental/GRM grids to check).

### E-038 TOTAL's net adjustment total omits some adjustment rows
- Symptom: 2-4 unit D-1 sample: every adjustment line is present in TOTAL's
  data and XML, yet `SalePriceNetTotalAdjustmentAmount` / adjusted prices
  differ from the sample: comp 1 short −2,000 (SITE_CHARACTERISTICS_ADJ),
  comp 2 short −10,000 (SITE_HAZARD_ZONE_ADJ −15,000 + DWELL_DISASTER_MIT_ADJ
  +5,000), comp 3 short −15,000 (SITE_HAZARD_ZONE_ADJ). Adjusted prices wrong
  (199,250 → 214,250).
- Cause: [C, from TOTAL's bundle, build 0.0.1.3848] `SalesCompCalcs.
  ApplySummaryCalculations(comp)` sums `GetCompAdjFields(comp)` but adds a
  field only when `IsFieldVisibleForAdjustmentCalcs` is true — the grid row's
  visibility rule (`salescomp-<row>`, instance) *at the moment it sums*. It sums
  during import, while the grid still hides rows that hold adjustments (E-037).
  Showing the rows afterwards does not re-sum. `ExecuteAllCalcs` does not either:
  `SalesCompCalcs.ApplyFormCalculations` returns at once when the event has no
  `changedKey`. And a plain event without `fieldSectionKey` runs the calcs of
  whatever section is *open* (`FormCalcs.ExecuteCalcsForSection`), not the
  sales-comparison calcs. (The earlier note "not a visibility effect" was wrong:
  it tested re-show + ExecuteAllCalcs, which never reaches the summary.)
  [I] The same holds in ordinary use: an adjustment typed into a row TOTAL has
  hidden is left out of the net without any message.
- Fix: `bridge/reconcile.py recalculate()` — after `show_rows_with_data`, one
  `ValueChanged` event per sales comparable on its `NETADJ_ADJ` field with
  `fieldSectionKey` "sales-comp": the event an edit of any of its adjustments
  raises; the field matches none of the per-field cases, so only the summary
  runs. [C by experiment, 2-4 unit sample] nets −82,200 / 5,400 / −35,500 →
  −84,200 / −4,600 / −50,500 (the package's), adjusted 199,250 on comp 3; a
  serialization diff before/after changed exactly those 12 figures (net,
  adjusted price, per unit, per bedroom × 3) and nothing else; stable through
  re-rendering the grid, Sales Comparison, Assignment and
  `ExecuteAllFormConditionality`. Diagnostics: `tools/roundtrip.py` writes
  `value_diffs.json` (every difference in adjustments, nets, adjusted
  prices/rents, multipliers, indications, the opinion) and the count per case.
  Layer: import, diag. State: general for the sales grid; rental/GRM
  summaries unchecked until the 12-sample batch reports `value_diffs`.

### E-039 A second building's front photo replaces the first's, and the subject photo
- Symptom: 2-4 unit D-1 sample (two buildings), e2e with pictures: TOTAL's XML
  holds `2-4_Dwelling2Front` as the subject's PropertyPhoto *and* as a
  DwellingFront, plus one DwellingFront still naming `2-4_Dwelling2Front.png`
  (not loaded); `2-4_Dwelling1Front` and `2-4_SubjectProperty` are gone. The
  report's first photo would show the wrong building. `photos.json` reported
  53 placed, 0 empty, 0 failed — the placer's own count did not see it.
- Cause: [C by experiment, 2-4 unit sample on a fresh blank; code in the
  bundle snapshot] three things together.
  1. TOTAL's importer *does* file the n-th DwellingFront as building n's front
     photo (`DE<n>_PHOTO1`, value = the file) -- but `place.py` found import
     slots with `/PHOTO$/`, which misses `DE<n>_PHOTO1`: building 2's slot was
     never filled by file and its "0 slots still empty" count was blind to it.
  2. Building 2's front then went "by category", and `BY_ROLE["DwellingFront"]`
     is hard-wired to `DE1_PHOTO1` and did not check the slot was empty: it
     overwrote building 1's front.
  3. TOTAL copies `DE1_PHOTO1` into `GSU_PHOTO`, `RSU_PHOTO`, `GRU_PHOTO` and
     `GSU_PHOTO_SUMMARY` one second after any `PHOTO1` changes
     (dwelling-exterior calcs `handlePhotoSummaryChange`); its XML writer
     delivers the subject `PropertyPhoto` from `GSU_PHOTO_SUMMARY`
     (`CreateInspectionImages`). So the subject photo followed the wrong front
     photo, and a separate subject photo can never be delivered by TOTAL.
     11 of the 12 D-1 samples use the same picture for both anyway.
- Fix: `place.py` — slots matched by `PHOTO\d*$`; a category placement never
  replaces a picture of the same category (`_held_category`, needs every
  picture of the file: `place(..., known=)`); a subject PropertyPhoto is not
  pushed into `GSU_PHOTO` (reported as `total_owned`). `deliver.pictures`
  lists every slot whose picture differs from the one the import named
  (`differs_from_import`). Generator: IMPORT_PROFILE P22 (subject photo = first
  building's front; one front per building, in order), P24. Verified live
  (2-4 unit, `bridge deliver`): DE1/DE2 fronts correct, 55 slots naming a file,
  0 empty, 0 value-affecting differences. Layer: import, profile. State: general.

### E-040 TOTAL's report pane goes white: its browser process ran out of memory
- Symptom: the owner saw the "sample blank" report fully white in TOTAL;
  WinTOTAL's title became "Appraisal Desktop"; the batch hung on sample 2 for
  8+ minutes without an error.
- Cause: [C] Windows Application log 2026-09-28 16:34:59:
  `CefSharp.Alm.BrowserSubprocess.exe` (CEF 109) terminated, exception
  `0xe0000008` — Chromium's out-of-memory code — during the import of the
  largest D-1 sample (4-unit Scenario 2). The report's CDP page target vanished;
  the only page left was a new Google satellite view. [O] That renderer had run
  since 13:42 through ~25 full imports and several hundred picture drops.
  [U] the threshold (how many imports/pictures a session takes) — not measured.
- Fix: `bridge/cdp.py Page.alive()`; `tools/roundtrip.py` checks it before
  every file and stops with a message instead of hanging, and after every file
  forces a collection and records the page's JS heap (`Page.heap_mb`,
  `heap_mb_after` in the summary) so the limit is measured. [C] TOTAL's browser
  is 32-bit (`WOW64`, Chrome 109.0.5414.120).
- Recover: **only the owner can** — reopen the report in TOTAL (the crashed
  process already released its memory; a TOTAL restart is not required). [C]
  the MOD cannot: it lives in the report page, which is gone from the target
  list (`Target.getTargets` shows only Appraisal Desktop's map page); the form
  → WinTOTAL channel (`CefConnector` events) has no "open report". The owner
  has said: do not drive the PC (no desktop control) — work through the MOD only.
  [O] 2026-09-28 ~17:12: the unsaved scratch report "sample blank" was gone
  after the crash (never saved — the MOD never saves); the owner opened a new
  report "sample" as the scratch report.
  Layer: import (environment). State: mitigated, threshold unknown.

### E-041 A Yes/No pair with both boxes marked delivers no value at all
- Symptom (latent; found by reading, not yet met on a case): an indicator the
  report shows as answered is missing from TOTAL's XML, and nothing flags it.
- Cause: [C] TOTAL reads every Yes/No pair through one helper (its `Indicator`
  class, `GetCheckBoxState`): Yes marked → true, No marked → false, **both
  marked or neither → no value**. Its XML writer takes the report's switches
  (cost / income approach, sales contract, amenities, defects, …;
  `builds/<build>/configuration.json`) from that helper, so a contradictory
  pair silently removes the switch — and what the switch governs.
- Fix (detect, not repair): `bridge/diagnose.py after()` scans every
  `_YES/_NO` and `_ENABLE/_DISABLE(D)` pair in the data layer and reports each
  pair with both marked as severe, clickable to the field; `bridge detect`
  flags the writer's own 22 switches. The package side: never state both.
  Layer: configuration. State: detector built; [U] whether TOTAL's importer can
  produce such a pair (watch the 12-sample batch).

### E-042 What the package does not state, TOTAL answers with its own default
- Symptom: a value the appraiser never gave appears in the report (a new
  report already says amenities exist, sketch provided, cost-to-repair
  "Itemized", one unit, Traditional appraisal …), and field validation then
  demands its details (a blank report asks for an amenity category).
- Cause: [C] TOTAL's form defines 557 field defaults (`builds/<build>/defaults.json`)
  and some calculations set more on a new report (FINDINGS §9); [C] a
  replace-import keeps what it does not overwrite (E-029).
- Fix: `bridge/diagnose.py before()` lists every switch TOTAL's writer reads
  that the package leaves unstated — warning when A-1 requires it, info (with
  A-1's condition) when conditional; tested on the 12 D-1 samples (none unstated
  when required) and on a mutated sample (`tests/test_diagnose.py`). After
  import, the round trip shows any default TOTAL delivered as "added".
  Layer: generator + import. State: general for the 13 switches that are MISMO
  data points; the other 9 (sales contract, revision history, rent comparison,
  agency …) are structural and are checked by the round trip only.

### E-043 The panel's own import button skips the Import Module
- Symptom: a package imported with the HUD's ">> inject" button loses values
  that `bridge deliver` keeps.
- Cause: [C] the button hands the file straight to `ImportMismoXml`: no P1
  (xsi strip, E-028), no P10/P16 relabelling (E-032, E-036), no fresh-report
  check (P5, E-029), no picture placement or reconciliation.
- [C] Met 2026-09-28 on the scratch report: a panel installed earlier by older
  bridge code stays in the page with that code's handlers, and `install()` only
  refreshed an existing panel — so the old button did a bare import although
  the new code no longer had one. (Scratch report only; reset with
  `roundtrip.reset_blank`, and `detect.freshness` saw 1,179 values a new report
  does not hold.)
- Fix: the button never imports by itself: it hands the file to the Import
  Module run by `bridge hud --watch` (`hud.serve_request`: refuse signed or
  used reports (P5, `detect.freshness` against `builds/<build>/new_report.json`),
  refuse packages with severe preflight findings, then `deliver.run`, then
  `diagnose.after` into the panel); with no watcher it refuses and says why.
  The panel carries a code version and `install()` replaces a panel of any
  other version.
  Layer: import. State: general (live test on SAMPLE BLANK, T-992).

### E-044 A defect picture without a caption becomes an exhibit TOTAL will not pass
- Symptom: field validation "Exterior exhibit description is required when an
  exterior exhibit category is not provided or the category is Apparent
  Defects, Damages, Deficiencies" (DE1/DE2 on the 2-4 unit sample), "Exhibit
  description is required when a photo is attached" (outbuilding, MH1),
  "Exhibit category is required …" (amenity, Condo1) — the "untraced" findings
  of `classify_findings.py` (no data point: exhibits are TOTAL's own rows).
- Cause: [C] TOTAL files each defect's picture as an exhibit of its building /
  unit / outbuilding / amenity with the picture's caption as the exhibit
  description; a defect picture without `ImageCaptionCommentDescription`
  leaves the exhibit undescribed. The official samples carry such pictures
  (2-4 unit, Condo1, MH1). A TOTAL rule, not a UAD one.
- Fix: generator — caption every defect picture from its own defect record
  (component, location, what was observed); preflight P27 reports any defect
  picture without one. Test: `tests/test_preflight.py::test_defect_pictures_need_a_caption_p27`
  (P27 fires exactly where TOTAL flagged, measured on 0.0.1.3855).
  Layer: generator. State: detector general; the engine's caption writing is
  the generator's job for each case.

### E-045 A comparable's functional issue is dropped although the package follows A-1
- Symptom: every sales comparable: field validation "Please complete all
  required functional issues fields" (GC#_DWELL_FUNC_ISSUES); the round trip
  shows `FunctionalIssueType` dropped (found by the 2-4 unit test package,
  T-995, 2026-09-28).
- Cause: [C] A-1 places a comparable's functional issue on the property
  (1800.0121: `PROPERTY/FUNCTIONAL_ISSUES/FUNCTIONAL_ISSUE/FunctionalIssueType`);
  TOTAL's sales-grid parser (bundle 0.0.1.3855, the comparable dwelling reader)
  reads it only from `IMPROVEMENT/FUNCTIONAL_ISSUES/FUNCTIONAL_ISSUE` of the
  comparable's dwelling improvement, so a spec-correct package loses it.
- Fix: `bridge/total.py prepare_for_total` gives TOTAL a copy inside the first
  dwelling IMPROVEMENT (the property-level original stays, the package itself
  is unchanged). Test: `tests/test_prepare.py::test_comparable_functional_issue_also_where_total_reads_it`.
  Layer: import. State: built; [U] live confirmation on the next test import.

### E-027 Tool misreads a clean E&O map
- Cause: once field validation is clean, `GetEandOItemMapForTesting` holds UAD
  rule items (`RuleId`, `MessageText`, `Severity`), not field items;
  `bridge/review.run` parsed them as blank findings.
- Fix: `bridge/review.py run()` parses both shapes — a UAD rule item becomes a
  finding with `rule` and `severity` (Fatal / Warning), never a blank field
  finding; `summarise()` says "field validation clear; UAD rules: n error(s)".
  Layer: diag. State: general (test: `total-bridge/tests/test_review_compare.py`).

### E-046 A comparable column cannot be added from the screen
- Symptom: a single-family report configured with three sales-comparable
  columns needs a fourth. The control exists -- `.button-guidance-add` whose
  text is `Add Comp #4` -- but clicking it does nothing, and
  `ui.click` returns False.
- Cause: [C] two things at once. The button's ancestor
  `div.guidance-entry-container` is `display: none`, so the button itself
  computes `display: none` and has a zero-sized box -- `ui.where` filters on
  `offsetParent !== null` and never finds it, and a coordinate click has no
  coordinates to use. And the grid itself is virtualised: with the sales-comp
  section open, `document.querySelectorAll('[fn]')` returns **20** controls
  and no `GC*` cell is rendered at all, so there is nothing to focus to make
  the guidance panel open. Clicking a `GC1_*` cell to raise the panel is
  therefore not available either. Same family as E-037 (the grid hides rows
  and TOTAL's XML then omits their values).
- Consequence: the number of comparable columns is fixed at whatever the
  report was created with, for anything driven from the screen.
  `HIDDEN_SALESCOMP_COUNT` is an **output** of the column state, so writing it
  does not add a column (same rule as the `HIDDEN_..._COUNT` fields in E-034).
- What does work: the columns that already exist are fully writable through
  the data layer even though none of their cells is rendered -- 69 of 72 grid
  values landed on three columns with `rtv.put` while the grid was virtualised.
- Fix (2026-09-29, confirmed on a live single-family report):
  * **Comparable column** -- call the method TOTAL's own button calls:
    `dataSet.CompManagers.get("sales").AddComp(1, false)` (bundle 3855:
    the `Add Comp #N` handler and the grid's empty-column cell both do exactly
    this, then `OnDataChanged(RenderAll)`). Navigating to the section renders
    it. 3 -> 4 columns, every `GC4_*` field created.
  * **Exhibit rows** -- the guidance entry is shown for whichever table has
    focus. Click a cell of that section's exhibit table through the input
    domain, then click the now-visible button. The cell and the label differ
    by section: description cell and `+ Add Exhibit` in Unit Interior and
    Dwelling Exterior; description cell and `Add Exhibit` (no plus) in Site;
    **caption** cell and `+ Add Exhibit` in Vehicle Storage (its description
    cell raises `+ Add Vehicle Storage` instead). Code:
    `bridge/formkit.py` `add_comparables()` / `ensure_exhibit_rows()`.
  Layer: bridge/ui. State: fixed for comparables and exhibits, in the MOD
  (2026-09-30); used by `bridge/casekit.py`.

### E-047 A photograph placed without being looked at
- Symptom: on a single-family case a living room was captioned Kitchen, a
  basement family room went in under a Level 1 category, and the
  air-conditioning condenser went in as the Deck. The owner caught all three.
- Cause: [C] the placer chose pictures by folder name ("first floor",
  "exterior") and by which slot was free. A folder says where a picture was
  taken, not what it shows, and no step compared a picture with the caption it
  was given.
- Fix: before any placement, build a labelled contact sheet of every picture
  (`PIL.ImageOps.exif_transpose`, no extra rotation), view it, and write a
  manifest row per picture stating what it shows, its section, category and
  description (`_work/rockland/photos.py EXHIBITS`). Categories come from the
  field's own `items`, read live -- Unit Interior offers `Level 1 - Kitchen`,
  `Level B1 - Family Room` etc. only after the room table exists. Every
  picture in the folder must appear in the manifest or be listed as excluded
  with a reason. Layer: intake/place. State: mechanism in case code; move the
  manifest step into intake.

### E-048 A pending comparable, and a driveway, each carry rows TOTAL forbids or requires
- Symptom: on a comparable with listing status Pending, field validation
  demanded "Sale price must be removed when listing status is Pending" and
  "Transfer terms must be removed"; on a comparable whose vehicle storage is
  Driveway, `VEHICLE_STORAGE` stayed "required based on related selections"
  although storage type and spaces were set.
- Cause: [C] TOTAL's sales-comp validators (bundle 3855). A pending sale must
  carry no `PR_SALEPR1` / `SALE_PRICE` / `TRANSFER_TERMS` -- the list price
  (`LP_PRICE`) stands for it. For `VEHICLE_STORAGE` the rule
  (`vehicleStorageRequiredCondition`, triggered on HidePopup = action 17)
  reads the spaces from `PU_VEHICLE_STORAGE_SPACES` for Driveway/Shared
  Driveway and from `..._SPACES_NUM` otherwise, and **requires
  `PU_VEHICLE_STORAGE_DETAILS` for garage, driveway, carport, open lot and
  parking garage** -- for a driveway the details are its surface material
  (the importer fills it from `ImprovedSurfaceMaterialType`).
- Fix: the generator leaves price and transfer terms empty on a Pending
  comparable and writes the driveway surface into details; the surface is
  read from the listing's photographs when the text does not state it.
  Layer: profile/generator. State: fixed on the case; add to the profile.

### E-049 Pick lists store the left half of "a^b"; a wrong half exports as something else
- Symptom: Hazard Zone written as `None` exported as `HazardZoneType=Other`,
  `HazardZoneTypeOtherDescription=None` (a hazard zone *named* None) on the
  subject and every comparable; UAD-1374 then asked for a Hazard Zones
  category "because the property is in a hazard zone".
- Cause: [C] option lists such as `No Hazard Zone Noted^None` and
  `Yes|None^No` pair a stored value (left) with a display text (right). The
  screen shows the right half; the exporter only recognises the left half.
- Fix: write the left half (`No Hazard Zone Noted`) -> exports
  `HazardZoneType=None`, as all 50 D-1 occurrences do. Read the field's
  `items` and split on `^` before writing. Layer: writer. State: fixed.

### E-050 Values written without their gate never reach the export
- Exposure time: `MarketingOrExposureDaysCount` exports only when the checkbox
  `PU_REC_REASONABLE_EXPOSURE_TIME_PRECISE = "X"` is set; the day count goes in
  `REC_REASONABLE_EXPOSURE_TIME_PRECISE`, not `REC_REASONABLE_EXPOSURE_TIME`
  (UAD-1746).
- Subject listing: `LISTING_INFORMATION` is exported only when `SLI_LISTINGS`
  is "yes"; writing a status such as "Off Market" for an unlisted subject
  *creates* a listing record (UAD-1204/1208, ListingType Other). For an
  unlisted subject: `SLI_LISTINGS = None`, `SLI_DATA_SOURCE` = the source
  searched (exported as the data source for "not listed"), and the empty
  listing-history row removed with the data set's own
  `RemoveFieldDataGroup("subj-listing-history-row", 0)` -- its two cells are
  otherwise always validated (no display rule hides them).
- Pending comparable: a sale date (`DT_SALTIM1`) on a Pending comparable
  creates a SALES_HISTORY with no amount (UAD-1439); a pending sale has no
  transfer -- leave it empty (see E-048).
- Room update status for kitchen/bath needs its timeframe too
  (`UI1_ROOM_TIME_FRAME`, UAD-1147).
- Layer: writer/profile. State: fixed on the case.

### E-051 TOTAL's UAD rules run only after field validation is zero
- Confirmed again: with 3 field-validation findings the E&O panel read "UAD
  Errors: 0"; the moment field validation reached 0 the same report read
  **18** UAD errors. A "UAD 0" is meaningless until field validation is 0.

### Where the single-family mechanisms live now (2026-09-30)
Every fix above that a single-family case needs is encoded once in the MOD,
so a new device does not relearn it: `total-bridge/bridge/casekit.py` (the
plan, its order, every field key), `formkit.py` (E-046 rows, E-049 pick
halves, events for E-048, formats for the UAD-1643 lesson, the neutral
section for UAD-1542), `adjust.py` (18 North, E-038 re-sum), `exhibits.py`
(E-047), `locmap.py` (UAD-1283), `certify.py` (E-035, E-051). Offline tests:
`total-bridge/tests/test_casekit.py`. A new error class is fixed there, with a
test, not in a case script.

### E-052 A machine-specific path makes the folder fail on any other device
- Symptom: `bridge/schema.py`, four engine spec scripts and three engine tests
  read `C:\3.6 uad zips\...`; on another device the schema check and the D-1
  tests would fail or skip silently.
- Fix: the specs ship in `specs/official/`; every reader resolves
  `UAD36_SPECS` → `<folder>/specs/official` → the old path; `setup/check.py`
  fails loudly if the specs are missing. Layer: portability. State: fixed.

### E-053 A 2-4 unit report: units in ONE building come from the setup panel's Multi-Family toggle
- Symptom: a new report is 1 building / 1 unit; "+ Living Unit" (single-family
  mode, earlier session) added a second *Dwelling*; importer collapsed units
  (Woodycrest, HANDOFF ~l.925).
- Mechanism (proven live 2026-10-01 on 1965 20th Dr, build 0.0.1.3886):
  `goto("report-setup")` -> click the **Multi-Family** half of the
  Single/Multi toggle (`label.report-setup-type-toggle`, checkbox
  `#report-type-toggle`) -> TOTAL makes Dwelling 1 with **2 units** -> the
  **copy icon on a unit row** adds a unit *in the same dwelling* (Units 3,
  Dwellings With Units 1) -> type dwelling/unit identifiers -> tick "Include
  Unit in Rent Schedule" -> **Save**. Detect then reads 1 building, 3 units,
  `interior-1..3`, `rental-information`, `income-approach`, UNIT_EXCL_ADU 3.
- Trap: the form runs at **90% zoom**. `getBoundingClientRect` is in CSS px;
  `Input.dispatchMouseEvent` wants viewport px = CSS x 0.9. `bridge/ui.click`
  (CSS rect) misses by 10% here -- the first toggle click landed on the panel
  body. Scale by the zoom or use screenshot coordinates.
- Layer: structure. State: proven by hand-driven script; to encode in the kit.

### E-054 Structural clicks miss: navigation that does not stick, smooth scroll, the HUD over the guidance panel
- Symptom (1965 20th Dr, 2026-10-01): the kit's "+ AMC", "+ Add Level",
  "+ Add Room" steps added nothing; `goto("interior-2")` showed Unit 1,
  `goto("site")` stayed on interior-2 (`currentActiveSectionKey` reset).
- Causes, each measured live:
  1. `Report.goto` set `currentActiveSectionKey` + `UpdateSectionVisibility` +
     `RefreshReport`; on this report the key was put back afterwards (engine's
     own focus/scroll handling). **Fix:** `goto` clicks TOTAL's navigation item
     `#nav-section-key-<key>` (what a person does), verifies the active key,
     and only then falls back to the engine calls with retries.
  2. `ui.where` read the rect right after `scrollIntoView`, but the nav list
     scrolls *smoothly* -> clicks landed 3-4 items lower. **Fix:**
     `behavior: 'instant'`.
  3. The bridge's own HUD (`#uad36-bridge-hud`, bridge/hud.py) floats over
     TOTAL's top-right guidance panel, where "+ Add ..." buttons appear.
     **Fix:** `ui.click` hides the HUD for the click and restores it.
  4. A table's "+ Add ..." guidance button exists only while a cell of that
     table has focus. **Fix:** `formkit.add_rows` focuses `[fn=<count_key>]`
     and retries when the button is not on screen.
  (and E-053's 90 % zoom: `ui.where` picks the centre that actually hits.)
- Test: live -- interior-1/2/3, site, sales-comp, reconciliation, assignment
  all land on the requested section; unit 2 rooms 1 -> 6, unit 1 levels 1 -> 2.
- Layer: MOD (ui.py, total.py, formkit.py). State: fixed.

### E-055 A block "cleared" with blanks is validated as required-but-empty
- Symptom (1965 20th Dr): with "Show All Field Validation" on, supervisor,
  SRPA, reconsideration-of-value, the site's easement/restriction/encroachment
  rows, parcel separators, water-influence type, comparables' native-lands /
  easement / drainage / water / outdoor-accessory rows, a listing's contract
  date, "other income" -- 80+ findings for things that do not exist.
- Cause: [C] `realTimeValidation.executeRtvRulesOnChildrenRecursively` returns
  early when `field.value == null` and validates a field holding "".  A data
  field's setter coerces null to "" (`value ?? ""`), so any write -- the kit's
  own "" for supervisor/SRPA levels, or TOTAL rendering a block once (the Order
  page) -- turns an untouched, skipped field into a validated empty one. The
  groups cannot be removed (repeatable minimum 1).
- Fix: `formkit.unset(report, keys, groups)` restores the untouched state on the
  backing `_value` (null); inside groups only blank leaves are touched, so real
  data is never wiped. Measured: survives TOTAL's ExecuteAllCalcs + global
  validation; 393 -> 364 (assignment/revision) -> site clean.
- Rule: use it ONLY for things that do not exist on this property. A blank
  field that should hold a value must be filled, never unset.
- Layer: MOD (formkit). State: fixed; to encode in casekit closing.

### E-056 Interior exhibit category reverts to the linked room on every calc pass
- Symptom: three living-room photos written as "Level n - Living Room" read
  "Level n - Kitchen" after any recalculation.
- Cause: [C] the category calc re-derives the value from
  `UNIT_INTERIOR_EXHIBIT_GUID_ID` (fallback `..._REQUIRED_GUID_ID`) -> the room
  row's `ROOM_ROW_ID`, pairing `field.items[i]` with `field.linkguids[i]`.
  The photos' links pointed at the Kitchen row.
- Fix: `exhibits.link_guid()`; `place_manifest` writes the GUID of the row its
  category names (from the field's own items/linkguids). Verified: categories
  hold after recalculation. Layer: MOD (exhibits). State: fixed.

### E-057 "- Remove Level" removes room rows too
- Symptom: trimming four blank level rows of unit 3 took its room rows 7 -> 1
  (levels 3/4 intact). Restored from case.json via the kit's unit step.
- Fix: `formkit.trim_rows(..., protect=[<room type key>])` raises the moment a
  protected count drops; trim levels BEFORE writing rooms, or not at all.
  Also: a direct `RemoveFieldDataGroup('level-details', i)` throws in the
  renderer and leaves a ghost row drawn -- use the guidance button.
- Layer: MOD (formkit). State: guarded.

### E-058 Below-grade access demanded on an above-grade level
- Symptom: "Below grade access type is required when below grade level exists"
  on unit 1's Level 1 row.
- Cause: [C] the rule reads `GetDataField("LEVEL_GRADE_TYPE")` with no
  instance -> row 0 only; with Level B1 in row 0 every level row is required.
- Fix: casekit lists above-grade levels first (stable sort); the basement row
  keeps its real access. Never write an access type on an above-grade level.
  Layer: MOD. State: fixed.

### E-059 Interior exhibits always need a category and a picture
- Cause: [C] `isExhibitFieldValid`: for UNIT_INTERIOR_EXHIBIT_PHOTO the
  category is required whenever a photo exists, description or not (the
  message says otherwise); an exhibit row with no image fails "A photo is
  required for this exhibit".
- Fix: (1) a feature that is not a room (in-unit washer/dryer) is recorded as
  the unit's "other" interior feature, which TOTAL then offers as a category
  (`units[n].other_features`); (2) a picture that was not taken gets a
  "PHOTOGRAPH NOT AVAILABLE / <room> / No photograph was taken of this room at
  inspection." card (`exhibits.not_available_card`, from `missing_photos`) --
  the owner's "label the exhibit without picture", in the only form TOTAL
  accepts. Layer: MOD. State: fixed.

### E-060 A 2-4 unit report's rental comparables are never written
- Symptom: on the 3-family at 1965 20th Dr every other section reached field
  validation 0 while Rental Information held **286** findings: 28 required
  cells in each of the 9 comparison columns (3 subject units x 3 rental
  comparables, `RC<u>.<k>_*`), 8 in each comparable record (`RP<k>_*`), and the
  subject units' own columns (`RS<n>_UNIT_VIEW`, `_GRADE_LEVEL`,
  `_PU_VEHICLE_STORAGE`).
- Cause: [K] `casekit.rent_schedule` wrote only each unit's lease
  (`RENT_SCH_*`, `RI_*`, `RS<n>_SMRY_*`). Nothing wrote the comparables, and the
  case file had no place to state them -- the previous session kept its rent
  research as prose in `rental.commentary`.
- Mechanism: `casekit.rental_comps` (in `plan()` after `rent_schedule`), driven
  by `rental.comps` (one record per comparable, with coordinates) and
  `rental.comparison[<unit>]` (per-unit overall, adjusted rent, weight, and the
  Superior/Similar/Inferior rows). Records are written before the grid; each
  column's header label is TOTAL's own pick-list form `#k^<address>, <unit>`;
  proximity is computed by `locmap.miles_and_bearing`, never typed.
  `rent_schedule` now also writes each subject unit's grade level, floor, view
  and car storage from facts the case already states.
- Proof: tests/test_rental_comps.py (7 tests: every key is an instance of
  TOTAL's `RCX_` template in build 0.0.1.3886; header form; computed proximity;
  per-unit comparison). Live: 286 -> 4 on 1965 20th DR (the 4 left are owner
  facts -- month-to-month x3 -- and one comparable photo behind bot checks).
- Trap: NYC rental listings rarely publish floor area, and the grid requires
  it. Use the listing's figure where published; otherwise the NYC PLUTO record
  (`data.cityofnewyork.us/resource/64uk-42ks`) residential area / units,
  stated as a building average on the handback. Condominium unit addresses may
  sit in PLUTO under the building's first address (8728 Bay 16 St -> 8726).

### E-061 A kitchen update word on a bathroom row fails the GSE schema
- Symptom: 12 XSD errors, `OverallBathroomsUpdateStatusTypeOtherDescription`.
- Cause: [C] the grid rates kitchens Fully/Partially/Not Updated but bathrooms
  Fully/Significantly/Moderately/Not Updated; TOTAL accepts "Partially Updated"
  on a bath row and exports it as an Other description the subschema rejects.
- Fix: `casekit.bath_update` maps it to "Moderately Updated" on every
  INT_COND_BATHS / OVERALL_UPD_STATUS_BATHS write. Test:
  `tests/test_rental_comps.py::test_bathroom_rows_use_the_bathroom_scale`.
  Layer: MOD. State: fixed.
- Also (E-060 addendum): a rent-grid column header must store the LEFT half
  of TOTAL's pick-list token ("#1", not "#1^42 Bay 25th St, 1"); the exporter
  links the column by the digits of the stored value, so the full token linked
  nothing and raised 21 UAD rental errors.

### E-062 Subject wall material never written (UAD-1080)
- Symptom: UAD-1080 at FV 0 -- WallMaterialType missing.
- Cause: [K] the dwelling step had no wall-material write; the rule fires for
  every dwelling whose owner maintains the exterior.
- Fix: case `subject.exterior_walls` (+ optional `exterior_walls_comment`) ->
  DE1_EXTEXTWALLS / DE1_EXT_FEAT_QUALITY_COMMENT in `casekit.dwelling`, taken
  from the viewed photographs. Test: `test_subject_wall_material_is_written...`.
  Layer: MOD. State: fixed.

### E-063 Multi-family adjustment profile; same-design row must stay blank
- Owner 2026-10-02: every 2-4 unit report adjusts on `adjust.MULTI_FAMILY`
  (GLA $150/sf >100 sf, site $20/sf >1,000 sf, age $250/yr >30 yr, bedroom
  $20k, full bath $20k, half $10k, semi-detached vs attached/detached $20k,
  cooling $20k, garage $20k/space, finished basement $40k, outdoor $20k,
  listing 2% of list). `casekit.profile(c)` picks it for any case with >1 unit.
- Trap: writing "$0" to DWELL_DESIGN_ADJ when the designs match -> FV "When
  subject and comparable characteristics are the same ... leave blank".
  Zero design lines are dropped from the table and nulled by comp_absent, both
  now judged by `design_of()` (structure design, else attachment).
- Reconciliation: case `reconciliation.summary` (short weighting reasons) ->
  value sentence -> "Adjustments:" line naming only the rows that moved a comp.
  Tests: `tests/test_multifamily_profile.py`. Layer: MOD. State: fixed.

### E-064 Bridge writes are lost when TOTAL reloads an unsaved report
- Symptom: next morning the live report held the PREVIOUS evening's older
  values (bath scale, rent headers, lease dates, wall material all reverted)
  although every write had been committed with rtv.put.
- Cause: [T] `engine.connector.SaveReport` / `SaveReportXml` only serialize the
  report and hand the XML to the WinTOTAL host; the save to disk is the host's
  action (the owner's Save). rtv.put persists to the open session only.
- Fix: none in the MOD (the bridge does not drive the desktop). After every
  working session the OWNER saves in WinTOTAL; a reload is recovered by
  re-running the kit's non-photo steps (`_work/bathbeach/run_reapply.py` is
  the pattern: dwelling, rent schedule, rental comps, grid, then adjustments +
  reconciliation last). Photos pasted directly in TOTAL are not on disk and
  cannot be recovered by the kit. Layer: process. State: open (owner action).

### E-065 REC_MARKET_VALUE is the reconciliation COMMENT, not an amount
- Symptom: exported ValuationReconciliationSummaryCommentDescription = "$1,825,000".
- Cause: [K] TOTAL maps REC_MARKET_VALUE (26.019, InputMultipage) to the
  reconciliation summary comment (UAD-1266, uid_map); the kit wrote money(value).
- Fix: `casekit.final_comment` -- short prose (approach relied on, approaches not
  developed and why, the concluded value); case may override with
  `reconciliation.final_comment`. Test: test_final_reconciliation_comment...
  Layer: MOD. State: fixed.
- Related trap (same session): a hidden 2-4 grid row (ATT_DET_ADJ) holding a
  value is left out of TOTAL's on-screen net but IS exported in the adjusted
  price -- after any outside edit, check the export's AdjustedSalesPriceAmount
  against the kit's nets, not just TOTAL's net row.

### E-066 The case kit had no condominium steps
- Symptom: a condo report (146 W 57th St 44C) could not be expressed as a
  case: project type, site owned in common, project information, floor /
  corner unit, high-rise floors, condo grid rows and the purchase contract
  were all missing from the kit (SF-only fixed answers such as CONDO_NO).
- Fix: case `project` {name, legal_structure, total_units, units_sold,
  units_for_sale, units_rented (None = unknown, not written), monthly_fee,
  amenities, special_assessment, commentary, ...}, `subject.unit /
  structure_design / floors_in_building / floor_number / corner_unit /
  site_owned_in_common`, comps `unit / project / same_project / monthly_fee /
  floor / corner`, and `contract` {price, date, terms, analysis, ...}.
  Steps `project_info`, `sales_contract`; condo branches in `subject_site`,
  `dwelling`, `interior`, `comp_rows`. Tests: `tests/test_condo.py`.
  Layer: MOD. State: written and unit-tested; steps 1-11 proven live on
  146 W 57th St (FV writes landed), steps 12+ not yet (E-067).

### E-067 Show/Hide pair written together hangs TOTAL
- Symptom: step "sales contract" (CHECK_SC_ENABLE = X and CHECK_SC_DISABLE =
  "" in ONE commit, with the contract fields) -> Runtime.evaluate no answer for
  minutes; the page ignored Page.reload; after Runtime.terminateExecution the
  whole WinTOTAL process closed (unsaved writes lost).
- Cause (most likely): the pair is radio-style (each handler clears the
  other); committing both at once ping-pongs. Same family as the Report Setup
  toggles that only answer to a click.
- Fix: `sales_contract` writes CHECK_SC_ENABLE alone, in its own step, never
  its partner (test enforces it). If a step ever hangs: STOP writing, poll a
  trivial evaluate; do not terminate scripts -- ask the owner to restart
  WinTOTAL. Layer: MOD. State: fix written, not yet proven live.
- E-067 update (same day, second run): CHECK_SC_ENABLE written ALONE through
  rtv.put froze the page again (step 12 of 146 W 57th St). The toggle is now a
  STRUCT step that clicks the rendered checkbox (`Report.set`), as the Report
  Setup toggles need. Not yet proven live.

### E-068 Saving: what does and does not persist the report
- `window.CefConnector` (the WinTOTAL host object bound into the page) has
  `save()`, `saveReportData(...)`, `signReport`, `reloadReport` ... Calling
  `CefConnector.save()` returns true but the `.zap` / `.bz1` / `.ztl` files under
  `Documents\a la mode\Reports\aci conversion files\` did NOT change -- it is
  not the save. `saveReportData` (likely the host receiving the serialized
  report) is untested. Never call signReport / removeSignature.
- Opening a report WITHOUT desktop control works: `WinTOTAL.exe "<path>.zap"`
  (Start-Process) opens it in the running WinTOTAL; a stale .LCK from a crash
  did not block it.
- casekit.run now calls `save()` after every step (harmless; keep until a
  proven save replaces it). Until then the OWNER's Save is the only proven one.
- E-067 cause (TOTAL code, bundle 3855 module 9850 + 7123): the sales-contract
  calc reacts to ANY change event on `SC_CONTRACT_NO` with
  `toogleShowHideOption(false); toogleSectionVisibility(false); resetContractData()`,
  and the GSU transfers (GSU_CONT_PRICE / GSU_CONT_DATE) listen to CHECK_SC_ENABLE,
  CHECK_SC_DISABLE, SC_CONTRACT_YES/NO, SC_ANALYZED_YES/NO. The kit's `_pair`
  wrote SC_CONTRACT_NO = "" -> reset -> toggles rewritten -> transfers -> ...
  Third freeze: 2026-10-02, step 13 after the toggle had been CLICKED fine.
  Rule: in the sales-contract section never write a "_NO" box or the toggle
  through the data layer; set each control on the rendered page (Report.set /
  pick), one field at a time, with a liveness check after each. The step is out
  of the automatic plan until that is proven live.

### E-069 Condo: what TOTAL demands once the unit is in a project (146 W 57th St)
- Site owned in common -> UI1_NON_RES_USE and UI1_LIVE_WORK_SPACE required.
- Interior exhibit categories are rooms / Flooring / Walls and Ceiling only:
  utility photos (thermostat, panel, intercom, fan-coil, door sign, detector)
  have no honest category -> excluded with the reason (E-059).
- Surplus exhibit rows: `formkit.trim_exhibit_rows` (focus row -> "- Remove
  Exhibit" guidance button); called by exhibits.place_manifest.
- No amenities: switch the section off by CLICKING CHECK_SUB_PROP_AMENITY_DISABLE
  (never a data-layer toggle write, E-067).
- Multi-select values are stored "a|b|c" (TOTAL's importer splits on "|"):
  PU_AMENITIES_SERVICES_INCLUDED, GC*_PROJ_AMENITIES.
- Grid: FLOOR_NUM_ADJ / CORNER_UNIT_ADJ / PROJINFO_OVERALL_ADJ need "$0" when
  subject and comparable differ (fee, name, amenities, assessment) and must be
  null when the same (`condo_differences`, comp_absent).
- StreetEasy is not an MLS: data source "Data Aggregator" (MLS demands a number).
- Project facts with no questionnaire (owner-approved estimates, disclosed):
  units rented (+ estimated flag + reason), single-entity units, commercial %,
  transfer fee: PU_UNIT_TRANSFER_FEES_DETAIL "None" + AMNT "$0" (the amount is
  numeric; "None" is cleared and the rule needs it filled), tax abatement None,
  line of credit No, association charge known "Yes".
- Result on 146 W 57th St: field validation 501 -> 1 (contract date, owner),
  schema 0, `bridge audit` clean. Layer: MOD. State: fixed (tests/test_condo.py).

### E-070 Report Setup panel: offsetParent is null inside it -> 8 units for 4; Cancel froze the page
- Symptom (601 Euclid Ave, 2026-10-02): `units_setup.set_units(r, 4)` read 0
  unit rows, kept pressing the copy icon -> 8 rows; Cancel then left the page
  unresponsive (Runtime.evaluate unanswered > 3 min; likely WinTOTAL's own
  confirm box behind the window). Nothing was saved.
- Cause: the setup panel is `position: fixed`; `offsetParent` is null for every
  element inside a fixed container, so an `offsetParent !== null` "visible" test
  reports nothing there. The loop had no "row count must grow" guard.
- Fix: visibility via `getClientRects().length > 0` in `ui.where/click_part/
  clear/type_into` and `units_setup`; `set_units` stops if a copy click adds no
  row or no rows are found. Never press Cancel on a setup panel from the
  bridge: re-open and correct instead.
- Layer: MOD (ui.py, units_setup.py). State: fixed; live rerun pending.

### E-071 A row told apart by its label printed the first block's values (Exterior Features, Utilities)
- Symptom (D-1 SF1 vs our page): every row of the Exterior Features table
  printed the wall's condition comment ("Minor cracks to vinyl typical for
  age."); Detail was blank for Walls and Windows; the Utilities table printed
  the water comment against Electricity and Gas (D-1 MH1). Wrong data on a
  signed report, not a layout slip.
- Cause: four rows (Walls, Foundation, Roof, Windows) share one Report Field ID
  (8.041, ImprovementComponentType) because MISMO keeps them as four
  STRUCTURE_COMPONENTs of one STRUCTURE_COMPONENTS and A-1 numbers fields by
  row, not by repeat. The row label picks the row, but the reader took the
  ordinal-1 block only, so rows 2..n found no block to select and fell back to
  "every instance" -- the single comment it had read. Cells also sit at
  different depths of the block (wall material under EXTERIOR_WALL, comment
  under STRUCTURE_COMPONENT_DETAIL), so matching by depth lost the Detail.
- Fix: `form._label_blocks` resolves a fixed row label to every block that
  holds it (the same two tests a label always had to pass), and each cell of
  the row is read from inside that block (`row_instances`). A label that is
  itself one of the field's values with no block ("Electricity", no
  electricity) holds nothing (`_names_a_value`); a label that is not
  ("Property Restriction" for A-1's "Property Restrictions") keeps the old
  per-cell marks -- guarded by a test. B-1 p.140: Electricity, Sanitary Sewer
  and Water always display as row headers -- NOT yet implemented (an empty
  Electricity row is dropped), see TASKS.
- Test: `engine/tests/test_report_rows.py` (5 of its 7 fail on the old code).
- Layer: model/render. State: general. Related, still open: the Unit Interior
  tables (Level and Room Detail, Kitchen and Bathroom Details, Interior
  Features) read the same way and are wrong the same way.

### E-072 C-1's PDF clips a few Report Field IDs; the extractor kept the clipped text
- Symptom: Electricity's row had no binding at all ("4.06"), so E-071's
  fallback printed the water comment against it; `a1_only` listed 4.009 and
  20.009 as "unplaced" and printed "Classification Code" and "Total Sales
  Concessions" a second time at the end of their sections.
- Cause: where a table runs to the page edge C-1's text layer holds "4.0"
  and the extractor completed it wrongly ("4.06" for 4.069, "4.05" for 4.058,
  "4.00" for 4.009, "20.00" for 20.009).
- Fix: `form._complete_clipped_ids` completes a clipped ID only when the answer
  is unique -- the one A-1 ID with that prefix filed under the same label, or,
  for a table row's first cell, the ID just before the row's next cell
  (4.070 follows 4.069). Applied when the form is loaded (`form.form()`), and
  `a1_only` / `coverage.c1_placements` read the repaired form.
- Test: `test_report_rows.py` (the four completions, and that none is left).
- Layer: spec extraction. State: general.

### E-073 Grid cells composed in the wrong order, with the wrong separator, unit or digits
- Symptom (ours vs D-1 MH2/SF1 grids): `Asphalt Local Road` for `Local Road |
  Asphalt`; `Electric Heat Pump`; `2 0` for `2 | 0`; `Driveway Pavers 4` for
  `Driveway | 4 | Pavers`; `SE 3.00` for `3 Miles SE`; `Porch | Deck` for
  `Deck | Porch`; the street and town of an address run together; only the
  first vehicle storage printed (no Garage line).
- Cause: different data points under one label were joined with spaces in the
  order A-1 lists them; the linear unit attribute was ignored; A-1's numeric
  precision "+3.2" was applied as a fixed width; instances of one enumerated
  data point kept the XML order; a grid cell read only the first instance of its
  block; the grid's HTML dropped the line breaks the text carried.
- Fix: `bind.COMPOSITES` -- each composite cell with its order, separator, "stack"
  flag and the B-1 / grid-supplement sentence it comes from; `bind.with_unit`
  (areas and distances: "3 Miles", "0.40 Miles", ".5" -> "0.5", never singular);
  Numeric prints the XML's own digits; values (and instances) of one enumerated
  data point list in A-1's enumeration order (alphabetical order would not give
  "8 Ft. | 9 Ft. | 10 or more feet"); `comparables._read` reads every instance of a
  stacked cell; `comparables._esc` keeps line breaks.
- NOT fixable as a rule: the order of `Assessor Record | MLS 124523` -- the 12
  samples disagree with each other for XML of identical structure (condo1 vs
  condo2, sf2 vs sf4) and B-1 states none. Left as the document order.
- Test: `test_report_rows.py` (composite, unit, order tests). Layer: render.
  State: general.

### E-074 A block's display rule lives on its heading; the extractor lost it; the block printed in every report
- Symptom: the Supervisory Appraiser certifications (a second full page of
  certification text) printed in all 12 samples; D-1 prints them only in MH1 and
  the 2-4 unit sample.
- Cause: B-1 p396 states the rule once, on the block's heading (29.054 "Display
  when PartyRoleType = AppraiserSupervisor"); the paragraphs under it carry
  none. The extractor takes the field-ID column from the column with most IDs and
  that table sets 29.054's ID one column over, so the row and its rule were
  dropped.
- Fix: `extract_display_rules.py` takes a lone ID from an unnamed column when the
  ID column is empty (regenerated display_rules.json / field_index.json: 29.054
  added, nothing else changed). `form._anchor_gate`: a margin slot that decides
  sets the state for its block; slots with no rule of their own inherit a hidden
  state.
- Test: all 12 samples -- our report contains the Supervisory certifications
  exactly when the official PDF does. Layer: spec extraction / render.

### E-075 Every empty comparable-grid cell printed an em-dash; rows judged per block; subject values missing
- Symptom: 2-6x the dashes of the official report; Contract Price / Contract
  Date rows (subject price, dashes for the comparables) missing; a row that
  only a fourth comparable has was absent from the first block.
- Cause: `html()` printed a dash for any empty cell. B-1's supplement gives each
  row "Display Em-Dash for Subject / Comp when ..." (mostly "Never display
  dash"). `GridRow.rules` read the label column ("Row Display Rules") instead of
  the rules column, so "Subject: Display if ..." was never seen and the subject
  FID of Contract Price / Date (N/A in the workbook, 22.01.04 / 22.01.06 in A-1)
  was never filled. Row visibility was decided per block of three comparables.
- Fix: `report/dashes.py` executes the sentences (data point =/<>/>/number, "an
  instance of X is not provided", "for all instances of", the column-wise prose,
  AND/OR); `comparables._attach_dash_sentences` pairs them with the rows by
  order; `_fill_subject_fids`; the rules column fixed; visibility judged over all
  comparables; the Not Used table uses the same sentences. `<>` on a data point
  that is not there is true.
- Evidence: grid dashes now equal the official count exactly on condo2, coop1,
  sf5 and 2-4 unit scenario 2 (was 2-6x over everywhere). Remaining differences
  are the outbuilding rows (T-123).
- Test: `test_report_rows.py`. Layer: render. State: general.

### E-076 A whole address typed into a report address field is refused
- Symptom: typing "186 8th St # 2B, Brooklyn, NY 11215" into Physical Address
  (3.000) answers 422 "could not be saved to its matching report field".
- Cause: a plain value went to the field's write target, chosen as "the
  enumerated data point" — for an address that is AddressUnitDesignatorType,
  which A-1 allows to hold only "Unit"; the read-back of a whole address in
  that slot failed. Every address field (subject, alternate, parties) had it.
- Fix: `edit.is_address` / `edit.split_address` store a whole typed address as
  its A-1 parts (street, unit designator + identifier, city, state, ZIP); "#",
  "Apt", "Suite" become the spec's one designator "Unit"; a plain value that
  is not a whole address goes to AddressLineText, never to the designator.
  Layer: model. State: general.
- Test: `engine/tests/test_address_entry.py` (owner's case, 9 checks: parts,
  unit removal, coordinates on the map pin, 0 schema errors).

### E-077 Every new blank report is blocked: "comparables are not numbered 1..n"
- Symptom: a blank case's sign-off and export list "The comparables are not
  numbered 1..n in the order the report prints them. (found ['', '', ''])".
- Cause: `templates.clear` kept only determinants and identity types; the
  comparables' `PropertyOrdinalNumber` (the column each occupies) was removed
  as if it were the sample's answer.
- Fix: `PropertyOrdinalNumber` is part of `templates.IDENTITY` — structure,
  kept in a blank. Layer: model. State: general.
- Test: all 12 blank templates: no COMP-NUMBERING blocker, 0 schema errors
  (`engine/tests/test_browser_scripts.py` covers the dialogs that show it;
  the check itself is `uad/integrity.py` COMP-NUMBERING).

### E-078 Level and Room Detail prints only the first level, data in the wrong rows
- Symptom: SF1's Unit Interior table showed "Level B1 | Interior and Exterior
  Access Walk Out | | 1,300 Sq. Ft. 230 Sq. Ft. |" then Level 1 and Level 2
  empty, and room names on blank lines; the published PDF has one row per
  level with Finished / Unfinished lines and "1 - Bath - Half" counts. The
  editor's Finish cells (C-1 10.031) answered 404: A-1 has no row for it.
- Cause: the generic table reader walks a field's first block only
  (`form._walk` / `bind._walk` ordinal 1) and pairs columns by position;
  10.031 is not a data point but a display of which area (finished /
  unfinished) the line carries (B-1 p195).
- Fix: `form._levels_table_html`, from B-1 10.029-10.033: every LEVEL, lowest
  grade first (`level_rank`); Grade, then AccessType when below grade, then
  BelowGradeExteriorAccessType when the access is from outside; a "Finished" /
  "Unfinished" line only when that area > 0 (both shown in the editor so they
  can be typed), each area cell writing its own data point (`_cell(point=)`);
  the room summary counted per RoomType per LevelType from the sibling ROOMS.
  Layer: render. State: general.
- Test: `engine/tests/test_level_table.py` — SF1 row by row, and every cell
  printed for all 12 samples found in the published PDF (12/12).

### E-079 A plural name is not a repeat: a second SALES_CONTRACT the schema refuses
- Symptom (owner's section test B1): on a blank SF / Condo / 2-4 report, after
  "Is there a sales contract? = Yes", Contract Price, Date, Sale Type and the
  non-arm's-length comment answer 422 "Element 'SALES_CONTRACT': This element
  is not expected. Expected is (EXTENSION)". No purchase could be entered.
- Cause: A-1 conditions the price on `SalesContractReviewedIndicator = true`;
  `edit.instance_for` treats a condition under a repeating block as "find the
  instance with that value, or add one", and judged SALES_CONTRACTS/
  SALES_CONTRACT repeating from its plural name. The GSE subschema allows one.
- Fix: `xsd_order.max_occurs` (from the XSD, cached in `spec/xsd_max.json`);
  `edit._plural` answers no when the schema allows one, so the condition is a
  gate on the single block. Layer: model. State: general.
- Test: `engine/tests/test_blank_writes.py` (all 12 blank templates).

### E-080 An element typed by another name has no child order (alternate address)
- Symptom (B8): 3.001 Alternate Physical Address refused on every type
  ("PostalCode: This element is not expected").
- Cause: the order table assumed every complexType is named after its element;
  ADDITIONAL_ADDRESS is typed ADDRESS, so its children were appended in typing
  order.
- Fix: `xsd_order._aliases` maps element -> type where they differ; the order,
  required, choice and max tables all carry the alias (adds ADDITIONAL_ADDRESS
  and PROJECT_CONVERSION; no existing entry changed). Layer: model. State: general.
- Test: `engine/tests/test_blank_writes.py`.

### E-081 Date of Signature refused on SF and 2-4 (arcrole, and a third SIGNATORY)
- Symptom (B9): 29.066 answers "RELATIONSHIP @arcrole enumeration" on SF; on
  2-4, "SIGNATORY is not expected".
- Cause: the writer hard-coded `{container}_CompletedBy_ROLE`; the schema's
  arcrole for SIGNATORY -> ROLE is IsAssociatedWith. And a blank drops the
  sample's parties but keeps SIGNATORY_Appraiser, so the writer found no
  signatory linked to the appraiser and added a third (the subschema allows two).
- Fix: `xsd_order.arcrole(source, target)` from the GSE xlink schema
  (`spec/xsd_arcroles.json`); `edit._related_instance` reuses an orphaned block
  (same label, or the only one left when the schema is full) and retargets its
  existing relationship. Also: an empty PARTY is falsy in lxml, so
  `_role_of_type` tests identity. Layer: model. State: general.
- Test: `engine/tests/test_blank_writes.py`.

### E-082 An answered Yes/No looks unanswered; choices read "<<Does Not Display>>"
- Symptom (B7): 10 of 47 Yes/No fields show blank after "Yes"; their lists
  offer "<<Does Not Display>>" and "None".
- Cause: B-1 prints nothing for some answers (the detail rows print instead);
  that print marker was used as the editor's label and value.
- Fix: `bind.answer_label` -- a `<<...>>` marker is a print rule, not a label;
  a Boolean is Yes / No. Used by `/fields` (`value`; `printed` keeps what the
  report prints), the option lists and the report-frame pickers. The printed
  report is unchanged. Layer: UI. State: general.
- Test: `test_blank_writes.py::test_every_yes_no_answer_reads_as_answered`.

### E-083 The sales grid's totals were never computed (B4)
- Symptom: with a sale price and adjustments entered, Net Adjustment Total,
  Adjusted Price and the per-unit / bedroom / area prices stay empty in the
  XML (H-1 UAD1456, UAD1460, UAD1461).
- Fix: `uad/grid_math.py`, each formula from A-1's Implementation Notes;
  `Store.save_tree` recomputes on every edit from every route (not on import,
  which is taken as it is). Validated first on the samples: all 141 delivered
  totals reproduced exactly, none computed where a sample has none.
  Layer: model. State: general.
- Test: `engine/tests/test_grid_math.py` (12 samples + a blank report).

### E-084 Every new report waited for a full layout pass
- Symptom: "New report" showed "Laying out the report in this browser..." for
  several seconds (25 s cold with the server's Chromium), every time.
- Cause: a layout was cached per case, but every new report is a new case --
  while its content (and so its render key) is identical every time.
- Fix: `app/layouts.py` keeps finished layouts by content key, case-neutral, in
  memory and the shared store (Vercel Blob / shared dir) or the work folder;
  `_rendered` serves one at once. A layout is stored when the server lays it out
  (renders `on_rendered`) or when the browser's final pass fits every page
  (`POST .../layout/{kind}/keep`; the server rebuilds the page from the same
  measurements -- never stores browser HTML). The launcher warms the hidden
  warm-up report (`POST /api/warm`, never listed) in the background.
  Measured (client-layout mode, shared dir): warm-up 3.4 s while the list is on
  screen; New report on screen in 0.36-0.87 s, also from another browser.
  Layer: app. State: general.
- Test: `engine/tests/test_one_report.py::test_a_new_report_opens_from_the_shared_layout`.

### E-085 A report had to be started from a chosen sample "form"
- Symptom: the launcher offered 12 sample templates (New blank / Open sample);
  a property that changed type mid-report could not change its report.
- Fix (owner's instruction 2026-10-05: one report, no form types): one "New
  report" (POST /api/cases needs no template; api.NEW_REPORT); `uad/shape.py`
  rebuilds the report when a determining answer (units, ADUs, project legal
  structure, construction method, attachment) changes the property type, on the
  closest D-1 structure, carrying every value by address (autofill.plan/apply);
  the editor reloads and says so; sections the report does not print are not
  offered in the rail. Every D-1 shape is the best match for its own answers.
  Known limit: a unit count no sample has (3 units) takes the 4-unit structure
  until the structure engine (T-1035) makes the count exact.
  Layer: model + UI. State: general.
- Test: `engine/tests/test_one_report.py` (condo, co-op, 2 and 4 units, ADU;
  values kept; no reshape when the shape does not change).

### E-086 Units and ADUs were numbers, not structure (owner's test B2/B3)
- Symptom: 3.005 = 3 wrote "3" and left 2 PROPERTY_UNITs; 3.006 = 1 created no
  ADU; nothing could add a unit, dwelling, ADU or outbuilding.
- Fix: the structure engine in `uad/structure.py` (tree, add_unit,
  add_dwelling, add_outbuilding [ADU in it], remove, set_units, set_adus,
  recount, tidy, prune_dangling) per F-1 3.005-3.007 / 8.000 / 10.002 / 10.011
  and B-1's section table. Counts are read from the tree; identifiers are made
  unique; every sales comparable of a multi-unit subject gets one unit row per
  subject unit, linked PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT (as both
  2-4 samples); removal takes the comparable rows, rental comparisons and
  defects that only that unit explained, and `loss` lists what goes first
  (typed counts answer 409 with the list until confirmed). API:
  GET/POST/DELETE /api/cases/{id}/structure, GET .../structure/loss; editor tab
  "Property". Blanks now keep AccessoryDwellingUnitIndicator and OutbuildingType
  (a blank SF4 counted its ADU as a living unit). Layer: model. State: general.
- Test: `engine/tests/test_structure_engine.py` -- every one of the 12 D-1
  structures rebuilt from a new report through the API (dwellings, units per
  dwelling, ADUs, outbuildings, counts), comparable unit rows linked, loss
  shown before removal, last unit/dwelling kept. Chromium: Property tab adds a
  unit and a standalone-ADU outbuilding; the report gains "Unit Interior -
  Building 1 - Unit 2" and an Outbuilding section.

### E-087 Sections that do not apply were offered (owner's test B14)
- Symptom: a site-built house showed Manufactured Home, Income Approach and a
  comparables' Outbuilding; spec/section_rules.json held each chapter's first
  sentence, which for several sections is a description, not the rule.
- Fix: `uad/spec/extract_section_display.py` -> `spec/section_display.json`,
  B-1's own "the section displays when ..." sentences per chapter;
  `form.section_shown` evaluates them on the subject when the data points are
  the subject's, keeps a section whose switch is unanswered, and reads the
  Manufactured Home trigger B-1 gives in bullets (ConstructionMethodType =
  Manufactured, p182). Sections whose own questions switch them on stay in the
  editor. Blanks keep the approach indicators (they decide the shape).
- Test: `engine/tests/test_section_display.py` -- Rental Information, Income
  Approach, Cost Approach, outbuildings, PUD/project and manufactured home on
  every sample equal the GSE's D-1 Sample Scenario Matrix (12/12).

### E-088 A shared layout could carry browser-sent markup
- Found while building E-084: MEASURE_JS returns each block's HTML, and pages
  were assembled from it; a layout kept for other reports would have held what
  a browser sent, and a case changing during "keep" stored a 6-page layout.
- Fix: `flow.skeleton` / `flow.trusted` -- the server's own galley supplies
  every block's markup; only heights and offsets come from the browser; block,
  item and row counts must agree or nothing is kept; the key is checked again
  after building. Test: `test_one_report.py::test_a_shared_layout_takes_only_numbers_from_the_browser`.

### E-089 B-2 / D-2 disagree on the Supervisory Appraiser Certifications
- B-2 p49 says the subsection "always displays"; the official D-2 AU1 (no
  supervisor) omits it, as B-1 29.054 does for the URAR. Decision: print it
  only when a party has PartyRoleType = AppraiserSupervisor (form._section,
  `gate`). Test: test_report_types.py (AU1 prints nothing the PDF does not).

### E-090 Rule sentences broken or misspelled by the guides' PDFs
- Narrow table cells split names ("ValuationReportInspectionCertificat
  ionType", 11 such in B-1 too, e.g. 9.012) and the guides misspell some
  ("PersonalInspectoinPerformedIndicator" B-3, "Conditoinal" B-3, "Atatched"
  B-1), so the rule named nothing and decided nothing.
- Fix: `rules.rejoin` joins two words when together they are a defined data
  point; `rules.spelled` corrects a name to the one defined name a swap or one
  letter away. Harness 87/0/21 unchanged. Test:
  test_report_types.py::test_a_rule_names_the_data_point_the_guide_broke_or_misspelled.

### E-091 Alternatives of one certification share one field ID
- B-2/B-3 give #10's three alternatives (interior+exterior / exterior / none),
  #13 and #15 one field ID and one sentence each; the extractor dropped the one
  that continues over a page break, and all alternatives printed.
- Fix: `extract_display_rules.extract(carry=True)` (B-2/B-3 only; on B-1 it
  attaches unrelated text, so B-1 is unchanged) keeps a leading field-less
  "Display ..." row with the row before the break; form counts repeats of a
  certification number (or paragraphs after a slot) and takes the n-th
  sentence; a line takes the slot beside it (C-2/C-3 set the slot 1pt below).

### E-092 A table column read only its first block
- `bind.scope_for(..., ordinal=1)` and `_walk_marked` pick the ordinal-th
  instance (A-1: one field ID per repeat). C-3's repair tables give one field
  ID per column, so a second repair vanished and "Other" location read the
  first defect's description.
- Fix: for namespaced IDs `form._walk` visits every block; a row's identity
  (CompletionReportNewDefectIndicator) becomes `entry["instance"]`, filtering
  rows; value conditions (Location = Other) are left to the display.

### E-093 Deriving a report wrote parties field by field
- A second borrower's name landed in whichever party the blank held at that
  ordinal. Fix: `report_types._carry_parties` copies the borrower / client /
  lender / AMC PARTY blocks whole and drops relationships left pointing
  nowhere (and an emptied RELATIONSHIPS). Test: derived documents are
  schema-valid (test_report_types.py).

### E-094 A section was numbered by the URAR's titles
- "Subject Property" is URAR section 3 but update section 1; the update's own
  sections had no number, so the rail, the reviewed-sections gate and the
  editor's section stamps were wrong. Fix: `form.section_number(printed, kind)`
  / `report_types.section_number`; `flow.Meta.kind` feeds the stamps; the gate
  names the kind's own sections.

### E-095 C-3's Completion Status read as one check
- The extractor merged two Yes/No questions into one check with both IDs, put
  "specifications?" into the table header and all four row IDs into one cell.
  Fix: `build_report_types._repair` splits by shape (bold "?" head over a
  two-ID check; a "?"-ended head prefix; a row whose one cell holds one ID per
  column), and restores the Yes/No header C-3 draws.

### E-096 Signature block printed the Layout's placeholders
- "[Role]" / "[Contact Name]" and the date slot printed as loose rows (URAR
  too). Fix: `form._signature_html` composes role, name over a rule with the
  date, the caption, and the licence rows, in print view; the editor keeps its
  controls. A font-size with no kerned family (11pt) or italic with no italic
  face embeds a system font -- the harness fonts check caught both.

### E-097 A forced page break printed the previous section's "(continued)" tab
- `flow.plan` placed the keep-with-next break before the forced one. Fix: the
  forced break runs first and never continues the section before.

### E-098 URAR certifications printed every alternative and dropped the supervisor's
- SF1 printed both #29 prior-services versions, all three #10 inspection
  versions and the FHA/USDA/VA intended users; MH1 and 2-4 dropped the
  supervisory block. Causes: B-1 states each alternative as its own sentence
  under one field ID; the alternative counter carried from #29 into the next
  block; a quoted value broken by the PDF ("...Apprai salAssistance"); the
  second alternative of #21 has no sentence of its own in B-1.
- Fix: the kinds' paragraph mechanism now runs for the URAR (number repeats ->
  n-th sentence; a missing sentence is the "otherwise" case; counters reset at
  each heading and slot); `rules.rejoin` mends quoted enumeration values from
  `values()` (A-1 enumerations sheet incl. Does Not Display); assistant names
  go into #21 where C-1's [Contact Name(s)] sits.
- Conflict left as C-1 prints it: Intended User "this report" (C-1, 10/12
  samples) vs "this appraisal report" (B-1 v1.4 29.008, 2 samples).
- Test: tests/test_certifications.py (12/12 samples, both directions).

### E-099 Exhibit cells were not D-1's geometry
- D-1 (19 photos in SF1) and D-3 draw 270pt x 200pt cells sharing one rule,
  caption 13pt under the top, photo 258 x 166 inset 6pt; ours were 264pt with a
  12pt gap and a flexible photo. Fix: `.ex` geometry in form.stylesheet.

### E-100 A new Completion Report table row belonged to no table
- The empty line under "New Observed Items for Repair" made a DEFECT without
  CompletionReportNewDefectIndicator, so it showed in both tables. Fix:
  `report_types.stamp_instance` writes the row identity (entry["instance"],
  "true" for 04 from A-3, "false" for 03 from B-3 p21) into the new block.
  Test: test_report_types.py::test_a_new_row_in_a_completion_table_belongs_to_that_table.

### E-101 Rooms could not be added to a level (owner request)
- The Level and Room Detail table printed the room summary as fixed text; an
  appraiser could add a level but not a room, and could not remove a level.
- Fix: `uad/rooms.py` (add / remove a ROOM on a LEVEL, remove a level with
  its rooms, recount Levels in Unit / Total Bedrooms / Bathrooms from the
  unit's own levels and rooms -- B-1 Usability item 8, as D-1 keeps them
  equal); `/api/cases/{id}/rooms` (POST, DELETE) and `/levels` (DELETE);
  editor: - / + per summary line, "+ Add room" (A-1 10.033's 19 types, Other
  asks its description), x on a level. Tests: tests/test_rooms.py (7) and a
  Chromium click-through (Bedroom added on Level 2 -> Total Bedrooms 5 -> 6).


### E-102 Kitchen/bath and Interior Features tables read only the first block
- The K&B table (10.034-10.043) printed one row and the Wet Bar amenity; the
  Interior Features table (10.044-10.049) printed one flooring. B-1: "each
  flooring type displays on a separate row"; K&B rows are each Kitchen /
  Full / Half bath ROOM, Time Frame only when Fully/Partially Updated.
- Fix: dedicated drawers in form.py (`_kitchen_bath_table_html`,
  `_interior_features_table_html`) that walk every block (`_walk(every=True)`,
  `instances(..., every=True)`); editor "+ Add flooring" and x per floor row
  (`rooms.add_flooring`, `/flooring`, `DELETE /rows`). Test: test_rooms.py.

### E-103 A typed Area Data Source vanished
- A-1 ties DATA_SOURCE to its target by a DATA_SOURCE_IsDataSourceFor_<T>
  relationship; the reader took the first DATA_SOURCE, the writer wrote one
  with no link, so it read back as nothing on any unit the template had not
  pre-linked. Fix: `form.data_source_target` reads the target from B-1's rule
  text; `uad/sources.py` writes / removes the source and its link;
  `edit.write` routes such fields there. Test: test_rooms.py (data source).

### E-104 Unit interior defects missing (SF1, Condo1, 2-4 per unit)
- Defect tables in the template-row path were read inside the unit scope,
  first block only. Fix: read at PROPERTY level, every DEFECT, filtered by
  its DEFECT_ContainsDefectOf_* link.

### E-105 Zero rows, numeric rules and per-field "Display when" rules
- `_is_zero` failed on "Sq. Ft." values; numeric comparators in B-1 rules
  (`>`, `<`, `>=`, `<=`) were not parsed (the empty-match alternative came
  first). `field_rule_hides` now applies a field's own display rule to check
  and row items in print view, skipping inverse "do not display" rules and
  "@attribute" conditions and truncating trailing notes (" - ", "Note:",
  "(Figure", ". "). Validated: across the 12 D-1 samples it hides only 3.007
  where the official PDFs omit it.

### E-106 Exhibit captions named the photo, not what it shows
- B-1: an exhibit's title comes from its owning block (ROOM, INTERIOR_COMPONENT,
  DEFECT, CAR_STORAGE, AMENITY). Fix: `form._owner_title` + `enum_label`.

### E-107 Two regexes held literal backspace characters instead of \b
- `bind.commentary_categories` and `form._agency_ok` were written with a
  raw 0x08 byte where `\b` was meant, so neither ever matched: Site
  Influence / View / Water Frontage / Project Factors / Sketch commentary
  had no category (never printed), and the FHA/USDA/VA certification gate
  was a no-op. Fix: `\b` restored; B-1's misspelt category
  "EnergyEfficiencyAndGreenFeatures" mended to A-1's enumeration.
  Lesson: grep the tree for control bytes (`grep -rlP "\x08" --include=*.py`).
  Test: tests/test_site_and_defects.py.

### E-108 Site Influence Proximity / Impact printed blank
- 4.026 / 4.028 gather data points from ENVIRONMENTAL_CONDITION,
  BODY_OF_WATER and SITE_INFLUENCE; the list reader only looked for the
  first (principal) one. Fix: when the principal has no blocks, every
  block of each other kind is read (`form._walk`). 2-4: "Busy Roadway |
  Bordering | Adverse" as D-1 prints it.

### E-109 Template-row tables read only the first block
- A table whose template row is one field ID per column printed one row
  (2-4 Scenario 2 lost "Residential"). Fix: template rows read every block
  (`instances(every=True)`), limited to the subject's own blocks when the
  field is the subject's (a comparable's SITE_INFLUENCE / DATA_SOURCE is
  not a row of it).

### E-110 Summary / Reconciliation defect tables were not grouped by structure
- B-1 p377: Site; each Dwelling Exterior then its Unit Interiors; each
  Outbuilding then its ADUs; Vehicle Storage; Amenities. C-1 draws one bar
  per kind with [Structure Identifier] / [Unit Identifier]. Fix:
  `form._defect_groups` expands the bars per structure / unit using the
  sections' own titles (`section_instances`), each read inside its scope.
  Rows list by Feature then Location in print (all D-1 samples; B-1 states
  no order -- recorded as sample-derived). Matches 2-4, SF1, Condo1, MH1.

### E-111 Corner Unit printed nothing for "false"
- A-1 gives CornerUnitIndicator "false" a blank display; every condo / co-op
  D-1 prints "No". Fix: `bind.FALSE_PRINTS_NO` (only that indicator: a
  broader rule turned SalesContractExistsIndicator into "No" and put the
  Sales Contract section into five reports the official PDFs omit it from --
  caught by test_golden).

### E-112 Dwelling Exterior exhibits empty; defect photos never printed
- Photos kept at property level (PROPERTY/INSPECTIONS/.../IMAGE) were filtered
  out of each scoped section copy; A-1 has no IMAGE -> IMPROVEMENT link. D-1
  2-4 holds two DwellingRear images and prints one per building, so
  `form._positional_image` gives the n-th to the n-th copy (single -> first).
  Defect photos (owner DEFECT, no category) go to the section of what the
  defect's DEFECT_ContainsDefectOf_* link points at (`_defect_section`).
  Title "Lead - Caption" printed once; category + caption joined with " - "
  ("Property Access (Street Scene) - East", D-1 Condo2).

### E-113 Several buildings: sections out of order
- D-1 2-4 prints Building 1, its Unit 1, Building 2, its Unit 2; we printed
  both buildings first. `form.build` interleaves each dwelling's units after
  it when there is more than one dwelling (B-1 p377 gives the same order).

### E-114 Component rows and Room Summary
- Fixed-label rows read only the first block inside the component: two
  EXTERIOR_WALLs printed "Brick" not "Brick | Wood" (SF2, SF5, MH2, 2-4 S2).
  Fix: `instances(..., every=True)` per row block.
- Noncontinuous area Room Summary printed "Family Room 1"; B-1 p175 "Count -
  Room Type, not when zero" -> `bind.display_value` composes TotalRoomCount +
  RoomType generically.

### E-115 Market "Graph" listed every photo category
- 17.017 is ImageCategoryType alone; it read every IMAGE. B-1: the graphs
  listed in Market Exhibits. Fix: `_graph_categories` keeps categories filed
  under the field's own section. SF1 now prints exactly its four graphs.

### E-116 Rules read inside a unit could not see the project's facts
- `rules.values_of` searched only the scope: 10.026 (gated on the project's
  LandOwnedInCommonIndicator) read false inside a unit, hiding "Non-Residential
  Use in Unit No" (Condo1, Coop1). Fix: when the scope lacks the name, the
  nearest ancestor that has it answers, never a sibling unit's copy.
- `field_rule_hides` skipped any rule containing "do not display" anywhere --
  10.011's trailing "When ... = 0 checkboxes do not display" -- and could not
  read "Display checkboxes on each instance ... when". Now the condition is cut
  first and the prefix normalised. It also applies to template-row tables
  (10.050 Accessibility, 27.000 Revision, 26.014, 8.041 Foundation, 10.056).
- Validated on all 12 D-1 samples (scratchpad hidden.py): every field it hides
  is absent from exactly those official PDFs (ADU 10/12, Accessibility 11/12,
  Ground Rent SF1/SF2, Foundation Condo1/Coop1, Revision table 10/12).

### E-117 Subject Property Amenities table printed categories in one cell, no Detail
- The C-1 template row's category column (14.001) is not delivered; the generic
  reader paired nothing. Fix: `form._amenities_table_html`: category from B-1's
  14.002 lists (Other -> Miscellaneous), groups in B-1's order, category once
  per group, a repeated name once (D-1 SF3 / MH1 "Deck" then blank), Detail
  composed per 14.004 (area + unit, "Total Number - n", pool features "|",
  "(Not) Attached to Manufactured Home" for ConstructionMethodType
  Manufactured -- B-1 misspells "Atatched", D-1 prints "Attached").
  Type names from A-1 over all 14.002 data points ("Multi-Zone HVAC"; D-1
  prints "Multiple Zone HVAC" -- A-1 wins by the authority order).
  Editor: each cell typed in place, x removes the AMENITY (`DELETE /rows`
  tag AMENITY), the empty line adds one. Tests: test_site_and_defects.py,
  test_rooms.py::test_an_amenity_is_added_in_its_category_and_removed.

### E-118 Prior Sale and Transfer History: every source in the report, comparable rows scrambled
- Subject "Data Source" listed every DATA_SOURCE; the comparable table printed
  all comps' numbers, then all terms, then all amounts. B-1 pp284-286.
- Fix: `form._transfer_table_html` (subject and comparable tables) and the
  21.001 reader: with PriorSalesOrTransfersIndicator false, "None" and the
  sources tied to that indicator; otherwise one line per prior transfer,
  newest first, Terms = SaleType for a Sale else the transfer type, Amount
  without cents ("$332,000"), sources tied to that SALES_HISTORY stacked in
  A-1 enumeration order. A comparable's prior transfer is a SALES_HISTORY a
  source is tied to; its own (grid) sale has none -- true of all 12 samples.
  A second transfer of one comparable leaves the number blank (D-1 Condo1).
  Tests: test_site_and_defects.py (transfer rows).

### E-119 Rent Schedule printed one unit and "[Unit Identifier]"
- B-1 23.01: a line per unit in the rent schedule; Actual Income beside
  Opinion of Market Income, each with Rent per unit, Subtotal, Other Real
  Property Rental Income, Subtotal, Total (D-1 2-4). Fix:
  `form._rent_units_html` / `_rent_income_html`; C-1's two income bars are the
  columns' own titles (RENT_INCOME_HEADS).

### E-120 Rental comparables were one grid against one subject
- A-1 pairs each rental comparable with a subject unit: one RENTAL_INFORMATION
  per pairing, tied by RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION;
  D-1 2-4 compares Unit 1 with #1-#3 and Unit 2 with #1, #4, #5 (Adjusted Rent
  for #1 differs per unit). Fix: `comparables.rental_pairs` -> one grid per
  subject unit; each cell is read in the innermost block its field's path runs
  through (`_field_scope`: pairing, unit, property) -- never the whole
  property for a unit's answer (Unit 2 prints em-dashes, not Unit 1's "No").
  Rows "Display if Exists" print a delivered "No" (`_EXISTS`).
- The Comparable Rental Properties strip (B-1 23.02: photo, number, address,
  data source, lease start, actual rent) was taken for the grid and lost:
  `form._rent_strip_html`, excluded from `_is_grid`.

### E-121 The grid cell editor only knew the sales grid
- Rental and GRM grid cells opened the editor against the sales rows, found no
  row and did nothing -- a dead control. Fix: the grid says its kind
  (`data-gk`), cells their block (`data-gs`); the editor fetches and writes
  that kind; `PATCH /comparables/{n}/fields/{fid}` takes `scope` and writes in
  the block the field's path runs through. Strip cells open the same editor
  (rental editor rows for 23.02.01-06). Tests: test_rooms.py::
  test_a_rental_grid_per_unit_writes_into_that_units_pairing; Chromium
  click-through (strip rent 800 -> 815 saved; Unit 2 grid cell opens).

### E-122 GRM grid: Sale Date blank, "$2,300 ~", an all-zero ADU row
- 24.018 carries A-1's subject condition 'IF PriorSalesOrTransfersIndicator =
  "true"'; a GRM comparable has no such indicator, so its own sale date was
  filtered out. Fix: grid reads drop a condition whose data point the
  property does not hold at all (`comparables._held_conditions`).
- An estimate's "~" now leads the figure in `bind.display_value` (D-1
  "~$2,300"), whatever A-1's data point order.
- An if-applicable row every property answers 0 is not applicable (D-1 2-4 GRM
  has no "Accessory Dwelling Units 0 0 0 0").

### E-123 Income formula line printed bare numbers
- C-1 p35 sets "Total Monthly Market Rent x Gross Rent Multiplier = Indicated
  Value by Income Approach" as label rows over one three-value slot. Fix:
  `form._formula_labels` / `_formula_html` (labels read from C-1, values under
  them, editable in place).

### E-124 Rental / GRM exhibits printed a garbled table
- C-1 p34/p35's "Comparable #" over a photo per comparable was read as a plain
  table (numbers in one cell plus every captioned photo of the report). Fix:
  each comparable's photo joins the section's exhibits ("Comparable #n",
  placeholder "Rental Comparable n" / "GRM Comparable n" as D-1).

### E-125 Data sources with no B-1 target listed every source in the report
- 18.005 Project Information Data Source printed nine sources; Cost Data
  Source / Quality Rating / Effective Date (25.052-25.054) printed nothing.
  A-1's ArcRoles sheet names each subject data-source target per report
  section ("Subject Property: Project Information - Overall Project Data
  Source" -> PROJECT, Cost Approach -> COST_APPROACH). Fix:
  `form._sheet_target` (subject fields only, one candidate per section) and
  `_linked_sources` accepts a target no property holds (COST_APPROACH).

### E-126 Land Comparables: values grouped by column, last first
- Fix: `form._comparable_rows_html` -- a table whose fields are one
  comparable role's (Land Comparable) prints a line per comparable in number
  order, each cell read in that PROPERTY (`comparables.value_for`); C-1 p36
  packs two fields in one cell -> one per column. D-1 MH1 Site and Cost.

### E-127 Sales grid: Site Characteristics, ADU and Outbuilding groups
- "Site Characteristics | Topography" printed beside the Topography row; B-1:
  "other than Drainage and Topography" -> `_other_than` / `_without`.
- The ADU group (Location of ADU, ADU Interior Quality and Condition)
  repeated the dwelling's values on reports with no ADU (SF1); B-1 repeats it
  only "for all PROPERTY_UNITS where AccessoryDwellingUnitIndicator = true"
  -> dropped when no property has one (`_has_adu`). Open: with ADUs (SF3,
  SF4) the group still reads the dwelling's unit, not the ADU's -- T-1042.
- Outbuilding rows read the whole property (the dwelling's Cooling printed
  under "Outbuilding" on SF1, T-123). Now the group repeats per position --
  the k-th outbuilding of every property side by side, each read inside it,
  outbuildings in name order, ADU outbuildings left out ("ADU ... not
  included"), the k-th adjustment of the row's type. Matches D-1 MH1 (Barn /
  Rec Room/Garage blocks) and SF3 (Stable, Pool House, Studio). The name
  order is what the samples show; A-1 ties no outbuilding to another.

### E-128 Sales grid groups drawn once, read from the whole property
- Unit(s) and Interior Quality and Condition printed the first unit only; the
  Exterior group the first dwelling; ADU rows repeated the dwelling's; "Walls
  and Ceiling" printed the flooring text; "Structure ID | Unit ID" read
  "Unit 1 | Building 1"; the comparables' exterior condition rows were blank.
- Fix (comparables.py): `_expand_outbuildings` repeats each group B-1 repeats
  (_REPEATS: units, dwellings, ADUs, outbuildings), each copy read inside its
  own block; a field over two levels is read part by part, outer first;
  `_row_marks` takes the instance B-1's row rule names
  ('ImprovementComponentType (FID: 8.041) = "Windows"', 'RoomType =
  "Kitchen"'); `_rule_hides` applies a row's own "Display when" only where it
  decides alone (no "relevant", no "Comps:"/"Subject:" split, every named
  data point delivered) -- validated: it hides nothing any official PDF prints.
- The harness grid-order check now judges against the spec as repeated.
- Known limit: rows whose B-1 rule ends "AND relevant to the analysis" with
  only "No" answers (2-4 All Rights Included, SF2 Townhouse Back to Back,
  Condo2 Site Owned in Common) print in some samples and not others; A-1
  carries no data point for "relevant", so they follow the data (shown when
  told, adjusted or always).  Tested: a "condition holds -> print" rule is
  wrong 103/122 times.
- Tests: test_site_and_defects.py::test_sales_grid_* ; golden baseline
  regenerated (row counts are the validated new ones).

### E-129 171 H-1 rules were never executed ("review")
- H-1 writes ~40% of its non-presence rules in a few recurring shapes. New
  `uad/compliance_shapes.py` executes them from their own Logic text: a count
  against the number of instances (UAD1011/1016/1019), one value against
  another incl. ISO dates (UAD1015/1131/1206), an instance that must exist
  with a value (UAD1038/1067/1624/1732...), "no instances ... are provided"
  (utilities, parties), a required PROPERTY role (UAD1214/1217/1238), "A is x
  and B is y" (UAD1215), the data-source arcrole links (UAD1183/1199-1202/
  1209, "to each" = every target), children required per owner block
  (FLOOR_COVERING / FlooringType ...), PostalCode / StateCode formats.
  `compliance.evaluate` asks the shapes before marking a rule for review.
- 107 of 171 now execute (also: bare conditions UAD1512-1515, market
  inventory, comment length limits, party names, units per improvement).
  Validated: none fires on any of the 12 D-1 samples, and each shape fires on
  a sample broken the way its rule describes (tests/test_compliance_shapes.py,
  30 tests). H-1's typo
  "'ExteriorWallsAndTrim" is mended; a party's condition is read party by
  party (SF1's trainee is the assistant, not the appraiser).
- Found on the way: `rules.CLAUSE` swallowed the OR that joins two clauses
  ('= "Dwelling" or (ImprovementType = ...') as if it listed values -- the
  expression became "1 (" and every such rule was undecidable. Fixed; the
  report's field_rule_hides results are unchanged (re-validated).

### E-130 H-1 rules written once each stayed "for review" (36 of the last 64)

- Symptom: after the sentence shapes (E-129), 64 H-1 rules still printed as
  "for review": sums across instances (UAD1461 net adjustment, UAD1693 unit
  total), dates against the effective date (UAD1051/1053/1529/1611), label
  resolution and uniqueness of RELATIONSHIP (UAD1717-1719), defect
  indicators without their DEFECT_ContainsDefectOf_* link (UAD1685-1692),
  value-or-range pairs (UAD1695/1696, UAD1733/1746) and others.
- Mechanism: `uad/compliance_checks.py` — one small function per Message ID,
  the rule text quoted above it, consulted first by `compliance_shapes.decide`.
  It covers all 64, so **every one of H-1's 171 non-presence rules now
  executes**. Inspections, signatures and comparable units are read through
  their arcs (INSPECTION_CompletedBy_ROLE, SIGNATORY_IsAssociatedWith_ROLE,
  PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT).
- Four (UAD1250 GRM added rows, UAD1777-1779 subject areas above zero) meet
  nothing in any D-1 sample, so they are tested on constructed cases.
- UAD1468 ("MLS source with arc role to PROPERTY container"): the first reading,
  "anything inside a comparable", faulted 9 samples. The samples link MLS
  sources to the comparable's PROPERTY element itself, so only that link counts.
- UAD1029: the Logic has no condition. Its Message Text says the block lists
  the rights *not* appraised, so every instance must say "false".
- Two first readings faulted every sample and were corrected from the samples:
  - UAD1179 (DataSourceType required): the Price Trend Source carries only a
    DataSourceName in all 12 samples (H-1 asks only that, in UAD1657), so a
    source linked by DATA_SOURCE_IsDataSourceFor_MARKET_TREND is exempt.
  - UAD1034 (@ValuationUseType required): limited to its xPath,
    VALUATION_ANALYSIS/PROPERTIES/PROPERTY. The inspection service's own
    PROPERTY carries no use type.
- Test: tests/test_compliance_checks.py (78 tests). No check fires on any of
  the 12 D-1 samples, and each fires on a sample broken the way its rule says.
- Golden review counts fell by about 32 per sample; fatal and warning are unchanged.

### E-131 The Sketch section printed the RESNET exhibit's caption
- Symptom: SF1's Sketch printed "RESNET HERS Score" as a one-cell table. SF1
  has no sketch; the caption belongs to its Energy Efficient exhibit.
- Cause: once tables read every block (E-102), the 7.002 image table took the
  caption of every IMAGE under the subject.
- Fix: an image table keeps only the categories A-1 names for its ".1"
  column (`form._image_categories`; for 7.002.1 that is FloorPlan and
  SubjectPropertyImprovementSketch).
- Known gap: D-1 SF1 draws a Sketch placeholder although its XML holds no
  sketch image. We print nothing; there is no data to show.
- Test: test_site_and_defects.py::test_the_sketch_table_takes_only_sketches_and_floor_plans.

### E-132 "(Primary)" printed before the view and with a single view
- B-1 4.039 says: "(Primary) displays to the right of the view ... The primary
  view must be in the first row. When there is only 1 view, (Primary) does not
  display". We printed "(Primary) Residential" for SF1's only view and put
  coop1's primary view second.
- Fix: in `bind.display_value` a parenthesised modifier follows what it
  qualifies. The table drawer reads B-1's "When there is only 1 ..., (X) does
  not display" (`form.alone_hidden`) and moves the row carrying the modifier
  to the top.
- Matches D-1: "Golf Course (Primary)", "Parking Lot (Primary)" first, "Lake (Primary)".
- Test: test_site_and_defects.py::test_the_primary_view_follows_b1.

### E-133 C-1 extraction lost IDs written in the shifted font ("9" = \x1c)
- Symptom: the MH2/MH1 Manufactured Home section printed Manufacturer Name,
  Year Installed and Moved Since *after* the commentary, and Date of
  Manufacture and HUD Data Plate Attached out of place. The modifications
  question printed a bare "No". The "clipped" IDs 4.06 / 4.05 / 4.00 / 20.00
  needed a mend (`_complete_clipped_ids`).
- Cause: one C-1 subset font writes digits 29 code points down, so "9" is
  \x1c, and Python's `str.strip()` counts \x1c-\x1f as whitespace. The
  extractor skipped every span that was a bare encoded "9" before decoding it.
- Fix: test the *decoded* text for blank (`extract_c1_form._marks`). That
  recovers 9.000-9.002, 9.008-9.011, 4.099, and the full 4.009 / 4.059 / 4.069
  / 20.009, so the clipped-ID mend now changes nothing.
- Also: a Yes/No question's ID may sit just under its line in the answer
  column (9.007, 16.004), or start inside its box above a commentary heading
  (20.002). Both now attach to the question.
- Test: test_report_rows.py::test_c1_ids_are_read_whole,
  ::test_c1_questions_hold_their_own_ids. Full suite and harness unchanged
  (87/0/21).

### E-134 Energy Efficient and Disaster Mitigation printed against their B-1 rules
- Symptom: Condo1 and 2-4 printed Energy Efficient and Green Features with
  all three answers "None". 2-4 printed no Disaster Mitigation, though its
  subject has impact resistant glass.
- Causes: (1) both sections are SELF_GATED. The editor keeps them so their
  questions can be answered, but nothing applied the rule in print.
  (2) `section_shown`'s fallback read the rule against the whole document,
  so comparable 2's DisasterMitigationFeatureType "None" decided the
  subject's section.
- Fix: `form.print_gate` applies B-1's rule when printing. The EEGF prose
  "one or more of the three ... features is true" reads the section's own
  ...ExistsIndicator points, and only when their count is the three B-1
  names. Disaster Mitigation is read as written, against the subject (the
  fallback now uses `_evaluate_section_rule`).
- Validated: the set of printed sections matches the official tabs on all 12
  D-1 samples (scratchpad secset.py; only the Certifications tab name differs
  in detection).
- Test: test_site_and_defects.py::test_self_gated_sections_print_by_their_b1_rule.

### E-135 Per-section text against the official PDFs: labels, notes and per-location text
Found by splitting each official PDF on its own white section tabs and
comparing word sets section by section (scratchpad secdiff.py), and by
checking every italic note per section (italics.py: 48 mismatches -> 0).
- **A-1 enumeration text is per Report Location.** The enumerations sheet
  gives a value's printed text per location: PropertyMixedUsageIndicator
  "false" prints "None" at 4.017; EnvironmentalConditionType "None" prints
  only at 22.03.14. Without the location the last row won, so Site printed
  no "Non-Residential Use None" (all 10 samples print it).
  `build_index` now keeps each option's `location`, and
  `bind.enumeration_texts` picks the field's own row, then the "Does Not
  Display" row, then any other location. The repeats-as-list fallback also
  reads a point the property holds once when no block-level point answered.
- **Known Sales Concessions "Yes":** A-1 leaves "true" blank, but D-1 SF1
  prints Yes (TRUE_PRINTS_YES, found by sweeping every such indicator).
- **Inspection Date (2.023/2.038)** borrowed the PDR row's
  PropertyDataReportIndicator = "true" (`_inherit_requires`), so it was hidden
  on 10 samples. A row whose own stated condition contradicts the borrowed
  one, or a subject row with an unrelated IF, no longer borrows
  (`_contradicts`; 15 data points). Points sharing an A-1 context and
  container now share its PartyRoleType (`_context_requires`, 11 points), so
  the appraiser's date is the appraiser's.
- **C-1 labels with the ID on the line below** (19.011 "Analysis of Subject
  Property Listing History", 18.094, 25.021) became prose. D-1 prints label
  and text inline.
- **Italic notes:**
  - A note looks past unanswered blocks to what it introduces (the listing and
    prior-sale captions).
  - B-1's "When X = v, display static text in italics" (spec/italic_rules.json,
    extract_italic_rules.py) decides the personal-property note.
  - A note's own "When <cond>: ... Display text in italics" decides it
    (26.075, cooperative).
  - The Summary's "None" only when *all* six DefectsExistIndicators are false
    (B-1 p82), including indicators named only in A-1's IF text; otherwise the
    sentence "There are no apparent defects ... requiring action".
- **"(Cooperative Interest)"** follows the Opinion of Market Value (26.074 /
  Summary 1.085 via summary_sources). It is shown in the editor too, outside
  the typed value.
- **Outbuilding sections by name** (Barn before Rec Room/Garage), as the grid.
- Tests: test_site_and_defects.py::test_static_notes_and_labels_follow_b1,
  ::test_outbuildings_print_by_name. Suite 648 pass; harness 87/0/21.

### E-136 A stated condition was met by a different block's value
- Symptom: SF1 printed "Unit Transfer Fees $34", its monthly dues. 18.071
  reads AssociationChargeAmount where OwnershipTransferFeeIndicator = "true".
  SF1 has no such charge, and `_instance_matches` lets a mark it cannot find
  through, so the dues block matched.
- Fix (`bind._walk_marked`): a condition the data point *states* (its own
  `requires`, not one inherited via requires_from or inferred from the A-1
  context) on a point A-1 places inside the same repeating block must be
  present in that instance. Context-inferred marks keep the tolerant
  behaviour, which a newly written Alternate Address relies on.
- Validated: SF1 prints no row, Condo1 "None", Coop1 "$3,000"; all golden
  shapes unchanged (the first, wider version dropped MH2's Contract Price
  grid row and was narrowed).
- Test: test_site_and_defects.py::test_unit_transfer_fees_read_their_own_charge.

### E-137 Project lists, B-1 value wording and amenity defects
- **Utilities Included (18.013)** printed only the first utility. The list's
  condition (AssociationChargeType = AssociationDues) is on the outer charge,
  not on the repeating utility block, so it is still a list.
  `repeats_as_list` allows such a condition, only for fields C-1 draws as a
  row (component tables have their own drawers: allowing it for them
  worsened Dwelling Exterior 37 -> 112 missing words). The list reader
  honours the condition.
- **B-1 words before a value:** 'Display "Greatest Number of Units Owned-"
  and value' / 'Display "Prior Use:" and value' (18.066-18.068). Printed as D-1
  does ("... Owned - 2"), and shown in the editor outside the typed value
  (`label_prefix`, `with_label_prefix`).
- **18.012 ownership "in () next to Amenity Type":** "Unit Storage
  (Assigned)" (`_bracketed_beside`). An "Other" amenity keeps its
  description ("Snow Removal", "Theater").
- **List order:** measured on all 28 multi-value lists in D-1: the case's
  order fits 19, A-1 enumeration order 18, alphabetical 23 (none fits all).
  B-1 orders only 12.010 ("display alphabetically", p220), so that list is
  sorted and the rest keep the case's order. Known exceptions: Condo1's
  amenities, and 17.017 graph categories.
- **Amenity defects:** the Feature column and the photo caption follow the
  defect's DEFECT_ContainsDefectOf_AMENITY / _CAR_STORAGE arc (D-1 Condo1
  "Balcony"; caption "Apparent Defects, Damages, Deficiencies - Balcony").
- secdiff totals: Project Information missing 56 -> 34, Amenities 11 -> 9;
  nothing worse. Tests: test_project_and_amenity_values_print_as_d1,
  test_b1_alphabetical_list.

### E-138 Cost Approach: one Depreciated Cost block per improvement
- Symptom (D-1 MH1): the dwelling's cost table carried the barn's and the
  garage's cost lines. No outbuilding blocks printed. "1,568 Sq. Ft. |
  $95.66", depreciation "$9,000", "Remaining Economic Life 45", and the
  outbuilding table printed inside the "Commentary on Effective Age".
- Fixes:
  - `form._cost_approach` repeats C-1's dwelling block (25.005-25.022) per
    dwelling and its outbuilding block (25.023-25.036) per outbuilding, by
    name, scoped to the IMPROVEMENT. `_walk` follows
    IMPROVEMENT_COST_AND_DEPRECIATED_VALUE_IsAssociatedWith_IMPROVEMENT
    (`_arc_linked`) to read the improvement's own cost block. Editor cells
    write there too (data-tscope = the linked block; tested through the API).
  - C-1 extraction: a table's column heads no longer reach above an h1 bar
    (the outbuilding table took "Commentary on Effective Age" as its head).
    An ID that starts above a label belongs to the label above it (25.021 /
    25.022). A one-row bar with an ID prints as label + value (25.041
    "Opinion of Site Value").
  - The every-block reader includes unit-attribute points (25.025's second
    area, "200 Sq. Ft.").
  - B-1 pp348-351 bullets (not in the per-field rules):
    - "@" between the area and its price;
    - "years" after 25.019 / 25.020;
    - Total Depreciation "if not 0, display as a negative number" ("$(9,000)"),
      stored positive whatever is typed (`entry.POSITIVE_ONLY`);
    - the highest-dollar line first.
- Result: the secdiff Cost Approach for MH1 and MH2 is down to footer IDs and
  "Set Up" vs "Setup". Tests:
  test_rooms.py::test_a_cost_line_edited_under_its_outbuilding_lands_in_that_cost_block;
  editor parity holds on all 12.

### E-139 Site (D-1 MH1): influence rows, "Ft.", conditional rows, and a B-1 gate D-1 overrules
- Symptoms:
  - Site Influence printed one row per data point rather than one row per
    influence;
  - linear measures printed "Feet";
  - the Non-Residential Property Use feature row was hidden;
  - row 4.044 was hidden by its own trailing "If there are multiple..."
    sentence.
- Fixes:
  - `form._site_influence_html` is the drawer for 4.025-4.029. It prints
    ENVIRONMENTAL_CONDITION, BODY_OF_WATER and the other
    SITE_INFLUENCE_DETAIL rows, one per influence. Environmental and water
    rows come first. Proximities are joined with " | " and "1 Mile" is
    singular. The editor cells write into the row's own block, plus a new row.
  - `bind.LINEAR_UNITS` prints "Ft." (all 12 samples do).
  - `field_rule_hides` cuts the rule at `\sIf\s` before it evaluates.
  - A fixed-row selector matches keys beneath it, and its commentary.
- Validator caught: B-1 p145 gates "Site Valuation Methodology" on
  CostApproachIndicator = false. D-1 MH1 develops the cost approach and still
  prints the site value and the land comparables in Site. The gate faulted a
  published sample (test_land_comparables_a_line_each[Site]), so the
  sample wins: `SUBSECTION_RULES` is empty, and the mechanism is kept for
  gates that D-1 agrees with.

### E-140 Editor: every input looked the same, and the comparable grid looked read-only (T-260)
- Symptoms (owner screenshots):
  - text, list, number and date fields all showed the same tint, so the
    appraiser could not tell which was which;
  - the comparable grid's cells had no affordance and read as printed
    output;
  - there was a stray "☐☐" before the Reconciliation defects table;
  - a flooring row's "×" wrapped onto its own line.
- Fixes:
  - `form.kind_of_point` / `form.input_kind` classify every field from
    F-1/B-1 data, not by hand. Format comes first: enumerated or boolean is a
    pick; date, month or year is a date kind; amount; then number or
    percent. An address or name field is text.
  - Each editable span and grid cell carries `data-k`. EDIT_CSS gives each
    kind its own fill and hint:
    - text: cream, "Type…";
    - pick: blue pill with an arrow, "Select";
    - amount, number, percent and year: green, right-aligned, with "$", "#",
      "%" and "YYYY";
    - date and month: violet, "MM/DD/YYYY" and "MM/YYYY";
    - commentary: a wide "Type comment…" field;
    - grid adjustments: green "±$".
  - A Yes/No italic note is a labelled question ("<Point name>? ☐Yes ☐No"),
    and only for a single Boolean point.
  - The legend in the editor toolbar matches the kinds.
- More fixes:
  - A heading's own placeholders ("- [Structure Identifier]") are named
    controls. An empty Outbuilding Type on a dwelling's heading is not
    offered.
  - An add-row line hints "← choose to add a row".
  - An empty commentary field stays on its label's line, so the editor page
    is no taller than the laid-out one (Zoning Compliance overlapped the
    footer).
  - Yes/No question boxes are captioned.
- Trap: CSS escapes inside the non-raw EDIT_CSS string need doubled
  backslashes (`'\\2026'`); a single one is a Python octal escape
  ("Type⋯6").
- Verified with Playwright screenshots of Assignment Information, Sales
  Comparison, Unit Interior, Site and Reconciliation on a blank case. The
  print path is unchanged (golden suite).

### E-141 Editor: tick cells that would not untick, a transfer's source not editable, and blank hints
- Symptoms:
  - (owner) Public/Private in the utilities table could be ticked but never
    unticked, and an empty cell looked like nothing at all;
  - Subject Transfer History's Amount was a "Select" (the "not available"
    reason point) and its Data Source had no control;
  - the Certifications "Additional Scope of Work / Intended Use / Intended
    User" answers were tiny boxes with no hint;
  - commentary bars said only "Commentary" (or nothing).
- Fixes:
  - flow.py: a click on a ticked cell sends "" and clears the row. Each tick
    cell is drawn as a hollow checkbox. E2E: tick, untick, reload; the cell
    stays clear.
  - `_transfer_cells`: Amount is the amount unless a reason was given. The
    new row writes the amount point.
  - `form._sheet_target`: when A-1's ArcRoles sheet lists several targets for
    a section, a column of a C-1 table sources its row's block (21.005 ->
    SALES_HISTORY) and a lone row sources its data point (21.001 ->
    PriorSalesOrTransfersIndicator). "&" is read as "and".
  - The cells route keeps the row as the scope for an arc-linked source and
    reads it back through the link. Printed text is identical on 12/12.
  - Test: test_rooms.py::test_a_transfer_rows_data_source_is_written_tied_to_that_transfer.
  - The certification answers and commentary bars are wide fields named
    after their field ("Add scope of work…", "Type the legal description…").
    `body.show-gaps .v[contenteditable]:empty:before{content:''}` had blanked
    every data-ph hint.

### E-142 Project Blanket Financing: one column per lien (B-1 over D-1), and more stray editor controls
- Symptoms:
  - Editor: typing in the Second Lien column overwrote the First Lien's block
    (one PROJECT_BLANKET_FINANCING, no LienPriorityType). Data was lost.
  - Print: every column showed the first lien's values (D-1 Coop1 does the
    same), plus "First Lien" four times as loose lines.
  - Editor: four unlabelled "Select" pickers (18.028/.037/.046/.055) under
    the lien table.
  - Monthly Payment was a "Select" (its PaymentAmountAvailableIndicator).
  - Unlabelled Unit Interior title placeholders (10.000-10.002) sat under
    the Manufactured Home exhibits.
  - Outbuilding "Total Area" (12.013) was text, with no data point.
  - The "Indicated Value by Cost Approach" heading box had no hint.
- Authority: B-1 18.028 says the priorities "Display as column headers in
  bold font ... Table is dynamic. Only display as many columns as there
  are Liens", and 18.029-18.063 are "Display for each LienPriorityType".
  D-1 Coop1 contradicts this (its second lien, a line of credit, is printed
  under all four heads). B-1 ranks above D-1, so B-1 is followed and the
  deviation is recorded here.
- Fixes:
  - `form._liens_table_html`: each column reads and writes the block of its
    own priority. A missing one is created with that priority (sel/label).
    The report prints a column per lien held; the editor offers all four.
    The priority slots never print loose.
  - `cell_point`: an "...AvailableIndicator" yields to the value it flags,
    and the cells route sets the indicator to true when a value is typed. A
    measure that carries its unit attribute counts as a data point.
  - Tab title placeholders are labelled ("Unit Interior: Structure
    Identifier"); an empty Outbuilding Type is not offered.
  - Commentary hints fall back to the bar they sit under.
- Tests (test_rooms.py):
  - test_each_lien_column_writes_its_own_blanket_financing;
  - test_a_lien_payment_typed_marks_the_payment_available;
  - test_an_outbuilding_area_cell_writes_its_measure.
- Open, for the owner: C-1 p33 sets two units' rental analyses side by side
  (as we print, T-1043). D-1 2-4 and Scenario 2 stack Subject + three
  comparables per grid instead.

### E-143 Rental analysis layout: the appraiser's choice per report (owner: "make it dynamic")
- C-1 p33 draws two subject units' rental analyses side by side. D-1 2-4 and
  Scenario 2 print one grid under the next. B-1 sets neither.
- `form.rental_layout(folder)` reads editor.json "rentalLayout":
  - "stacked" (the default, as D-1 prints): one grid per unit, "Subject
    Unit 1 | Comparable #1 #2 #3", each with its own paired comparables;
  - "paired": `comparables.html_pair`, two units to a line.
- The editor shows a two-way switch on top of the first rental grid, only
  when two or more units have paired comparables. It is never printed. A
  click saves the pref, and the API marks the render changed; the render key
  includes rentalLayout for every output kind.
- Tests:
  - test_site_and_defects.py::test_rental_comparables_strip_and_a_grid_per_unit
    (stacked);
  - test_the_rental_analysis_layout_is_the_appraisers_choice (paired, switch
    state, never printed).
  - E2E: click "Units side by side", the pref is saved, and after reload the
    side-by-side grid shows with the switch on.

### E-144 Multi-family showed no Rental section; no way to state the property type; unit defects refused
- Symptoms (owner, 2026-10-07):
  - Making the report multi-family did not bring up Rental Information.
  - There was no first page for choosing the property type.
  - "The dropdowns don't work".
- Causes:
  - B-1 shows Rental Information, Income Approach and Cost Approach when
    RentScheduleIndicator / IncomeApproachIndicator / CostApproachIndicator
    = "true", and all three are "FID: Not on report". The editor offered no
    place to set them. When a single-family report was reshaped to 2-4, the
    single-family report's "false" was carried over the 2-4 structure's own
    "true".
  - A defect row added in a unit's or building's own table built
    DOCUMENT_SETS/... inside the PROPERTY_UNIT. The schema refused it, so
    every such pick failed: 8.060, 10.056-10.060, 26.031, 26.039. Found by an
    E2E sweep that opened pickers across a 2-4 report and recorded refused
    saves: 75 ok, 12 failed before the fix.
- Fixes:
  - `uad/setup.py` and `GET/PUT /api/cases/{id}/setup`: the property type
    (single family, 2-4 with 2/3/4 units, condominium, cooperative,
    manufactured) plus the approaches.
    - A new report starts directly on that kind's D-1 structure
      (`POST /cases` with `setup`), with nothing carried. All five kinds give
      the right sections and pass the schema.
    - An open report is reshaped as by an answer. Moving to a non-project
      kind clears the carried project answers.
  - `shape.reshape` keeps an approach on if the old report had it or the new
    structure develops it; the structure's own values are read before the
    carry.
  - A carried property-data-report INSPECTION_SERVICE goes into the
    structure's own inspection SERVICE.
  - The cells route creates a unit or building defect under the PROPERTY and
    ties it with DEFECT_ContainsDefectOf_<TAG>.
- UI: the "What are you appraising?" screen opens on New report. The editor
  toolbar has "Report setup".
- Tests: tests/test_setup.py (8).
- Open: changing an existing filled report into a condominium leaves schema
  findings from the condo structure's separate inspection SERVICE (PARTIES
  order) and VALUATION_SOFTWARE_SYSTEM. This is the old reshape path; a new
  report is clean.

### E-145 Signature taken where it prints; lists that can be typed into
- Owner's complaints:
  - "In the signature section it should ask for the signature input." The
    line held only the name and a hint-less date box.
  - "Most adjustments don't need dropdowns, just put text or number." Grid
    and report lists could only be clicked through.
- Signature:
  - The editor shows "Sign here" on each signer's line.
  - The pad offers Draw (pointer or finger), Type (the name set in a
    handwritten face) or Upload.
  - It saves a PNG as case media: category "signature", section 29,
    caption "Signature <n>". Saving again replaces it; "Remove" deletes it.
  - `_signature_html` draws it above the line in the editor, the preview and
    the PDF. It is never shown as an exhibit (excluded in the media-exhibit
    loop). The date, ID, state and expiry controls carry their kind hints.
- Typeable lists:
  - Grid lists (`field()`) have a "Type to find…" box. Typing narrows the
    choices; Enter saves the first match.
  - Text that matches nothing saves as the field's "Other", with the words
    as its OtherDescription. The server still refuses an invalid
    enumeration (verified: MortgageType "sim" gives 422 when sent raw).
  - Report pickers with more than 6 choices open with a search box; Enter
    picks the first visible choice.
- E2E:
  - sign (type) → save → reload: img.sgimg in the editor and in the preview;
    media [["signature","Signature 1"]];
  - type "sim" in Financing Type → saved as Other: sim.

### E-146 Editor feel: instant adds, one list at a time, typed addresses, clean Yes/No boxes; type changes schema-clean
- Owner (2026-10-07, screenshots):
  - "Adding…" waits; additions should look instant and save in the
    background;
  - the Additional Properties Analyzed Not Used address was a "Unit" list;
  - its dates showed "—w";
  - several lists were open at once;
  - Yes/No boxes looked doubled and offset.
- Fixes:
  - "+ Add a property analyzed but not used" clones an empty row at once.
    The row is inert until the laid-out report swaps in with its key.
    "+ Add Comparable" confirms at once. A signature shows on its line at
    once.
  - A whole-address cell is one typed field (`_cell` for an
    `edit.is_address` binding: data-tdp='', text). The cells route splits it
    with `edit.split_address` and echoes the whole address.
  - Empty editable cells in the comparable-rows drawer are blank, not "—".
  - Picker lists are cached per field, and only the last click's list
    opens; closing cancels a list still loading.
  - Yes/No boxes: the outline around the 12pt cell sat offset from the
    Wingdings glyph and drew a second box. Removed; an unanswered pair's
    glyphs are amber instead.
- Changing a filled report's type: the new structure's inspection-only
  SERVICE stands aside during the carry, and the old report's inspection
  SERVICE is carried whole in front of the valuation. All 40 changes (5
  kinds × 4 targets, filled and blank) are schema-clean and classify as the
  target (tests/test_setup.py).
- E2E: row count 5→6 right after the click; the address saved without
  error; one list open after two quick clicks.

### E-147 Multi-family rentals: which comparable is compared with which subject unit
- Owner (2026-10-07): "If it's multi-family rental, how can I put each unit,
  and say how many units each rental has ... dynamic per unit."
- What the spec says:
  - Subject units come from the unit count (Report setup, or 3.005). Each
    has its own Unit Interior and Rent Schedule line (23.01: identifier,
    rented, occupancy, rent ...).
  - A rental comparable is one rented unit: its unit number is part of its
    address (23.02.03 AddressUnitIdentifier). B-1 23.03.24 draws it "for
    each rental comparable being compared to the subject unit".
  - How many units a comparable building has is the GRM grid's 24.001 /
    24.012 Units Excluding ADUs and 24.002 / 24.013 ADUs.
- Cause: the pairing is data (a comparable's RENTAL_INFORMATION per unit,
  RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION), and nothing let
  the appraiser set it. A single-family report made 2-unit had no pairing
  and one unnamed grid.
- Fixes:
  - `uad/rentals.py` (matrix, set_pair, pair_new_comparable) and
    `GET/PUT /cases/{id}/rentals/pairs`.
  - A rental comparable added is paired with every unit.
  - The editor panel "Which rental comparable is compared with which
    subject unit" sits above the rental analysis. A tick applies at once and
    the grids follow.
  - An unnamed unit's grid is titled "Subject Unit n".
- Trap: an lxml element with no children is falsy. `a or b` between
  elements chose the wrong RENTAL_INFORMATION and made a second one per
  unit, which split the grids. Use explicit `is None`.
- Tests: tests/test_setup.py::test_rental_comparables_are_paired_with_subject_units_and_the_grids_follow.
- E2E: unticking #1 for Unit 2 changed its grid from #1, #4, #5 to #4, #5.

### E-148 Hard-to-see hints and cursor; the rent schedule's subtotal went stale
- Owner (2026-10-07):
  - placeholders were too light, and the blinking cursor was barely visible
    when typing;
  - the rent schedule showed $123 + $13 with a Subtotal of $32.
- Visibility (EDIT_CSS):
  - hints are darker (rgba .66) and larger (6.6 to 6.8pt);
  - the field being typed in is white, with a 1.2pt blue edge and a 3.5pt
    soft glow, and caret-color #0b57d0;
  - its hint steps aside on focus, so the caret is not hidden behind the
    text;
  - an open picker gets the same ring.
- Rent totals:
  - B-1 23.01.14/17/18/21/24/25 are "Calculated" sums.
  - `uad/rent_math.py` recomputes them on every save, beside grid_math. It
    changes nothing in the three D-1 samples (validator validated).
  - The editor shows them read-only (td.calc, Σ).
  - The page re-adds them the moment a rent is saved, and mirrors that rent
    into every place that shows it (the Rent Schedule and the Actual Income
    column).
  - Rows for unnamed units read "Unit n".
- Tests: tests/test_setup.py rent-schedule tests (4).
- E2E: typed 123 and 13; within 1.5s the Actual Income column showed $123
  and $13 and the totals $136, $0, $136.

### E-149 -- An area cell offered a "Sq. Ft." list and no way to type the area; grid values opened a popup (2026-10-08)
- Symptom (owner): "Finished Area Above Grade (Nonstandard)" opened a list
  holding only "Sq. Ft."; adjustments opened an "Adjustment" popup; "too many
  dropdowns for fields whose unit we know".
- Cause: an area is one data point whose unit sits in
  `@AreaUnitOfMeasureType`. `comparables.points_for` dropped every
  attribute-carrying point, and `options_for` returned the unit's
  enumeration, so the editor offered the unit as the cell's only choice.
- Mechanism:
  - `points_for` keeps a point whose attribute is a unit
    (`entry.unit_attribute`) with no options;
  - `options_for` returns nothing when every point is a unit-carrying measure;
  - the write fills in the unit (`entry.normalize`: square feet unless the
    appraiser types another, e.g. "120 sf").
- Typing in place: `comparables.typed_in_place(fid)` names the single typed
  data point of a cell (no list, not Yes/No). Edit-mode cells carry
  `data-gin` (the point, or `adjustment`). flow.py `typeInCell` puts the caret
  in the cell: Enter saves and moves down, Tab moves right, Escape restores.
  The value shows at once and the save runs behind it. Cells of several
  parts (address, data source) and real lists keep the editor.
- The adjustment save returns the printed form ("$(2,500)"), not the raw amount.
- Edit-mode look: square boxes, deeper fills, solid edges, 7.6pt darker
  hints, a larger Yes/No. Only in EDIT_CSS: preview, PDF and ZIP are
  untouched (golden tests).
- Tests: tests/test_workflow.py (4 new).
- E2E: GLA "1850" → "1,850 Sq. Ft."; "120 sf" → "120 Sq. Ft."; adjustment
  "-2500" → "$(2,500)"; "abc" refused with a message.

### E-150 -- A report opened on a shared layout waited 12 s for its images (2026-10-09)
- Symptom: measured with Playwright against the browser-layout server
  (the web's path). Reopening a filled report took 15–19 s, with every page
  image arriving after about 12 s. Every new blank report opens the same way.
- Cause: a layout kept for identical content (renders/layouts, shared by
  key) names images under its own case's asset folder. The new case had no
  such files, and each of the ~18 image requests rebuilt the whole report
  (`client_galley`) in parallel to recreate them.
- Mechanism (`api.render_asset`):
  - assets are content-addressed, so an identical file is first looked for
    in any case's `_render/assets/` and copied;
  - only if none exists is the report rebuilt, once, under a per-case lock.
- Evidence: reload went from 15–19 s to 3.6 s.
  `tests/test_desktop.py::test_a_shared_layout_finds_its_images_without_rebuilding`.

### E-151 -- Opening a report built the whole report twice at the same moment (2026-10-09)
- Cause: two calls fire together when a report opens, `GET /cases/{id}` and
  `GET /cases/{id}/review`. Both need `sections_present`, a full `form.build`
  of over a second. `Store._memo` had no lock, so both computed it in
  parallel and the open took twice the CPU.
- Mechanism: a per-(name, case) lock in `_memo`. One thread computes the
  result and the rest wait for it.
- Related: the rail's `fields?slim=1` no longer runs the H-1 rules it never
  shows (`findings=False`, saving 0.25–0.45 s per version).
- Evidence: `test_a_per_version_result_is_computed_once_when_asked_together`.
  A first open of a filled SF1 report went from 8.6 s to 5.7 s.

### E-152 -- The blank-report warm-up competed with the report being opened (2026-10-09)
- Cause: the home page lays out a hidden blank report so that new reports
  open at once. Opening an existing report while that ran split the CPU
  between the two layouts.
- Mechanism: `openCase` calls `stopWarm()`, which cancels the warm-up
  frame. The warm-up never starts while a report is open.

### E-153 -- The desktop edition: PDF without Playwright, and two build traps (2026-10-09)
- PDF without Playwright: `uad/report/cdp.py` drives the system Edge/Chrome
  over the DevTools protocol, and `browser.py` chooses Playwright, then the
  system browser, then none.
  - Equivalence on SF1 was exact: 230 measured blocks, page bottoms, and 20
    PDF pages, text and pixels.
  - Chromium's printToPDF tags PDFs by default, which made the file 2.4×
    larger. `generateTaggedPDF: false` matches Playwright.
  - As root on Linux, Chromium needs `--no-sandbox`. It is never added on
    Windows or macOS.
- Build trap 1: a file-writing step turned the text `괶` in
  installer.nsi into the character 괶. Icons are now `icon.ico`, and a test
  asserts the NSIS script is plain ASCII.
- Build trap 2: `build.py` packs only git-tracked files, so new files must
  be `git add`-ed before building. This is deliberate: it keeps case
  material and licensed fonts out of the installer.
- Wine quirk: `pythonw.exe` with redirected stdio fails to start under Wine
  ("init_sys_streams"). It is fine on a terminal and on Windows, where a
  shortcut passes no handles.
- Mechanism and evidence: `desktop/README.md`, `tests/test_desktop.py`
  (16 tests). Wine 9 runs of the real installer and app: wrong key refused,
  right key installs, app serves, activation, uninstall keeps reports.

### E-154 -- The Vercel build failed when the installer joined the bundle (2026-10-09)
- Symptom: `LAMBDA_SIZE_EXCEEDED`. The bundle was 244.07 MB against a 225 MB
  maximum once `downloads/desktop/**` (24 MB) was added to `includeFiles`.
  The failed build was never promoted, so production stayed on the previous
  version.
- Mechanism: PyMuPDF (65 MB installed) is out of the root `requirements.txt`.
  The web platform never imports it; only the spec extractors, `uad/ingest`
  and the golden tests do. The app was checked to import and serve with
  pymupdf blocked.
- Watch: the installer is the bundle's elastic part. At over ~40 MB, serve
  it from its own small function instead.

### E-155 -- One unclosed CSS rule unstyled half the editor on the live site (2026-10-09)
- Symptom: in the shipped editor the report frame was drawn at the browser's
  default 300 × 150 px, the Save / Save & Next buttons sat loose, and the
  inspector was unstyled. Clicks in the frame hit the wrong field, because a
  145 × 18 px field became 7 × 1 px.
- Cause: moving the Download dialog's CSS from `index.html` into
  `ui/download.js` filtered lines by prefix. `.dlbtn{…` spans two lines, so
  its second line (with the closing brace) went to `download.js`. In
  `index.html` the rule never closed and swallowed every rule after it. In
  `download.js` the stray line began the stylesheet. Browsers report neither.
- Mechanism: `tests/test_browser_scripts.py::test_stylesheets_close_every_rule`
  counts braces in every stylesheet: each `<style>` in `index.html`, the
  `/download` page, `EDIT_CSS`, and the dialog CSS in `download.js`. It
  ignores comments and strings. It fails on the shipped files (checked) and
  passes on the repaired ones. Never move CSS by line filters; move whole
  rules.

### E-156 -- Field guidance: A-1's condition language and twin fields (2026-10-09)
- A-1 writes 568 distinct conditions in a small language. It has
  parentheses, `OR` between clauses, `OR` inside a value list
  (`= "Pending" OR "SettledSale"`), `>`, `Is (Not) Present`, `Exists`,
  `Included In … Approach`, and shared lists (`A AND B AND C Are Not
  Present`). Splitting on `AND` printed half of them as raw syntax.
- Mechanism: `uad/conditions.py`, a recursive-descent reader.
  - `OR` before a quoted value continues the value list; before anything
    else it joins conditions.
  - Top-level `@ValuationUseType` / `PartyRoleType` / `ServiceType` clauses
    become the field's *scope* ("for the Appraiser Supervisor", "for each
    Sales Comparable"), not a condition. A field required in a block that
    may be absent is shown "Required for …", never "always required".
  - Test: all 568 A-1 conditions read with no parenthesis, quote, operator,
    keyword or CamelCase name left.
- A finding is filed under one field, but some values print twice (the
  Summary's 1.001 repeats Reconciliation's 26.007). The guidance counts a
  finding as this field's when it is filed here, or when it is one of this
  field's own H-1 rules (same data point and same label) filed on its twin.
- Rules are matched by data point **and** label. Matching by data point
  alone showed the subject's address rules on the comparable rows.
- Validated against all 12 D-1 samples:
  `tests/test_field_guide.py::test_guidance_agrees_with_review_master_on_every_sample`.
  A rule shown failing is a Review Master finding, and every Fatal or
  Warning filed under a field shows in its guidance.

### E-157 -- A test compared parties by `id()` of lxml elements (2026-10-09)
- Symptom: `test_autofill::…holding_everything_the_case_holds` failed for
  condo1 and one other scenario on unchanged code. It had passed the day
  before. It compared the Appraiser at `PARTY[3]` with the Lender there.
- Cause: `_by_role` keyed each party by `id(party)`. lxml builds element
  proxies on demand and frees them, so the `id()` taken while indexing is
  not the `id()` of the proxy met later. The role lookup missed silently,
  and parties were compared by position. Whether it missed depended on
  memory layout. The autofill itself was right.
- Mechanism: parties are keyed by `getelementpath()`. Never key lxml
  elements by `id()` unless the elements are held alive in the same
  structure.

### E-158 -- A PDF test demanded the licensed font on a machine without it (2026-10-09)
- Symptom: `test_golden::test_the_pdf_is_text_not_a_picture` failed in a
  container without the licensed Myriad Pro files. The PDF embedded the
  committed substitute (`UADSubstitute-*`), which is what that machine
  should embed.
- Mechanism: the test asks `fonts.substituted()` which face this machine
  draws and requires that face embedded. It still fails on a system fallback
  face or Type3 glyphs.

### E-159 -- Additional certifications could not be saved at all (2026-10-09)
- Symptom: typing in 29.053 (appraiser) or 29.062 (supervisor) answered
  "could not be saved to its matching report field", on filled and blank
  reports alike. No appraiser could add a certification.
- Cause: both fields share one A-1 path
  (`SCOPE_OF_WORK/VALUATION_REPORT_ADDITIONAL_CERTIFICATIONS/...`). What
  tells them apart (`ValuationAdditionalCertificationIncludedByType`) and
  the indicators that make the text required are not on the form, so the
  general writer had no way to pick or create the right instance.
- Mechanism: `uad/certifications.py` keeps the list, each entry's type and
  both indicators on every change. `PATCH /cases/{id}/certifications/{by}`
  writes entry #ordinal; one past the last adds, empty text removes. The
  form prints them numbered; the editor keeps the next number open, and x
  removes one (WinTOTAL's Add / Remove).
- With none added, print keeps an invisible empty line: it is what hides
  the "cannot be contrary" note, as the official reports do.
  `tests/test_certifications.py` (the official comparison) caught the
  first version, which dropped it.
- Length: 360 characters, read from A-1, not assumed.
- Tests: `tests/test_additional_certifications.py` (add / edit / remove on all
  12 samples: schema 0, no new H-1 finding, the supervisor's untouched).

### E-160 -- The browser measured a half-loaded galley, so layouts came out short (2026-10-09)
- Symptom: after an edit the report sometimes never refreshed, or showed a
  report missing its last blocks (cut off in Certifications, no Signature).
  It was intermittent: about 1 round in 4-7 under repeated edits.
- Cause: `frame()` in the client-layout page attached the measuring iframe
  before setting `srcdoc`. Chrome fires `load` for the initial about:blank
  on attach, so the promise resolved on that. 120 ms later MEASURE ran on
  however much of the ~900 KB galley had been parsed. The planner then laid
  out a short report. `flow.trusted` refused to share it (length mismatch),
  so the damage stayed in that browser, but that browser showed it.
- Mechanism: `srcdoc` is set before attaching, and only a load whose
  document is `about:srcdoc` counts. The page counts the galley's blocks
  with DOMParser and measures again (up to 3 times) if the measurement is
  short. An image that never answers no longer holds the pass up (8 s).
- Evidence: a repeat harness (save, wait for the new layout) went from a
  stuck round within 4-7 rounds to 36 of 36 rounds, at 3.4-5.0 s each.
  `tests/test_additional_certifications.py::test_the_layout_never_measures_a_half_loaded_galley`
  pins the order.
- This affected every client-laid-out report (web and desktop), not only
  certifications.

### E-161 -- Eight required unit fields were never checked on a dwelling (2026-10-10)
- Symptom: removing a dwelling unit's BedroomCount, Full/HalfBathroomCount,
  Interior Quality/Condition, OverallBathroomsUpdateStatusType,
  UnitInteriorDefectsExistIndicator or UnitIncludedInRentScheduleIndicator
  raised no finding (UAD1159-1161, 1173-1176, 1688; all Fatal).
- Cause 1: the tokenizer let an atom take a structural ")" as its own
  ('Indicator = "true"))'), so a rule's groups came out unbalanced. UAD1146
  parsed as "Dwelling or (... and RoomType)" instead of
  "(Dwelling or (...)) and RoomType".
- Cause 2: `selects` (written for UAD1145's real precedence slip) forced
  every unit-level condition onto every branch. "(Dwelling) or (Outbuilding
  and AccessoryDwellingUnitIndicator = true)" then governed ADUs only.
- Mechanism: an atom consumes ")" only when it opened "(".
  `compliance.mixed_precedence(logic)` limits the repair to conditions that
  mix and/or at their top level (10 rules; only UAD1145 is affected).
- Validated: the 12 D-1 samples raise exactly the findings they did before
  (none). Each of the 8 rules fires on a sample copy with its value
  removed, and did not before (`tests/test_rule_parsing.py`). 6 of 728
  rules parse differently; 4 of those are the same logic regrouped.
- Effect: blank reports show more fatal findings, correctly: each unit's
  bedrooms, baths and ratings are now asked for.

### E-162 -- A section switched off by its own question vanished from the editor, question and all (2026-10-10)
- Symptom: answering "No" to "Is there a sales contract?" (20.000), or
  "None" to the Mitigation Feature (5.000), removed the whole section from
  the editor. The question went with it, so the section could not be
  switched back on from the form. D-1 Condo1, MH1, MH2 and SF5 opened that
  way.
- Cause: `form.SELF_GATED` says the editor keeps these sections to be
  answered and only the print rule hides them. But `section_shown` fell
  back to `section_rules()` (B-1's overview sentence) for Sales Contract and
  Disaster Mitigation, and `build` dropped any section it called False
  before the edit check. Energy Efficient escaped only because its rule
  names no data point, so in the editor it showed in full with every
  sub-field marked unanswered.
- Mechanism: a section B-1 switches on by its own question
  (`form.switch_fields`, read from B-1's sentences: the FID the rule names,
  or the counted ...ExistsIndicator points) stays in the editor. When it is
  switched off it is collapsed to that question plus B-1's sentence
  (`.secoff`). The printed report is unchanged: the print galleys of all 12
  samples are byte-identical before and after.
- Test: `tests/test_optional_sections.py::test_the_editor_keeps_the_question_of_a_section_left_out`
  (Condo1: 20.000, 5.000 and the three 6.0xx questions present, the rest
  not, three notes; none in print).
- Shipped with T-1057 (Show / Hide), whose leftover answers this exposed.
  Leaving a section out now also moves its other answers out of the XML.
  The D-1 samples that don't print it hold only the question.

### E-163 -- The live site could not make the PDF, so it could not deliver at all (2026-10-10)
- Symptom: on Vercel `report.pdf` answered 503 and `package.zip` failed with
  it (owner's section test B5). Every layout already ran in the appraiser's
  browser; only the print step needed Chromium on the server.
- Cause: the PDF came only from `flow.to_pdf` (Playwright / CDP). A
  serverless function cannot start a browser, and a browser page cannot print
  to a file a script can read.
- Mechanism: `uad/report/pdfdraw.py`.
  - `DISPLAY_JS` runs in the laid-out pages and reports, in points, each
    glyph's x (per character, so kerning and letter spacing are the
    browser's own), each run's baseline (measured with a probe in the same
    face), filled boxes and borders (collapsed table borders straddle the
    line; `::before`/`::after` bars), pictures with object-fit and clip, and
    the inline SVG ticks. Computed lengths are calibrated against the
    screen, because browsers disagree on whether CSS zoom is included; a
    page shown smaller is drawn at full size while it is read.
  - `write` makes the PDF with fontTools, Pillow and zlib only. The report's
    own TTFs are embedded and subset (Type 0 / CIDFontType2, Identity-H,
    ToUnicode), glyphs are placed with TJ adjustments, JPEG goes in as is,
    an 8-bit RGB PNG passes through with PNG predictors, and EXIF
    orientation is honoured.
  - `check_text`: the server's own pages for the key (the shared layout, or
    rebuilt from the browser's numbers with `flow.trusted`) must contain
    every character the browser drew, page by page and in order. Pictures
    are read from the case's own asset files. A small inline data: picture
    is accepted only when the server's page holds that exact URI. An SVG
    picture (a market chart) is rasterised by the browser at 4 px/pt.
  - API: `POST /cases/{id}/report.pdf` (gzip allowed) keeps the PDF under
    `_render/pdf/<key>` and in the shared store
    (`Durable.put_output`, `cases/<id>/out/pdf-<key>.zip`). On a host
    without server layout, `GET report.pdf` and the package use it, or answer
    409 `draw`. `POST /cases/{id}/package` plus
    `GET .../package/part/{n}` and `report.pdf?part=n` hand files over in
    3.5 MB parts: a serverless function answers at most 4.5 MB.
  - Editor: Open PDF and Export ZIP lay the preview out in a hidden frame,
    run the script, post it and fetch the parts (`drawPdf`, `openPdf`,
    `exportZip` in `index.html`).
- Validated: all 12 D-1 samples match Chromium's own PDF of the same pages:
  same page count, the same characters on every page, glyphs within 0.01 pt
  across and 0.13 pt down (Chromium snaps baselines to its 3x grid), and
  every picture. Pixel difference is below 0.1 % per page; SF2's speckled
  plat map resamples to 1.3 %. `tests/test_client_pdf.py` (12 tests) runs 3
  samples against Chromium, plus forgery refusals, the writer's units, and
  the editor end to end with the server forced to the no-Chromium path: draw,
  parts, refusals, and the ZIP holding that same PDF.
- Known limits:
  - The browser decides geometry. The words are the server's, but their
    placement is the appraiser's own browser's.
  - A character outside the report faces and the Source Sans 3 fallback is
    left out and named to the appraiser.
  - SVG `<img>` pictures are raster in the PDF (vector in Chromium's).

### E-164 -- A refusal marked "stale" made the case vault restore the case over itself (2026-10-10)
- Symptom: found while building E-163. After a refused PDF request, the
  drawn PDF had vanished from the case folder.
- Cause: `app/ui/vault.js` reads any 409 whose body says `"stale": true` as
  "this server copy holds an older revision". It then restores the case from
  the browser's copy, `replace=True`, which deletes the case folder first.
  The new route's "the report changed while it was laid out" answer used
  that same word.
- Mechanism: the route answers `"changed": true`. A comment at `_draw_pdf`
  says why. The editor retries once on `changed`.
- Test: `tests/test_client_pdf.py::test_the_editor_draws_the_pdf_and_exports_the_zip_in_parts`
  (a refused request leaves the drawn PDF in place).
- Rule: in an API answer to a vault-wrapped request (any `/api/cases/<id>`
  route), `stale` is reserved for the vault protocol.

### E-165 -- A 2-4 unit / ADU report showed the first unit's adjustment on every unit's line (2026-10-10)
- Symptom: on SF3, the ADU's Finished Area Above Grade line printed the
  dwelling's adjustments. The official PDF prints $(1,840), $18,560 and
  $(6,440) there.
- Cause: `comparables.build` read a per-unit row's adjustment with
  `_nth_adjustment(..., ob)`, the outbuilding index, which is 0 for every
  unit and ADU line. A-1 keeps one COMPARABLE_ADJUSTMENT per type per line,
  in the order the lines are drawn (units, then ADUs).
- Mechanism: positional instances. Each expanded row of a type gets
  `instance` = its running count in drawing order. Reading uses the k-th
  adjustment of that type, and writing uses
  `comparables.write_nth_adjustment(prop, type, k, value)`, which creates the
  preceding blocks and keeps a type's blocks together. The editor sends
  `instance` (`data-gai`) with every adjustment cell it saves.
- Test: `tests/test_worksheet.py::test_the_adu_row_reads_its_own_adjustment`
  and `::test_per_unit_lines_are_positional_as_the_samples_keep_them`.

### E-166 -- Adjustments filled by a worksheet went stale, and a hand-typed one was overwritten (2026-10-10)
- Symptom (owner's addendum to DR §11): after OK, changing a comparable's
  area left its adjustment at the old figure. Re-applying a worksheet wrote
  over amounts the appraiser had typed.
- Cause: a worksheet was a one-shot write with no memory of its rate, and
  nothing recorded which cells were the appraiser's own.
- Mechanism:
  - `uad/worksheet.py` remembers each applied worksheet (rate, threshold,
    rounding, profile) in `worksheets.json` beside the case, so it travels
    with the bundle.
  - `Store.save_tree` runs `worksheet.recalc`, which recomputes every
    applied row on the document as it now stands, and every write route
    returns `recalculated`. The editor lays the page out again and flashes
    the moved cells.
  - An adjustment typed in the grid, or in the drawer, is marked manual
    (`type|comp label|instance`, so it follows the comparable when the
    comparables are reordered) and is never overwritten. "Use worksheet"
    releases it.
  - `marks()` gives the grid its (+) / "✓ $75/sf" icons and each cell's
    arithmetic as its title.
- Test:
  - `tests/test_worksheet.py::test_an_applied_worksheet_follows_its_values_and_spares_a_typed_one`
    and `::test_the_deliverables_carry_what_the_worksheet_wrote` (preview,
    PDF, mismo.xml and ZIP);
  - `tests/test_worksheet_grid.py` (Chromium): icons on SF / condo / 2-4,
    including new comps and units and after a re-render; drawer preview
    equals the server; OK, Esc, Ctrl+J; recalc in the grid; signed is read
    only.
- Spec note: the UAD 3.6 rental and GRM grids define no adjustment rows (0
  of 26 / 0 of 14). The icons therefore apply to the sales grid and its
  per-unit/ADU lines.

### E-167 -- A second building showed the first building's front photo; an extra front photo never printed (2026-10-10)
- Symptom 1: D-1 2-4 printed 2-4_Dwelling1Front atop both buildings'
  Dwelling Exterior. Building 2's own 2-4_Dwelling2Front never showed.
- Symptom 2: D-1 SF1 prints SF1_DwellingFront among its Dwelling Exterior
  Exhibits, captioned "Dwelling Front". We dropped it.
- Cause: A-1 lists DwellingFront twice. 1400.0619 is the large photo atop
  the section (8.000.1, "Does Not Display" a caption). 1400.0638 is an
  exhibit captioned "Dwelling Front" (8.062.1). `image_categories` kept the
  first row, so DwellingFront had no section and was never an exhibit.
  `_photo_for` took the first DwellingFront for every dwelling.
  (`_exhibits` even had a no-op `if ... DwellingFront ...: pass` where this
  had been started.)
- Mechanism: a category A-1 lists twice keeps the row that places it on the
  report. `_front_photos` gives the n-th property-level DwellingFront to the
  n-th dwelling as its top photo, and any beyond one per dwelling is an
  exhibit (of the one dwelling, when there is one). Delivery replaces only
  the first dwelling's front, in place, when the appraiser supplies a
  subject photo. It used to remove every DwellingFront, a second building's
  included.
- Validated: on all 12 samples only SF1 gets a "Dwelling Front" exhibit, as
  in D-1. `tests/test_dwelling_fronts.py` (5).
- Not changed: D-1 SF1 lists Dwelling Front before Dwelling Rear; we keep
  document order (Rear first). Neither B-1 nor Appendix E states an order,
  and A-1's row order would reorder MH1/MH2's Site exhibits away from D-1.

### E-180 -- Removing the last of a repeating block left its schema-required wrapper behind (T-509, 2026-10-11)
- Symptom (owner, DR §4):
  - The XSD fatal "AMENITY_CATEGORY_DETAIL: not expected, expected
    AMENITIES" on comparables #1 and #3 of a 2-4 unit report.
  - The editor's x on a category's last amenity was refused with the same
    message.
  - The same class elsewhere:
    - removing a named grid row or the last party name was refused;
    - every "[Other Exterior/Interior Feature]" row was refused;
    - the first block added under a new holder left a nameless phantom
      beside it.
- Cause: every remover used `holder.remove(node)` and then dropped the holder
  once it was empty. MISMO nests repeats in wrappers that must each hold the
  next (PROPERTY_AMENITY > AMENITY_CATEGORIES > AMENITY_CATEGORY > AMENITIES
  > AMENITY), so the last amenity took AMENITIES with it. Adders appended
  after EXTENSION, or added a second instance beside the skeleton that
  `insert_ordered` had just made.
- Mechanism (`uad/edit.py`):
  - `remove_block` / `removal_plan` walk up only through holders left empty
    or below the XSD's minOccurs (`xsd_order.min_occurs`, generated as
    `spec/xsd_min.json`; MARKET_INVENTORIES needs 3).
  - A holder that holds an answer, is linked, or is a document singleton is
    never discarded. The removal raises `Unremovable` and the route answers
    422.
  - `place` inserts in sequence order; `add_instance` / `adopt` reuse a new
    holder's skeleton; `empty_block` keeps the only PARTY of a SERVICE.
  - Every remover and adder in the engine uses them.
- Test: `tests/test_repeating_groups.py` (51). It covers:
  - the owner's case reproduced with the old pattern;
  - every editor route that adds or removes a group, on the 2-4 sample and
    a blank 2-4 report;
  - the first and last instance of every XSD-repeating group removed and
    re-added on all 12 D-1 samples.

### E-181 -- A blank report counted fatal findings on things it never shows (T-506, 2026-10-11)
- Symptom (owner, DR §4): an almost empty 2-4 unit report showed 160 fatal
  and 28 warning findings, most on fields that should not exist.
- Causes:
  - `templates.clear` kept the D-1 sample's empty claim blocks (defect rows,
    REAL_PROPERTY_INTEREST, comparable SALES_HISTORY, single-family HOA
    dues).
  - Relationships pointed at removed labels.
  - The Review Master judged the editor's copy rather than the file that
    ships.
  - No finding was tied to section visibility.
- Mechanism:
  - `templates._drop_guarded` / `_drop_unshown_repeats` / `_drop_dangling`
    tidy a blank under the schema guard; `drop_unclaimed` does the same for
    reports made before the fix.
  - `review.findings` runs H-1 on `delivery.as_delivered`.
  - `review.shown_in` uses the same B-1 calls as `form.build`
    (`section_shown`, `print_gate`, `switch_fields`). A finding on a section
    B-1 leaves out is Review ("not counted"), never Fatal or Warning.
  - Field-level "Display when" is deliberately not used: H-1 requires
    UAD1296 and UAD1138 unconditionally.
- Evidence: a new report gives 2-4 149/22 (was 160/28) and SF 129/17 (was
  143/23). The 12 D-1 samples stay 0/0/0. Harness unchanged.
- Test: `tests/test_applicable_findings.py` (55).
- Open: a value left in a section B-1 hides is still written to the
  delivered XML (DR §5 "excluded from output"). That needs a move-aside like
  `optional_sections` (T-1066).

### E-182 -- Comparable-grid "Name this row" rows spawned by themselves and wrote into the wrong row (T-1070, 2026-10-11)
- Symptom (owner, DR §7):
  - A blank "Name this row" sat under every named-row group: 5 on SF, 14 on
    2-4. Another appeared after each row named.
  - Custom-row descriptions were refused ("is an adjustment"), and their
    adjustments overwrote the group's first row.
  - Rename added a second name element; deleting a property's only row was
    refused.
- Cause:
  - `specs(every_row)` drew the unnamed template as a live row.
  - Named rows were copied into every repeated block.
  - Writes found a row by the field id its whole group shares.
- Mechanism:
  - The template prints only as "+ <B-1 label>"; a named row is a real text
    box with a hover ×.
  - Cells send item_name / container / line_type to
    `comparables.write_named`.
  - `Named.per_block` comes from the A-1 xpath.
  - `named_nodes` + `drop_named` (via `edit.remove_block`) handle rename and
    delete.
- Test: `tests/test_grid_rows.py` (10) and `test_grid_rows_browser.py`
  (Chromium). The printed grids are byte-identical on the 12 D-1 samples.

### E-183 -- Vehicle storage / garage did not save, and the garage had no size (T-1071, 2026-10-11)
- Symptom (owner, DR §8): a Garage had no input for its area, and its spaces
  were asked as Assigned/Owned/Unassigned. It never reached the grid, so
  13.000 stayed empty. In the grid, a garage replaced the driveway.
- Causes:
  - A table cell had one input, and a measure with a unit attribute was
    dropped.
  - New rows were appended after the empty insertion blocks that readers by
    position stop at.
  - The grid editor wrote every stacked line into instance 1.
  - A blank "Other" description created a typed block.
- Mechanism:
  - `form.cell_points` gives one input per data point a template-row cell
    prints, filtered by A-1 conditions, with unit measures included.
  - `form.decides_row`: the A-1 type that chooses a row's inputs
    (CarStorageType, SiteInfluenceType) relays out the form.
  - `_new_instance` fills the first wholly empty instance;
    `comparables._read` skips empty instances.
  - Stacked grid cells edit each line in its own block (Vehicle Storage,
    View | Range, Street | Surface, Heating, certifications).
  - A blank write with nothing to clear is a no-op.
- Test: `tests/test_vehicle_storage.py` (17). It covers the round trip
  through mismo.xml, the preview and the grid, a Chromium test of the grid
  editor, and every vehicle-storage value on the 12 samples.

### E-300 -- An integrated sketch printed no sketch space (2026-10-11)
- Symptom: D-1 SF1 p5 and SF5 p4 print the Sketch section's full-page box
  ("Sketch", "This is where the Sketch image would display."). Ours printed
  only "Measurement Standard ANSI" and ran on, a page short on SF1.
- Cause: the sketch space was drawn only from an IMAGE with category
  SubjectPropertyImprovementSketch / FloorPlan. Those two samples carry
  SketchExistsIndicator "true" and no such IMAGE.
- Authority: B-1 p162-163. With the indicator "true" the sketch "displays as
  an image in the space provided", and a sketch embedded by integrated sketch
  software needs no separate IMAGE or category.
- Mechanism: `form._section` adds the 7.002 space, captioned "Sketch", when
  the indicator is "true" and no sketch or floor-plan IMAGE exists. It uses
  D-1's wording, "image" rather than "photo". In the editor the box takes a
  dropped picture as the sketch (`data-category='sketch'`).
- Test: `tests/test_pagination.py::test_a_sketch_that_exists_has_its_space`,
  `::test_a_sketch_image_is_not_doubled`.

### E-301 -- "Sketch or Floor Plan Not Available": the whole Sketch section vanished (2026-10-11)
- Symptom: with SketchExistsIndicator "false" nothing of the Sketch section
  printed. No D-1 sample answers "false", so nothing caught it.
- Authority: B-1 p162, "The Sketch section always displays", and "If
  SketchExistsIndicator ... = "false", "Sketch or Floor Plan Not
  Available" displays" (Figure 7-1).
- Cause: C-1 sets the note in the left column. A column's italic note took
  its visibility from the item above it, and this one is first.
- Mechanism: `uad/spec/extract_italic_rules.py` now also reads B-1's "If X
  (FID: f) = "v", "<note>" displays." sentences (two in B-1: 7.000, and
  14.000, which is a value slot and unaffected). `form.note_displays`
  decides such a note from the document, and an `Item.stated` note counts as
  content. Result: "Sketch / Sketch or Floor Plan Not Available", no
  Measurement Standard ("displays when a sketch or floor plan is included").
- Test: `tests/test_pagination.py::test_no_sketch_prints_no_sketch_space`,
  `::test_a_sketch_that_exists_keeps_measurement_standard`.

### E-302 -- The land comparables map printed in Site Exhibits (2026-10-11)
- Symptom: D-1 MH1 prints "Map of Land Comparables" under Cost Approach
  Exhibits (p25). We printed it full page among the Site exhibits.
- Cause: A-1 gives LandComparableMap two report locations, 4.118.1 (Site
  Exhibits) and 25.059.1 (Cost Approach Exhibits), and `image_categories`
  kept the first. It is the only category A-1 places in two sections.
- Mechanism: `form.image_sections` lists every A-1 home a category has, and
  `form.image_section` takes the later home when its section prints, the
  earlier otherwise. B-1 p360 describes the map beside the land comparables
  it maps. `delivery._category_for` recognises both homes for an uploaded
  map.
- Test: `tests/test_pagination.py::test_the_land_comparables_map_prints_in_the_cost_approach`,
  `::test_the_land_comparables_map_falls_back_to_site`.

### E-303 -- Full-page images did not open a page (2026-10-11)
- Symptom: our Sketch section began at the foot of a page and carried its
  frame over under "(continued)". The Sales Comparison Map and other maps
  shared a page with what came before them.
- Authority: Appendix E p31. Photos "can start on same page as section";
  maps and sketches are full page (45 x 48 pica frame). In the D-1 PDFs every
  full-page image heads its page with only its lead-in above it, even with
  room to spare: MH1 p6 follows a page ending at 211 pt, MH1 p22 one at
  242 pt. That is 11 raster images plus the vector sketch boxes, 12 of 12
  samples.
- Mechanism: `flow.full_page_leads` finds each `ex full` exhibit and the
  block that opens its page. That is its run of headings ("Sales Comparison
  Map", "Site Exhibits"). An image with no heading of its own takes its
  section's tab when only the section's opening rows (at most `LEAD_IN`,
  120 pt) stand between them, as with the Sketch's tab and Measurement
  Standard. `plan` breaks there, under "(continued)" when the break is
  inside a section. What follows the image may share its page (SF1 p5).
- Test: `tests/test_pagination.py::test_a_full_page_image_opens_a_page_with_its_lead_in`,
  `::test_a_full_page_image_under_its_heading_carries_a_continued_tab`,
  `::test_photos_still_share_the_page`.

### E-304 -- The Scope of Work never opened its page (2026-10-11)
- Symptom: in all 12 samples the official Scope of Work text heads a page
  with no tab above it (Appendix E p79/p85 "Starts new page"; "TAB sets
  elsewhere"). Ours ran on under "Reconciliation (continued)" or
  "Revision History (continued)".
- Cause, in two parts:
  - "Certifications and Scope of Work" is in `NEW_PAGE_SECTIONS`, but the
    flag was set only on a section's tab, and this section opens with text.
  - `plan` honoured `newpage` only on tabs, headings and grids.
- Mechanism:
  - `form.build` puts the flag on the first block of a new-page section that
    has no tab.
  - `plan` honours it on any block, opening a page with no "(continued)" tab
    and clearing the section to continue (its tab is set later).
- Test: `tests/test_pagination.py::test_the_scope_of_work_and_the_certifications_open_pages`,
  `::test_a_section_opening_with_text_opens_its_page_without_a_tab`.

### E-305 -- Certifications: tab orphaned at a page foot, and its own page (2026-10-11)
- Symptom: the Certifications tab sat alone at the bottom of the Scope page,
  with its H1 and first paragraph carried to the next page.
- Causes:
  - A tab kept only with the next block, so "tab + H1" fitted while the H1's
    own first line did not.
  - The same holds for any heading followed by a heading.
- Mechanism:
  - `flow._keep`: a heading keeps with every heading straight after it and
    the first line of what they head.
  - Certifications is in `NEW_PAGE_SECTIONS`. Appendix E is silent and C-1
    draws the tab mid-page (Layout p41). Yet all 12 D-1 samples open a page
    with it, with 90-100 pt free above the footer, while the same samples
    set other tabs with two lines under them (Functional Obsolescence: MH1
    p12, SF3 p9, SF4 p10). Recorded as D-1 practice, not an E rule.
- Test: `tests/test_pagination.py::test_a_tab_keeps_with_its_heading_and_first_line`.

### E-306 -- A grid moved off a page that held only its section's tab (2026-10-11)
- Symptom: Co-op1 printed a page holding nothing but the "Sales Comparison
  Approach" tab. The grid was moved whole to the next page under
  "(continued)".
- Cause: `at_top()` counted only a "(continued)" tab as nothing. The page's
  own new-section tab made it "not at the top", so a table that fits a page
  was moved rather than split.
- Mechanism: a page holding only tabs is at the top. D-1 Co-op1 p12 sets
  the grid straight under the tab and splits it.
- Test: `tests/test_pagination.py::test_a_grid_under_a_lone_tab_is_split_not_moved`.

### E-307 -- Two print-only fixes on the Scope and Sketch pages (2026-10-11)
- **Market value footnote.** Appendix E p80 sets the Definition of Market
  Value's footnote ("*Adjustments to the comparables ...") as FN, 8/10
  Myriad Pro (p25). C-1 records it at 8 pt, and it is the only plain
  paragraph of fixed wording below 9 pt. We set it at body size, so the
  Scope page ran 10-40 pt long. `_fixed_text` gives it `fn`, set as
  `.txc.kp.fn` 8/10.
- **Sketch caption.** "Sketch" (or "Floor Plan") printed twice: once from
  the C-1 7.002 table as a text row, and again on the exhibit's frame (D-1
  SF3 p6, Condo1 p5, MH1 p6 print it once). A C-1 table whose every cell is
  a picture's category or caption is that picture's frame. Only 7.002
  qualifies. In print it is left to the exhibit (`form._picture_frame`); the
  editor is unchanged.
- Test: `tests/test_pagination.py::test_the_market_value_footnote_is_set_as_fn`;
  the Sketch galley text in `::test_a_sketch_that_exists_keeps_measurement_standard`.
- Page counts after E-300..E-307 (official / before / after): Condo1
  22/22/23, Condo2 24/26/26, Co-op1 18/18/19, MH1 30/25/27, MH2 20/21/22,
  SF1 21/20/21, SF2 22/21/22, SF3 23/23/25, SF4 22/23/24, SF5 19/16/18,
  2-4 29/29/30, 2-4 S2 26/28/29. Exact matches fall from 4 to 2: the earlier
  four were coincidences, since none had Sketch, Scope of Work or
  Certifications heading a page, and now all 12 do. What remains is our
  content running taller than D-1's (vertical metrics, T-034). Example: SF3
  p6, where Dwelling Exterior misses the sketch page by 0.6 pt because our
  front-photo box measures 172.6 pt against D-1's ~160 pt.

### E-308 -- A tab's own placeholders printed in the section before it (2026-10-11)
- Symptom: D-1 MH1 has nothing between its Manufactured Home Exhibits and
  the Unit Interior tab. Ours printed a stray "Rec Room/Garage" line there.
- Cause: C-1 p14 sets the Unit Interior tab's placeholders ([Outbuilding
  Type] - [Structure Identifier] - [Unit Identifier], slots 10.000-10.002,
  y 52 pt) on the tab, which puts them ahead of it in reading order. The
  section split gave them to the section before, where 10.000
  (OutbuildingType) printed as text.
- Mechanism: `form.build` skips a slot that C-1 sets above its page's first
  tab when the slot's field belongs to that tab's section.
  `section_instances` already composes them into the printed title ("Unit
  Interior - Building 2 - Unit 2"). The only other pre-tab slot in C-1,
  29.016 on p41, is Scope of Work text and stays.
- Print only. In the editor `_section` names these slots as the unit's
  controls ("Unit Interior: Outbuilding Type"). The first version of this
  fix skipped them in the editor too, which removed MH1's three controls;
  restored in the next commit.
- Test: `tests/test_pagination.py::test_a_tabs_own_placeholders_do_not_print_in_the_section_before`,
  `::test_the_editor_keeps_a_tabs_placeholders_as_controls`.
- Checked, not a rule: D-1 MH1 sets the Retailer's and Manufacturer's
  Invoices full page (one page each) but the HUD Data Plate, a more portrait
  image, as a photo. Appendix E p31 leaves image size to "properly display
  the content", so this is the producer's judgment, not encoded. Nor is
  B-1 p187's exhibit order (Data Plate, Labels, others): D-1 MH1 puts
  "Foundation", one of the others, first.

### E-309 -- Vehicle Storage printed the first storage type above its own table (2026-10-11)
- Symptom: on all 12 samples our Vehicle Storage began with a loose line
  ("Carport", "Parking Garage", "Driveway") above the Storage table. Every
  D-1 sample sets the table straight under the tab.
- Authority: B-1 p228. "When CarStorageType (FID: 13.000) = "None",
  display "None"; the Vehicle Storage detail table and the Apparent Defects,
  Damages, Deficiencies subsection does not display" (Figure 13-1). Any
  other storage is the table's (13.001-13.003).
- Cause: slot 13.000, a value set under the bar, printed its first value
  like commentary.
- Mechanism: `extract_italic_rules.py` reads B-1's "When X (FID: f) = "v",
  display "T"[; the ... does not display]" sentences (`"shape": "value"`;
  B-1 has three: 4.078, 13.000, 13.004). `form.value_slot` prints T only
  when the subject's values are all v, and nothing otherwise.
  `_hidden_by_rule` drops what the sentence says does not display: the next
  table, and the subsection it names. This is print only; the editor keeps
  the table to fill. 4.078 (a table cell) and 13.004 (an italic note) do
  not pass through value slots and are unchanged.
- Test: `tests/test_pagination.py::test_vehicle_storage_prints_no_storage_type_above_its_table`
  (12 samples), `::test_no_vehicle_storage_prints_none_alone`.

### E-310 -- An ADU in an outbuilding printed before its outbuilding (2026-10-11)
- Symptom: D-1 SF3 prints "Outbuilding - Standalone ADU" and then "Unit
  Interior - Standalone ADU - Cottage". We printed the ADU's Unit Interior
  straight after the primary dwelling's, before Functional Obsolescence.
- Authority:
  - B-1 p377 orders the report "Dwelling Exterior - Unit Interior (... each
    living unit ... in Dwelling) - Outbuilding - Unit Interior (repeat Unit
    Interior for each ADU ... in Outbuilding) - Vehicle Storage".
  - B-1 p30 sets an ADU "after the applicable Outbuilding section".
- Cause: sections print in C-1's order, where Unit Interior precedes
  Outbuilding. Only dwellings interleaved their units.
- Mechanism: in `form.build`, a unit whose PROPERTY_UNIT stands in an
  Outbuilding IMPROVEMENT is printed right after that outbuilding's section,
  when the Outbuilding section prints. Outbuildings are keyed by
  `bind.stable_path`: lxml proxies have no stable `id()`. An ADU in the
  dwelling (SF4) stays with the dwelling. The other 10 samples are
  unchanged. Applies to print and editor alike.
- Test: `tests/test_pagination.py::test_an_adu_in_an_outbuilding_follows_its_outbuilding`,
  `::test_an_adu_in_the_dwelling_stays_with_the_dwelling`.

### E-311 -- Every section started 2.6 pt low; H2s and H1s under tabs ran long (2026-10-11, T-1150)
- Symptom: our pages drifted down against D-1, section by section.
  Dwelling Exterior missed the sketch page by 0.6 pt (SF1, SF3), and
  "Legal Description" spilled to page 3 on SF1.
- Method: compare the gap from each heading's text to the next line, against
  the same heading followed by the same line in the official PDF. A
  scratchpad aligner scores every page that starts on the same line as
  D-1's: the mean |dy| of matched lines.
- Found, and set from D-1 (constants beside `form.BAR`; the planner's
  `TAB_H` follows `TAB_BELOW`):
  - **Under a section tab.** The first line sat 27.0 pt below the tab's
    text; D-1 sets 24.4 (the commonest gap, 43 tabs). Appendix E p19 fixes
    the tab's 15 pt height and the 19.5 pt above it, not the space below.
    `TAB_BELOW` 10.8 -> 8.2 pt.
  - **An H1 straight under a tab** (Prior Sale and Transfer History,
    Reconciliation, Certifications) was 38.5 pt below the tab; D-1 sets
    28.1. `H1_AFTER_TAB` = 3.9 pt.
  - **Under an H2 rule.** A contact block's first row was 18.0 pt below the
    H2; D-1 sets 15.3 (20 of 20). A table head was 20.0 below; D-1 sets
    15.0. `H2_BELOW` 2.8 -> 0 pt.
  - **A photo that opens its column** (the Dwelling Exterior front photo)
    started 10.6 pt lower than D-1's, which sets it 3.0 pt under the first
    row. `PHOTO_FIRST` = 5.9 pt. A photo after rows keeps 13.6 pt: the
    Summary's matches D-1 within 0.3 pt.
- Result:
  - SF1 tab-to-first-line, paired with D-1: median difference 4.0 -> 0.11 pt.
  - On the ten v1.4 samples' aligned pages, median line offset
    10.1 -> 2.4 pt.
  - Lines within 2 pt: 18% -> 46%.
  - SF3 25 -> 24 pages (D-1 23). Word diff 7122 -> 7094.
- Still open (T-1150):
  - H2 -> table head is +2.2 pt.
  - Kitchen and Bathroom Details' head sits lower in D-1 (a two-line head).
  - H1 -> first paragraph is -2.8 pt (Certifications).
  - The Contact Information H1 -> Client/Lender H2 is +4.0 pt.
- Test: `tests/test_pagination.py::test_tabs_and_headings_sit_where_d1_sets_them`
  (Chromium, against SF1's official PDF).

### E-170 -- The editor showed a supervisory appraiser's fields though none was chosen (2026-10-11)
- Symptom (the owner's brief, DR §8): every new report's Assignment
  Information showed the Supervisory Appraiser and Significant Real
  Property Appraisal Assistance subsections with empty fields (2.032-2.046
  and the rest), and Certifications showed "Supervisory Appraiser
  Certifications". Nobody had added such a party.
- Cause: B-1 shows these subsections only when the party exists. p106 says
  "If there is no Supervisory Appraiser, the subsection does not display";
  p108 has the same for Significant Real Property Appraisal Assistance; p396
  gates the supervisor's certifications. The print followed these rules, but
  the editor showed every subsection so it could be filled in, and so it
  offered a party nobody chose.
- Mechanism:
  - `uad/spec/extract_party_gates.py` reads those B-1 sentences and the
    PartyRoleType each names into `spec/party_gates.json`.
  - In the editor, a gated subsection without its party shows its heading
    and "+ Add <party>", and the subsections it drives stay out.
  - POST /cases/{id}/parties adds the party (fields follow);
    DELETE /cases/{id}/parties/{role} removes it ("× Remove", confirmed).
  - The control is also in the side panel's Add list.
- Test: `tests/test_party_gates.py` (3): the gates come from B-1; a blank
  report has no supervisor fields; added, its fields and certifications
  follow, and removed they go. Neither changes the schema-error count.
  Chromium: add, then remove after the confirmation dialog.
- The print is unchanged: the gate is editor-only.

### E-171 -- The editor showed fields the report's own answers rule out (2026-10-11)
- Symptom (the owner's brief, DR §5):
  - Zoning "Legal" still offered Reasons Illegal;
  - no renewable energy component still offered its type, ownership and
    financing;
  - a listing "None" still offered the listing's details;
  - a single-family report still offered Project Information.
- Cause: the print applies each field's B-1 display rule
  (`field_rule_hides`) and drops empty fields. The editor bypassed both so
  that everything stays answerable, gates included.
- Mechanism: `form.edit_hides`. In the editor a field is left out when
  either:
  1. its B-1 display rule is decided against it by another answer, exactly
     as the print leaves it out; or
  2. it is empty, and A-1's "IF ..." for its principal data point is known
     false by a gate the report answers once (zoning compliance, the three
     "exists" indicators, "listed within the previous year"). A condition
     on a repeating block (each amenity, each influence) is the block's and
     is not applied.

  The gate question stays. A field that is its own gate (10.050
  Accessibility) stays. A write that changes which fields show returns
  `relayout`, so the reasons come back the moment zoning becomes
  "Illegal".
- Validated first: a blanket A-1 gate was tried and faulted the samples.
  Values present in a gated-off field appeared in condo1's influences and
  amenities, because those conditions are per instance. Hence the two
  limits: single-valued gates and empty fields only. On all 12 samples the
  editor never hides a field holding a value unless the print hides it too.
- Second trap, found by the full suite (`test_add_list`): "answered once"
  was read as "fewer than two values", so SF1's single, non-water site
  influence removed Frontage and with it the Water Frontage table's
  "+ Add". Its gate (`SiteInfluenceType`) lives in a repeating block
  (SITE_INFLUENCES/SITE_INFLUENCE), and the next influence added could be
  a body of water. Fix, all read from A-1:
  - a gate whose xpath has a MISMO repeat (`bind.repeating_container`)
    decides nothing (`form._point_repeats`);
  - a gate with no value decides nothing, unless every field that asks it
    is itself left out by its own gate. No renewable energy component
    means no ownership question, so no financing (6.003). No field asks
    PrivateAccessIndicator, so the Water Frontage fields stay;
  - quoted values are not data point names ("LegalNonconforming").
- Not changed: the comparable grid's Renewable Energy / Certification /
  Rating rows. B-1 says "When false display None, when true display ...",
  so they always print, and they are where each comparable's answer is
  entered.
- Test: `tests/test_edit_visibility.py` (17) and `tests/test_add_list.py`.

### E-172 -- A report could contradict itself, or lean on an addendum, without a word (2026-10-11)
- Symptom: three cases passed review in silence:
  - a commentary reading "See attached addendum";
  - a Market Value Condition of "As Is" over a defect whose Recommended
    Action is Repair;
  - an Overall Condition of C1 on a house that is not new construction.
  B-1's Usability supplement (items 6 and 10) asks the software to alert
  the appraiser in each case. H-1 checks only the other direction
  (UAD1624, UAD1732: Subject to Repair needs a Repair defect).
- Mechanism: `uad/spec/extract_usability.py` reads the supplement's three
  exact statements into `spec/usability.json`. Every value is resolved
  against A-1:
  - "Recommended Action" and "Market Value Condition" are resolved by label
    to their data point;
  - "Subject to Completion" becomes the enumeration "Completion";
  - "Kitchen and Bathroom" becomes RoomType Kitchen / FullBathroom /
    HalfBathroom;
  - the redisplay FIDs 22.11.02 and 1.031 are confirmed to be 15.005's own
    data point, so it is entered once.

  `uad/usability.py` runs them (U6, U10.1, U10.2). `review.build` lists
  them as Warnings, source `usability`, on the field that fixes them.
- The owner's DR 6.5 checks with no spec rule behind them sit in
  `uad/owner_checks.py`, source `owner`, and each says it is not a GSE
  rule:
  - O1: on a purchase, a seller who is not an owner of public record;
  - O2: on a refinance, no borrower on title;
  - O3: a comparable sold after the effective date.

  Two of the owner's list are H-1's already:
  - signature before inspection (UAD1536 + UAD1557);
  - the area total cannot be checked for *equality*, because A-1 defines
    it to include common area (D-1 2-4 Scenario 2: 5,282 against 4,760).
    It can never be smaller than the units' above-grade finished area, so
    O4 warns when it is (added later the same day).
- One-click fixes (T-510), offered only where the specification leaves one
  answer:
  - U10.1 with a single kind of action: "Make it 'Subject to Repair'" (the
    A-1 value named SubjectTo<action>);
  - U10.2 on a field the report holds once: "Make it 'Yes'" for New
    Construction.
  - Rooms and mixed actions get no button.
  - The fix shows on the Review panel row and in the field guide. Clicking
    writes the value through the normal field PATCH, after which the
    report and the review refresh.
  - Chromium e2e passed: As Is -> Subject to Repair, and the warning
    clears.
- Not done: item 9 (prohibited / veiled language). It cites the GSE
  Selling Guides, which are not in the repo. No invented word list.
- Validated first: all 12 D-1 samples raise nothing from either module.
  The 12 also show the pattern O1 / O2 rest on:
  - every purchase seller is the same MISMO party as an owner;
  - every refinance borrower is on title.
- Test: `tests/test_usability.py` (22), `tests/test_owner_checks.py` (15).

### E-173 -- One photograph filed under several categories printed once per category (2026-10-11)
- Symptom (T-127): MH1's waterfront photo printed three times. Each copy
  sat in its own box under a bare category name ("Water Frontage", "Site
  Influence", "View - Lake Virginia"). D-1 prints the photo once as "Site
  Influence - Water Frontage - View - Lake Virginia". The same fault
  appeared in five more samples: SF1, SF3 and SF4 vehicle storage and
  decks, MH2's kitchen and living room, and the comparables map in
  Condo2 and 2-4 Scenario 2.
- Cause: the XML has one IMAGE per category, all pointing at the same
  file, exactly as B-1 p59 (Image Data, Scenario 1) prescribes. The
  renderer drew one exhibit per IMAGE.
- Mechanism: `form._shared_exhibits` (print only), applied per section to
  IMAGEs sharing an ImageFileLocationIdentifier.
  - Category exhibits:
    - headers are in the order of B-1's exhibit table, by Report Field ID
      (`form.image_fids`, from A-1's Report Location);
    - each caption follows its header;
    - a caption the next header repeats prints once (Condo2 "Site
      Influence - View - Golf Course").
  - Exhibits titled by what they are of (rooms, vehicle storage,
    amenities): in document order, each after the first without the part
    it shares with the first. MH2 prints "Level 1 - Kitchen - Living
    Room"; SF3 prints "Deck - Deck 1 and Deck 2" once.
  - Rental and GRM comparable maps that are the sales map's file do not
    print. B-1 p60 Scenario 2 applies, and D-1 Condo2 and 2-4 Scenario 2
    print the one map as the "Sales Comparison Map".
  - The editor keeps one box per IMAGE, each with its own caption and
    remove.
  - The same file in two sections prints in both (Scenario 4: SF1's
    media room appears under Unit Interior and under Amenities).
- Validated first: every exhibit title the report prints, in all 12
  samples, was checked as a line in the D-1 PDF.
  - Before: 18 of 319 titles were not in D-1.
  - After: 0 of 299, once curly apostrophes are matched.
  - A weaker line match had passed "Driveway" and "Garage" because they
    are also grid cells. The test requires the title to stand alone.
- Not done: exhibit *order*. D-1 orders neither by XML nor by Field ID
  everywhere: SF2 prints Plat Map before Property Access, and MH1 prints
  Dock before Pier. Ours stays in document order; handed to the
  pagination session.
- Test: `tests/test_shared_exhibits.py` (24).

### E-174 -- The Market section's search figures were typed by hand (2026-10-11)
- Symptom (T-1075; the owner's brief, DR 8): the appraiser counted the
  MLS search and typed in eleven numbers. These are the 17.005-17.015
  active, pending and sold counts, their median days on market, and their
  lowest, median and highest prices. A slip there is a contradiction no
  reviewer can trace.
- Mechanism: `uad/market_search.py` counts them from the MLS export (CSV)
  exactly as A-1 defines each figure.
  - Status decides the inventory: active, pending or sold.
  - Sales count only when closed within the lookback months (17.011)
    before the effective date.
  - A median of an even count is the mean of the middle two.
  - Amounts are whole dollars, as the samples hold them.
  - MLS header names are matched from a list of common ones. That list is
    tooling, not a specification.
  - A file whose columns cannot be told apart is refused with the reason.
  - Each row that does not count is named (a sale outside the window, a
    withdrawn listing).

  `POST /cases/{id}/market/search` returns each figure beside the one the
  report holds. `?apply=true` writes them all through `_write_checked`, or
  writes none.
- Validated first: a search shaped like the one D-1 SF1 describes (two
  active, one pending, 35 sales in 24 months) reproduces all eleven of
  SF1's published figures.
- Not done: no editor control yet (the lead owns the shell); 17.016
  (distressed competition) and 17.004 (the search criteria text) stay the
  appraiser's.
- Test: `tests/test_market_search.py` (5).

### E-175 -- A photo's altitude shipped without its unit; a camera's local time shipped as UTC (2026-10-11)
- Symptom (T-906): `delivery.exif` read ImageDatetime and
  AltitudeElevationLinearMeasure from the photograph, but two things were
  wrong:
  - the altitude was written bare. A-1's Implementation Note says "Deliver
    @LinearUnitOfMeasureType when AltitudeElevationLinearMeasure is
    provided", and D-1 Condo1 carries `LinearUnitOfMeasureType="Feet"`;
  - the EXIF local time was stamped "Z" as if it were UTC.
- Mechanism:
  - `delivery._set_meta` sets the unit attribute wherever an IMAGE takes
    the EXIF facts (`UNIT_OF`: the altitude, in feet, as `exif` converts
    it).
  - `exif` moves the time to UTC by the camera's own OffsetTimeOriginal
    (EXIF 2.31) when present. Without one, the time is delivered as taken.
    Nothing is invented for a photo that records nothing.
- Test: `tests/test_photo_exif.py` (4). One of them is a delivered SF1
  package with an appraiser's photo: the altitude is 25 Feet, the time is
  UTC, and the schema is valid.

### E-184 -- A data source picked in the editor was refused, and per-unit answers went to the first unit (T-1072, 2026-10-11)
- Symptom (owner, DR §8):
  - The Subject Listing "Data Source" (19.001) would not select. 17.018,
    10.009 and 25.052 behaved the same way.
  - After a first source, changing, adding or removing one was refused.
  - The round-trip test found more:
    - a Yes that B-1 prints nothing for came back blank after reload;
    - Building 2's and Unit 2's controls wrote into Building 1 / Unit 1;
    - a conditioned answer was refused without saying what it waits for.
- Cause: A-1 ties these sources by arcrole
  (DATA_SOURCE_IsDataSourceFor_<TARGET>; D-1 SF5, MH2 and Condo1).
  `sources.write` stored the source with its link, but the read-back (api,
  autofill, provenance) read the first DATA_SOURCE in the list. Controls in
  sections drawn per dwelling or unit carried only the field id.
- Mechanism:
  - `edit.source_target` + `sources.read` / `groups` read through the
    link, and `sources.write` keys a list row by its DATA_SOURCE.
  - `form._scoped` + `data-iscope` → `edit.section_scope` send the
    section's scope with each write.
  - `edit.unmet_gate` names the answer to give first.
  - `form.shown_pairs`: the editor shows a value B-1 prints nothing for.
  - Reconciled with T-1066 in the merged tree:
    - `form.source_of_answer`: a data source tied to an answer hides with
      that answer;
    - `form._waiting_for`: a field waiting for a hidden question hides with
      it.
- Test: `tests/test_every_choice_saves.py` (17). It round-trips 348 choices
  on a blank SF report and 430 on a blank 2-4 report; the known gaps are
  listed with reasons (T-1204). Also `tests/test_choice_saves_browser.py`
  (2).

### E-185 -- Checkbox problem outlines sat off the box (T-125, 2026-10-11)
- Symptom (owner, DR §8, screenshot 05): the red/amber outline round a
  Quality/Condition checkbox was offset from the box.
- Cause: each box is a Wingdings 2 glyph in a 12pt-wide inline-block span.
  The glyph plus its letter spacing (15.38pt) overflowed the span, and line
  height 10pt put the ink off the box's middle. Every mark was drawn round
  the span, not the glyph's box. The editor's pitch also differed from
  print.
- Mechanism:
  - `form.box_glyph()` reads the box's position and size from the embedded
    Wingdings 2 file with fontTools (nothing hand-typed).
  - `form._box_marks_css()` (editor only) adds a `::before` overlay placed
    from that geometry. Problem outlines, the unanswered tint, import
    green, the highlight and the found-flash are drawn on the overlay.
  - The fixed-width span is gone, so the editor's pitch now equals print.
  - Ticks of boxes drawn on their own are centred (tick cells, rental
    pairing, rent schedule units).
- Test: `tests/test_checkbox_centre.py` (Chromium, device scale 4) checks
  110 boxes on sf1 and 2-4, in the editor and the preview: outline and tint
  centred within 0.5 px.

### E-186 -- A reader could see the case document empty while it was being saved (2026-10-11)
- Symptom: `tests/test_grid_rows_browser.py` failed about one run in three
  with "Document is empty" reading mismo.xml.
- Cause: `Store.save_tree` (and case creation) truncated mismo.xml and then
  wrote it. Anything reading in that window saw an empty file: another
  request, the background renderer, the vault, a test.
- Mechanism: `cases._write_atomic` writes the document beside it and
  renames it over the old one (`os.replace`). A reader sees the old file or
  the new one, never a half-written one. A failed write leaves the old
  document and no temporary file.
- Test: `tests/test_atomic_save.py`; `test_grid_rows_browser.py` passes 6
  runs out of 6.

### E-187 -- The location map never reached the report: "unknown error", and Save to report did nothing (T-416, 2026-10-11)
- Symptom (owner, DR §8/§13): "Generate map" answered "unknown error", and
  "Save to report" changed nothing.
- Causes:
  - POST /maps could draw only with the server's own Chromium. The live
    site has none, and a failure escaped as a bare 500, which the editor
    showed as "unknown error".
  - Save reloaded the tool under the appraiser, and a failed export timed
    out silently.
  - `checkFresh()` dropped a change made while the report's first layout
    was still running.
  - The map tool exported before it had read the case ("Nothing is placed
    on the map yet").
- Mechanism:
  - With no server map tool, or a failed one, the routes answer
    `{state:"browser", problems:[why]}`. The editor then draws with the
    same tool in the appraiser's browser (`ui/map/draw.js`) and saves
    through /maps/image.
  - Every failure is shown in the server's own words (`apiError`).
  - The tool reports export failures at once and is never reloaded under
    the appraiser.
  - `checkFresh` remembers changes made during the first layout (`S.again`).
  - The tool holds `body[data-seeding]` until it has read the case, and
    both Save paths wait for that (`whenRead`).
- Test: `tests/test_location_map.py` (20, incl. the 12 D-1 samples) and
  `tests/test_location_map_browser.py` (6, client-layout mode). The browser
  tests cover the map pixel-exact in the PDF and in the ZIP, with the
  IMAGE category from engine/spec.
- Trap: under Playwright's sync API, route handlers run only inside
  Playwright calls. Poll with `page.wait_for_timeout`, never `time.sleep`.

### E-188 -- The header's problem counts went stale (phase 2 S0a, T-1206, 2026-10-11)
- Symptom: the owner saw 144 fatal in the header while Sign-off said 143,
  and the header kept an old count after edits.
- Cause: `S.review` was set in five places, and only some of them redrew
  `#stat`.
- Mechanism: `setReview()` is the one place a review lands. It redraws the
  rail, markers, `drawStat()` and Sign-off, and emits a `review` event for
  the shell.
- Test: `tests/test_shell_core.py::test_e187_header_counts_follow_every_review`
  and `::test_review_event_from_each_of_the_five_paths`.

### E-189 -- Export ZIP on the live site never used the in-browser export (T-1206, 2026-10-11)
- Cause: `#zip` had two click handlers, and the second replaced the first,
  which drew the PDF in the browser for a serverless host.
- Mechanism: one handler.
- Test: `tests/test_shell_core.py::test_e188_export_zip_has_one_handler`.

### E-190 -- Problem outlines disappeared after a layout swap (T-1206, 2026-10-11)
- Cause: a swapped-in report frame did not get the marks message again
  until the next review.
- Mechanism: `UADShell.frames.keep` / `replay`; marks are replayed at
  `ready` and in `finishSwap`.
- Test: `tests/test_shell_core.py::test_e189_outlines_survive_a_layout_swap`.
