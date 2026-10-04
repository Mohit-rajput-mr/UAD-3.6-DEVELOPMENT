# What this is, and where it stands

Read this first, then `CLAUDE.md` (the working agreement), then `TASKS.md`
(what is actually finished) and `_work/HANDOFF.md` (the narrative).

---

## What we are building

A **UAD 3.6 appraisal report platform**. Not a form that resembles the URAR --
the report itself, editable in place. One canonical MISMO 3.6 document is the
case at every moment, and the form, the comparable grids, the PDF, the XML and
the delivery ZIP are all drawn from it. What the appraiser fills in and what
the lender receives are the same page.

The redesigned URAR (UAD 3.6) replaces the 1004/1073 generation. It is a far
larger dataset: 1,459 Report Field IDs across 29 sections, against roughly
three hundred on the old form.

### The one rule that governs everything

**The published specifications are the authority, and the code is generated
from them -- never hand-typed.** In order: Appendix A-1 (delivery / MISMO
XML), B-1 (display rules), C-1 (layout), D-1 (twelve sample scenarios with
their XML), E (report style), F-1, G-1, H-1 (compliance rules) and the GSE
subschema.

Everything else follows from that. If a value cannot be traced to a spec file,
it is a guess, and a guess in an appraisal is a defect. `CLAUDE.md` states this
as the zero-guess mandate; it is not decoration, it has caught real errors.

---

## Who the users are

An appraiser inspects a property, photographs it, sketches it, pulls comparable
sales from MLS, and writes an opinion of value. The report is a **legal
instrument**: it carries their signature, their licence number, and their
liability. Two consequences that shape every decision here:

* **Never invent a value.** Adjustments, the opinion of market value, the
  comparable weighting and the reconciliation are the appraiser's professional
  judgment. Fill what the documents establish; leave the rest marked
  unanswered. A fabricated number in a signed report is somebody's licence.
* **Never lose one.** A value that arrives must survive to delivery. The
  round-trip is tested value-for-value, not "mostly".

---

## Where the code lives

```
engine/
  spec/            extracted specification data (JSON) -- generated, not hand-written
  uad/
    spec/          the extractors that produce spec/*.json
    uadmap.py      THE CANONICAL MAPPING -- see below
    bind.py        label -> field -> value, and how a value prints
    edit.py        writing a value back, in the schema's own order
    provenance.py  which fields a file answered (drives the green marking)
    importer.py    bringing a UAD 3.6 file in, pictures and all
    delivery.py    the UCDP package (B-1)
    compliance.py  the 728 H-1 rules, executed
    maps.py        the Sales Comparison Map
    report/
      form.py      the form itself, from C-1
      flow.py      measurement, pagination, the in-page editor JS
      comparables.py  the comparable grids
  app/
    main.py        server + passcode gate
    api.py         REST API -- the UI is one client of it, not a privileged path
    autofill.py    the filler: writes a whole case while the page replays it
    ui/            the editor (index.html) and the map tool (ui/map/)
  tests/           harness, conformance, round-trip, compliance
  tasks.py         the shared task registry tool
```

Run it: `python engine/app/main.py` (passcode verifier: `engine/app/access.json`).
`.claude/launch.json` has the preview configurations.
`URAR_WORK` gives an instance its own case store; `URAR_HOST=0.0.0.0` puts it
on the local network.

---

## The canonical mapping (`uad/uadmap.py`)

The single authority for what the standard calls things. Generated from A-1 by
`uad/spec/build_uad_map.py` into `spec/uad_map.json`: **678 data points** --
634 that display and **44 that never do** -- each with every container A-1
places it in, its format, its conditionality per property role, the values it
may hold, the values each report location restricts it to, and the display
text the report prints.

It exists because every module used to carry a little of this knowledge of its
own, each right about the case in front of it and none complete. The same class
of defect kept coming back somewhere new.

---

## The testing story

Three layers, and they catch different things.

1. **The twelve D-1 samples.** Written by the people who wrote the standard.
   `engine/tests/harness.py 12`. Necessary, not sufficient -- they exercise the
   standard *as documented*.

2. **Conformance against a real file.**
   `engine/tests/test_uad36_conformance.py` runs against a delivery package
   produced by **certified UAD 3.6 software (ACI-WB 1.0.3.0)** for a real
   assignment -- MISMO XML, the PDF, 42 images. It is the only artefact that
   says what the standard looks like *as shipped*.

   It is git-ignored (real client data). It lives at
   `_work/reference/urar_18_north/`; the tests skip cleanly when it is absent.
   **If you have it, put it back there.** It has caught three defects that
   every other test passed -- see below.

