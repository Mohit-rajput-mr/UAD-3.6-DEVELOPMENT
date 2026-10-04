# Import and export

## Import (`engine/uad/importer.py`, `POST /api/import`)

Accepts any of these:

- an `.xml` file alone;
- a B-1 delivery `.zip` (XML plus `Images/`);
- an XML file with loose images.

Steps: open, parse, normalise, attach pictures, report.

- **Parsing** is safe: entities are off, so there is no network access and no XXE.
- **Normalisation**:
  - the GSE namespace is applied;
  - values are put into their A-1 form, and anything unreadable is reported, never silently changed;
  - elements the subschema does not know are removed but reported;
  - children are put back in XSD order.
- **Pictures** are found in the bundle, at a URL, in a `data:` URI, or as
  embedded base64. A missing picture leaves an empty box and a report line.
- **Atomic.** Nothing is written until everything succeeds; a failed import leaves no case.
- **Provenance.** `provenance.py` records which fields the file answered, and the editor marks them.

## Exports

| Output | Endpoint | What it is |
|---|---|---|
| MISMO XML | `GET /cases/{id}/mismo.xml` | The case document, schema-ordered |
| Portable XML | `GET /cases/{id}/portable.xml` | The MISMO document plus the editor's own state in the `urn:uad36:portable:1` extension namespace, so another installation restores everything. Older files still import. |
| Report PDF | `GET /cases/{id}/report.pdf` | Needs Chromium (local or Docker) |
| Delivery ZIP | `GET /cases/{id}/package.zip` | UCDP package, signed cases only |
| Case bundle | `GET /cases/{id}/bundle`, `POST /cases/restore` | Backup and restore of the whole case |

## The UCDP delivery ZIP (`engine/uad/delivery.py`)

Appendix B-1, "Creation of .zip File" and "Images":

- **One ZIP per appraisal**, at most 60 MB.
- **Contents:** exactly one UAD 3.6 XML, one PDF and an `Images` folder, and nothing else.
- **The PDF** is not embedded. `FOREIGN_OBJECT/ObjectURL` names it relative to the ZIP root.
- **Images** are not embedded. Each IMAGE points into `\Images\`.
  - Every file is referenced at least once.
  - Names are unique.
  - Types come from A-1's `MIMETypeIdentifier` enumeration.
- **Pre-flight.** `GET /package/check` reports everything wrong before export.

The software name written into the XML is "UAD 3.6 Form Filler".
