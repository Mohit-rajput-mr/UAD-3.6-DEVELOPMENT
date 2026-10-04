# UAD 3.6 → TOTAL Bridge

Fills a UAD 3.6 report in **TOTAL** (a la mode / Cotality) from a MISMO 3.6 XML
file, and then checks its own work.

It is a standalone application. It does not need, and does not talk to, any
other appraisal software: hand it a UAD 3.6 XML file from any vendor and a
report open in TOTAL, and it fills the form.

---

## Why this exists

TOTAL's UAD 3.6 report is a web form (`uadwebengine.alamode.com`) hosted inside
the desktop application. Its **menu import handles MISMO 2.6 only** — the 923
DataMaps that drive importing are all for the 2011 generation of forms, and
there is no 3.6 form file on disk at all. So a 3.6 file arriving from another
vendor has, until now, had to be re-keyed by hand: 1,459 fields across 29
sections.

This bridge types it instead.

## How it works

TOTAL hosts the form in CefSharp, and a la mode ship their CEF wrapper with
`RemoteDebuggingPort` enabled — so the form is reachable the way any web page
is reachable. The bridge connects to that endpoint and drives the form.

**Nothing in the TOTAL installation is modified.** No file is patched, no
library is injected, no licence check is touched. A patched binary would break
on the next TOTAL update and put the licence at risk; this uses the product's
own interface, so it survives updates.

### The mapping is derived, not written by hand

Both sides key on the same identifier. The published Appendix A-1 gives every
value in the standard a **Report Field ID**, and TOTAL stamps that same ID onto
each of its controls in an `fmid` attribute:

| TOTAL control | `fmid` | The standard's field |
|---|---|---|
| `GSU_AD_ADDR` | 22.01.01 | Property Address — subject |
| `GC1_AD_ADDR` | 22.01.17 | Property Address — comparable 1 |
| `GC1_PROX1` | 22.01.19 | Proximity to Subject — comparable 1 |

So the map is read off the two indexes rather than transcribed — and TOTAL's
half is read **at run time, every run**, so when a la mode add fields there is
nothing to regenerate and nothing to go stale.

A control's name also says which column of a grid it belongs to: `GSU_` is the
subject, `GC1_`/`GC2_`/`GC3_` the comparables.

### It verifies what it did

After filling, the bridge asks TOTAL to serialise **its own** report back to
MISMO and compares that against the source file, value by value. The report it
prints is what TOTAL kept, not what the bridge typed:

```
Sales Comparison Approach      41/41
Subject Property               18/19
   22.03.17  Site Size   file "0.22 Acres"   TOTAL ""   NOT SET
187 of 191 values confirmed in TOTAL's own XML
```

A field that looks accepted on screen and saves nothing is a real failure mode
in this form — the bridge is built to catch it rather than report success.

## Install

```
pip install -r requirements.txt
```

Python 3.11+. Two dependencies: `lxml` and `websocket-client`.

To build a single-file Windows executable:

```
build.bat
```

## Try it

Two official Fannie Mae / Freddie Mac sample cases ship in `samples/` — public
specification files, no client data:

```
bridge fill --xml samples/SF1_Appraisal_v1.4.xml --report "<your report>" --dry-run
```

`--dry-run` writes nothing. It walks all 30 sections, reports every value it
would set and where, and is the right way to see what a file covers before
touching a report.

## Use — a case from its folder (single family)

When the case arrives as a folder of PDFs and pictures rather than a MISMO
file, the agent reads it, writes one `case.json`, and the **case kit** fills
the report open in TOTAL (runbook: `../knowledge/PLAYBOOK.md`):

```
python -m bridge.cli sheets  --folder "<case folder>" --out <scratch>   # view every picture first
python -m bridge.cli case    --json <case.json> --dry-run               # plan vs the open report
python -m bridge.cli case    --json <case.json>                         # fill, then certify
python -m bridge.cli certify --report "<report>"                        # FV, schema x2, UAD rules
```

Modules: `casekit.py` (the plan and its order), `formkit.py` (rows TOTAL only
makes through its own handlers, pick-list and money formats, events),
`adjust.py` (the 18 North rate profile), `exhibits.py` (contact sheets and the
photo manifest), `locmap.py` (the SCA location map), `certify.py` (the three
gates). Template: `case_template.json`; worked example:
`../knowledge/cases/worked_example_sf/case.json`.

