---
name: uad36-total-bridge
description: The WinTOTAL mod is a separate installed app driven over CefSharp CDP on 127.0.0.1:8088; the traps that cost hours
metadata:
  node_type: memory
  type: project
  originSessionId: 55f99e9c-80f8-42ee-9cd0-a94f6af1badd
  modified: 2026-09-26T16:26:07.563Z
---

`total-bridge/` is a **standalone installed application**, deliberately not
connected to the UAD 3.6 platform in `engine/` (the owner said so explicitly).
It fills a UAD 3.6 report inside the owner's own WinTOTAL from one portable
MISMO XML with photographs embedded as base64, so the appraiser signs instead of
typing. It must work for driveby, single family, condominium and 2-4 unit.

**Why:** the owner already owns and trusts WinTOTAL; the mod removes the typing
without asking them to switch software, and keeping it uncoupled means neither
product can break the other.

**How to apply:**
- Speak raw Chrome DevTools Protocol to `127.0.0.1:8088` on the *page*
  endpoint. Playwright's `connect_over_cdp` fails on CefSharp
  ("Browser context management is not supported") — do not retry it.
- Section navigation needs all three: `currentActiveSectionKey = key`, then
  `UpdateSectionVisibility()`, then `RefreshReport()`. Setting the key alone
  returns the same 329 fields for every section.
- Photographs upload by dispatching real `dragenter`/`dragover`/`drop` with a
  `DataTransfer` on `.photo-image-wrap`. `DOM.setFileInputFiles` succeeds and
  places nothing, because TOTAL listens to the drop zone, not the input. Always
  read back that the `img` lost `.photo-none`.
- `window.engine.showEandO` is a boolean flag, not a function.
- Controls carry `fmid`, which is the UAD Report Field ID; grid columns are
  prefixed `GSU_` (subject) and `GC1_`..`GC4_` (comparables).
- Before concluding anything about what arrived, walk the sections — a read of
  the form only sees the section it is sitting on.
- TOTAL's 3.6 import silently drops some values the file carries (zoning
  compliance/code, measurement standard, living unit count, structure
  identifier, cost-service name); set them after import (see
  `_work/woodycrest/total_fix.py`). Some checks run only on LeaveField, so a
  data-layer write still shows "required" — type it with `bridge.ui.type_into`.
- A case blanked from an official D-1 sample can keep that sample's people
  (e.g. an empty supervisor SIGNATORY); TOTAL turns it into a signature block.
  Check SIGNATORIES/ROLES before shipping a portable file (2026-09-26, T-970).

Related: [[uad36-build-decisions]], [[uad36-platform-features]],
[[uad36-zero-guess-mandate]].
