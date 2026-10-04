# Preflight — the package checked against the TOTAL import profile, before TOTAL

`total-bridge/tools/preflight.py PACKAGE.xml` — for whoever generates a portable
UAD 3.6 package (the platform, an AI, another program). Every finding names its
rule in `../IMPORT_PROFILE.md`, its CATALOG entry, where it is, and the fix.
Exit code 1 while any **error** remains. It repairs nothing.

## What it checks (2026-09-28)

| Rule | Check | Severity |
|---|---|---|
| P1 | `xsi:` attributes (TOTAL skips values under them) | info — the Import Module strips them |
| P2 | every `xlink:from`/`xlink:to` names an existing label (blanked-sample leftovers) | error |
| P3 | containers with no value; adjustment rows with no type, or a type and nothing else | warning / error |
| P4 | each `SITE_UTILITY` has type **and** ownership; no identical (type, ownership, source) twice | error |
| P8 | a GRM comparable's price and date in one `SALES_HISTORY` | error |
| P11 | every picture named and present (embedded or beside the file) | error |
| P22 | subject `PropertyPhoto` = first building's `DwellingFront`; one front per building | warning |
| P23 | per sales comparable: adjustment rows sum to the net; adjusted price = a price of that comparable + the net | error |

Not yet: P12 (comparable data TOTAL validates beyond UAD) and P13 (explicit $0
where subject and comparable differ). TOTAL's validators do not carry their
conditions, so these are to be learned from measured e2e findings and then
checked against them — not typed from the validator list.

## Validated on the twelve D-1 samples

`d1_results.txt` / `d1_results.json`: **0 errors on all 12**. Two warnings,
both true statements about the samples relative to TOTAL:

- 2-4 unit: its subject photo is a different picture from building 1's front
  photo — TOTAL will deliver building 1's front as the subject photo (E-039).
- SF1: two DwellingFront pictures for one building (the official sample has
  them) — TOTAL has one front slot per building. [U] where the second goes:
  read SF1's e2e result.

Three broken checks were caught by the samples and corrected before this was
recorded: adjustment rows on the **subject** (it describes custom rows without
amounts), two electricity rows (public **and** solar are legitimate), and a
comparable's custom row without an amount (describes, does not adjust — E-017).
Tests: `total-bridge/tests/test_preflight.py` (each check finds its fault on a
small broken package and leaves the legitimate shapes alone).
