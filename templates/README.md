# Templates — per-configuration fill sheets

**Not built yet (TASKS: phase 2).** What will live here, generated — never typed:

For each configuration (single family, condominium, cooperative, 2–4 unit,
manufactured home; × inspection type: interior + exterior, exterior only,
desktop, hybrid; × project, ADU, outbuilding and approach variants):

- `<configuration>.json` — every data point that applies: UID, report field ID,
  XPath, required / conditionally required (with the H-1 condition), enumeration,
  format, the TOTAL field(s) that hold it, and the TOTAL import-profile notes;
- the D-1 sample of that configuration as the worked example
  (`specs/official/Appendix D-1 …`).

Generated from `engine/spec/` (A-1, B-1, H-1) by running the H-1 engine on a
minimal document per configuration, and from TOTAL's form model
(`knowledge/total/builds/`). The official samples are examples to read, never a
base to blank and fill (CATALOG E-003, E-004).
