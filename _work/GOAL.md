# What this project is for

The one-page orientation. `TASKS.md` is status, `_work/HANDOFF.md` is the
narrative and the traps, `README.md` is the architecture. This file is the why,
so no agent has to infer it.

## The owner

An appraiser running real UAD 3.6 assignments for AMCs and lenders, who also
owns a WinTOTAL licence. Every deliverable here goes out under a real signature
on a real report, which is why nothing may be invented and nothing may be
claimed without a test.

## The two products, which must stay separate

**1. This folder — the UAD 3.6 platform.**
Produce a Fannie Mae / Freddie Mac UAD 3.6 deliverable: `appraisal.pdf` +
`mismo.xml` + `Images/` in a validated ZIP. One canonical MISMO document per
case; the PDF, the XML and the ZIP are all derived from it, so the file the
appraiser edits is the file that ships and it is schema-checkable at every
moment. The report must be pixel-faithful to the Appendix D-1 samples.

**2. `total-bridge/` — the WinTOTAL mod.**
A standalone installed application that fills a UAD 3.6 report inside the
owner's existing WinTOTAL from one portable XML, so they sign rather than type.
The owner was explicit: *"it should not be connected to our software."* No
shared imports with `engine/`. It must handle any 3.6 form — driveby, single
family, condominium, 2-4 unit.

## Standing instructions from the owner

- **The official specifications are the authority** — A-1, B-1, C-1, D-1, E,
  F-1, G-1, H-1 and the GSE subschema, unzipped under
  `C:\3.6 uad zips\_UNZIPPED_ALL`. Not screenshots, not another vendor's PDF,
  not memory.
- **Generate from the spec files; never hand-type what a spec defines.** If no
  authoritative source can be found for something implemented, say so rather
  than presenting it as verified.
- **Validate your validators.** Every check runs against the twelve official
  samples first. A check that faults a published sample is a broken check; that
  rule has now caught six.
- **No fake controls, no sample content in a real report, no compliance claim
  without a test that demonstrates it.**
- **No blank field in a delivered case; fill gaps by research, not invention**
  (owner, 2026-09-28). A fact the case folder does not give is researched online
  from public sources (county assessor / records, listing portals, FEMA flood
  maps, census tract, zoning, rent and market data), and each value keeps its
  source — UAD's data-source fields need it anyway. Every researched or
  estimated value is listed for the appraiser to confirm before signing; the
  value opinion is derived from the comparables with the arithmetic shown.
  Placeholder / demo values never go into the deliverable.
- **The folder must work on another device as is** (owner, 2026-09-30): it is
  handed to other appraisers' machines, where an agent is told only "refresh
  your memory". So: `START_HERE.md` is the entry point, `setup/` installs and
  checks the MOD, no path may point at this PC (specs live in
  `specs/official/`), every lesson lives in the folder (never only in an
  agent's private memory), and a case runs through the case kit, not
  hand-written case scripts. `setup/export_for_device.py` packages it
  (client case material left out unless asked for).
- **Appraiser credentials ARE filled** (owner, 2026-09-29, superseding the
  earlier "no licence number" rule — TOTAL will not clear field validation
  without them). Designation is **always MAI**. The appraiser's details live
  in agent memory (`uad36-appraiser-defaults`), not in this repo document.
- **Assignment Information exhibits are always the appraiser's licence and
  E&O insurance declaration** — never the engagement letter.
- **Adjustments use the 18 North parameters** (owner, 2026-09-29): $75/sq ft
  GLA, $10/sq ft site (>1,000 sq ft), $250/year age (>5 years), $10,000 a
  bedroom, $5,000 a half bath, $10,000 finished basement, $10,000 a garage
  space, $10,000 outdoor living, 2% of list for market exposure on a listing
  or pending sale. Derivation: `_work/rockland/adjust.py`.
- **The development tree stays separate from real case material** — names,
  credentials and everything else. The repo
  (`github.com/kech8014/3.6-UAD-DEVELOPMENT.git`) is private and stays private.
- **Do not control the owner's PC** (no desktop/computer-use clicking). Work in
  WinTOTAL only through the MOD (`total-bridge/`, CDP on :8088). What only the
  desktop can do (open or reopen a report), ask the owner to do.
- **Keep TASKS.md and HANDOFF.md current as work lands**, because several agents
  share this folder in sessions that cannot see each other and a session can end
  on a credit limit.

## What the owner expects of a delivered case

Their words: the portable XML should arrive in TOTAL as a finished driveby, and
their only manual work should be **adding a signature and generating the ZIP**.
So fill everything the record settles, and estimate what an exterior-only
inspection cannot observe **under a disclosed extraordinary assumption** naming
the source -- that is ordinary driveby practice. What must never be invented is
a figure with no basis in the file at all; for those, ask.

The live case (129-35 131st St) stands at 35 fatal H-1 findings from 114, schema
clean. Of the 35: 13 are the rent schedule and income approach, blocked because
the packet carries no rental data of any kind; 2 are the licence the owner asked
to leave out; 10 are A-1 points that do not display and the editor cannot write
(T-227); the rest are T-934 and T-935.

## Where things stand

See the last section of `_work/HANDOFF.md`, and `python engine/tasks.py next`.
