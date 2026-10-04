---
name: uad36-spec-assets
description: Where the machine-readable UAD 3.6 spec lives and which source is authoritative for XML element order
metadata:
  type: reference
---

In `C:\UAD 3.6 DEVELOPMENT`, the GSE appendices were extracted to
`engine/spec/*.json` (delivery spec 1,625 data points, 322 enumerated data
points, 728 compliance rules) and `_ref/` holds the XSD, the 12 official GSE
use-case reports and two real ACI-produced reports.

**Critical gotcha:** the delivery spec's "XML Sort Number" column is a workbook
listing order, *not* the schema sequence order — serialising by it yields
XSD-invalid XML. Child element order must come from the XSD's own
`<xs:sequence>` declarations (`engine/uad/xsd_order.py`).

Also: GSE's own sample XMLs carry an `xsi:schemaLocation` on MESSAGE that the
UAD schema forbids, so those files fail validation as shipped. The generator
must not emit it.

**Why:** both cost real debugging time and are invisible from the docs.
**How to apply:** treat the XSD as authoritative for structure, the workbooks
for content rules. See [[uad36-build-decisions]].
