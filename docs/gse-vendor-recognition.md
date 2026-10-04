# GSE vendor recognition: what is required, what is inferred, what we may claim

**Rule: never claim that this software is GSE-approved, certified,
recognised or "UCDP-ready" without written evidence from Fannie Mae or
Freddie Mac.** The GSEs publish specifications. Passing our own checks
against them is evidence of conformance, not approval.

## What the published material requires (authority: the appendices)

These are requirements of the **deliverable**, and the software is built to
meet them:

| Requirement | Source | Where we meet it | Evidence |
|---|---|---|---|
| MISMO 3.6 XML valid against the GSE UAD subschema | A-1, GSE XSD | `uad/schema.py` | Harness check 2; 0 schema errors on all 12 blank templates |
| Data points in their A-1 formats and enumerations | A-1 | `uad/entry.py`, `uad/edit.py` | `test_entry.py`, `test_edit.py` |
| The H-1 compliance rules (728) | H-1 | `uad/compliance.py` | Harness check 3; validated against the samples |
| Report layout and display rules | B-1, C-1, E | `uad/report/*` | Harness checks 4-7 and 9; `_work/audit/linediff.py` word diff vs the D-1 PDFs (still open items, see `AI_HANDOVER.md` §5) |
| Delivery ZIP: one XML, one PDF, `Images/`, at most 60 MB, referenced images | B-1 pp. 56-61, 69-73 | `uad/delivery.py` | `test_delivery.py`, harness check 8 |
| Software and PDF named in the XML | A-1 | `uad/delivery.py`, `uad/extra.py` | Written as "UAD 3.6 Form Filler" |

## What is inference (not stated in the material we hold)

- **Whether the GSEs run a vendor registration, recognition or testing
  programme for UAD 3.6 software, and its steps.** We have no document
  describing one. Do not describe it until the owner supplies the official
  source.
- **Schema version.** We hold the v1.3 subschema. The samples declare v1.4.
  Conformance to v1.4 is inferred from the samples validating, and is not
  proven against a v1.4 XSD (`uad/schema.py` records where they diverge).
- **UCDP acceptance.** The actual submission portal can apply checks beyond
  the published H-1 rules. Only a real submission shows whether a package is
  accepted.
- **Fonts.** Appendix E names Myriad Pro (Calibri as substitute). Without the
  licensed font the report uses metric-matched substitutes. They are visually close but are not the named face.

## What we may say

- "Built to the UAD 3.6 specifications (Appendices A-1 to H-1)."
- "Checked against the GSE UAD subschema and the published H-1 compliance
  rules on every save."
- "Verified against the twelve official Appendix D-1 sample cases", giving the
  harness numbers and date.

## What we may not say

- "GSE-approved", "Fannie Mae / Freddie Mac certified", "UCDP-certified",
  "guaranteed to pass UCDP", or any wording that implies an endorsement.
