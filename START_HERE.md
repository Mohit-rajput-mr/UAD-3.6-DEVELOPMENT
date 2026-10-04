# START HERE — UAD 3.6 appraisal work in WinTOTAL, driven by an AI agent

> **Every AI agent: read [`AI_HANDOVER.md`](AI_HANDOVER.md) first** — the owner's aim, the main goal, what the last session finished, what to take over next, and how to behave. Keep it current in the same commit as your work.


You are an AI agent opening this folder, possibly on a device you have never
seen. The owner's instruction to you will usually be short — **"refresh your
memory"** — and then a case folder. This page tells you what that means and
what to do, in order. Read it fully before touching anything.

---

## 1. What this is

An appraiser's shop produces **UAD 3.6 appraisal reports** (Fannie Mae /
Freddie Mac redesigned URAR, MISMO 3.6) in **WinTOTAL** (a la mode).
This folder holds:

| Part | What it is |
|---|---|
| `total-bridge/` | **The MOD** — a standalone Python app that drives the UAD 3.6 report open in *this device's* WinTOTAL through TOTAL's own debugging port (127.0.0.1:8088). It fills, places photos, adjusts, and checks. **This is what you use for cases.** |
| `knowledge/` | Everything learned: how WinTOTAL really behaves, every error met and the mechanism that prevents it (`errors/CATALOG.md`), shared memory notes (`memory/`), the case runbook (`PLAYBOOK.md`). |
| `profiles/` | The signing appraiser(s): credentials, designation, licence and E&O images. |
| `specs/official/` | The official GSE specifications (A-1…H-1, XSD, the 12 D-1 samples). **They are the authority.** |
| `engine/` | A separate web platform that renders/validates UAD 3.6 reports. Not needed for WinTOTAL cases. |
| `_work/` | Working notes and past cases; `_work/HANDOFF.md` is the long history (its **last** section is the current position). |

The owner's goal: **hand over a case folder, get back a report in WinTOTAL
that is ~100% filled and passes every check — field validation 0, schema 0,
UAD errors 0 — ready for the appraiser to review and sign.**

## 2. When the owner says "refresh your memory"

1. Read this file, then `knowledge/PLAYBOOK.md`, then `knowledge/memory/INDEX.md`
   and the notes it lists, then the **last** section of `_work/HANDOFF.md`.
2. Run the device check and read every line:

       python setup/check.py

