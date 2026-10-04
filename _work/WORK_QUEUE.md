# The live work queue — UAD 3.6 defect sweep (opened 2026-09-18)

This file is the running record of one long job: *"fix every remaining defect in
the form filler, the field mapping, the dynamic rows, the conditional sections,
the dropdowns, the checkboxes, the placement, the propagation and the
backend-to-frontend filling"*.  It exists so the work survives a session ending:
another agent picks it up here, in the same way, without re-deriving anything.

Read `CLAUDE.md`, `TASKS.md` and `_work/HANDOFF.md` first; then this.

## How this job is worked (keep to it)

1. **The audit is the queue.**  `python engine/uad/coverage.py` classifies every
   one of the 1,524 Report Field IDs IMPLEMENTED / PARTIAL / MISSING / INCORRECT
   / NOT APPLICABLE and writes `_work/coverage.json` and
   `_work/UAD36_CHECKLIST.md`.  Work the largest cause first, not the first row.
2. **Validate the validator before believing it.**  Twice already the audit was
   wrong, not the editor (a `data-tsel` row selector *is* a control; a run of
   tick boxes *is* how C-1 asks an enumerated question).  A check that faults a
   published sample is a broken check.
3. **The specification decides, never the guess.**  A-1 for what a field is and
   where it lives, B-1 for display rules and the grid supplement, C-1 for the
   layout, D-1 for what the answer looks like, H-1 for compliance.  If the
   specification cannot answer, say so in the code comment and record it in
   "Open questions" below rather than inventing.
4. **Fix the cause, not the field.**  Nearly every cluster came from one thing
   (the old page model not knowing a field; `id()` on an lxml proxy; a named row
   not carrying its own identifier).  One fix closes 20 rows.
5. **Verify behaviour, not the diff.**  After each batch: the unit suite
   (`python -m pytest engine/tests -q`), the twelve-sample harness
   (`python engine/tests/harness.py 12`), then the real UI at
   http://127.0.0.1:8766 (passcode `kech`) — click the control, read the value
   back, look at the printed report.
6. **Record it here the same turn.**  Move the item to "Done" with the evidence,
   and add anything new you found to "Queue".

## Where things stood

| | at the start of this job | now |
|---|---|---|
| IMPLEMENTED | 1,200 | **1,223** |
| INCORRECT | 12 | **9** |
| MISSING | 103 | **83** |
| unit tests | 271 pass | 268 pass, 3 to fix (below) |
| harness | 100 pass / 0 fail / 8 gap | 99 pass / 0 fail / 9 gap |

## Done in this job (with the evidence)

- **Properties Analyzed Not Used (A-1 22.17.01-06) is drawn at last.**  C-1 has
  no element for it, so it is laid out from the samples' own rules (SF1 p17:
  54 / 144 / 198 / 288 / 378 pt).  Each row is edited where it prints, several
  reasons stack in the one cell, and the list has Add and per-row Remove.
  `form._not_used_html`; verified add/remove through the API.
- **Every grid has Add/Remove, not just the sales sheet.**  `+ Add Rental
  Comparable #n` and `+ Add GRM Comparable #n` now appear; the route already
  accepted any kind.  Verified: add then remove on sales / rental / grm /
  not_used all 200.
- **Rows the appraiser adds are real rows now.**  B-1's "[Additional Row]" and
  "[Other Exterior/Interior Feature]" are expanded into one row per name the
  case holds (`comparables.specs`), each row labelled with that name, valued by
  the field A-1 gives that column's role, adjustable where the workbook says so,
  and named / renamed / removed through `PUT /cases/{id}/comparables/lineitems`
  (which writes the name to the subject and every comparable at once).  SF1 now
  prints "Below Grade Exterior Access | Walk Out | Walk Up $2,000 ..." exactly
  where the sample prints it, and the 2-4 unit scenario 2 prints "Amenities" in
  its rental grid.
- **Addresses print as the samples set them** — "123 Falling Tree Ct" then
  "Treeville, VA 12345", not "Treeville 12345 VA" (`bind._address_text`).
- **The certifications' own questions are answerable** (scope of work, intended
  use, intended user, inspection certification, prior services and its
  description, supervisor, signature date): a slot inside fixed wording is drawn
  when it holds a value of its own, and an enumerated answer does not print
  twice because the paragraph it chooses *is* the answer.
- **The old page model no longer hides fields.**  `edit.field` and
  `comparables.binding_of` fall back to A-1's index, so a field it never laid
  out still gets its control type, its list of values, and a write that works
  (this was why 29.030 typed free text where A-1 gives three values, and why
  grid cells outside the model silently read and wrote nothing).
