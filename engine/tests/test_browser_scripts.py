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
    yield "download.js", [(UI / "download.js").read_text(encoding="utf-8")]
    yield "index.html", _scripts((UI / "index.html").read_text(encoding="utf-8"))
    for f in sorted((UI / "shell").glob("*.js")):           # the editor shell (DR phase 2)
        yield f"shell {f.name}", [f.read_text(encoding="utf-8")]


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
                       ("EDIT_JS", flow.EDIT_JS),
                       *((f"shell {f.name}", f.read_text(encoding="utf-8"))
                         for f in sorted((UI / "shell").glob("*.js")))):
        for m in re.finditer(r"(?<![\w.])(alert|confirm|prompt)\(", text):
            found.append(f"{name}: {m.group(0)}")
    assert not found, found


def _stylesheets():
    from app import download
    from uad.report import form
    html = (UI / "index.html").read_text(encoding="utf-8")
    for i, m in enumerate(re.finditer(r"<style[^>]*>(.*?)</style>", html, re.S)):
        yield f"index.html style {i}", m.group(1)
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", download.PAGE, re.S):
        yield "download page", m.group(1)
    yield "EDIT_CSS", form.EDIT_CSS
    js = (UI / "download.js").read_text(encoding="utf-8")
    yield "download.js", re.search(r"var CSS=`(.*?)`;", js, re.S).group(1)
    for f in sorted((UI / "shell").glob("*.css")):          # the editor shell (DR phase 2)
        yield f"shell {f.name}", f.read_text(encoding="utf-8")


@pytest.mark.parametrize("name,css", list(_stylesheets()), ids=lambda x: x if isinstance(x, str) and len(x) < 40 else "")
def test_stylesheets_close_every_rule(name, css):
    """E-155: one rule that lost its closing line (``.dlbtn{...cursor:pointer;``)
    swallowed every rule after it, so the shipped editor drew the report frame
    at 300 x 150 px and the inspector unstyled.  A browser never reports that;
    this does.  Comments and strings are left out of the count."""
    text = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    text = re.sub(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"", "''", text)
    depth, line = 0, 1
    for ch in text:
        line += ch == "\n"
        depth += (ch == "{") - (ch == "}")
        assert depth >= 0, f"{name}: a closing brace with no rule open, near line {line}"
    assert depth == 0, f"{name}: {depth} rule(s) never closed"
