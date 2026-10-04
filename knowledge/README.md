# Repository knowledge — the permanent source of truth

Everything this project has learned lives here: how UAD 3.6 and WinTOTAL
actually behave, every error we have hit and the mechanism that now prevents
it, the architectural decisions, and the memory earlier agents kept. **Every
agent reads this before changing anything, and writes to it when it learns
something.** A fact that is not written here is lost when the session ends.

## Order of authority

1. **The official specifications** (A-1, B-1, C-1, D-1, E, F-1, G-1, H-1, the GSE
   subschema) — `specs/official/` in the portable-XML repository (on the
   development machine `C:\3.6 uad zips\_UNZIPPED_ALL`) — and the data this repo
   generates from them (`engine/spec/`).
2. **This folder** — what the specifications do not say: how WinTOTAL really
   imports, validates and delivers, and what went wrong on real cases.
3. Code comments, then everything else.

When this folder and the code disagree, the code is wrong or this folder is
stale: find out which, fix it, and record which it was.

## Read first

| File | What it holds |
|---|---|
| [`PLAYBOOK.md`](PLAYBOOK.md) | **The case runbook**: a single-family report from case folder to ready-to-sign with the case kit (`bridge case` / `bridge certify`), the judgement calls, and the traps checklist. Start here for case work (and `../START_HERE.md` on a new device) |
| [`cases/worked_example_sf/case.json`](cases/worked_example_sf/case.json) | A finished single-family case file (FV 0 / schema 0 / UAD 0), anonymised |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The decision (portable XML + Import Module), the pipeline, the verification gates, the diagnostics design, the phased plan |
| [`total/BLUEPRINT.md`](total/BLUEPRINT.md) | **How a UAD 3.6 report lives inside WinTOTAL** — data set, import, calcs, transfers, visibility, writer, validation — with the generated inventories behind it |
| [`total/IMPORT_PROFILE.md`](total/IMPORT_PROFILE.md) | **The rules the package must follow for WinTOTAL to rebuild it** — beyond the UAD spec, each with its evidence |
| [`total/preflight/`](total/preflight/) | `tools/preflight.py`: the package checked against the profile before TOTAL — run it on every generated package |
| [`total/FINDINGS.md`](total/FINDINGS.md) | How WinTOTAL's UAD 3.6 form is built, validated, signed and delivered — confirmed / observed / inferred / untested, kept separate; §9 how a report is recognised (form, TOTAL's configuration, GSE property type → legacy form), §10 WinTOTAL on disk |
| `total-bridge/bridge/detect.py`, `diagnose.py` | `bridge detect` — which report is open and what it is; `bridge diagnose` — one list before import (`--xml`) and after (`--report`), shown clickable in the HUD (`--hud`); `bridge hud --watch` serves the panel's import through the Import Module |
| [`errors/CATALOG.md`](errors/CATALOG.md) | Every error class met so far: symptom, root cause, the generalized mechanism that fixes it, and its test |
| [`total/builds/`](total/builds/) | TOTAL's form model, extracted per web-engine build (fields, pick lists, templates, popups, validators, the MISMO↔field table) |
| [`memory/`](memory/) | The long-lived memory notes, moved in from agent memory so every agent shares them |
| TOTAL's own code | `total-bridge/tools/dump_bundle.py --report <scratch>` keeps a copy of the open build's form-engine modules in `%LOCALAPPDATA%괶-bridge\bundle\<build>\` — read it offline instead of through a live report (E-040). a la mode's code: **never copied into this repository**; findings go here in our own words |
| [`cases/`](cases/) | How a real case becomes a regression case |

## Rules for changing the system

- **No property-specific fixes.** A problem on one case is a symptom of a
  mechanism. Find the mechanism, fix it once, and record it in
  `errors/CATALOG.md` with the test that proves it stays fixed.
- **Generated, not typed.** Anything a specification or TOTAL's own form
  defines is extracted by a tool (`engine/uad/spec/*`,
  `total-bridge/tools/form_model.py`), never transcribed by hand.
- **Validate the validators.** A new check runs against the twelve official
  D-1 samples before it is trusted; a check that faults a published sample is
  a broken check.
- **Keep confirmed and guessed apart.** Write *confirmed* only for what code,
  a specification or a repeatable test shows. Everything else is *observed*,
  *inferred* or *untested*, and says so.
- **Never bypass or silence validation.** The goal is output that satisfies
  the rules, not a quieter error list.
- **Record as you go**, not at the end: a session can stop at any moment.

## Privacy

The repository is private (see `.gitignore`: by the owner's decision the whole
working folder, case material included, is versioned). The documents in *this*
folder still stay generic: describe a case by its shape ("a three-unit
attached rowhouse"), never by address, borrower, appraiser or licence number.
