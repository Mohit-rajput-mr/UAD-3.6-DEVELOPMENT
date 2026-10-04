"""Every script the server writes into a page parses as JavaScript.

The editing script, the layout bootstrap and the freshness script live inside
Python strings, where one backslash too few turns "\\n" in the JavaScript
into a real line break -- a syntax error that silently disables editing in
the report frame.  It happened twice; this keeps it from shipping a third
time.  Needs node (skipped without it).

Run:  python -m pytest -q engine/tests/test_browser_scripts.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NODE = shutil.which("node")
UI = Path(__file__).resolve().parents[1] / "app" / "ui"


def _scripts(html: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"<script>(.*?)</script>", html, re.S)]


def _check(code: str, tmp_path: Path, name: str) -> None:
    f = tmp_path / f"{name}.js"
    f.write_text(code, encoding="utf-8")
    r = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, f"{name}: {r.stderr[:500]}"


def _sources():
    from app import api
    from uad.report import flow
    yield "EDIT_JS", _scripts(flow.EDIT_JS.replace("__BODY_BOTTOM__", "926"))
    yield "FIT_JS", _scripts(flow.FIT_JS)
    yield "FRESH_JS", _scripts(api.FRESH_JS)
    yield "client layout", _scripts(api._client_layout_page("0123456789ab", "form"))
    yield "MEASURE_JS", ["(" + flow.MEASURE_JS + ")"]
    yield "OVERFLOW_JS", ["(" + flow.OVERFLOW_JS + ")"]
    yield "dialog.js", [(UI / "dialog.js").read_text(encoding="utf-8")]
    yield "vault.js", [(UI / "vault.js").read_text(encoding="utf-8")]
    yield "index.html", _scripts((UI / "index.html").read_text(encoding="utf-8"))


@pytest.mark.skipif(not NODE, reason="node is not installed")
@pytest.mark.parametrize("name,codes", list(_sources()), ids=lambda x: x if isinstance(x, str) else "")
def test_parses(name, codes, tmp_path):
    assert codes, f"{name}: no script found"
    for i, code in enumerate(codes):
        _check(code, tmp_path, f"{name.replace(' ', '_').replace('.', '_')}_{i}")


def test_no_browser_dialogs_in_the_editor():
    """The platform's dialogs only (app/ui/dialog.js): never the browser's
    "... says" alert / confirm / prompt, which the owner asked to be gone."""
    from uad.report import flow
    found = []
    for name, text in (("index.html", (UI / "index.html").read_text(encoding="utf-8")),
                       ("EDIT_JS", flow.EDIT_JS)):
        for m in re.finditer(r"(?<![\w.])(alert|confirm|prompt)\(", text):
            found.append(f"{name}: {m.group(0)}")
    assert not found, found