- **The report was not deterministic** (found by the filler): `bind._walk_marked`
  grouped instances by `id()`, which lxml does not keep stable, so the same
  document rendered twice could drop a row.  Keyed by element path now.

## Queue — open, in the order to take them

1. **Three tests to settle after the named-row change** (do this first):
   `test_golden[sf3]`, `test_golden[sf4]` (shape moved: check the diff is the
   "Other Interior Feature" rows and regenerate if it is right), and
   `test_workflow::test_a_bracketed_placeholder_row_is_reachable_in_edit_mode_but_not_printed`
   (the contract has changed: a bracketed row is now expanded into named rows,
   and the empty template is the thing that is editable but not printed).
2. **38 table cells with no control** (`coverage.json`, reason "value prints in
   a table but the table cell has no editor control").  Clusters:
   - Rental Information 23.01.x / 23.02.x — the unit rent schedule and the
     comparable rental analysis table draw no cells at all.
   - Cost Approach 25.008 / 25.026 ("@ ___" price per area), 25.041, 25.043.
   - Reconciliation 26.027-26.051 — the [Structure]/[Unit]/[Outbuilding]
     identifier cells.
   - Site 4.043 / 4.050, Sketch 7.002.2, Income 24.027.2.
3. **31 fields A-1 locates that C-1 never placed.**  Most are now reachable
   through the named rows (check the next audit); what is left is Site 4.059 /
   4.069 / 4.099, Outbuilding 12.020.1/.2, and the Summary rows 22.15.03 /
   22.16.01 / 22.05.27.
4. **Instance identifiers** (8.000, 10.053, 10.054, 12.001, 15.002-15.009,
   25.023): the [Structure Identifier] / [Unit Identifier] / [Outbuilding Type]
   placeholders in headings.  The appraiser must be able to name a structure, a
   unit and an outbuilding, and every heading that prints that name must follow.
5. **Nine writes that do not read back** (2.017, 4.017, 13.004, 17.017,
   22.02.09, 23.03.18, 29.063, 29.065, 22.17.02): each is its own bug; take them
   one at a time with `_work/fid.py <fid>` and a write/read-back probe.
6. **The filler must act out what has been added** — the replay already opens
   lists, ticks boxes and types; it should also be seen to add a comparable, add
   a row and name it, and drop a photograph into its box.
7. **Propagation and calculation** (the user's list): a value entered once must
   reach every section that shows it (the Summary already redisplays; check
   totals, price per square foot, area breakdowns) and must not leave a stale
   figure behind when its source changes.
8. **Re-audit from scratch** after 2-7 and take whatever the audit then finds.

## Open questions (a specification cannot answer these)

- **Which grid group an added row belongs to is not recorded anywhere.**  A-1
  enumerates exactly three additional-item types and none of them names the
  group, so a row named in "Site" and one named in "Dwelling(s)" are the same
  thing in the XML.  It is therefore printed once, at the last place the
  workbook offers it -- which is where both samples that use the feature print
  theirs.  If the GSEs clarify this, it belongs in `comparables.specs`.
- Value colour, MyriadPro-Black, subschema v1.4: see the table at the foot of
  `TASKS.md`.

---

## 2026-09-18, late — picked up again after another agent's session

The folder moved on while this queue was open.  Another session added the
import pipeline and measured the app against a **real certified UAD 3.6
package** (`_work/reference/urar_18_north/`, ACI-WB 1.0.3.0): the canonical
`uad/uadmap.py` + `spec/uad_map.json` (678 data points), `uad/importer.py`,
`uad/provenance.py` (what an import answered, shown green), filling from an
uploaded file (`POST /cases/{id}/autofill/source`), per-instance case stores
(`URAR_WORK`), and 43 more tests.  Read `_work/HANDOFF.md` from
"2026-09-18 (later)" onward before doing anything here.

Closed on return:
- The two golden fingerprints this queue left open (sf3/sf4).  The cause was
  real, not a baseline drift: a row the appraiser names was being judged by
  reading its data point *anywhere in the property*, so "Standard Grade" on
  some other interior component printed an empty "Wet Bar" row.  A named row is
  now judged by what it actually holds.  **Full suite 314 passed, harness
  99 pass / 0 fail / 9 gap.**
- Restored the evidence note on T-905, which a mistyped `tasks.py done` here
  overwrote with the word "placeholder"; re-ran `test_package.py` (10 green) to
  write a true one.

The queue below is unchanged and still the next work, with one addition from
the other session's findings: **T-925** (filling from a source with more
comparables than the target leaves an empty extra column) belongs at the top of
item 6, because it is the filler and it is reproducible.
