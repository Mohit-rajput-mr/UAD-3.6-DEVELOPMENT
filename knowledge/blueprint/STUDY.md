# The UAD 3.6 Blueprint — what it holds and how the report is dynamic

Studied 2026-10-05 from the owner's repo `Mohit-rajput-mr/UAD36-Blueprint` (cloned at
`/home/user/uad36-blueprint` in the session that wrote this; re-clone it to read the files).
Every statement below cites the official document it comes from. Nothing here is from
memory or from another vendor.

## 1. What is in the blueprint, compared with what the app already uses

| Material | In the app already? | Note |
|---|---|---|
| URAR A-1, B-1 (+ Usability supplement, Comparable Grids), C-1, D-1 (12 samples + Scenario Matrix v1.3), E, F-1, G-1 | **Yes, identical** | the 12 D-1 XMLs differ only by CRLF line endings |
| H-1 Compliance Rules v1.5 | **Yes, identical** | blueprint copy is .xlsx, ours .xlsm; every sheet equal (729 rules, 70 cardinality rows) |
| GSE subschema v1.3 (all 12 XSDs) | **Yes, identical** | |
| A-2..H-2 Restricted Appraisal Update Report + sample AU1 | **No — new** | a separate report type |
| A-3..H-3 Completion Report + samples CR1, CR2 | **No — new** | a separate report type |
| 03_Guidance: FAQs (9/30/2026), Lessons Learned (6/23/2026), Photo and Image Requirements, ANSI, HBU playbook, C/Q rating definitions, Mapping Legacy Forms, Freddie SSR guide | **No — new** | clarifications; none overrides the appendices |
| 04_Policy_Timeline: mandate Nov 2, 2026; policy exception to May 19, 2027; LL-2026-08; Lender Readiness Kit | **No — new** | planning only |
| `AI_BLUEPRINT.md`, `ROADMAP.md`, `GSE_VERIFICATION.md` | rules match `CLAUDE.md` and `docs/gse-vendor-recognition.md` | roadmap phases 0-8 |

So the URAR the app is built on is the current official set; the blueprint adds the
two other report types, the job aids, and the build roadmap.

## 2. The report is driven by data, not by a form number

B-1 p26 / F-1 p10: the URAR replaces 13 legacy forms (1004, 1004 Desktop/Hybrid, 1073
and variants, 1075, 2055, 1004C, 2090, 2095, 1025, 1007). "Data — not a form number —
will drive the property type." FAQ 8 and 13: one structure covers traditional, hybrid,
desktop and exterior assignments.

The drivers, as the D-1 Scenario Matrix lays them out column by column:
assignment parties · Property Valuation Method (Traditional / Hybrid / Desktop) ·
Units Excluding ADUs · ADU (in dwelling / in outbuilding) · PUD / Project (Condo, Co-op) ·
Attachment Type · Structure Design (Mid-Rise, High-Rise, Rowhouse/Townhouse) ·
Construction Method (Site Built / Manufactured) · outbuildings · DDDs · As Is / Subject To ·
vehicle storage · amenities · number of sales comps (3-5, with listings / pending) ·
Additional Properties Analyzed · Rental Information · Income Approach · Cost Approach.

## 3. When each section displays and when it repeats (B-1 pp29-31, F-1 pp10-11)

Each trigger is a MISMO data point (B-1 chapter text, line refs to the pdftotext of v1.4):

