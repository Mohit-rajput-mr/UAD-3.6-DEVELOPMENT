# Cases as regression tests

Every real case, once delivered, becomes a regression case, so a mistake it
exposed can never come back unnoticed.

A regression case records, generically (no names, addresses or licence numbers
in this folder):

- its **shape**: form, inspection type, property/project type, buildings, units,
  ADUs, outbuildings, approaches, number of comparables per grid;
- where its **input** lives (the case ZIP, kept with the case material);
- the **expected results**: generator gates pass; after import into TOTAL, field
  validation 0, schema valid, UAD fatal 0; round trip equal to the package except
  the listed expected differences; the key figures (indicated values, adjusted
  prices, totals);
- the CATALOG entries it produced.

The twelve official D-1 samples are regression cases too, and run first.

| Id | Shape | Catalog entries | State |
|---|---|---|---|
| R1 | URAR, physical interior + exterior, 3-unit attached rowhouse, 1 building, 4 sales / 3 rentals / 4 GRM comparables, cost + income + sales approaches; source: appraiser's 2.6 XML + report PDF | E-001 … E-027 | delivered 2026-09-27 in TOTAL (field validation 0, UAD 0); end-to-end re-run from files not yet done (T-971) |
