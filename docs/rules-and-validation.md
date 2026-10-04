# Display rules and validation

## Display rules (B-1)

A conditional element prints only when its own B-1 rule holds. The rules are
sentences over MISMO data points, for example
`Display when GovernmentAgencyAppraisalType = "FHA" AND ...`. They are
extracted to `engine/spec/display_rules.json` and executed by
`engine/uad/report/rules.py`.

Two more rule sets drive the comparable grids:

- `report/dashes.py`: when an empty cell prints an em-dash.
- `report/comparables.py`: row display, "always" or "when applicable".

## Three authorities: Review Master (`engine/uad/review.py`)

| Layer | Source | Module |
|---|---|---|
| `schema` | GSE UAD subschema (XSD) | `schema.py` (lxml / libxml2, milliseconds per check) |
| `compliance` | The 728 H-1 rules, by Message ID and severity | `compliance.py` |
| `completeness` | Fields B-1 says print for this property but are empty | `review.py` |

A rule the engine cannot execute is reported as `review`, not counted as a pass.

**Schema version.** We hold only the **v1.3** subschema. The D-1 samples
declare **v1.4**. `schema.py` validates the untouched samples first and reports
where they diverge. A difference that makes a GSE sample fail is recorded as a
schema-version fact, not as a fault in the document.

## The sign-off gate (`engine/app/cases.py`)

A state machine with no bypass:

- A package exports only from a **signed** case.
- A case can be signed only when:
  - every section is acknowledged (`POST /acknowledge`);
  - the Review Master reports no fatal finding;
  - the schema is valid.
- Any edit after signing voids the signature and returns the case to review.

## Validating the validators

Every check runs first against the twelve official D-1 samples. A check that
faults a published sample is a broken check, and is fixed before it is
trusted. `engine/tests/validate_compliance_engine.py` and
`test_compliance_detects.py` do this for H-1. This rule has caught several
broken checks (see `knowledge/errors/CATALOG.md`).

## Integrity (`engine/uad/integrity.py`)

Compares the deliverable with the case. It catches:

- images filed against deleted comparables;
- GSE sample pictures still attached;
- stray files in the archive.

Exposed at `/api/cases/{id}/integrity` and `/package/check`.
