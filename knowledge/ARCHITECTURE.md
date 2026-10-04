# Architecture — case ZIP → portable UAD 3.6 package → Import Module → finished report

Decided 2026-09-28 with the owner. Evidence: `total/FINDINGS.md`,
`errors/CATALOG.md`.

## The decision

**A complete portable UAD 3.6 XML package, imported by the Import Module — not
field-by-field filling.** Field-by-field writing stays only as the repair tool
*inside* the Import Module.

| | Field-by-field fill | Portable package + Import Module |
|---|---|---|
| Creates structure (buildings, units, ADUs, outbuildings, comps, rows) | Cannot, reliably: 1,139 controls exist only after TOTAL builds a template | TOTAL's own importer builds it, the way it does for any 3.6 file |
| TOTAL's own calculations, links, defaults | Bypassed; the generic fill produced 334 findings, smeared adjustments and 19 "Clear Comparable Data" prompts | Run by TOTAL |
| Checkable before touching TOTAL | No | Yes: schema, H-1 (728 rules), leftovers, images — offline |
| Portable | TOTAL only | Any UAD 3.6 software; the platform uses the same document |
| Verifiable | Only by reading screens | TOTAL serializes its report back; compared by UID |
| Weakness | — | The importer drops or reshapes some values → handled by one generic reconciliation stage, keyed by TOTAL's own MISMO↔field table |

## The pipeline

```
case ZIP ──► 1 Intake ──► 2 Case model ──► 3 Generator gates ──► 4 Package
                │                                                  │
          question sheet                                           ▼
          (gaps, judgments)                  5 Import Module (inside WinTOTAL)
                                               a preflight
                                               b TOTAL import
                                               c structure reconciliation
                                               d value reconciliation (by UID)
                                               e pictures and exhibits
                                               f verification
                                                      │
                                                      ▼
                                             6 Diagnostics (one list,
                                               every item → its field)
                                                      │
                                    7 Learning loop ◄─┘  (catalog + regression)
```

