"""The coordination tool parallel sessions share (engine/agents.py).

The checks are tested on the collision that made the tool necessary: on
2026-10-10 two sessions each took "the next free number", so T-125 and E-163
meant different things on two branches.

Run:  python -m pytest -q engine/tests/test_agents.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agents
import tasks

ROW = "| {id} | open | render | {title} |  |"


def _tasks(*rows: tuple[str, str]) -> str:
    return "\n".join(ROW.format(id=i, title=t) for i, t in rows)


def test_a_number_used_for_two_things_is_caught():
    ours = _tasks(("T-124", "Roof detail"), ("T-125", "MH1/MH2 Site Exhibits titles differ from D-1"))
    theirs = _tasks(("T-124", "Roof detail"), ("T-125", "DR8 Quality/condition checkboxes not centred"))
    found = agents.id_collisions({"keen": ours, "sleepy": theirs}, "T")
    assert [i for i, _t in found] == ["T-125"]                       # T-124 is the same task
    cat_a = "### E-163 -- A second building showed the first building's front photo\n"
    cat_b = "### E-163 -- The live site could not make the PDF\n"
    assert [i for i, _t in agents.id_collisions({"a": cat_a, "b": cat_b}, "E")] == ["E-163"]


def test_a_task_claimed_twice_is_caught():
    statuses = {"a": {"claims": ["T-510", "T-909"]}, "b": {"claims": ["T-909", "T-1085"]}}
    assert agents.claim_conflicts(statuses) == {"T-909": ["a", "b"]}


def test_blocks_never_overlap():
    others = {"a": {"ids": {"T": [1100, 1149], "E": [170, 179]}},
              "b": {"ids": {"T": [1150, 1199]}}}
    assert agents.next_block(others, "T") == [1200, 1249]
    assert agents.next_block(others, "E") == [180, 189]
    assert agents.next_block({}, "T") == [agents.T_FIRST, agents.T_FIRST + agents.T_BLOCK - 1]
    assert agents.free_in_block([1100, 1102], {1100, 1101}) == 1102
    assert agents.free_in_block([1100, 1101], {1100, 1101}) is None


def test_messages_for_this_branch_until_answered():
    statuses = {
        "me": {"acks": {"other:o-1": "done"}},
        "other": {"messages": [{"id": "o-1", "to": "me", "text": "merged"},
                               {"id": "o-2", "to": "all", "text": "taking T-126"},
                               {"id": "o-3", "to": "third", "text": "not for me"}]},
    }
    assert [m["key"] for m in agents.unread(statuses, "me")] == ["other:o-2"]


def test_new_tasks_are_numbered_from_the_branch_block(monkeypatch):
    monkeypatch.setattr(agents, "current_branch", lambda: "me")
    monkeypatch.setattr(agents, "local_status", lambda b: {"branch": b, "ids": {"T": [1100, 1149]}})
    assert tasks._branch_block() == [1100, 1149]
    monkeypatch.setattr(agents, "local_status", lambda b: None)
    assert tasks._branch_block() is None


def test_a_message_left_in_a_markdown_board_reaches_its_branch():
    board = ("## Messages\n\n"
             "### 2026-10-10 (late night) — from `claude/ecstatic-bohr-d4iffh` to both: a third session\n"
             "- I take pagination.\n\n"
             "### 2026-10-10 — from `claude/keen-turing-3r26sh` to `claude/sleepy-hypatia-e2pzcn`\n"
             "- my own message\n")
    got = agents.board_messages({"claude/ecstatic-bohr-d4iffh": board}, "claude/keen-turing-3r26sh", {})
    assert [m["from"] for m in got] == ["claude/ecstatic-bohr-d4iffh"]
    assert "pagination" in got[0]["text"]
    assert agents.board_messages({"x": board}, "claude/keen-turing-3r26sh", {got[0]["key"]: "done"}) == []
