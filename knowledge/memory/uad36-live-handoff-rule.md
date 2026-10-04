---
name: uad36-live-handoff-rule
description: "Record goal, status, challenges in TASKS.md and _work/HANDOFF.md as work happens, not at the end of a session"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 55f99e9c-80f8-42ee-9cd0-a94f6af1badd
  modified: 2026-09-24T12:08:41.168Z
---

Update `TASKS.md` (via `python engine/tasks.py`) and `_work/HANDOFF.md` **as
each piece of work lands**, not when a session is wrapping up. The next agent
must be able to see what the owner is trying to achieve, the current task, the
current challenges, and what is verified versus assumed.

**Why:** several AI agents work this folder in sessions that cannot see each
other, and a session can end abruptly on a credit limit. Anything not written
into the folder is lost. The owner raised this after a six-day stretch — the
whole WinTOTAL bridge and a live case — went unrecorded in `HANDOFF.md`.

**How to apply:** close a task only with evidence (`tasks.py done` refuses an
empty note on purpose), and register a new finding the moment it is found, even
mid-task. When a measurement cannot be trusted, write that down too, with the
reason — an unverifiable number recorded as fact is worse than a gap. Put the
narrative in `HANDOFF.md` and the status in `TASKS.md`; keep the newest
`HANDOFF.md` section last and point to it from the top.

Related: [[uad36-zero-guess-mandate]], [[uad36-total-bridge]].
