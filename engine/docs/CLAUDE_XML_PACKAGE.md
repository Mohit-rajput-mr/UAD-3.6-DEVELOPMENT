# Writing a complete UAD 3.6 XML from a property folder (for Claude)

The owner attaches a property folder (order sheet, subject data, MLS, comps,
CMA / geodata, floor plans / sketches, photographs) to a Claude Code session.
Claude reads everything and writes **one UAD 3.6 MISMO XML**; the software's
import engine (`POST /api/import`, `engine/uad/importer.py`) turns that one file
into the whole editable report. The software does not analyse documents itself.

## The rules

1. **Start from the right D-1 scenario's structure**, not from memory:
   `engine/uad/templates.py` (`python -c "from uad import templates; print([t.key for t in templates.catalogue()])"`)
   — single family `sf1…sf5`, condo, co-op, manufactured, 2–4 unit. Copy its
   MESSAGE skeleton (`templates.load(key, blank=True)` gives an empty one) and fill it.
2. **Every value in A-1 form.** Field meaning, data point, enumeration and
   format come from `engine/spec/field_index.json` (A-1). Use
   `python engine/uad/dossier.py <section>` to see, per report field: the MISMO
   name, where it lives, its list of allowed values, R/CR/O, the B-1 display rule
   and the H-1 compliance rules. Lists use the enumeration **value**
   (`DeedInLieu`, not "Deed in Lieu"); an "Other" needs its `…OtherDescription`.
3. **Parties by role** (A-1 `IF PartyRoleType = …`): borrower, seller, owner
   (B-1 Case A/B/C: the owner who is the borrower or seller is a second ROLE on
   that PARTY), client (+ its second role: Lender / AMC / …), appraiser,
   supervisor, AMC; fees as `SERVICE_PROVIDER/PROVIDED_SERVICES` in their own
   ROLE of that party.
4. **Comparables**: one `PROPERTY ValuationUseType="SalesComparable"` per sale,
   as many as there are (the grid grows in blocks of three); rental, GRM, land and
   "analysed not used" the same way with their own ValuationUseType.
5. **Repeating things are repeated elements**, never a joined string: each
   room, level, unit, amenity, utility, defect, prior sale is its own block.
6. **Pictures: every photograph goes in an `IMAGE`** in the block it shows
   (subject inspection, a room, a comparable's PROPERTY, the Sales Comparison Map
   under the subject with `ImageCategoryType` `SalesComparableMap`, sketch
   `SubjectPropertyImprovementSketch`, graphs, site exhibits …), with
   `ImageCategoryType`, a caption where the report shows one, and
   **`ImageFileLocationIdentifier` = `\Images\<the real file name in the folder>`**.
   Never invent file names (a file that does not exist cannot be embedded — this
   is why an earlier import showed 13 empty photo boxes).
7. **Never invent facts.** Anything the folder does not establish is left out
   (the appraiser completes it in the editor); conflicting sources are noted in
   the relevant commentary or reported to the owner, not silently resolved.

## Then pack it into one file

```bash
python engine/tools/pack_xml.py appraisal.xml --images "<the property folder>" --out appraisal_portable.xml
```

The packer reads the XML exactly as the import will, embeds every named picture
inside its IMAGE (`EXTENSION/OTHER/kech:EmbeddedFile`, base64 + SHA-256 — valid
against the GSE subschema), validates, and lists anything missing, unreadable or
not UAD 3.6. Fix what it lists and run it again until it reports nothing.
Exit code 0 = ready.

## Then import

Cases screen → **Import a UAD 3.6 appraisal** → choose `appraisal_portable.xml`.
The report opens with every value, list, box, row, comparable and picture in the
editable form; Preview, PDF and XML export are drawn from the same document.
