# What my PDF was missing, measured against the GSE samples

Taken from Appendix D-1 SF1 (the Fannie Mae / Freddie Mac published sample),
the ACI 3.6 report you supplied, and the third vendor's output.

## The three PDFs you gave me

| File | Producer | Fonts | Pages | Images |
|---|---|---|---|---|
| `urar_2026-09-14` | iText Core 9.3 | Calibri + Wingdings 2 | 22 | 43 |
| `urar_2026-09-15` | iText Core 9.3 | Calibri + Wingdings 2 | 22 | 36 |
| `15_Church_Street` (ACI) | Chromium / Skia | **Segoe UI** | 13 | 38 |
| GSE SF1 (official) | Adobe InDesign | **Myriad Pro** + Wingdings 2 | 21 | 33 |
| Mine, before this pass | Chromium / Skia | Myriad Pro | 21 | **0** |

Neither `urar_*` file is from this software — both are iText-produced, so they
are another vendor's. Note that **ACI sets the form in Segoe UI**, not the
Myriad Pro the Style Guide specifies, and its output leaks
`<<Does Not Display>>` into the Year Built field. Matching ACI is not the goal;
matching the GSE sample is.

## What was wrong, and what it cost

Measured on SF1's 21 report pages:

| Missing | Evidence in the sample | Effect |
|---|---|---|
| **Row rules** | 1,023 rules, `#939598` 0.5 pt, spanning the full 264 pt column | the page read as a list, not a form — the single biggest reason it looked wrong |
| **Subsection bars** | 54 bands, `#e6e7e8`, **15 pt × 540 pt** | sections ran together with no visible structure |
| **Bar height** | I had 13 pt | the samples draw the bar as a thick *stroke*, so a fill-only survey found few of them and measured those short |
| **Rules around the section tab** | grey 0.5 pt above, ink 0.5 pt across the full measure at its foot | tabs floated with nothing anchoring them |
| **Rule above the footer** | `#939598` 0.5 pt, 540 pt | footer ran into the body |
| **Yes/No pairs** | `Yes ☐ No ☑` inline at the value | booleans printed as a single bare tick |
| **Images** | 33 in the sample, in bordered boxes with the caption inside the top-left | **nothing at all printed** |
| **Narrative blocks** | commentary runs the full 540 pt measure under its own label | commentary was squeezed into the 119 pt value column and ran pages long |

## Fixed in this pass

All eight. Page 2 of the Condo1 case now carries section tabs with their
rules, grey subsection bars, ruled rows, inline Yes/No pairs, a
`Subject Property Exhibits` bar and a bordered exhibit box with its caption —
the same anatomy as SF1 page 4.

## Still not matching

- **Repeating component blocks** (Foundation / Roof / Windows, each with a
  condition and a quality) are printed by the GSEs as a **three-column table**
  with a header row. I print them as alternating label/value rows under one
  bar. The data is right; the arrangement is not.
- **Page count** still differs case by case, because the count follows how much
  is on the page and images are only placed where a section has been given one.
