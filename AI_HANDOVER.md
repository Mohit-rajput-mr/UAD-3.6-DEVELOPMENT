# AI HANDOVER — read this first, every session, every agent

Several AI agents (Claude sessions, other assistants) work on this repository
one after another. A session can end at any moment — a credit limit, a
timeout, a closed tab. **This file is how the next agent continues exactly
where the last one stopped, with the same goal, the same approach and the same
behaviour.** If you are a new agent: read this whole file before doing
anything, then follow §7 ("How to take over").

If you finish a piece of work, update §4 and §5 of this file **in the same
commit** as the work. If you stop mid-task, write what you were doing in §5
before you stop. An agent that leaves this file stale breaks the chain.

---

## 1. The owner's aim (in their words, condensed)

The owner is a working appraiser. They want a **live, working UAD 3.6 report
form filler** on the web:

- It must **look the same as the official UAD 3.6 URAR report** from the GSE
  documentation (Appendix C-1 layout, D-1 samples, E style guide).
- An appraiser opens it, starts a report (blank or from a template/XML), fills
  every section, adds photos, exhibits (maps, market charts), comparables and
  adjustments, and gets out a **valid UAD 3.6 deliverable**: `appraisal.pdf` +
  `mismo.xml` + `Images/` in a ZIP — one canonical document, so the editor,
  preview, validation, PDF and XML never disagree.
- It must be **deployed and working live** on Vercel, with continuous
  deployment, protected by the passcode **`uad3.6`**.
- **No "Kech" branding anywhere** (owner, 2026-10-04). The software names
  itself "UAD 3.6 Form Filler".
- Wanted after the core works: a professional, modern, appraiser-friendly UI
  (glassmorphism card / admin-dashboard style), complete permanent
  documentation, a forensic audit of every section and field, regression
  tests, a second audit, and a final report.

## 2. What we (the AI) are trying to achieve — the main goal

**Make the live site do the whole appraisal job correctly, end to end, without
glitches**, and keep every claim provable:

1. Every page renders exactly like the official report (fidelity to D-1).
2. Every field saves, re-reads and validates (MISMO XML against the GSE
   subschema; H-1 compliance rules).
3. Photos, exhibits, comparables, maps, market charts all land in the report.
4. The deliverable ZIP is valid.
5. Nothing is invented: the official specifications are the authority
   (A-1, B-1, C-1, D-1, E, F-1, G-1, H-1, GSE subschema — under
   `specs/official/`). Never claim "Fannie Mae approved" or compliance without
   a test that shows it.

## 3. Where things are live

| What | Where |
|---|---|
| Live site | https://uad36-form-filler.vercel.app — passcode `uad3.6` |
| GitHub | `Mohit-rajput-mr/UAD-3.6-DEVELOPMENT` — **`main` auto-deploys to Vercel production** on every push |
| Working branch | `claude/keen-turing-3r26sh` (fast-forwarded into `main` after each verified fix) |
| Vercel | team `team_yLARSrJxmy8eba17j9vCfKRT`, project `prj_DAFzsrP7CsyJX3tG838oglSyqQ3l` (`uad36-form-filler`), region iad1 |
| Shared case store | Vercel Blob store `uad36-cases` (private); `BLOB_READ_WRITE_TOKEN` is injected by Vercel — never print or copy it |
| Entry point on Vercel | `api/index.py` → `engine/app/main.py` |

**Deploy = commit, run the checks, push to the branch, fast-forward `main`.**
No Vercel tool calls are needed to deploy. Use the Vercel connector only to
read build state and runtime logs (`get_runtime_logs`, `get_runtime_errors`,
`list_deployments`). This container cannot open vercel.app directly.

