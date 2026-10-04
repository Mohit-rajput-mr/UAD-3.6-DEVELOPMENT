# Testing

## The harness

```bash
python engine/tests/harness.py 12
```

The harness runs nine checks against each of the twelve official D-1 scenarios:

1. package;
2. schema;
3. compliance (H-1 Fatal and Warning counts);
4. fonts;
5. page furniture;
6. grid rows;
7. traceability: every printed value is in the XML;
8. archive structure;
9. overflow: nothing below the body rule.

Each check runs against the GSE's own sample first. A check that faults a
sample is reported as a broken check.

Last recorded result: **87 pass, 0 fail, 21 gap**. The gaps:

- 12 come from the font substitute, which is expected without licensed Myriad Pro;
- 9 are page counts that differ from the samples.

## Unit and integration tests

```bash
python -m pytest -q engine/tests
```

| Suite | Proves |
|---|---|
| `test_access.py` | The gate, the throttle and stateless sessions |
| `test_durable.py` | The shared store, across server copies |
| `test_edit.py`, `test_entry.py`, `test_address_entry.py` | Writes in XSD order, typed formats, address splitting |
| `test_roundtrip.py`, `test_import.py` | Lossless round trip; import normalisation |
| `test_delivery.py`, `test_package.py`, `test_integrity.py` | The UCDP ZIP rules |
| `test_compliance_detects.py`, `validate_compliance_engine.py` | H-1 checks fire on bad input and stay silent on the samples |
| `test_browser_scripts.py` | Every generated script parses (`node --check`); no browser `alert/confirm/prompt` |
| `test_report_rows.py`, `test_golden.py`, `test_cells.py` | Report rows, golden baseline, cell writes |

**Known failures on `main` that predate recent work:**

- `test_cells` (sf1);
- `test_autofill` (condo1 and mh1);
- `test_golden::test_the_pdf_is_text_not_a_picture`.

Status is tracked in `AI_HANDOVER.md` §5.

## Rules for adding a check

1. Run it against the twelve official samples first. If it faults a
   published sample, the check is wrong.
2. Fix a case's problem as a mechanism. Enter it in `knowledge/errors/CATALOG.md` with its test, never as a per-property patch.
3. Never skip or disable a test to get green.

## Browser checks

Playwright with Chromium (`PLAYWRIGHT_BROWSERS_PATH`) drives the editor
end to end. It is used to verify:

- instant updates;
- no native dialogs;
- the two-copy store.

Record each result with its numbers in `AI_HANDOVER.md`.