## Use — a MISMO 3.6 file

1. In TOTAL, create a **new UAD 3.6** report (an import does not reset a report
   that already holds another case -- knowledge/errors/CATALOG.md E-029). Note
   its name.
2. Run the Import Module:

```
bridge deliver --xml "C:\path\to\case_portable.xml" --report "<new report>"
```

It does, in order (knowledge/ARCHITECTURE.md §5): TOTAL's own import of the
file as TOTAL's importer needs it; every picture into the slot TOTAL made for
it; the grid rows TOTAL hid although they hold values shown again and the
totals it summed while they were hidden summed again; a supervisor nobody named
removed; buildings and units named. Then it verifies: TOTAL serializes the
report and it is compared with the file value by value -- **value-affecting
differences** (adjustments, nets, adjusted prices, multipliers, the opinion)
are listed first -- and TOTAL's own E&O is read from a neutral section. Results
go to `<file>_TOTAL_check\` beside the file. `--fill` adds the older
field-by-field fill as a repair step (not for 2-4 unit reports).

Or from inside TOTAL: keep `bridge hud --watch` running and use the panel's
**>> inject** button — the file goes through the same Import Module (the
button refuses a signed report, a report that is not new, and a package with
severe preflight findings, and never imports on its own: CATALOG E-043), and
the after-import list appears in the panel, each item clickable to its field.

### Diagnose and recognise

```
bridge diagnose --xml <package>                   before import: preflight, what the package is,
                                                  switches it leaves to TOTAL's defaults
bridge diagnose --report "<name>" [--xml <pkg>] --hud
                                                  after import: TOTAL field validation, UAD rules,
                                                  Yes/No conflicts, mirrors, round trip; list in the panel
bridge detect [--report <name>] [--xml <f>]       which report is open/active and what it is
                                                  (form, configuration, legacy-form equivalent)
bridge hud --watch                                panel on every open report, kept current,
                                                  and serving its import button
```

### Other commands

```
bridge reports                       list the UAD 3.6 reports open in TOTAL
bridge fill  --xml <f> --report <n>  field-by-field fill (the older path; --dry-run first)
bridge read   --report "<name>"      dump what TOTAL currently holds
bridge verify --xml <f> --report <n> compare without writing anything
bridge harvest --report "<name>"     regenerate the field map from TOTAL
```

## Safety

- A report is chosen **by name**. The bridge never guesses when more than one
  is open.
- **A signed report is never written to.** Signing is what makes an appraisal
  somebody's legal instrument; the bridge refuses and says so.
- `verify` writes nothing at all, so a run can always be rehearsed first.
- Every run snapshots TOTAL's report to MISMO **before** touching it, so there
  is always something to go back to.

### Three kinds of control, three ways of writing

* **Text** — set the value, then fire the events the form's own handlers are
  bound to. Assigning the value alone paints it on screen and saves nothing.
* **Tick boxes** — `click()`, and only when the current state differs from the
  wanted one. That is the same code path a mouse click takes.
* **Pick lists** — these are not `<select>` elements. The control is opened,
  the option carrying the wanted text is found among what became visible, and
  *that* is clicked. Typing the value into the control is what leaves the field
  empty while appearing to work.

Which fields are pick lists is not guessed: A-1 says which are enumerated, and
the 3,132 permitted values it publishes are what turn the document's
`SettledSale` into the form's "Settled Sale", and `North` into `N`.

## What it does not do yet

- **Value reconciliation by UID** (ARCHITECTURE §5d): what the comparison finds
  dropped or changed is listed, not repaired.
- **Comparable data TOTAL validates beyond UAD** (financing, levels, zoning,
  street... on every comparable -- CATALOG E-030) and explicit $0 adjustments
  where subject and comparable differ (E-031) must be in the file; the official
  D-1 samples lack them, so their field validation is not 0.

## Status

Measured on the twelve official D-1 samples, each imported into a freshly
blanked report (`tools/roundtrip.py`, which runs the same `bridge/deliver.py`):
see `knowledge/total/e2e/0.0.1.3848/total/SUMMARY.md`. Real cases filled in
TOTAL are recorded in `_work/HANDOFF.md` with TOTAL's own E&O as evidence.