| # | Section | Displays | Repeats | Trigger in the XML |
|---|---|---|---|---|
| 1-4 | Summary, Assignment Information, Subject Property, Site | always | never | — |
| 5 | Disaster Mitigation | when there are features | never | `DisasterMitigationFeatureType` other than "None" |
| 6 | Energy Efficient and Green Features | when renewable components, certifications or ratings are known | never | any of the three `...ExistsIndicator` = true |
| 7 | Sketch | always | never | — |
| 8 | Dwelling Exterior | always | **per dwelling** | each `IMPROVEMENT` with `ImprovementType = Dwelling` |
| 9 | Manufactured Home | when there is a manufactured home | **per MH** (dwelling or ADU) | `ConstructionMethodType = Manufactured` on a Dwelling (after its Dwelling Exterior) or on an ADU outbuilding (after its Outbuilding); an MH outbuilding that is not an ADU goes to Outbuilding instead |
| 10 | Unit Interior | always | **per unit and per ADU** | each `PROPERTY_UNIT`; after its Dwelling Exterior, or after its Outbuilding when the unit is in one |
| 11 | Functional Obsolescence | always | never | — |
| 12 | Outbuilding | when there is one | **per outbuilding** | each `IMPROVEMENT` with `ImprovementType = Outbuilding`; real property first, then not-real-property (abbreviated) |
| 13-17 | Vehicle Storage, Amenities, Overall Q&C, HBU, Market | always | never | — |
| 18 | Project Information | in a project or PUD | never | `PropertyInProjectIndicator = true` (condo / co-op / condop) or `PUDIndicator = true`; Cooperative Information subsection when co-op with blanket financing |
| 19 | Subject Listing Information | always | never | — |
| 20 | Sales Contract | active contract | never | `SalesContractExistsIndicator = true` |
| 21 | Prior Sale and Transfer History | always | never | — |
| 22 | Sales Comparison Approach | when applicable | never | `SalesComparisonApproachIndicator = true` |
| 23 | Rental Information | when applicable | never | `RentScheduleIndicator = true`; required whenever the Income Approach is |
| 24 | Income Approach | when applicable | never | `IncomeApproachIndicator = true` |
| 25 | Cost Approach | when applicable | never | `CostApproachIndicator = true` |
| 26 | Reconciliation | always | never | — |
| 27 | Revision History | when provided | never | `RevisionCategoryType` exists (never on the original) |
| 28 | Supplemental Information | when provided | never | an IMAGE with `ImageCategoryType = SupplementalExhibit` |
| 29 | Certifications and Scope of Work | always | never | — |

Inside a section, subsections follow the same pattern (e.g. Ownership Rights only when
not a co-op; Site Valuation Methodology when `CostApproachIndicator = false AND
SiteValueIndicator = true`; Commentary / Exhibits subsections only when provided).
B-1 states each one; they should be extracted, not typed (see §7).

**What the app has today:** `engine/spec/section_rules.json` holds these as prose only,
and `form.section_shown` interprets some. There is no structured "displays / repeats /
trigger" table and the editor's field list is static (owner's test B14). This table is
what the applicability engine must be generated from.

## 4. The structure tree, in the XML and on the page

From F-1 ch. 03, 08, 10, 12 and the samples:

```
PROPERTY (SubjectProperty)
  LivingUnitExcludingADUCount (3.005)   AccessoryDwellingUnitTotalCount (3.006)   DwellingCount (3.007)
  IMPROVEMENTS/IMPROVEMENT  ImprovementType=Dwelling   StructureIdentifier (8.000, "Building 1")
      PROPERTY_UNITS/PROPERTY_UNIT   unit identifier (10.002, "Unit 1")   AccessoryDwellingUnitIndicator (10.011)
  IMPROVEMENTS/IMPROVEMENT  ImprovementType=Outbuilding  OutbuildingType (12.001: Barn, StandaloneADU, Other+"ADUGarage")
      PROPERTY_UNITS/PROPERTY_UNIT   (only when the outbuilding holds an ADU)
```

Samples: 2-unit = 2 dwellings × 1 unit; 2-unit Scenario 2 = 1 dwelling × 4 units (A-D);
SF3 = dwelling + Standalone-ADU outbuilding ("Cottage"); SF4 = ADU inside the dwelling;
MH1 = dwelling + two outbuildings (garage "Other", barn).

Rules (F-1 3.005-3.007, 8.000, 10.002, 10.011):
- 3.005 counts living units excluding ADUs (1 for a single family with or without ADU);
  2-4 means a 2- to 4-unit property. 3.006 counts ADUs (0 if none), wherever they are.
  3.007 counts dwellings (outbuildings excluded) and displays only when 3.005 > 1.
- Structure Identifier is required when 3.005 > 1; Unit Identifier is required when
  there is more than one living unit and **cannot repeat**.
