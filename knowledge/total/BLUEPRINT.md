# Blueprint — how a UAD 3.6 report lives inside WinTOTAL

The map an agent needs before generating a package for TOTAL or changing the
Import Module. Web engine build 0.0.1.3848. Facts are marked **[C]** (code or a
controlled test), **[O]** (observed), **[I]** (inferred). The data behind this
page is generated, not typed:

| File | What | Made by |
|---|---|---|
| `builds/<build>/blueprint.json` | every class of the form engine, its methods, the field keys its code switches on; the pipeline's classes by role | `total-bridge/tools/blueprint.py` (offline, from the bundle snapshot) |
| `builds/<build>/transfers.json` | the 99 transfer groups (388 fields kept equal) and the copies done in code | same |
| `builds/<build>/fields.json`, `datafields.json`, `validators.json`, `visibility.json`, `uid_map.json`, `validation_profile.json` | the form model: controls, pick lists, 759 validators, visibility rules, the MISMO↔field table | `tools/form_model.py` (live report) |
| `%LOCALAPPDATA%괶-bridge\bundle\<build>\` | the code itself, for reading — **not in this repository** | `tools/dump_bundle.py` |

## 1. Two programs, one conversation

WinTOTAL (.NET) hosts the UAD 3.6 form (a web app, `uadwebengine.alamode.com`)
in a 32-bit CefSharp browser (Chrome 109). **[C]** They talk both ways:
WinTOTAL → form through `ExecuteReportAction` (42 actions: open, save, import,
PDF, XML, sign…), form → WinTOTAL through `CefConnector` events (`PhotoChanged`,
`FieldsChanged`, `ValidateSchema`…). WinTOTAL stores the report file and the
pictures; the form holds the data while the report is open. **[C]** The
browser process can die out of memory mid-session (E-040): the report page
vanishes and only reopening the report brings it back.

## 2. The data: one data set, fields by key and instance

**[C]** `engine.dataLayer.DataSets.get(formName)` holds every value as a field
`KEY` with an `instance` (repeating rows). Keys carry a **section prefix**:
`DE<n>_` building n, `UI<n>_` unit n, `OB<n>_` outbuilding, `GC<n>_` sales
comparable n, `RP<n>_`/`RC<n>_` rental, `GR<n>_` GRM, `GSU_`/`RSU_`/`GRU_` the
subject's column in each grid. Structure (buildings, units, comparables) is
itself data: `*_SECTION_KEY/GUID/PARENT_GUID` fields, `HIDDEN_*_COUNT`
repeatable counts, the **section manager** (identifiers, captions) and the
**comp managers** (`sales`, `rentalprop`, `rentalunit`, `grossrental`). A
field's **visibility rule** (`visibilityRules`, by row key and instance) is
state too — and the writer and the totals read it (§5, §6).

## 3. Import: `ImportMismoXml` → parse → model → populate

**[C]** `MismoDeserializerFactory.Create(engine)` → `MISMODeserializerURAR`:

1. **Parse** the XML into a report model — one parser per URAR area
   (`…ParserAssignement, SubjectProperty, Site, Units, SalesComp,
   RentalInformation, IncomeApproach, CostApproach, DataSources,
   ValuationCommentaries, Reconciliation, Certifications, VehicleStorage,
   EnergyEfficient, RevisionHistory, PropertiesNotUsed`), plus the **image
   parser** (inspection, room, defect, car-storage, amenity images; owner by
   ancestor `PROPERTY/@ValuationUseType`, structure/unit by owner identifiers).
2. **Populate** the data set — `MISMODeserializerURARImporter` and its
   sales-comp, rental, income and cost importers; `Import_<CONTAINER>` per
   MISMO container; every value through `PopulateDataField` (format transform,
   pick-list mapping). Grids and repeatables are grown with
   `AddFieldDataGroup`.
3. **Pictures**: the importer creates a slot per picture and sets its value to
   the file location; it **never loads the bytes** (E-019, E-033).

What the importer depends on, beyond UAD (each confirmed, IMPORT_PROFILE):
every ancestor's attributes go into its XPath — `xsi:` breaks it (P1, E-028);
comparables are found by **xlink label patterns** (`PROPERTY_<Role>_P<n>`,
rental units `…_I<n>`: P10, P16, E-032, E-036); the n-th `DwellingFront` is
building n's front photo (P22).

The importer narrates every decision (`MISMODeserializerHelpers.Log`) but its
switch is module-private and never called — unreachable from outside.

## 4. Calculations: FormCalcs → the open section's calcs

**[C]** `FormCalcs` (a data-layer observer) runs, for each change event, the
calcs of **the section the event names** (`fieldSectionKey`) or else **the open
section** (`ExecuteCalcsForSection`); `ExecuteAllCalcs` runs every section's
calcs with no changed key. There are 58 calc classes (`SalesCompCalcs`,
`DwellingExteriorCalcs`, `SiteCalcs`, `CostApproachCalcs`, `IncomeApproachCalcs`,
`RentalInfoCalcs`, `ReconciliationCalcs`, …); `blueprint.json` lists the field
keys each one switches on. Consequences met so far:

- a comparable's **net adjustment** is summed only on a change to one of its
  fields and counts only rows visible at that moment (E-038, P23);
- one second after any front photo changes, building 1's front photo is
  copied over the subject's photo fields (E-039, P22).

## 5. Transfers: fields kept equal

**[C]** The `Transfers` observer keeps groups of fields equal across the order,
assignment, subject and grid sections (99 groups, 388 fields —
`transfers.json`), and its methods move subject values into the grid's subject
columns (`GSU_*`, `RSU_*`: site, view, dwelling, amenities, quality and
condition). **A value written into one member of a group is copied over the
others.** Cross-checked against the MISMO↔field table (2026-09-28): 84 of the
99 groups hold one data point in several sections; the other 15 are
**composites of one fact** — full name (first/middle/last/suffix), full address
(street/unit/city/state/ZIP), a type and its "other" description, project type
(PUD / in-project / legal structure). So transfers force no two different facts
equal; a generator only has to keep a composite's parts consistent (e.g. the
project indicators with the legal structure). The copies TOTAL does **in code**
rather than as transfers are the ones that override a fact: building 1's front
photo over the subject photo (§4).

## 6. Visibility → what is delivered

**[C]** `SalesCompCalcs.ProcessRowVisibility*` (about 40 rules) decide which
grid rows show; rendering applies them. The **writer includes a comparable
value only if its row is visible** (E-037) and the **totals count only visible
rows** (E-038). Section-level too: the writer asks `IsSectionHidden` /
`Is…SectionHidden` before exporting a section's data and exhibits.

## 7. Delivery: the MISMO writer

**[C]** `MISMOSerializer` (module 7419, ~150 `Create…` steps: parties, roles,
licences, parcels, site, utilities, hazard zones, units, rooms, inspections,
images, data sources, approaches, commentaries, project…) builds the delivery
XML from the data set — `CreateAndReturnMismoXML`. It writes its own software
identity, `ValuationReportContentIdentifier` "…v1.3", the subject
`PropertyPhoto` from `GSU_PHOTO_SUMMARY`, a supervisor role whenever
`HIDDEN_SUPERVISOR_COUNT` > 0 (E-034), and identifiers from sections, not fields
(E-006).

## 8. Validation: three gates

**[C]** E&O = (1) field validation — 759 validators (`validators.json`,
`validation_profile.json`), each on a trigger (LeaveField, SelectClosed,
HidePopup…) → (2) schema (WinTOTAL's `ValidateSchema`) → (3) the UAD rules and
the GSE findings. A later gate does not run while an earlier one fails (E-012);
field validation skips grid findings while Sales Comparison is open (E-035).
TOTAL validates comparable data UAD does not require (E-030) and wants an
explicit adjustment wherever subject and comparable differ (E-031).

## 9. What this means for whoever generates the package

1. Meet UAD 3.6 (schema + H-1) **and** `IMPORT_PROFILE.md`.
2. Run `total-bridge/tools/preflight.py` on the package: zero errors.
3. Deliver with `bridge deliver` into a **new** report: it imports, places the
   pictures, puts back what rendering changes, and verifies against the file —
   value-affecting differences first.
4. What TOTAL still asks for (field validation) is listed per data point; the
   answer goes into the package, not into TOTAL by hand.

## Open

- [U] how a la mode's own round-trip test is invoked (FINDINGS §7).
- The conditions of TOTAL's 759 validators are not in the form model; P12/P13
  are learned from measured e2e findings (`e2e/<build>/total/`).
- Rental and GRM grid totals: not yet seen to differ (E-038 note).
