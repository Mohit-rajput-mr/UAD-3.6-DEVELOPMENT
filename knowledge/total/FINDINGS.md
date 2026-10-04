# WinTOTAL's UAD 3.6 form — how it is built, validated, signed and delivered

Investigated 2026-09-28 on a blank report ("sample blank"), form
`UAD-3.6-AR-1.000`, web engine build **0.0.1.3848** (bundle SHA-256
`6e606f31…a91b`, the same build the three-unit rowhouse case was filled on).
Read-only: nothing in TOTAL was changed, no native method was called.

Sources: the running form over CDP, and the form's own served bundle
(`https://uadwebengine.alamode.com/0.0.1.3848/index.js`). The binaries of the
desktop application were **not** decompiled; what WinTOTAL does natively is
recorded only as far as the form's side of the conversation shows it.

Everything below is labelled:
**[C] confirmed** — read in code or reproduced; **[O] observed** — seen on a
real case, cause not fully proven; **[I] inferred** — reasoned, not shown;
**[U] untested** — needs the experiment named.

The extracted tables behind these numbers are in `builds/0.0.1.3848/`
(regenerate with `total-bridge/tools/form_model.py`).

---

## 1. The two halves: a web form inside a desktop application

- **[C]** The 3.6 report is a web application (`uadwebengine.alamode.com`)
  hosted in CefSharp inside WinTOTAL. One script bundle (11.8 MB) plus an
  environment file (`static/web.env.config.json`).
- **[C]** WinTOTAL exposes a .NET object, `CefConnector`, to the page. The form
  reaches the desktop through `CefConnector.handleEvent(...)` and a generic
  `FireEvent(name, …)` channel (35 event names: `ValidateSchema`,
  `RemoveSignatures`, `generatepdfresult`, `mismoexportgenerationresult`,
  `LeaveField`, `PhotoChanged`, `GeocodeAddress`, …).
- **[C]** WinTOTAL drives the form by calling
  `TotalFormsEngineConnector.ExecuteReportAction(action, …)`. 42 actions,
  including `openreport`, `savereport`, `loadform`, `getreportdata`,
  `createtotalxml`, `xmlgenrequest`, `getmismoxml`, `importmismoxml`,
  `pdfgenrequest`, `getpdfhtml`, `signreport`, `unsignreport`,
  `loadsignature`, `geteandowarningcount`, `toggleeando`,
  `addrepeatableobject`, `removerepeatableobject`, `setfieldtext`,
  `getfieldtext`, `setfocustofield`, `setactivesectionkey`, `addphoto`,
  `setimage`, `processschemavalidationresult`. Full list: `connector.json`.
- **[C]** Signing, saving, PDF and XML generation and the ZIP are therefore a
  conversation: WinTOTAL asks, the form produces (XML text, PDF HTML, a count),
  WinTOTAL decides and writes files.
- **[C, observed with `tools/observe.py`]** When a picture is dropped the form
  fires `PhotoChanged` and WinTOTAL answers with `SetImage` + `SetFieldText`:
  **WinTOTAL stores the picture files itself**; the form holds references. On
  `FieldsChanged` WinTOTAL pulls the whole report (`GetReportData`) — its save /
  sync path. Opening a report file (`OpenReportXml`) triggers `PostLoadForm`,
  answered by `loadquicklist`. The E&O schema gate is WinTOTAL's
  (`ValidateSchema` → `processschemavalidationresult`).

## 2. The data the form holds

- **[C]** 4,482 controls; 2,848 distinct field names; 1,227 distinct report field
  IDs (`fmid`, the A-1 "Report Field ID" stamped on each control).
- **[C]** **1,139 controls exist only inside templates** — the dwelling
  exterior, unit interior, outbuilding and manufactured-home sections, the
  lien tables, the grid columns, the reconciliation/summary per-structure
  blocks. They do not exist in a report until Report Setup (or an import)
  creates the structure. A "blank form" read therefore never shows them; this
  is why earlier cases looked complete on screen while conditional data was
  missing.
- **[C]** **568 controls live in popups** (191 popups, opened by 207 trigger
  fields): detail pickers, "Other — describe" boxes, amenity and feature
  details. A value that belongs in a popup is invisible on the page.
