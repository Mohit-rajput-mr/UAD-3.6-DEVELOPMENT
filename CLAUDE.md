# UAD 3.6 appraisal report platform — working agreement

> **Every AI agent: read [`AI_HANDOVER.md`](AI_HANDOVER.md) first** — the owner's aim, the main goal, what the last session finished, what to take over next, and how to behave. Keep it current in the same commit as your work.


Several AI agents work in this folder, in sessions that cannot see each other.
Everything below exists so the next one picks up where the last stopped instead
of re-deriving it.

## "Refresh your memory" — and any first session on a device

**Read `START_HERE.md` first.** When the owner says *refresh your memory*, it
means: read `START_HERE.md`, `knowledge/PLAYBOOK.md`, `knowledge/memory/INDEX.md`
and its notes, and the last section of `_work/HANDOFF.md`; run
`python setup/check.py`; if the device is not ready (the WinTOTAL MOD not
installed), run `setup\install.ps1` first; then tell the owner what this is,
whether the device is ready, which appraiser profile signs, and what you need.
A single-family case runs through `python -m bridge.cli case` (the case kit);
the traps it prevents are in `knowledge/PLAYBOOK.md` §10.

## Start here, every session

**Other sessions may be working right now, on other branches.** Run
`python engine/agents.py` first (a session-start hook does it for you), and
read `_work/AGENTS_BOARD.md`: who works where,
which session holds production, the T-/E- number block you may use, and
messages addressed to you. Post there before anything another session
could collide with; never push to another session's branch.

**`knowledge/` is the permanent source of truth** for everything learned —
WinTOTAL's real behaviour, every error class and the mechanism that fixes it,
the architecture decision (portable XML package + Import Module), and the
shared memory notes. Read `knowledge/README.md` first; follow it before
changing anything; write to it as you learn. No property-specific fixes: a
case's problem is fixed as a mechanism and entered in
`knowledge/errors/CATALOG.md` with its test.

0. **`_work/GOAL.md`** — what this is for, the two products and why they stay
   separate, and the owner's standing instructions. One page.
1. **`TASKS.md`** — what the user asked for and what is actually finished.
   Run `python engine/tasks.py next` for the live picture.
2. **`_work/HANDOFF.md`** — the current position: what is half-built, what the
   traps are, what to do next.
3. **`README.md`** — how the system fits together.

`_work/HANDOFF.md` is long and in date order; its **last** section is the
current position, and the top of the file says so.

Keep these three current **as work lands**, not at the end of a session.
Several agents share this folder in sessions that cannot see each other, and a
session can stop on a credit limit — anything not written into the folder is
lost. Record a finding when you find it, even mid-task, and write down a
measurement you could not trust, with the reason: an unverifiable number
recorded as fact is worse than a gap.

## Update the registry in the same turn

When the user gives an instruction, record it:

```bash
python engine/tasks.py add "Location map must save back to the report" --area map
```

When something is finished, close it **with evidence**:

```bash
python engine/tasks.py done T-025 "harness 84 pass / 0 fail on 12 samples"
```

`done` means implemented *and* verified. If it renders but has not been checked
against the Appendix D-1 samples, it is `partial`. The tool refuses a `done`
with no note on purpose — a status with no evidence is worse than no status.

## Non-negotiables

- **The official specifications are the authority.** Not screenshots, not
  another vendor's PDF, not memory. In order: Appendix A-1 (delivery / MISMO
  XML), B-1 (display rules and data mapping), C-1 (layout), D-1 (sample
  scenarios and XML), E (report style), F-1 (reference), G-1 (cross reference),
  H-1 (compliance rules), and the GSE subschema. They are unzipped under
  `C:\3.6 uad zips\_UNZIPPED_ALL`.
- **Generate from the spec files at build time; never hand-type what a spec
  defines.** If you cannot find an authoritative source for something you
  implemented, say so rather than presenting it as verified.
- **Validate your validators.** Every check runs against the twelve official
  samples first. A check that faults a published sample is a broken check. That
  rule has already caught five broken checks here.
- **No fake controls.** Every button is wired to real state or it does not ship.
- **No sample or demo content in a real report**, its preview, or its ZIP.
- **Do not claim compliance without a test that demonstrates it.**

## Layout of the system

```
engine/
  spec/            extracted specification data (JSON) -- generated, not hand-written
  uad/
    spec/          the extractors that produce spec/*.json
    bind.py        label -> field -> value, and how a value prints
    edit.py        writing a value back, in the schema's own order
    compliance.py  the 728 H-1 rules, executed
    review.py      Review Master: schema + compliance + completeness
    report/
      form.py      the form itself, from C-1
      flow.py      measurement, pagination, overflow verification
      rules.py     B-1 display rules
      comparables.py  the comparable grids
      urar.py      the earlier renderer (still used by some tests)
  app/
    main.py        server + passcode gate (hashed verifier in access.json)
    api.py         REST API -- the UI is one client of it, not a privileged path
    cases.py       case storage and the sign-off state machine
    ui/            the editor
  tests/           harness, span/pixel diff, compliance validation, round-trip
  tasks.py         the shared task registry tool
```

## Running it

```bash
python engine/app/main.py          # http://127.0.0.1:8765 (passcode: see app/access.py)
python engine/tests/harness.py 12  # 8 checks x 12 official scenarios
```

## The shape of the pipeline

One canonical model, every output derived from it:

```
form editor -> case document (MISMO XML on disk)
                 |-- compliance engine -> Review Master
                 |-- report renderer   -> appraisal.pdf
                 |-- XML               -> mismo.xml
                 `-- asset manager     -> Images/
                                           `-> validated ZIP
```

The case *is* the MISMO document at every moment, so the file the appraiser
edits is the file that ships, and it is schema-checkable in between.
