# UAD 3.6 report platform

> **Every AI agent: read [`AI_HANDOVER.md`](AI_HANDOVER.md) first** — the owner's aim, the main goal, what the last session finished, what to take over next, and how to behave. Keep it current in the same commit as your work.


> **New device, or an AI agent told "refresh your memory"? Open
> [`START_HERE.md`](START_HERE.md) first.** It installs the WinTOTAL MOD
> (`setup/install.ps1`) and runs a case (`knowledge/PLAYBOOK.md`).

Produces a Fannie Mae / Freddie Mac UAD 3.6 deliverable — `appraisal.pdf`,
`mismo.xml` and `Images/` in one archive — for any property type, from a case
the appraiser edits in the browser or a program drives through the API.

## Running it

> Deploying the web platform on Vercel: see [`DEPLOY_VERCEL.md`](DEPLOY_VERCEL.md).

```bash
python engine/app/main.py
```

Then open <http://127.0.0.1:8765> and enter the passcode. It is stored only as a
PBKDF2 verifier in `engine/app/access.json`; change it with
`python engine/app/access.py set-passcode` or override it with `URAR_ACCESS_CODE`.
The API is the same surface: <http://127.0.0.1:8765/api/docs>.

## How it is built

Nothing about the form is typed in by hand. Every structure the report has is
read out of the specification at build time, and every measurement is taken off
the GSEs' own sample reports.

| What | Where it comes from |
|---|---|
| Which fields exist, where they display, in what order | Appendix A-1 Delivery Specification (`Report Location`) |
| Allowed values and the text the page prints | Appendix A-1 UAD Enumerations |
| When a field appears | Appendix B-1 Implementation Guide + A-1 `Conditionality` |
| The comparable grids, row by row | Appendix B-1 Comparable Grids supplement |
| What a checker rejects | Appendix H-1 UAD Compliance Rules v1.5 (728 rules) |
| Element order in the XML | the GSE subschema's `xs:sequence` |
| Page size, columns, type, rules, colour | measured from the twelve Appendix D-1 samples |
| Starting templates | the twelve Appendix D-1 sample cases themselves |

The extractors live in `engine/uad/spec/` and write to `engine/spec/*.json`.
Re-run any of them to rebuild the data the engine is driven by.

## The parts

```
engine/
  spec/                  extracted specification data (JSON)
  uad/
    templates.py         the twelve GSE samples, classified by property type
    bind.py              label -> field -> value, and how a value is printed
    edit.py              writing a value back, in the schema's own order
    compliance.py        the 728 H-1 rules, executed
    schema.py            the GSE subschema
    review.py            Review Master: schema + compliance + completeness
    report/
      page.py            the measured page geometry
      typography.py      the measured type and colour
      fonts.py           Myriad Pro, from this machine's licensed Adobe install
      urar.py            the report, drawn
      comparables.py     the comparable grids
      paginate.py        pagination by measurement, and the PDF
  app/
    main.py              the server and the passcode gate
    api.py               the REST API
    cases.py             case storage and the sign-off state machine
    ui/index.html        the interface
  tests/
    harness.py           Phase 3: 8 checks x 12 scenarios
    validate_compliance_engine.py   the compliance engine against the samples
    test_compliance_detects.py      mutation testing, per rule kind
    test_edit.py         write/read symmetry and schema validity
    test_roundtrip.py    lossless XML round-trip
```

## The sign-off gate

A package cannot be exported unless the case is signed; it cannot be signed
unless every section the report prints has been acknowledged **and** the Review
Master reports no fatal finding and a valid schema; and any edit to a signed
case voids the signature and returns it to review. The export route asks the
state machine and the state machine asks the Review Master — there is no
parameter that skips either.

## Verification

Run these from the project root.

```bash
python engine/tests/test_roundtrip.py
python engine/tests/validate_compliance_engine.py
python engine/tests/test_compliance_detects.py sf1_appraisal_v1_4 600
python engine/tests/test_edit.py sf1_appraisal_v1_4 1500
python engine/tests/harness.py 12
```

Each check in the harness is run against the GSEs' own samples first. A check
that faults a published sample is a broken check, not a broken build, and that
has caught four defects in the checks themselves — a font allowlist that
counted the specification wrapper, a header rule that did not allow a full-page
image, a traceability test that compared composed strings, and a fixed
wrapper length that is three pages for Condo2 and two for the rest.

## Where it stands

The harness reports **85 pass, 0 fail, 11 gap** over 12 scenarios × 8 checks.
Every scenario passes schema, compliance, fonts, page furniture, grid and
archive; the eleven gaps are all the same check.

- **Page count against the published sample** is the gap. SF1 matches exactly
  at 21 pages; the others run between 14 and 30 against the GSEs' 18 to 30.
  Most of the difference is that photographs are not yet placed on the page.

## Known gaps

These are listed because they are real, not because they are acceptable.

- **The v1.4 subschema is not on this machine**; validation runs against
  **v1.3**, which all twelve v1.4 samples pass. The v1.4 file should be
  dropped into the spec folder when available.
- **MyriadPro-Black is not installed** (Acrobat ships Light, Regular, Italic,
  Semibold, Bold, Bold Italic). The two display lines on the Summary page that
  the samples set in Black are set in tracked Bold at the measured width, and
  that is an approximation, not a match.
- **171 of the 728 compliance rules are not executed automatically.** They are
  reported with their text and the reason, never silently passed. They test
  formats, span instances, or depend on an xLink relationship.
- **Write/read symmetry is 90%** (1100 of 1221 fields). The remainder are
  writes that create a branch which does not yet exist and whose discriminator
  the reader then filters on.
- **Photographs are not yet placed on the page.** They are stored, listed and
  delivered in `Images/`, but the report does not lay them out.