- **[C]** 196 repeatable groups, each with a minimum and maximum
  (`repeatables.json`). Comparable grids: sales 3–24, rental property 1–24,
  rental unit 1–24, GRM 3–24.
- **[C]** 54 shared pick lists; 557 fields with default values; every select
  field's allowed items are in `datafields.json`. A value not on a field's
  list is not stored as that choice.
- **[C]** The Report Setup tree (buildings → units, ADUs, outbuildings,
  manufactured home) lives in a *section manager*, not in data fields. A
  building's `StructureIdentifier` is written from the section's Description
  (`CreateSubjectPropertyDwellingExterior`), which is why setting
  `DE1_SECTION_DESCRIPTION` alone did not satisfy UAD-1091.
- **[C]** The order sheet (`order-1`, 171 `ORD_` fields) is a separate section.

### What makes the form change shape

**[C]** These fields and structures decide which sections, templates and rules
apply (values from `datafields.json`):

| Driver | Field(s) | Values |
|---|---|---|
| Inspection (full / exterior / desktop / hybrid) | `APPRAISER_SPI_EXTERIOR` 2.021, `APPRAISER_SPI_INTERIOR` 2.022 (and `SUPERVISOR_SPI_*`) | Physical, Virtual, No Inspection |
| Attachment | `ATTACHMENT_TYPE` 3.004 | Attached, Detached |
| Units | `UNIT_EXCL_ADU` 3.005, unit-interior sections, ADU flags | count |
| Project | `PUD_YES/NO` 3.010, project-information section, `…_SITE_PROJECT_TYPE` | PUD, Condominium, Cooperative, Condop |
| Structure design | `DE#_STRUCTURE_DESIGN_TYPE` 8.002 | High-rise, Low-rise, Mid-rise, Rowhouse / Townhouse, Semi-Detached |
| Rights | `PROPRIGHTSAPPR` 3.019 | Fee Simple, Leasehold |
| Government loan | `GOV_AGENCY` 2.008 | FHA, USDA, VA |
| New construction | `NEWCONST_YES/NO` 3.017 | |
| Supervisor | `HAS_SUPERVISOR`, supervisor contact count | adds the supervisor signature block |
| Other forms | `FORM_COMPLETION_1_000`, `FORM_UPDATE_1_000` | Completion Report, Appraisal Update |

**[U]** Which rules and sections each *combination* switches on is not yet
measured. Planned: set the blank report to each configuration and record the
visible sections and the field-validation findings (ARCHITECTURE.md, phase 2).

## 3. The MISMO ↔ field table (the join key for everything)

- **[C]** The bundle carries a table (in the module that turns an E&O finding's
  XPath back into a field) mapping **642 MISMO data points** to **2,002 field
  placements**: field name, section, report field ID, and the specification's
  own **UID** (e.g. `1500.0125` → `SIT_COMPLIANCE`, `SUM_ZONING_COMP`,
  `GSU_SITE_ZONE_COMPLIANCE`, `GC#_SITE_ZONE_COMPLIANCE`), with repeat keys
  and grid prefixes. Saved as `uid_map.json`.
- **[C]** The UIDs are the A-1/H-1 UIDs our engine already uses, so an H-1
  finding, a value in our XML and a TOTAL field join directly.
- **[C]** Of the spec's 678 data points, 642 have TOTAL fields. **36 have none**
  — TOTAL derives them from structure or settings (latitude/longitude,
  `SalesComparisonApproachIndicator`, `RentScheduleIndicator`,
  `ReconsiderationOfValueIndicator`, `GovernmentAgencyAppraisalIndicator`,
  image file data, software identifiers, …).
- **[C]** Of H-1's 728 rules, **583 point at a TOTAL field; 145 do not**
  (114 fatal; 90 are "Does Not Display"). When one of those fails there is no
  field to click: the cause is a setting or a structure elsewhere. A
  diagnostics layer has to know what drives each of them.

## 4. Field validation (the E&O panel's first stage)

- **[C]** 759 validation registrations in 28 validator classes (one per
  section family). Each names a field, a trigger and optional dependants:
  **LeaveField 411, SelectClosed 320, HidePopup 25, ValueChanged 3**
  (`validators.json`); messages in `rtv_messages.json`.
