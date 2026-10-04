# Section-by-section test of the live form filler (owner's tester, 2026-10-04)

Tested https://uad36-form-filler.vercel.app at main 9c0ea4c. Four blank types (SF1, Condo1,
2-unit, Coop1) had ~265 writes each, ~1,060 in all, plus checks on structure, the grid,
photos, preview / PDF / ZIP and review. WinTOTAL web engine 0.0.1.3901 was the reference
(scratch report "understanding 3.6 dynamic").

| # | Sev | Where | What | Repro |
|---|---|---|---|---|
| B1 | Critical | Sales Contract | After 20.000 = true, 20.003/20.004/20.005/20.006 -> 422 "Element 'SALES_CONTRACT': This element is not expected. Expected is (EXTENSION)" on blank SF/Condo/2-4 | PATCH /fields/20.000 true; PATCH /fields/20.004 425000 |
| B2 | Critical | Structure | 3.005 Units / 3.006 ADUs write a number only; no PROPERTY_UNIT / ADU / section / comp row | 2-unit blank: 3.005=3 -> still 2 units |
| B3 | High | Structure | Ordinary field writes create unnamed PROPERTY_UNITs, an IMPROVEMENT without type, an outbuilding | case f38fee1440be |
| B4 | High | Sales grid | Net adjustment (22.15.08), adjusted price (22.15.13), gross/net % never computed | comp 1: $500,000, +$5,000, -$10,000 |
| B5 | High | Delivery | report.pdf 503 on Vercel; no client-side PDF | any case |
| B6 | High | Review | 171 of 728 H-1 rules not executed | GET /rules |
| B7 | Medium | Yes/No | 10 of 47 Yes/No fields display blank after Yes; pick list shows raw "true" (6.000, 6.004, 6.010, 8.008, 12.009, 19.000, 20.008, 20.009, 21.000, 22.01.05) | GET /fields, options for 6.000 |
| B8 | Medium | Subject | 3.001 Alternate Physical Address refused (AddressLineText not expected) | PATCH /fields/3.001 |
| B9 | Medium | Certifications | 29.066 Date of Signature fails on SF and 2-4 (RELATIONSHIP @arcrole) | PATCH /fields/29.066 |
| B10 | Medium | Grid | Comparables deletable below the minimum (sales 3-24) | DELETE /comparables/3 on 3 comps |
| B11 | Medium | Navigation | Reload loses the open report; case not in the URL | reload |
| B12 | Medium | Delivery | /package/check ready:true while package.zip refuses (409) | 2-unit case |
| B13 | Low | API | Adjustment field without adjust_type filed under another type | PATCH /comparables/1/fields/22.07.27 |
| B14 | Low | Applicability | SF accepts Manufactured Home and co-op data | sweep |
| B15 | Low | Gates | 14.004 / 26.001 "check the related selection first" without naming it | sweep |
| B16 | Confirm | Photos | category "DwellingFront" stored as "other" | POST /media |

Not bugs: table rows are editable through their new row; the Summary is read-only by design.

Test residue on the live site: "2- to 4-unit Appraisal v1.4" (f3c3bc82d333),
"DYNAMIC TEST SF (delete me)" (78ea11412dce).

## The goal that follows (owner's prompt, condensed; full text in the session)

1. A generated blank skeleton (A-1 + XSD), not a D-1 sample, for "New report"; samples become "Open sample".
2. A Property Setup step: property type (SF, condo, co-op, condop, PUD, manufactured, 2-4),
   valuation method, inspection type, construction method, attachment, structure tree
   (dwellings -> units, ADUs by four types, outbuildings, manufactured flag, rent-schedule
   flag per unit), comparable counts.
3. A structure engine (`uad/structure.py`) with `POST/DELETE /api/cases/{id}/structure/{dwelling|unit|adu|outbuilding}`:
   creates/removes A-1 containers with identifiers, re-derives 3.005/3.006/dwelling count,
   adds/removes per-unit rows in every comparable and the rent schedule, names sections by ID;
   loss warning + undo before delete. A typed count runs the same operations.
4. Dynamic applicability from B-1 display rules and H-1 conditions: `/fields` and navigation
   return only applicable items, with the deciding rule exposed.
5. Every applicable field editable; containers created on first write in schema order.
6. Grids within limits: sales 3-24, rental 1-24, GRM 3-24.
7. Fill agent and imports use the same structure engine.

Acceptance: rebuild each of the 12 samples' structure from the skeleton by setup operations
only (test in engine/tests); add/remove a unit on a 2-unit blank; detached ADU on SF; SF shows
no MH/Outbuilding/Project/Rental; condo vs co-op blocks; PUD can start; structure changes
< 1 s warm; harness stays green.