3. **Working the app by hand.** Everything in the evening of 2026-09-18 came
   from the user driving the editor with their own file open, and none of it
   was caught by 299 passing tests. Tests check the report against the
   specification; they cannot tell you the map looks wrong.

Run: `python -m pytest engine/tests --ignore=engine/tests/test_golden.py -q`
(`test_golden.py` has known baseline drift, tracked as T-705.)
Currently **299 passed**.

---

## What the real file taught us

Each of these passed every spec-derived test:

* **Imported images were silently rewritten.** `importer.py` wrote
  `\Images\name` where B-1 packages `\\Images\name`, so a report arriving from
  another vendor left with all 42 image locations changed.
* **Dropdowns were as complete as one spreadsheet row.** A-1 writes
  enumerations against a Report Location and packs several into one cell, so a
  value reached only the field it was written against -- eight of thirteen
  party roles, six of twenty-seven amenities, and no way to file an image as a
  Sales Comparable Map.
* **Forty-four data points were never delivered**, thirteen of them Required.
  A-1 marks them "Does Not Display", so a model built from the printed page
  cannot see them. `delivery._delivery_only` now derives the ten Boolean ones
  from the document itself, and all ten match the certified file exactly.
* **The map had one pin.** A-1 requires coordinates on every property and the
  case carries them, but the map seeded from the *printed* addresses and
  geocoded each one. Those addresses were wrong too: `bind._address` joined
  `AddressUnitDesignatorType` with no unit number, producing "15 S Beechwood
  Rd Unit" -- a street no gazetteer knows.

---

## The editor, and how it is meant to feel

* **The form is the report.** `GET /api/cases/{id}/form` is the same renderer
  that prints, with `edit=True`: every printed value editable where it stands,
  every enumerated field an in-page pick list (never a native `<select>` -- the
  page is laid out at 3x and transformed down, so a native popup draws at the
  wrong size), every Wingdings tick box clickable.
* **Amber marks what is unanswered**, from the moment the report opens.
* **Green marks what a file brought in**, including the Summary (which holds no
  values of its own -- a Summary line counts as imported when the field behind
  it was). Toggle in the editor bar.
* **"Fill the report"** replays a whole case on screen, section by section, in
  page order, each field turning green the instant it is answered. It accepts
  an uploaded UAD 3.6 file (portable, delivery XML, or the zip) staged through
  the ordinary import -- the filling logic itself is untouched.

---

## Two XML flavours

| | Delivery `mismo.xml` | Portable XML |
|---|---|---|
| Images | **referenced** `\\Images\NAME.jpg` | **embedded** in MISMO `EXTENSION` nodes |
| Schema | valid | valid |
| Re-import alone | pictures reported missing (correctly -- the file does not carry them) | everything returns |
| Use | what ships to UCDP, inside the ZIP with `Images/` | one file that carries a whole job |

Both round-trip value-for-value.

---

## WinTOTAL / a la mode -- closed question

The user asked whether UAD 3.6 data could be pushed into a la mode's TOTAL.
Read-only investigation of the install concluded: **no local mechanism can do
it.** TOTAL's 3.6 report is not a local form at all -- it is a **web report
engine** (`WebReportEngine`, `ReportDataXMLCreatedUsingWebReportEngine`,
`SendAlaredunSettingsToUAD36WebEngine`, hosted in embedded Chromium), gated by
licence flags (`TOTAL_UAD36Enabled`) served by a la mode's service. There is no
form file to write and no map to extend. Its 1,416 local forms are all the 2011
UAD generation (MISMO 2.6).

Do not re-derive this, and do not go near the licensing surface.

---

## Open, and deliberately so

* **T-118** -- 18 print-rule differences against the certified PDF (7 values it
  prints that we do not, 11 we print that it does not). Each needs checking
  against **B-1**, which is the authority; the certified PDF is evidence of
  practice, not of what the standard requires.
* **T-925** -- filling from a source with more comparables than the target
  leaves one empty extra column.
* **T-117** -- our render of the certified file runs 26 pages to its 24. The
  section order is right; the drift is cumulative page-break calibration.
* **T-705** -- golden baseline drift, not regenerated on purpose.
* A trailing group of seven fill steps carries no section, so they play last.

`python engine/tasks.py next` is the live picture. Close tasks with evidence;
the tool refuses a `done` with no note on purpose.

---

## Working with the user

* They test by **using the product**, not by reading test output, and they are
  right to. Ship something they can click.
* When they say a thing is broken, it is broken -- but find the *cause* before
  changing anything. Several reports this session turned out to be two
  different faults wearing one symptom.
* **Say what you did not do.** A rough edge named is worth more than a clean
  summary that hides it.
* They correct sharply and they are usually right. Take the correction.