- **[C]** Most rules are conditional ("required based on related selections"):
  the condition is code, so which fields are required depends on the
  configuration and on other fields' values.
- **[C]** An E&O run executes all rules globally
  (`ExecuteGlobalRtvAnalysis(Global)`: preprocessor → all calculations → every
  rule → custom validations) before anything else.
- **[O]** On the rowhouse case, comparable unit areas written into the data
  layer stayed "required" until each was typed and the cell left; typing
  cleared them. The global run executes every rule, so the likelier cause is
  that the rule reads state the typed path sets and a data write does not
  (control value vs data-layer value). **[U]** Confirm on a scratch report.

## 5. The E&O check — three gates, in order

**[C]** `EandOWidget.RunRules`:

1. **Field validation.** Any finding → fatal count set to **-1**, a "Field
   Validation Errors" toast, and **the UAD rules are not run**. (This is why
   the UAD list once looked clean while field errors existed.)
2. **Schema.** The form serializes its own MISMO XML (`ExportMismoXml`) and
   WinTOTAL validates it against the schema (`ValidateSchema` event →
   `processschemavalidationresult`). Invalid → fatal **-1**, UAD rules not run.
3. **UAD / E&O rules.** The XML is posted to a la mode's service
   (`titanreportsapi.alamode.com/api`), polled, and merged from three rule
   sets: a la mode *review* rules, a la mode *UAD validation* rules (H-1), and
   **Fannie Mae's own findings** (`FannieMae-UADnnnn`). Duplicates between
   a la mode's H-1 and Fannie Mae's are dropped in favour of a la mode's; rules
   on a configurable blacklist are skipped; each item is mapped back to a
   field through the table in §3. Severities: FATAL, SEVERE, WARNING.
- **[C]** WinTOTAL asks for counts with `geteandowarningcount(n)`: all or
  UAD-only × fatal / severe / warning (14 selectors); `-2` if the rules did not
  run.

## 6. Signing, XML, PDF, ZIP — what blocks what

- **[C]** The form itself blocks **none** of them on missing data:
  - `SignReport` refuses only a missing signature image, a report already
    signed in that role, or a supervisor signature with no supervisor contact.
  - Signing writes `<ROLE>_CRED_ID/_STATE/_EXPIRES` from WinTOTAL's profile and
    `SIGNED_DATE` into signature block **0 (appraiser) or 1 (supervisor)** —
    block order matters.
  - `ExportMismoXml` / `CreateAndReturnMismoXML` serialize whatever is there.
  - PDF output is rejected only if empty or missing the subject-address field.
- **[I]** Any refusal to sign, deliver or build the ZIP because of errors is
  decided in WinTOTAL from the E&O counts. **[U]** Which selector it uses and
  what it refuses: observe with a CDP logpoint on `ExecuteReportAction` while
  the appraiser signs / builds a ZIP on a test report.
- **[I]** The binding gate outside TOTAL is the GSE portal, which applies the
  H-1 fatal rules; TOTAL's E&O is the closest local copy of it.

## 7. Import (`importmismoxml`)

- **[C]** Two modes: `NewReport`/`OverwriteFormData` → full import; otherwise a
  keep-existing merge. 43 importer classes (parsers per section, image parser,
  data sources, commentaries, per-grid importers).
- **[C]** The importer writes at least 1,254 literal field names; the XML
  writer reads at least 580. Names built at run time make static counting
  imprecise — **[U]** the exact per-data-point fidelity must be measured by
  round trip (import a known XML, have TOTAL serialize it, compare by UID).
- **[C]** **The main cause of import loss is `xsi:schemaLocation` on the
  root** (CATALOG E-028): the importer's generic path puts every ancestor's
  attributes into the XPath it resolves, cannot resolve the `xsi` prefix, and
  silently skips the value. Removing that one optional attribute took the SF1
  sample from 938/986 to 972/985 values kept with zero importer errors; the rest
  are TOTAL-owned values (software identity, version, PDF name) and defect
  pictures it files under the inspection.