How the live site works (so you don't re-derive it):
- Vercel runs **several server copies**, each with its own `/tmp`. Cases live
  in the shared Blob store (`engine/app/durable.py`); the middleware in
  `engine/app/main.py` pulls a case before each request and pushes it after
  each change.
- Vercel has **no Chromium**, so the **appraiser's browser lays the report
  out** (client layout: `/layout/{kind}/galley` → measure →
  `/layout/{kind}/pages`). PDF export on Vercel answers 503 (needs a server
  with Chromium, e.g. Docker).
- Fonts: licensed Myriad Pro is not in the repo; open-licence substitutes with
  Myriad's published widths are used (`engine/uad/report/substitute_fonts.py`).
- Anything named by a content digest or used as a "is it current?" key must be
  **built deterministically and from content, never from file times** — every
  server copy must compute the same answer.

## 4. What the recent sessions finished (with evidence)

Most recent first. Each line: what, and how it was verified.

- **2026-10-04 — NOT YET DEPLOYED.** The branch `claude/confident-maxwell-id7biz` (head
  = the commit that carries this line) holds slices 1-2 plus the Roof detail composer
  (T-124). Full suite on `ee2dd82` (slice 2): 328 pass, 4 fail -- all four pre-existing
  (`test_cells` sf1, `test_autofill` condo1/mh1, `test_golden::test_the_pdf_is_text_not_a_picture`);
  harness 87 pass / 0 fail. The agent's push to `main` was refused by the session's
  permission classifier ("Production Deploy"), so Vercel still serves the older `main`.
  To deploy: `git push origin claude/confident-maxwell-id7biz:main` (fast-forward, main is
  an ancestor), then check the Vercel build is READY and ask the owner to try it live.
- **2026-10-04 — Audit slice 2: grid fidelity** (E-073, E-074, E-075).
  (a) Grid cells compose as B-1 says (`Local Road | Asphalt`, `3 Miles SE`,
  `Driveway | 4 | Pavers` + a Garage line, enumeration order, address on two lines).
  (b) The Supervisory Appraiser certifications print only with a supervisory
  appraiser (B-1 p396; extractor fixed, regenerated specs; matches 12/12 official
  PDFs). (c) An empty grid cell prints an em-dash only where B-1's per-row
  sentence says so (`report/dashes.py`; exact dash count on 4 samples, was 2-6x
  over); Contract Price / Date subject values and the all-comparables row
  visibility fixed. Whole-report word diff vs D-1: 21411 -> 17706. Harness 87 pass
  / 0 fail; `test_report_rows.py` 27 pass. Golden baseline regenerated (+2 grid
  rows per sample: Contract Price / Date).
- **2026-10-04 — Audit slice 1: wrong data in repeated-row tables fixed** (E-071,
  E-072). Laying our SF1/MH1 pages beside the official PDFs showed the Exterior
  Features table printing the wall's comment on every row, and the Utilities
  table printing the water comment against Electricity and Gas. Cause: rows told
  apart by a label read only the first block. Fix: `form._label_blocks` /
  `row_instances`; C-1's clipped IDs (4.06 for 4.069, 4.05, 4.00, 20.00) repaired
  at load (`form._complete_clipped_ids`), which also removes two duplicate prints.
  Tests: `engine/tests/test_report_rows.py` (5/7 fail on the old code). Harness
  87 pass / 0 fail / 21 gap. New audit tools: `_work/audit/render_all.py`,
  `linediff.py` (whole-report word diff vs the D-1 PDFs; total is the number to
  drive down).
- **2026-10-04 — Negative dollar amounts print as `$(10,000)`** (bind.py
  `format_value`, kind "amount"). Authority: B-1 Figure 22-5 (page 297 of B-1
  v1.4) and all 12 D-1 PDFs (121 x `$(n)`, 0 x `-$n`). Harness 87 pass / 0 fail.
- **2026-10-04 — Audit: no character falls back to a system font.** The MH2
  sample's "®" printed in a system font because the kerned fonts were subset
  to a hand-typed list; the set is now derived from the WinAnsi (cp1252)
  encoding, and the font cache key includes the build code. Harness over the
  12 official samples: **87 pass · 0 fail** · 21 gap (was 1 fail).
- **2026-10-04 — This handover file (`AI_HANDOVER.md`)** created at the
  owner's request and linked from `START_HERE.md`, `README.md`, `CLAUDE.md`,
  `_work/HANDOFF.md`.
- **2026-10-04 — Saves/photos/exhibits update the live report** (7d77174).
  The endless "Updating the report…" spinner is gone. Verified in Chromium
  against two server copies with one shared store: edit shown in 3 s, photo
  shown in 3 s; 121 tests pass. **Owner confirmed it works live.**
- **2026-10-04 — "Kech" removed everywhere** (fc16dbe, f57cd44). Vendor/product
  in exported XML is "UAD 3.6 Form Filler"; XML extension namespace is
  `urn:uad36:portable:1`; old files still import. Full scan: 0 occurrences.
- **2026-10-04 — Layout 500 on the live site fixed** (345ffb5): font-cache race
  and non-deterministic font bytes.
- **2026-10-04 — New blank report loads on the live site** (31a0cb1): shared
  durable case store. `engine/tests/test_durable.py` 9/9.
- **2026-10-04 — Continuous deployment from GitHub `main` working.**
- Earlier in the same effort: report renders without licensed fonts
  (substitutes), passcode `uad3.6` (PBKDF2 verifier in
  `engine/app/access.json`, never in client code), blank templates validate
  against the GSE subschema, case bundles (backup/restore), browser-side layout.

Full narrative and traps: last sections of `_work/HANDOFF.md`.
Task registry with evidence: `TASKS.md` (`python engine/tasks.py next`).

## 5. In progress right now / what to take over next

**State of the text-fidelity audit (updated 2026-10-04, slice 2).** Method:
`python _work/audit/render_all.py` (renders the 12 samples to `_work/harness/`,
~1 min), then `python _work/audit/linediff.py [-v] [sample]` (whole-report word
diff vs the D-1 PDFs; the TOTAL is the number to drive down: 21411 at the start,
17706 now), and look at pages side by side (render with pymupdf and read the PNGs --
this found the real bugs; the text diff alone hides wrong-but-present data).
Restore the tracked PDFs afterwards: `git checkout -- _work/harness/`.

Done: E-071..E-075 (repeated-row tables read their own block, clipped C-1 IDs, grid
cell composition/units/order/dashes, supervisory gate). Known NOT a rule: the order of
data sources in a grid cell (samples disagree for identical XML).

Still wrong, found by looking at SF1 pages (each is a task in TASKS.md, T-119..T-121,
T-123): **Unit Interior** (Level and Room Detail, Kitchen and Bathroom Details, Interior
Features read only the first instance -- B-1 10.029-10.049 gives every rule; the XML
shape and the official table are in `_work/HANDOFF.md`'s last section), the Apparent
Defects tables (Dwelling Exterior, Unit Interior) and per-section Exhibits with their
captions, the Outbuilding grid rows (ADUs excluded; area/heating/utilities), roof detail
("Estimated Age:" on its own line, "(Unobservable)"), Utilities header rows that always
print, Market "Price Trend Source", Cost approach `1,568 Sq. Ft. @ $121.25` and
`45 years`, page counts differing on 9 of 12 samples.
Pre-existing failing tests (also fail on the commit before slice 1): `test_cells` sf1,
`test_autofill` condo1/mh1, `test_golden::test_the_pdf_is_text_not_a_picture`.

**Next, in priority order:**

1. The 21 harness "gap" lines: 12 are the font substitute (expected until the
   owner installs licensed Myriad Pro); 9 are **page counts that differ from the
   official samples** (e.g. 24 vs 20, 26 vs 29). Investigate page-break rules
   against Appendix E/C-1 — a mechanism, never a per-sample tweak.
2. Forensic audit of every section/field against B-1 display rules and the D-1
   PDFs (render each sample, compare text per page with the official PDF;
   suspected items still to confirm: a missing "Price Trend Source" row, a
   stray "Yes" in Highest & Best Use, manufactured-home rows (HUD Data Plate)
   showing on single-family editable pages, unit-address comma formatting, the
   Graph row listing all images, a default defects sentence). Confirm each
   against the spec before changing it; record each in
   `knowledge/errors/CATALOG.md` with its test.
3. Pre-existing test failures (fail on `main` too, not caused by recent work):
   `test_cells` sf1 (fields 4.093 / 10.031 / 10.045 not writable),
   `test_autofill` condo1/mh1 blank fill. `total-bridge/tests` fail at
   collection in this Linux container (Windows-only bridge).
4. PDF export on a host with Chromium (Docker image) — the owner asked for
   Docker; on Vercel PDF is 503 by design.
5. UI redesign (reference style: glassmorphism card, admin dashboards, content
   list UI) — after correctness, never at its expense.
6. Permanent documentation set (architecture, data model, field registry,
   UAD/MISMO mappings, rules, validation, import/export, images, comps,
   adjustments, maps, PDF, XML, persistence, deployment, testing), a GSE
   vendor-recognition note (requirement vs inference; never claim approval),
   second audit, final report.
7. Housekeeping: the old `UAD_P1..UAD_P7` and `UAD_BUILD` patch env vars on the
   Vercel project are dead weight now that `main` carries the code — delete
   them when convenient (the build skips the patch because
   `engine/app/access.json` exists).

## 6. The approach — keep it unchanged

- **Specifications are the authority.** Generate from spec files; never
  hand-type what a spec defines. If you cannot find the source, say so.
- **Validate your validators**: every check runs against the 12 official
  samples first; a check that faults a published sample is a broken check.
- **No property-specific fixes.** A case's problem is fixed as a mechanism,
  entered in `knowledge/errors/CATALOG.md` with its test.
- **No fake controls, no sample/demo content in a real report.**
- **Prove before you push**: run the relevant tests (`python -m pytest -q
  engine/tests/...`, `python engine/tests/harness.py 12`, the
  `engine/tests/test_*.py` scripts); for a live bug, reproduce it locally
  first (two server copies behind a round-robin proxy with a shared
  `URAR_DURABLE_DIR` reproduces Vercel), show the fix, then push.
- **Record as you go**: `TASKS.md` via `python engine/tasks.py add/done`
  (done needs evidence), `_work/HANDOFF.md` new section at the end, and §4/§5
  of this file.
- Commit messages describe the mechanism and the evidence. Never put secrets,
  tokens or the passcode verifier's inputs in commits, logs or client code.

## 7. How to take over (new agent checklist)

1. Read this file, then `CLAUDE.md`, `_work/GOAL.md`, the **last** section of
   `_work/HANDOFF.md`, and run `python engine/tasks.py next`.
2. `git status` and `git log --oneline -15` — compare with §4/§5 here. If the
   tree has uncommitted changes that §5 describes, continue them; do not
   discard them.
3. Pick up §5 "In progress", then the next item in order.
4. After each verified fix: commit → push the working branch → fast-forward
   `main` (`git push origin HEAD:main`) → check the Vercel build is READY →
   ask the owner to try it live if you cannot reach vercel.app.

## 8. How to behave with the owner — this matters

- **Act, don't ask.** The owner has said, repeatedly and emphatically: continue
  with all decisions without asking, and do not ask for permission chunk by
  chunk. Make the reasonable decision, do it, verify it, report briefly.
  Ask only when something truly cannot proceed without them (a credential, a
  business choice such as a company name).
- **Keep the tool calls that trigger approval prompts to a minimum.** The owner
  finds repeated "allow once" prompts very annoying. Prefer git for deploys.
  If a safety check blocks an action, do not try to get around it; say in one
  or two lines what is blocked and the one thing the owner can do.
- **Short, plain updates.** What changed, how it was verified, the live link.
  No long surveys of options.
- **Be honest.** Say what was verified and what was not (e.g. "verified
  locally; could not open the live site from this container"). Never present
  an unverified result as done.
- Never re-introduce "Kech", never weaken the passcode, never put demo data in
  a real report, never claim GSE approval.
