# Phase 1 count reconciliation — resolved against the authoritative sheets

| Item | User said | I said | Truth | Source |
|---|---|---|---|---|
| Grid rows | 170 | 170 | **170** | B-1 Suppl `Sales Comp Grid`: 171 labelled rows in col A, of which row 1 is the label header |
| `[Additional Row]` positions | 24,46,69,89,144,157 | same | **24,46,69,89,144,157** | same sheet, counting from the first real label (my earlier raw indices were +1 because I counted the label header) |
| "Indicated Value by Sales Comparison Approach" | row 169 | omitted it | **row 169** | 4th-from-last labelled row |
| Em-dash rules | 203 | 202 | **202 rules** (203 sheet rows incl. header) | B-1 Suppl `Em-Dashes in Grids` — we were counting the same thing differently |
| Compliance rules | 728 (confirmed) | 728 | **728** — 592 Fatal, 136 Warning, 728 distinct Message IDs | H-1 v1.5 `UAD Compliance Rules v1.5`: 729 sheet rows |
| Always-display grid rows | 40 | 51 | **32** | F-1 Suppl `Summary of Rows in Comparable Grids` → `Sales Comp Grid`. Neither of us was right; I had been counting the B-1 sheet, which does not carry the always/applicable/relevant flags at all. |

## F-1 Supplement `Sales Comp Grid` — the authority for row behaviour
172 data rows, 8 subsection headings.

- Row Always Displays ....... 32
- Row Displays if Applicable  36
- Row Displays if Relevant .. 106
- Adjustable Row ............ 70

(32+36+106 > 172 because some rows carry both Applicable and Relevant, which
B-1's prose describes as "conditionally required (If Applicable), or may be
provided (If Relevant)".)

The 32 always-display rows:
Property Address, Data Source, Proximity to Subject, List Price, Listing Status,
Sale Price, Transfer Terms, Sales Concessions, Contract Date, Sale Date,
Days on Market, Attached/Detached, Site Influence (Location), View | Range,
Year Built, Heating, Bedrooms, Baths - Full | Half, Finished Area Above Grade,
Finished Area Below Grade, Unfinished Area Below Grade,
Interior Quality and Condition, Quality, Condition, Quality, Condition,
Type | Spaces | Detail, List Price, Sale Price, Net Adjustment Total,
Adjusted Price, Comparable Weight
