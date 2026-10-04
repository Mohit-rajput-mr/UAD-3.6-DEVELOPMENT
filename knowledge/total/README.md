# TOTAL form model, per web-engine build

`builds/<build>/` holds what WinTOTAL's UAD 3.6 form contains, extracted from the
running form and its own bundle by `total-bridge/tools/form_model.py`. Nothing
here is typed by hand.

```
cd total-bridge
python tools/form_model.py --report "<a blank report open in TOTAL>" --out ../knowledge/total/builds
```

Read-only: it attaches over CDP, reads, and writes files here. The bundle copy
it reads goes to `total-bridge/tools/.cache/` and is not committed (it is
a la mode's code; only the extracted tables are kept).

| File | Contents |
|---|---|
| `index.json` | build, bundle hash, date, counts |
| `fields.json` | every control: field, instance, control class, report field ID, section / template / popup, required flag, default visibility, trigger |
| `datafields.json` | per field: pick-list items, shared list, default, format, "other" companion, mutual exclusion |
| `templates.json` | the repeatable sections and rows and their fields — the structure that only exists after Report Setup or an import |
| `popups.json` | each popup, its trigger field(s), its fields |
| `repeatables.json` | min / max per repeatable group |
| `visibility.json` | visibility rule keys and instances |
| `shared_items.json` | shared pick lists |
| `grids.json` | comparable grid managers |
| `section_tree.json` | Report Setup structure of the report it was read from |
| `datamodel.json` | the data layer's group hierarchy |
| `defaults.json` | fields with default values |
| `uid_map.json` | MISMO data point → TOTAL field placements, keyed by the spec's UID and report field ID |
| `validators.json` | field-validation registrations: field, trigger, dependants, rule names, validator class |
| `rtv_messages.json` | the messages those rules show |
| `connector.json` | actions WinTOTAL calls on the form; events the form sends back |

**When TOTAL updates** (the build number in the form's script URL changes),
extract again into a new folder and diff it against the previous build before
trusting the Import Module on the new build.