The **package is the only interface** between the two products. The platform
(`engine/`) produces it; the Import Module (`total-bridge/`) consumes it. The
Import Module shares no code with the engine (the owner's standing rule) — only
the package format and the knowledge in this folder.

### 1 Intake — understand the whole ZIP

Inventory every file (order sheet, MLS sheets, public records, prior report or
2.6 XML, photographs, sketch, floor plans, maps, licence, E&O declaration,
engagement letter, …), classify it, and extract facts **with provenance** (file,
page, and how it was read). Decide the configuration: form (URAR, Completion,
Update), inspection type, property and project type, attachment, buildings,
units, ADUs, outbuildings, manufactured home, approaches used.

Output: the facts, the configuration, and **one question sheet** — what the
files do not settle, and every judgment (condition words → C-ratings,
estimates, conflicting sources). Standing defaults the owner approves once are
applied silently and listed on the result page. Nothing without a basis is
invented.

### 2 Case model

The canonical UAD 3.6 MISMO document, built from a **clean skeleton generated
from the XSD and B-1** — never from a blanked official sample (a blanked sample
left a supervisor, a cesspool and empty rows behind; CATALOG E-003, E-004).

### 3 Generator gates (offline, before TOTAL)

All must pass:

- **Schema** (GSE subschema).
- **H-1** — the engine's 728 rules; zero fatal, or a written reason for each.
- **Completeness for the configuration** — every data point B-1/H-1 require
  for this configuration is present.
- **Integrity** — no dangling xlink labels, no empty containers, no signatory
  or role without a party, one record where TOTAL needs one (inspection, GRM
  sale), unit identifiers, grid ordinals.
- **TOTAL import profile** — the conventions TOTAL's importer depends on
  (CATALOG entries marked *profile*), each an executable check.
- **Pictures** — every `IMAGE` has its file, a legal A-1 category and a caption
  that names its slot.

### 4 Package

The XML with pictures embedded, a manifest (files, hashes, categories, slots),
the configuration, and the provenance of every value.

### 5 Import Module (`total-bridge/`)

- **a Preflight.** Report is new or blank and unsigned; the TOTAL web-engine
  build is known. On a new build, re-extract the form model
  (`tools/form_model.py`) and diff it against `total/builds/`, so a TOTAL update
  is noticed before it breaks a report.
- **b Import** with TOTAL's own deserializer (full mode).
- **c Structure reconciliation.** Buildings, units, ADUs, outbuildings and
  their identifiers (section manager); comparable counts per grid; signature
  blocks; repeatable rows that must not exist (empty "Other" rows).
- **d Value reconciliation.** TOTAL serializes its report; the result is
  compared with the package **data point by data point, by UID**. Every
  missing or different value is written to the field(s) the MISMO↔field table
  names, formatted to the field's pick list and format, through the path its
  validator listens to (typed + leave for LeaveField, select for SelectClosed,
  popup for HidePopup). Repeat until nothing changes. This replaces per-case
  fix lists.
- **e Pictures and exhibits.** Placed by A-1 category and caption into TOTAL's
  slots; every drop read back.
- **f Verification** (below).

### 6 Diagnostics — one list, every item clickable

Every finding from every layer, in one schema:

```
layer        generator-schema | generator-h1 | integrity | profile | import-drop |
             roundtrip-diff | total-field-validation | total-schema | total-uad | print
severity     fatal | severe | warning | info       blocking: sign / delivery / none
data point   MISMO name, UID, report field ID
location     TOTAL section key, field, instance      (or the driving setting)
message      the rule's own text
cause        CATALOG id, when known
fix          what to change; "re-validate" re-runs only what it affects
```

Shown inside TOTAL (the bridge's panel, `bridge/hud.py`) and in the platform's
Review Master. **Clicking an item navigates to the field** with TOTAL's own
calls (`setactivesectionkey`, `setfocustofield`). An item whose data point has
no field (the 145 H-1 rules, the 36 derived data points) goes to the setting or
structure that drives it — a table built in phase 4 and verified by round trip.

Hidden problems this list must show and the E&O panel does not: values the
import dropped or changed, values present but not what the package said, empty
repeatable rows, leftovers, pictures not placed, and UAD rules that never ran
because field validation failed.

### Verification — "done" means all of these

1. Generator gates pass.
2. TOTAL field validation: 0.
3. TOTAL schema: valid.
4. TOTAL UAD/E&O: 0 fatal (warnings listed and justified).
5. **Round trip: TOTAL's serialization equals the package**, apart from a
   written list of expected differences (formatting, values TOTAL computes).
6. Print check: key figures, the signer, no doubled units, no blank labels.
7. Screenshots of the signature, grid and totals pages attached.

Only the appraiser's signature remains.

### 7 Learning loop

Every new case ends with a short review: what the diagnostics caught, what the
appraiser still had to fix, and for each: the mechanism, the fix in the
generator / Import Module / knowledge, a CATALOG entry, and a regression check.
The regression set is the twelve official D-1 samples plus every real case
(`cases/`). No change ships unless the whole set still passes.

## Phases

| Phase | Deliverable | Needs from the owner |
|---|---|---|
| 0 ✓ | Investigation, form-model extractor, this knowledge folder | — |
| 1 | Import fidelity per data point: the 12 D-1 samples round-tripped through TOTAL → the *TOTAL import profile* | a scratch report |
| 2 | Configuration matrix: sections and field-validation findings per configuration | permission to change the blank (or a copy) |
| 3 | Import Module rebuild: structure + UID-based value reconciliation, validator-aware writes, generic picture placement; per-case fixer scripts retired | — |
| 4 | Diagnostics: unified list, clickable in TOTAL; table of drivers for field-less rules | — |
| 5 | Intake: ZIP → facts with provenance → configuration → question sheet → case model on a clean skeleton | a first real case ZIP |
| 6 | Regression harness: catalog checks and all cases run on every change; the rowhouse case re-run from its files end to end | — |