- 10.011 "Unit is an ADU" displays in every Unit Interior when 3.006 >= 1.
- H-1 UAD1016: the dwelling count must equal the number of Dwelling improvements.
- Tab names come from the identifiers: "Dwelling Exterior – Building 2",
  "Unit Interior – Building 2 – Unit 2", "Unit Interior – ADU/Garage – ADU",
  "Outbuilding – [OutbuildingType]".

So **the counts are derived from the tree**, and adding a unit means adding a
`PROPERTY_UNIT` (and its Unit Interior), which is what the owner's brief (T-1035) asks for.

## 5. The sales grid is dynamic too (B-1 ch. 22, F-1 Key Concepts, Lessons Learned §1)

Subsections: General Information, Site, Dwelling(s), Unit(s), Quality and Condition,
Vehicle Storage, Summary always; Project Information if the subject or any comp is in a
project; Water Frontage with Private Access if applicable; Energy Efficient and Green,
Property Amenities if relevant; Outbuilding if applicable. **Unit(s) repeats for each
living unit including ADUs.** Rows: predefined rows from the B-1 Comparable Grids
supplement; a "blank" row only when no predefined row fits; never the same item twice;
rows not applicable to the subject or any comp are not shown (Lessons Learned 1a-1d).

## 6. Usability rules the editor must follow (B-1 Usability supplement v1.0)

1. Show when a field allows several values; "Other" asks for a description (only the
   description prints) and should warn when it duplicates a valid value; "None" disables
   the other values.
2. Calculate subtotals and totals (price per area, finished/unfinished, above/below
   grade) and **let the user override** them.
3. Data-entry aids from public records / MLS, editable.
4. Reference help from F-1 (definitions for ADU, CLT, site owned in common, etc.).
5. Link the Quality and Condition rating definitions.
6. Commentary only for its section; discourage "see addendum".
7. Use the GSE UAD Compliance API early and often.
8. **Single source of entry**: a value shown in several places is entered once and
   flows everywhere (e.g. Overall Q&C 15.005 -> grid 22.11.02 and Summary 1.031), with
   a notice of what was pre-filled.
9. Flag prohibited / unsupported language.
10. **Reasonableness checks across sections** — e.g. a Recommended Action of
    completion / inspection / repair means the value condition cannot be "As Is"; a C1
    rating requires new construction = true and kitchens/baths NewOrLikeNew and
    FullyUpdated (Lessons Learned 11 says the same for new construction).
11-12. Trend data and sketch integration feeding the area breakdown and noncontinuous area.

## 7. What this changes in the plan (T-1035, the owner's dynamic-report brief)

1. **Generate `spec/sections.json`** from B-1 pp29-31 and each chapter's "section /
   subsection displays when" sentences (about 120 of them, all naming a data point), the
   same way the display rules are already extracted. Validate: for each of the 12 D-1
   samples the predicted sections (and their repeat counts) equal the sections in the
   published PDF.
2. **Applicability engine** reads that table against the live document: `/fields` and the
   navigation return only applicable sections, with the rule that decided each.
3. **Structure engine** operates on the tree in §4: add / remove / reorder dwelling,
   unit, ADU (in dwelling, attached, in garage, standalone, MH), outbuilding; counts
   3.005 / 3.006 / 3.007 re-derived; unique identifiers; tab names from identifiers;
   grid Unit(s) rows follow the units. Acceptance: rebuild each sample's tree from a
   blank skeleton.
4. **Usability rules** in §6 become editor behaviour (single source, overridable totals —
   `grid_math` already computes A-1's totals; the override is still to add).
5. **Later phase (ROADMAP Phase 6)**: Restricted Appraisal Update (A-2..H-2) and
   Completion Report (A-3..H-3) as their own report types, attached to a URAR; their
   format must match the original report's format (FAQ 9).
6. Photo requirements by section (Photo and Image Requirements job aid) become
   completeness checks: required (e.g. Dwelling Front, Property Access, Sketch or Floor
   Plan, HUD Data Plate) vs conditionally required vs optional.
