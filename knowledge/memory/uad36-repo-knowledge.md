---
name: uad36-repo-knowledge
description: "The repo's knowledge/ folder is the owner-mandated permanent source of truth; read it first, write every learning there"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 883733c5-77c7-4979-9f45-5e7455d729c1
  modified: 2026-09-28T12:09:17.020Z
---

Since 2026-09-28 the owner requires that everything learned (WinTOTAL behaviour,
error classes and their mechanisms, mappings, architecture decisions, memory) lives
in the repository at `C:\UAD 3.6 DEVELOPMENT\knowledge\` — README, ARCHITECTURE,
total/FINDINGS, errors/CATALOG, total/builds (extracted TOTAL form model), memory/,
cases/. Agent-private memory (this folder) is only a pointer to it.

**Why:** several agents and future sessions work from the repo; the owner will give
only a case ZIP and expects every past fix to be inherited, with no per-case hacks.

**How to apply:** read `knowledge/README.md` before changing anything; fix problems
as mechanisms, add a CATALOG entry + test; keep confirmed / observed / inferred /
untested separate; write durable learnings into `knowledge/memory/`, not only here.
Related: [[uad36-total-bridge]], [[uad36-zero-guess-mandate]], [[uad36-live-handoff-rule]].