- **[C] Measured on all twelve D-1 samples** (each into a freshly reset blank,
  `xsi:schemaLocation` removed; `roundtrip/0.0.1.3848/d1/SUMMARY.md`): values kept —
  single family 97.8–99.3 %, manufactured home 98.6–98.7 %, co-op 99.2 %, condo
  93.5–96.2 %, 2-4 unit 91.3–93.0 %. What is still lost concentrates in a few
  mechanisms: rental comparables' unit data beyond the grid's columns (E-032);
  report-level data sources (`DataSourceType` / `DataSourceIdentifier`); the
  management-company party; licence details (which signing writes from
  WinTOTAL's profile anyway, §6); condo `FloorIdentifier`; defect pictures (moved
  under the inspection, not lost). On **every** sample TOTAL's field validation
  (60–327 findings) stops the E&O before the UAD rules run — TOTAL validates more
  than UAD requires (E-030, E-031; `IMPORT_PROFILE.md`).
- **[C]** TOTAL declares `ValuationReportContentIdentifier` "URAR Delivery
  Specification v1.3" on its own output (the samples say v1.4).
- **[C]** A replace-import is **not a reset** (CATALOG E-029): it keeps whatever
  the previous content had that the new file does not mention. Measured: a
  batch of the 12 D-1 samples imported one after another into one report was
  contaminated sample to sample and was discarded.
- **[C]** TOTAL's own report file (`SaveReportXml`: `<Report><ReportInfo/>
  <Data><Forms><Form><Fields><Field FieldName Instance><FieldData><DataValue>
  <EditContent>…`, plus visibility rules) reopens through `OpenReportXml` — the
  path WinTOTAL uses. A blank is that header with only the structure fields of a
  new report (building 1 → unit 1, order page); **with zero fields TOTAL builds
  no data store and the form breaks** (it was restored from a backup of the
  same file). Structure lives in fields: `DE#_SECTION_KEY/GUID`,
  `UI#_SECTION_KEY/GUID/PARENT_GUID` (the unit's parent is the building's GUID),
  `OB#_…`, `SSDE#_SECTION_KEY`, `ORD_SECTION_*`.
- **[O]** Values present in a valid file that the import did not keep (the
  rowhouse case — now explained by E-028 for the most part): zoning compliance, zoning code and description, measurement
  standard, living unit count, structure identifier, cost-service name, one
  comparable's construction method.
- **[O]** Values the import *made up or moved*: a listing's sale-to-list
  adjustment spread across every adjustment cell of its column; one rental
  comparable's rent copied into unused rental columns; an ownership-only
  `SITE_UTILITY` became an "Other" utility row; an empty supervisor
  `SIGNATORY` became a "Supervisory Appraiser" signature block holding the
  appraiser.
- **[C]** **TOTAL's sales-grid totals count only visible rows.** The net
  adjustment (and from it the adjusted price, per unit, per bedroom, per area)
  adds an adjustment only if its grid row is visible at the moment it sums
  (`IsFieldVisibleForAdjustmentCalcs`). The sum runs during import, when the
  grid still hides rows that hold adjustments, and is not re-run by showing the
  rows or by `ExecuteAllCalcs` — only by a change event on one of that
  comparable's fields, addressed to the sales-comparison calcs (calc events run
  the *open* section's calcs unless `fieldSectionKey` names another). Measured
  on the 2-4 unit sample: adjusted prices off by $2,000–$15,000 with every
  adjustment line present. CATALOG E-038; `reconcile.recalculate()`.
- **[C]** **The subject photo is building 1's front photo.** The importer
  files the n-th `DwellingFront` as building n's `DE<n>_PHOTO1` and the subject
  `PropertyPhoto` (container "SubjectPropertyPhoto", fallback building 1's
  front) into `GSU_PHOTO_SUMMARY`, `GSU_PHOTO`, `RSU_PHOTO`, `GRU_PHOTO`; then,
  one second after any `PHOTO1` changes, the dwelling-exterior calcs copy
  `DE1_PHOTO1` over all four. The XML writer delivers `GSU_PHOTO_SUMMARY` as
  the subject `PropertyPhoto`. CATALOG E-039, IMPORT_PROFILE P22.
- **[C]** The importer narrates every decision (`MISMODeserializerHelpers.Log`:
  categorisation summary, unmapped images, each field populated, keep-existing
  skips) but only with `ENABLE_LOGGING`, a module-private static that nothing
  calls `SetLogging` on and nothing exports; the importer object is created per
  import (`MismoDeserializerFactory.Create`) and not kept. Not reachable from
  outside without patching the bundle — which the MOD does not do.