3. If anything FAILS, go to §3 (first time on a device) and fix it.
4. Tell the owner, in a few lines: what the MOD is, whether this device is
   ready, which appraiser profile is active, and what you need (usually: the
   case folder, and TOTAL open on that property's report).

## 3. First time on a device — install the MOD

The MOD changes **nothing** in WinTOTAL: a la mode ship TOTAL's browser
component with its debugging port enabled; the MOD talks to that. So
"installing" means installing Python and the MOD's packages.

1. Python 3.11+ must exist (`python --version`). If not, ask the owner to run
   `winget install -e --id Python.Python.3.12` (tick *Add to PATH*).
2. Run, from this folder:

       powershell -ExecutionPolicy Bypass -File setup\install.ps1

   It installs the packages, seeds your memory for this folder, and runs
   `setup/check.py --tests` (the MOD's own test suite must pass).
3. **Ask the owner whose credentials sign reports on this device.** The
   default profile is `profiles/appraiser.json`; `profiles/advent.json` is a
   second appraiser. A different appraiser gets a new profile file — never
   put one appraiser's licence on another's report.
4. The licence and E&O images must be on disk at the paths the profile names
   (`profiles/documents/...`). Images pasted into a chat are **not** saved to
   disk — ask for the files.
5. Open TOTAL with a UAD 3.6 report and run `python setup/check.py` again. If
   it warns that TOTAL's web-engine build differs from the extracted model,
   follow the command it prints before filling anything.

## 4. Running a case (summary — the full runbook is `knowledge/PLAYBOOK.md`)

1. **The owner opens** the property's UAD 3.6 URAR in TOTAL (you never open,
   create, sign or delete reports). Confirm it is the right property.
2. Read the case folder: inspection sheet (the hard gate — transcribe it
   fully), measured sketch, public record, each comparable's MLS + GEO sheet.
   Record every fact with its source (`_work/<case>/facts.py`).
3. `python -m bridge.cli sheets --folder "<case>" --out <scratch>` and **look
   at every picture** before deciding where it goes.
4. Write `_work/<case>/case.json` from `total-bridge/case_template.json`
   (worked example: `knowledge/cases/worked_example_sf/case.json`).
5. From `total-bridge/`:

       python -m bridge.cli case --json <case.json> --dry-run
       python -m bridge.cli case --json <case.json>
       python -m bridge.cli certify --report "<report name>"
       python -m bridge.cli audit --json <case.json>      # the delivered XML vs the case

6. Every error left is a mechanism to fix **in the MOD** (with a test and a
   CATALOG entry), not a one-off patch. Repeat until certify says READY **and**
   audit is clean (certify alone missed a $20,000 hidden-row error and a bare
   reconciliation comment on 1965 20th Dr).
7. Write the handback (`_work/<case>/HANDBACK.md`): judgement calls, researched
   values with sources, conflicts left standing. Tell the owner what to check.
8. **Ask the owner to SAVE in WinTOTAL.** Bridge writes are lost if TOTAL
   reloads an unsaved report (CATALOG E-064).

## 5. Rules you must never break

- **WinTOTAL only through the MOD** (the debugging port). No mouse/keyboard
  control of the owner's desktop.
- **Only the owner** opens, creates, signs or deletes reports.
- **The official specifications are the authority** — not screenshots, not
  memory, not another vendor's output.
- **No demo or placeholder data** in a real report. Facts the folder lacks are
  researched from public sources (assessor, FEMA, listing portals, ATTOM), the
  source recorded, and listed on the handback for the appraiser to confirm.
- **Never bypass or silence a validation.** The goal is a report that
  satisfies the rules, not a quieter error list.
- **Look before you place.** Every photograph is viewed before it is filed.
- **Standing defaults** (owner, 2026-09-29): designation **MAI**; credentials
  filled from the profile; Assignment exhibits = **licence + E&O**; adjustments
  on the **18 North** rates for 1 unit and the owner's **multi-family** rates
  for 2-4 units (2026-10-02) — both in `total-bridge/bridge/adjust.py`, chosen
  by `casekit.profile`. Reconciliation **short**: most weight and why, the
  value, the adjustments listed at the bottom; **one value everywhere**.
- **A photo that looks AI-generated or staged is not placed** until the owner
  confirms it was taken at the property.
- **Keep the record** as you go: `TASKS.md` (`python engine/tasks.py`),
  `_work/HANDOFF.md`, `knowledge/errors/CATALOG.md`. A session can end at any
  moment; what is not written down is lost.

## 6. Honest status (2026-10-02)

- **2-4 unit proven**: 1965 20th Dr (3-family, Bath Beach) reached field
  validation 0, schema 0, UAD 0, audit clean except one owner-supplied DOM, and
  the owner generated the ZIP. Units, rent schedule, rental comparables,
  per-unit grid rows and multi-family adjustments are kit steps with tests
  (`tests/test_rental_comps.py`, `tests/test_multifamily_profile.py`,
  `tests/test_audit.py`). It was done step by step, not in one `bridge case`
  run — the next 2-4 unit case should try the full run with `--dry-run` first.
- Condos (Shore Pkwy stopped at FV 9), co-ops, manufactured homes: not yet in
  the kit.

### Earlier (2026-09-30)

- Proven on a real single-family report: every field key, structural move and
  fix in `bridge/casekit.py` was executed on the 89 Rockland report, which
  reached **field validation 0, schema 0, UAD errors 0**. The kit's plan is
  checked offline against TOTAL's model (every key exists) and reproduces
  TOTAL's own adjustment nets exactly (`total-bridge/tests/test_casekit.py`).
- **Not yet done:** `bridge case` has not been run end to end in one go on a
  fresh blank report — run `--dry-run` first on your first case, watch the
  run, and record what it teaches. Condos, co-ops, 2–4 units and manufactured
  homes are not covered by the case kit yet (see `knowledge/PLAYBOOK.md` §9).
