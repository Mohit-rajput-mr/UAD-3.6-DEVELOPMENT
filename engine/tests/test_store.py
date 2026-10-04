"""Shared review state must be consistent for everyone, on any device.

Two reviewers working at once is the normal case, so these pin the properties
that make that safe: edits survive a restart, a write to one field never
disturbs another, and every open viewer is told what changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from app.store import Store  # noqa: E402

REPORT = "r1"


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "report.db")


def test_edits_persist_across_restart(tmp_path):
    path = tmp_path / "report.db"
    Store(path).apply(REPORT, {"field.1.001": "1750000"}, editor="Priya")

    reopened = Store(path)
    assert reopened.values(REPORT) == {"field.1.001": "1750000"}
    assert reopened.revision(REPORT) == 1


def test_concurrent_edits_to_different_fields_both_survive(store):
    store.apply(REPORT, {"field.1.001": "1750000"}, editor="Priya")
    store.apply(REPORT, {"field.26.009": "Subject To"}, editor="Dan")

    assert store.values(REPORT) == {
        "field.1.001": "1750000",
        "field.26.009": "Subject To",
    }


def test_last_writer_wins_on_the_same_field(store):
    store.apply(REPORT, {"field.1.001": "A"}, editor="Priya")
    store.apply(REPORT, {"field.1.001": "B"}, editor="Dan")
    assert store.values(REPORT)["field.1.001"] == "B"


def test_unchanged_values_do_not_bump_the_revision(store):
    first = store.apply(REPORT, {"field.1.001": "A"}, editor="Priya")
    again = store.apply(REPORT, {"field.1.001": "A"}, editor="Dan")
    assert first == again, "re-saving an untouched form must not wake other viewers"


def test_open_viewers_are_told_what_changed(store):
    queue = store.subscribe()
    store.apply(REPORT, {"field.1.001": "1750000"}, editor="Priya")

    message = json.loads(queue.get(timeout=2))
    assert message["type"] == "changes"
    assert message["editor"] == "Priya"
    assert message["changes"] == {"field.1.001": "1750000"}


def test_a_viewer_can_catch_up_after_reconnecting(store):
    store.apply(REPORT, {"field.1.001": "A"}, editor="Priya")
    store.apply(REPORT, {"field.2.002": "B"}, editor="Dan")

    missed = store.since(REPORT, 1)
    assert [c.field_id for c in missed] == ["field.2.002"]


def test_reports_are_isolated_from_one_another(store):
    store.apply("first", {"field.1.001": "A"})
    store.apply("second", {"field.1.001": "B"})
    assert store.values("first")["field.1.001"] == "A"
    assert store.values("second")["field.1.001"] == "B"


def test_presence_lists_current_editors_and_expires_them(store):
    store.seen("u1", "Priya")
    store.seen("u2", "Dan")
    assert store.editors() == ["Dan", "Priya"]
    assert store.editors(window=-1) == []


def test_reset_returns_the_report_to_what_the_engine_generated(store):
    store.apply(REPORT, {"field.1.001": "edited"})
    store.reset(REPORT)
    assert store.values(REPORT) == {}
    assert store.revision(REPORT) == 0