- **[C]** a la mode ships its own round-trip test in the bundle (export MISMO →
  `engine.ImportMismoXml` → snapshot the data set before/after → diff, "Step
  5/6 … 6/6", GUID fields skipped). [U] how it is invoked; worth using as a
  second opinion beside `tools/roundtrip.py`.
- **[O]** Required-shape conventions the import depends on: comparable units
  line up only when each carries `UnitIdentifier` "Unit n"; the appraiser's
  inspection must be one `INSPECTION` linked to the appraiser role; a GRM
  comparable's price and date must share one `SALES_HISTORY`; pictures are not
  imported from embedded base64 and have to be placed per slot.

## 8. What this means for the Import Module

1. The form's structure must be **created by TOTAL** (import, Report Setup),
   not written field by field: 1,139 controls only exist inside templates.
2. After import, **compare TOTAL's own serialization with the package, by
   UID**, and repair each difference through the field(s) the §3 table names —
   one generic mechanism instead of a per-case fix list.
3. A repair must use the path the field's validator listens to (LeaveField,
   SelectClosed, HidePopup); a bare data write can leave a stale finding.
4. Structure lives partly outside data fields (section tree, signature blocks,
   repeatable rows) and needs its own reconciliation.
5. The 145 H-1 rules with no field need a table of *what drives them*, so every
   diagnostic can still send the user somewhere.
6. Verification is the three E&O gates **plus** the round-trip comparison;
   the E&O panel alone cannot see a value that was dropped but not required.

## 9. Recognising the report: form, configuration, property type (build 0.0.1.3855)

Investigated 2026-09-28 on "SAMPLE BLANK" (a new report, web engine
**0.0.1.3855** — TOTAL updated itself from 0.0.1.3848 that day; what changed:
`builds/0.0.1.3855/DIFF_FROM_0.0.1.3848.md`, only vehicle storage). Read-only.
Implemented as `total-bridge/bridge/detect.py` (`bridge detect`), shown per
report in the HUD.

- **[C] UAD 3.6 has no form number to find.** The GSEs retired 1004, 1004
  Desktop/Hybrid, 2055, 1073 (+Desktop/Hybrid), 1075, 1004C, 2090, 2095, 1025,
  1007 and 1004D for one data-driven URAR (UAD FAQ 8–9). "Is this a 1025?" is
  answered by the GSEs' own *Functioning without Form Numbers* (v1.1,
  2025-06-10; now beside the other official files, extracted into
  `engine/spec/legacy_forms.json` by `engine/uad/spec/extract_legacy_forms.py`):
  six data points — Property Valuation Method 1.010, Construction Method 1.012,
  Subject Site Owned in Common 1.020, Project Legal Structure 1.016–1.018,
  Units Excluding ADUs 1.021, ADUs 1.022 — and the values each legacy form
  corresponds to; plus the properties that have no legacy form (more than one
  ADU, site condominium, manufactured home with more than one unit or another
  construction method or in a condo/co-op, hybrid/desktop outside the forms
  that had them, condops).
- **[C] How the table is read, checked on all twelve D-1 samples**
  (`tests/test_detect.py`): SF1–5 → 1004, Condo1 → 1073 Hybrid, Coop1 → 2090,
  MH1 → 1004C, both 2-4 unit samples → 1025; Condo2 (a desktop site
  condominium) and MH2 (manufactured + site built) → no legacy form, which the
  document itself lists as atypical. Two readings the samples forced:
  (a) the Construction Method note "does not apply for High-rise, Mid-rise, or
  Low-rise structures" resolves (from A-1) to `StructuralDesignType`; for such
  a structure a missing method satisfies the general cell but not
  "Manufactured" — without that, Coop1 matched 1004C; (b) the document's
  Project Legal Structure cell for 1004C and 1025 says "Condominium or
  Cooperative", which read literally excludes every ordinary 2-4 unit and
  manufactured home; the second reading lets an "A or B" cell admit absence,
  and the result says which reading matched.
