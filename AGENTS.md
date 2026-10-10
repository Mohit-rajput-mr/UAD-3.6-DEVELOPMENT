# For any AI agent working in this repository

Several AI sessions (Claude, Codex, Cursor, Copilot, Gemini...) may be working
here **at the same time**, each on its own branch, unable to message each
other. Do this before anything else:

1. `python engine/agents.py`. It fetches every branch and shows:
   - who is working where, and who holds production;
   - messages addressed to you;
   - tasks two sessions both claim;
   - task (T-) and error (E-) numbers used for two different things;
   - files you and another branch both change.
2. `python engine/agents.py init --focus "what you will do" --push`. This
   gives your branch its own T-/E- number block, and says what you are
   taking.
3. `python engine/agents.py next`: what to pick up, minus what others have
   claimed. Claim it with `python engine/agents.py claim T-xxx --push` (it
   refuses a task another branch holds).
4. Talk with `python engine/agents.py post --to <branch|all> "..." --push`.
   Answer messages with `ack <key> "..." --push`.

Then follow `AI_HANDOVER.md` (the owner's aim, the current position, how to
behave) and `CLAUDE.md` (the non-negotiables). In short:
- The official specifications are the authority.
- Validate every check on the 12 D-1 samples.
- Record work in `TASKS.md` (`python engine/tasks.py`), `_work/HANDOFF.md`
  and `knowledge/errors/CATALOG.md` as it lands.
- Never push to another session's branch.
- Only the session holding production deploys it.

`_work/AGENTS_BOARD.md` keeps the history of how sessions agreed this.
