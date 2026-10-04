# Memory notes (moved into the repository 2026-09-28)

Long-lived notes earlier agents kept in their private memory, now shared here so every agent
inherits them. This copy is the authoritative one; when you learn something durable, write it
here (and in `../errors/CATALOG.md` if it is an error class). Each note is a point-in-time
observation: verify a file, function or flag it names before relying on it.

- [Repo knowledge is the source of truth](uad36-repo-knowledge.md) — read ../README.md first; record every learning here
- [UAD 3.6 build decisions](uad36-build-decisions.md) — browser-editable preview, user-supplied MLS, all property types
- [UAD 3.6 spec assets](uad36-spec-assets.md) — where the spec JSON lives; XSD (not the workbook) owns element order
- [UAD 3.6 zero-guess mandate](uad36-zero-guess-mandate.md) — read fully; never hand-write logic a spec file already defines
- [UAD 3.6 spec-driven architecture](uad36-spec-driven-architecture.md) — which spec file is the authority for each part of the report
- [UAD 3.6 platform features](uad36-platform-features.md) — Review Master, media + buttons, dynamic pages, per-type templates
- [UAD 3.6 spec parsing facts](uad36-spec-parsing-facts.md) — packed Report Location, format precision, irregular plurals, Chromium/Type3
- [UAD 3.6 PDF fidelity work](uad36-pdf-fidelity-gap.md) — user demands pixel-identical to D-1; C-1 engine + span_diff calibration status
- [UAD 3.6 render tricks](uad36-render-tricks.md) — Chromium sub-pixel/zoom/contain, Wingdings2 boxes, B-1 generated text
- [UAD 3.6 autofill agent](uad36-autofill-agent.md) — the report fills itself on screen while the server writes it
- [UAD 3.6 WinTOTAL bridge](uad36-total-bridge.md) — separate installed app; CefSharp CDP on :8088, drop-zone photos, three-call navigation
- [Keep the handoff live](uad36-live-handoff-rule.md) — record goal, status and challenges in TASKS.md and HANDOFF.md as work lands, not at session end
- [Research, never demo data](uad36-research-not-demo.md) — real cases: no blank fields; fill gaps by sourced online research; takeover brief = last section of _work/HANDOFF.md
- [Appraiser report defaults](uad36-appraiser-defaults.md) — MAI always, credentials from profiles/appraiser.json, assignment exhibits = licence + E&O, 18 North adjustment rates
- [Case kit: one command per case](uad36-casekit.md) — sheets -> case.json -> `bridge case` -> `bridge certify`; the traps it encodes
