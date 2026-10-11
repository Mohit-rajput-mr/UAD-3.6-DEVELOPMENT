"""A case document is never seen half written (E-186).

A save used to truncate mismo.xml and then write it, so a reader at that
moment -- another request, the background renderer, the vault -- read an
empty file ("Document is empty"; tests/test_grid_rows_browser.py failed one
run in three).  It is now written beside the file and renamed over it.

Run:  python -m pytest -q engine/tests/test_atomic_save.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import cases  # noqa: E402
from app.cases import Store  # noqa: E402


def test_a_save_that_fails_midway_leaves_the_old_document(tmp_path):
    st = Store(tmp_path / "cases")
    case = st.create(template="sf1_appraisal_v1_4", name="atomic", blank=True)
    path = st.xml_path(case.case_id)
    before = path.read_bytes()

    class Broken:                                      # a write that dies half way
        def write(self, target, **kw):
            Path(target).write_bytes(b"<partial")      # what a reader would have seen
            raise OSError("disk full")
    with pytest.raises(OSError):
        cases._write_atomic(Broken(), path)
    assert path.read_bytes() == before
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]


def test_a_save_leaves_no_temporary_file(tmp_path):
    st = Store(tmp_path / "cases")
    case = st.create(template="sf1_appraisal_v1_4", name="atomic", blank=True)
    st.save_tree(case.case_id, st.tree(case.case_id))
    assert sorted(p.name for p in st.folder(case.case_id).iterdir() if p.name.endswith(".tmp")) == []
    etree.parse(str(st.xml_path(case.case_id)))
