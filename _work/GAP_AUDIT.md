# UAD 3.6 specification audit — gap list

Started 2026-09-16.  Each gap names the authority that defines the requirement
and the evidence that the current system misses it.  Status lives in
`TASKS.md` (IDs in brackets); this file is the reasoning behind the list.

Priority: **P0** blocks a valid UCDP delivery; **P1** blocks a professional
appraiser from completing a real report; **P2** is quality/usability the
specifications ask for.

## What was read for this audit

| Source | Used for | Read into the engine before? |
|---|---|---|
| A-1 Delivery Spec 1.4 (3,349 rows), Enumerations (2,885) | data points, conditionality, formats | yes (`delivery_spec.json`, `enumerations.json`) |
| A-1 *URAR Visual Schema* (4,278 rows), *UAD ARC Roles* (58) | container tree, xlink arcroles | **no** |
| B-1 Implementation Guide v1.4 (401 pp) + Comparable Grids supplement | display rules, packaging (pp 69-73), images (pp 56-61), Summary sources (ch. 01) | display rules yes; packaging/images **no**; Summary sources added 2026-09-16 |
| B-1 Usability and Implementation Guidance | editor behaviour (calculations, Other/None, single source, reasonableness) | **no** |
| C-1 layout, E Style Guide (92 pp) | form geometry, grid/exhibit layout | yes |
| E-2 Restricted Appraisal Update, E-3 Completion Report | the two other UAD 3.6 report types | **no** |
| D-1 twelve samples + Scenario Matrix v1.3 | templates, validation of every check | samples yes; matrix partly |
| F-1 Reference Guide (378 pp) + grid rows supplement | definitions, key concepts | partly (supplements) |
| G-1 Cross Reference | legacy UAD mapping | listed in supplements only |
| H-1 Compliance Rules v1.5 (728) + Adjustments Cardinality | compliance engine | yes (557 executed) |
| GSE subschema v1.3 (+ readme) | XSD validation, element order | yes |
| Combined UAD FAQs 2026-08-12, Lender Readiness Kit, C&Q Rating Definitions | scope, report types, mandate dates | **no** |

**Not in the folder, and needed:** subschema **v1.4** (the D-1 samples point at
it), **A-2/A-3, B-2/B-3, H-2/H-3, F-2/F-3** for the Appraisal Update and
Completion Report, and access to the **GSE UAD Compliance API**.  Nothing
local can certify UCDP acceptance; a real UCDP test submission is the only
proof.

## P0 — delivery package (B-1 pp 69-73, 56-61)

1. **Extra file in the ZIP.**  B-1: the ZIP holds one XML, one PDF and an
   `Images` folder.  `package.zip` also writes `manifest.json`.  [T-902]
2. **Uploaded images are not in the XML.**  B-1: "Each image provided in the
   Images folder must be referenced at least once in the XML file", each as an
   IMAGE with ImageCategoryType, ImageFileLocationIdentifier
   (`\\Images\name`), MIMETypeIdentifier and caption.  Media are written to
   `Images/` only.  [T-901]
3. **PDF reference does not match the PDF.**  FOREIGN_OBJECT/ObjectURL in a case
   copied from a template still names the sample's PDF
   (`\\SF1_Appraisal_v1.4.pdf`); the package ships `appraisal.pdf`.  [T-903]
4. **Template images referenced but not shipped.**  The XML of a
   template-based case references D-1 image files the package does not
   contain (and must not contain — they are sample content).  [T-904]
5. **Package limits unchecked:** 60 MB, unique image names, MIME types from
   A-1's MIMETypeIdentifier enumeration, unencrypted first-generation PDF.
   [T-905]
6. **Photo metadata:** A-1 "Required Photos": ImageDatetime and
   AltitudeElevationLinearMeasure are CR when an image file exists — to be
   read from EXIF, never invented.  [T-906]
7. **Vendor identity is the sample's.**  ValuationSoftwareVendorName /
   ProductName (A-1: R) carry "Nowhere Technologies / Some Appraisal Creator"
   from D-1 in every template case — sample content in a real report.  [T-907]

## P1 — completing a real report

8. **180 required/conditional appraiser data points have no place to be
   entered.**  A-1 marks them "Does Not Display" (Scope of Work indicators,
   ImprovementType, CostToRepairType, defect discriminators, water frontage,
   manufactured-home certification, parcel info, …).  The editor only edits
   what prints, so a report started blank cannot supply them.  [T-227]
9. **Tables, party blocks, prior sale/transfer history not editable in place.**
   [T-222, T-300, T-301, T-014]
10. **Restricted Appraisal Update Report and Completion Report** (FAQ 10, E-2,
    E-3) are separate UAD 3.6 submissions tied to a URAR; not supported.
    Blocked on A-2/A-3/H-2/H-3.  [T-304]
11. **Outbuilding photo slot** (B-1 12.007.1).  [T-223]
12. **171 H-1 rules not executed automatically.**  [T-908]
13. **Subschema v1.4 validation.**  [T-012, blocked]

## P2 — what the usability guidance asks of the software

14. Calculations with override (price per sq ft, area totals, sketch → area
    breakdown).  [T-228]
15. "Other" prompts for a description that must not duplicate a valid value;
    "None" disables the other values; multi-select shown as such.  [T-229]
16. Single source of entry with a notice when a value repopulates elsewhere
    (Summary done; Q&C ratings → SCA grid etc.).  [T-230]
17. Reasonableness / cross-field checks (C1 needs new construction, fully
    updated kitchens/baths; As Is not allowed with Subject-to actions).  [T-909]
18. F-1 definitions reachable from the field (hover/popup) and the C&Q rating
    definitions.  [T-231]
19. Commentary checks: flag "see addendum" and prohibited/veiled language
    (usability item 9).  [T-910]
20. Report layout fidelity (pages 2+ uncalibrated, stray grid text, page
    count vs samples).  [T-033, T-034, T-110, T-111]