- **[C] What 0.0.1.3855 changed in code**: 11 classes (`tools/diff_builds.py`
  now compares class sizes from `blueprint.json`); read side by side in the two
  bundle snapshots, every change is vehicle storage (driveway spaces as
  "1–9 / 10 or More", other storage as a number, `TenOrMoreParkingSpacesIndicator`
  only for driveways, a data migration for old reports) plus the rental
  comparable map exhibit. No other behaviour changed.
- **[O] Field-validation counts depend on grid-row visibility.** The 2-4 unit
  D-1 sample gave 60 findings on 3848 (17:52, 0 hidden grid rows re-shown) and
  69 on 3855 (20:07, 20 rows re-shown by P18) with the same Import Module code;
  the 9 new ones (comparable cooling, topography) are data the sample does not
  carry. [I] TOTAL does not validate what a hidden row holds, and whether rows
  are hidden when P18 runs depends on the report's render state — so the later,
  higher count is the truer one, and earlier counts may be undercounts.
- **[C] TOTAL keeps the property type through import.** On the 8 samples the
  0.0.1.3848 end-to-end batch completed (`e2e/0.0.1.3848/total/*/total.xml`),
  the six data points in TOTAL's own XML equal the package's, and so does the
  legacy form each maps to.
- **[C] TOTAL's UAD 3.6 form codes** (its own literals, generated into
  `builds/<build>/configuration.json` by `tools/blueprint.py`):
  `UAD-3.6-AR-1.000` URAR, `UAD-3.6-CR-1.000` Completion Report,
  `UAD-3.6-AU-1.000` Restricted Appraisal Update, `UAD-3.6-TM-1.000` and
  `UAD-3.6-CR-TM-1.000` the mobile variants. `ReportInfo.MajorFormKey` and
  `currentForm.formName` carry it; the E&O preprocessor runs only for the URAR
  (other forms get a no-op one).
- **[C] TOTAL's own configuration object.** Before writing MISMO, TOTAL builds
  one object of report-level switches from the form (class
  `SharedDataCommonInfo`; 22 switches, each with the field(s) it reads, in
  `configuration.json`): sales comparison (always on), cost approach, income
  approach, rent comparison (= any unit interior flagged "in rent schedule"),
  sales contract, revision history (+ reconsideration of value), prior sales,
  additional properties analysed, amenity / amenity-defect / vehicle-storage
  defect indicators, homeowner exterior maintenance, sketch-or-plan, units
  excluding ADUs, ADU count, government agency (VA/FHA/USDA), cost-to-repair
  type, coordinates. These decide which MISMO sections TOTAL writes at all.
- **[C] How TOTAL reads a Yes/No pair** (its `Indicator` helper, found and
  called by detection): Yes marked → true; No marked → false; **both marked,
  or neither → no value**, and the XML carries nothing, silently. A package or
  a fix that ticks both boxes produces a missing indicator, not an error.
  Selectors: Yes / "Visual Observation Completed" / "Typical for Market" →
  true; No / None / Inaccessible … → false.
- **[C] Structure** is the section manager's list: `dwelling-exterior`
  (buildings, `DE<n>_`), `interior` (units, `UI<n>_`; flags `InteriorIsADU`,
  `IncludedInRentSchedule`), `outbuilding` (`OutbuildingIsADU`),
  `manufactured` (`AduIsManufacturedHome`), `order`. TOTAL calls a report
  **multi-family when it has more than one non-ADU unit interior**
  (`IsMultiFamilyReport`); its section tree and the report-setup validators
  change shape on that test.
- **[C] Grids**: sales (`GSU`/`GC`, 3–24), rental property (`RSU`/`RP`, 1–24),
  rental unit (`RS`/`RC`, 1–24), GRM (`GRU`/`GR`, 3–24); `comps` is the column
  count.
- **[C] A new report is not empty.** TOTAL's form defines 557 field defaults
  (`builds/<build>/defaults.json`), among them most of the writer's switches:
  valuation method Traditional Appraisal, units 1, prior sales None, amenity
  exists Yes, sketch Yes, cost-to-repair Itemized, site owned in common No, and
  cost / income / revision / additional-properties / defect indicators No.
  **[O]** On SAMPLE BLANK three more were set by TOTAL's calculations, not the
  default table: sales contract No (`SC_CONTRACT_NO` "x"), ADUs 0, and the
  grid's subject column "site owned in common: No". **[I]** A package silent on
  any of these leaves TOTAL's default in the delivered report (P5: a
  replace-import keeps what it does not overwrite) — so the package must state
  each explicitly; `bridge/diagnose.py` lists the ones a package leaves open.
- **[C] Several reports.** Each open 3.6 report is its own CDP page; the
  active one is the visible page (focused, among several visible). Each page
  gets its own HUD and its own detection; the report's `Proj2000ID` is also
  the name of its working folder (below), which joins the page to WinTOTAL's
  files.
- **[C] The HUD's own "inject" button imports without the Import Module**:
  it hands the file straight to `ImportMismoXml`, so P1 (xsi), P10/P16
  (labels) and P5 (fresh report) are not applied. Use `bridge deliver`; the
  button needs the same preparation before it can be trusted (task T-992).

## 10. WinTOTAL on disk (read-only survey, 2026-09-28)

- **[C]** Program: `C:\Program Files (x86)\a la mode\TOTAL` (`WinTOTAL.exe`,
  `bin\alamode.WinTOTAL.exe`, the CefSharp browser subprocess). Main window
  "Appraisal Desktop - TOTAL by a la mode".
- **[C]** `Forms\MajorForms.xml` — 435 legacy major forms (code, description,
  number: 1004, 1004UAD, 1025, 1073, 1073UAD/DESKTOP/HYBRID, 1075, 2055, 2090,
  2095, 1004C, 1004D …). **No UAD 3.6 entry**: the 3.6 report is not a form in
  this registry, it is the web engine. `Forms\LegacyFormsMap.xml` — 605
  "Olympus" names (form code, section code, name). `Contents.xml` — the
  add-a-form catalogue (invoices, covers, addenda). `Forms\UAD\` — the UAD 2.6
  field maps (`UADFieldsMap.XML`, `UADFields.xml`, read-only map);
  `FormDefs\` — five vendor defaults files; `Transfer\*.xfr` — legacy transfer
  tables. None of these define the 3.6 report.
- **[C]** `%LOCALAPPDATA%\alamode\WinTOTAL\Reports\<Proj2000ID>-<guid>.oz_` —
  one working folder per open report. A new, unsaved report holds only empty
  `RepInfo.xml` / `History.xml`: its data is in the page's memory. A saved one
  adds `ReportData.exml`, `Appraiser.S3#` (both encrypted) and `UAD2.xml`;
  `RepInfo.xml` carries `WinTOTALVer`, `DeliveryPreCheckItems` and
  `ReviewSettings` (excluded review rules, rule sets).
- **[C]** A saved report (`.zap`) is a ZIP of `History.xml`, `RepInfo.xml`,
  `UAD2.xml` and an **encrypted** `ReportData.XML`. We stopped there: the
  report data is read only through the form, never by decrypting the file.
- **[O]** Logs: `C:\ProgramData\alamode\Common\Logs` (`API.log`, `INet.log`,
  `SafeStart.log`, `trace\…`). The delivery trace
  (`trace\alamode.wintotal.totaldelivery`) is empty on this machine — no ZIP has
  been built here yet — and no log records 3.6 validation. What blocks a ZIP
  can only be learned by watching one being built (U4 / T-979).

## Untested — next experiments

| # | Question | Experiment | Needs |
|---|---|---|---|
| U1 | Exact per-data-point import fidelity | Import each official D-1 sample into a scratch report, serialize, compare by UID | a scratch report |
| U2 | Which rules/sections each configuration turns on | Set the blank to each configuration, run field validation, record | permission to change the blank (or a copy) |
| U3 | Why a data-layer write can leave a LeaveField finding | Write vs type the same value, compare control and data values and the finding | a scratch report |
| U4 | What WinTOTAL refuses on errors (sign / ZIP / deliver) | CDP logpoint on `ExecuteReportAction` while the appraiser signs and builds a ZIP | the appraiser at the keyboard, a test report |
| U5 | What drives each of the 36 field-less data points and 145 field-less H-1 rules | Read the serializer for each; confirm by round trip | U1 |
| U6 | Where the E&O rule blacklist comes from and what is on it | Read `settings.eoBlacklistedRules` source (read-only) | — |
