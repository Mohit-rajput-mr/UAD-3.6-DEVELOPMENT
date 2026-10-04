"""The GSEs' own map from legacy form numbers to URAR property characteristics.

UAD 3.6 has no form numbers: "the data that describes the subject property
drives the appraisal report, not a form type/number".  People still say
"a 1025" or "a 2055", and the Import Module is asked to recognise which one a
report is.  The GSEs answered that themselves in *Functioning without Form
Numbers: Mapping Legacy Forms to Redesigned URAR Property Type
Characteristics* (Fannie Mae / Freddie Mac, v1.1, 2025-06-10): six UAD data
points, and the values of each that correspond to each legacy form.  This reads
that document's two tables, so nothing about the mapping is typed by hand.

Output ``spec/legacy_forms.json``:

* ``drivers`` -- the six data points, with the UID and FIDs the document names
  and, joined from A-1 (``spec/enumerations.json``), the MISMO enumeration
  behind every value the document spells in words;
* ``forms`` -- one row per legacy form: Fannie Mae / Freddie Mac numbers, the
  family, the document's description, and per driver the cell *verbatim* plus
  the values it allows;
* ``atypical`` -- the properties the document says have no legacy form, and
  its example table.

Cells are kept verbatim beside the parsed values because one row does not read
literally (``Project Legal Structure`` for 1004C and 1025 is "Condominium or
Cooperative", although both families plainly include properties in no
project); ``bridge/detect.py`` says how it reads that row and why.

    python engine/uad/spec/extract_legacy_forms.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from paths import specs_root

NAME = "Functioning without Form Numbers - Mapping Legacy Forms to URAR v1.1.pdf"
URL = "https://sf.freddiemac.com/docs/pdf/functioning-without-form-numbers-mapping-legacy-forms-to-URAR.pdf"
OUT = Path(__file__).resolve().parents[2] / "spec" / "legacy_forms.json"
ENUMS = Path(__file__).resolve().parents[2] / "spec" / "enumerations.json"
UID = re.compile(r"UID:\s*([\d.]+)")
FIDS = re.compile(r"\b(\d{1,2}\.\d{3})\b")
DRIVER_LABELS = ("Property Valuation Method", "Construction Method", "Subject Site Owned in Common",
                 "Project Legal Structure", "Units Excluding ADUs", "Accessory Dwelling Units")


def _source() -> Path:
    root = specs_root()
    for p in (root / "_Loose_Files_From_Root" / NAME, root / NAME,
              Path(__file__).resolve().parents[3] / NAME):
        if p.exists():
            return p
    raise SystemExit(f"{NAME} not found under {root} -- download it from {URL}")


def _clean(text) -> str:
    """One line: the PDF breaks words inside cells ("On-\\nFrame Modular")."""
    t = str(text or "").replace("-\n", "-").replace("\n", " ")
    return re.sub(r"\s+", " ", t).strip()


def _alternatives(cell: str) -> list[str]:
    """ "A | B", "A or B", "2, 3, or 4" -> ["A", "B", ...]; a dash -> []."""
    if not cell or set(cell) <= set("_—–- "):
        return []
    parts = re.split(r"\s*\|\s*|\s*,\s*or\s+|\s*,\s*|\s+or\s+", cell)
    return [p.strip() for p in parts if p.strip()]


def _enumerations() -> dict[str, dict[str, str]]:
    """UID -> {display text: MISMO enumeration}, from A-1."""
    out: dict[str, dict[str, str]] = {}
    for row in json.loads(ENUMS.read_text(encoding="utf-8")):
        uid = row.get("Unique ID")
        enum = row.get("Supported Enumerations")
        disp = next((v for k, v in row.items() if k.startswith("Output Report Display Text")), "")
        if uid and enum:
            out.setdefault(uid, {})[_clean(disp).split(" R")[0] or enum] = enum
            out[uid].setdefault(enum, enum)
    return out


def _exception(note: str) -> dict | None:
    """A driver's note "Does not apply for High-rise, Mid-rise, or Low-rise
    structures" -> the subject data point whose display texts are those words,
    and its enumerations: when the subject holds one of them, the driver's
    absence is expected."""
    m = re.search(r"Does not apply for (.+?) structures", note)
    if not m:
        return None
    words = {w.lower() for w in _alternatives(m.group(1))}
    hits: dict[tuple[str, str], list[str]] = {}
    for row in json.loads(ENUMS.read_text(encoding="utf-8")):
        disp = next((v for k, v in row.items() if k.startswith("Output Report Display Text")), "") or ""
        if row.get("Subject Property") == "x" and _clean(disp).lower() in words:
            key = (row["Unique ID"], row["MISMO Data Point / Attribute Name"])
            hits.setdefault(key, []).append(row["Supported Enumerations"])
    full = [(k, v) for k, v in hits.items() if len(set(v)) == len(words)]
    if len(full) != 1:
        raise SystemExit(f"note {note!r}: {len(full)} subject data points carry exactly {sorted(words)}")
    (uid, name), values = full[0]
    return {"uid": uid, "data_point": name, "values": sorted(set(values)), "text": m.group(0)}


def _to_enum(word: str, table: dict[str, str]) -> str | None:
    """The document's word for a value -> A-1's enumeration.  The document
    abbreviates ("Traditional" for "Traditional Appraisal"): an exact display
    text wins, then a display text the word begins."""
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    for disp, enum in table.items():
        if norm(disp) == norm(word):
            return enum
    hits = {enum for disp, enum in table.items() if norm(disp).startswith(norm(word))}
    return hits.pop() if len(hits) == 1 else None


def _driver_rows(rows: list[list], label_col: int) -> list[tuple[str, int, int]]:
    """(label, first row, last row) of each driver block in a table."""
    starts = [(i, _clean(r[label_col])) for i, r in enumerate(rows)
              if _clean(r[label_col]) in DRIVER_LABELS]
    out = []
    for n, (i, label) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(rows)
        out.append((label, i, end))
    return out


def _driver_meta(rows, label_col, blocks) -> list[dict]:
    meta = []
    for label, a, b in blocks:
        text = " ".join(_clean(rows[i][label_col]) for i in range(a, b))
        uid = UID.search(text)
        note = re.sub(r"^.*?\)\s*", "", text[text.find("(UID"):]) if "(UID" in text else ""
        meta.append({"label": label, "uid": uid.group(1) if uid else None,
                     "fids": FIDS.findall(text[text.find("FID"):]) if "FID" in text else [],
                     "note": note.strip()})
    return meta


def _mapping(page) -> tuple[list[dict], list[dict]]:
    rows = page.find_tables().tables[0].extract()
    fm = next(i for i, r in enumerate(rows) if _clean(r[0]) == "Fannie Mae Number")
    fr = next(i for i, r in enumerate(rows) if _clean(r[0]) == "Freddie Mac Number")
    pt = next(i for i, r in enumerate(rows) if _clean(r[0]) == "Property Type Characteristics")
    label_col = next(j for j, c in enumerate(rows[pt + 4]) if _clean(c) in DRIVER_LABELS) \
        if any(_clean(c) in DRIVER_LABELS for c in rows[pt + 4]) else 4
    blocks = _driver_rows(rows, label_col)
    first = blocks[0][1]
    form_cols = [j for j, c in enumerate(rows[fm]) if j > label_col and _clean(c)]
    # a family is a run of form columns sharing the merged cells below the
    # valuation method: its first column is where those cells carry text
    shared = next(a for lbl, a, b in blocks if lbl == "Construction Method")
    starts = [j for j in form_cols if _clean(rows[shared][j])]
    family_of = {j: max(s for s in starts if s <= j) for j in form_cols}

    def family_text(start: int, rows_: range) -> str:
        end = min([s for s in starts if s > start] + [len(rows[0])])
        return " ".join(_clean(rows[i][k]) for i in rows_ for k in range(start, end) if _clean(rows[i][k]))

    forms = []
    for j in form_cols:
        s = family_of[j]
        row = {"fannie_mae": _clean(rows[fm][j]), "freddie_mac": _clean(rows[fr][j]),
               "family": family_text(s, range(0, fm)),
               "characteristics": family_text(s, range(pt, first)),
               "drivers": {}}
        for label, a, b in blocks:
            cell = _clean(rows[a][j]) or _clean(rows[a][s])
            row["drivers"][label] = {"cell": cell, "values": _alternatives(cell)}
        forms.append(row)
    return forms, _driver_meta(rows, label_col, blocks)


def _atypical(doc) -> dict:
    # the bullets under the section heading -- a line that is the heading
    # alone (the contents page and the introduction only mention it)
    listed = []
    for page in doc:
        lines = [ln.strip() for ln in page.get_text().splitlines()]
        if "Atypical Properties" in lines and not listed:
            body = "\n".join(lines[lines.index("Atypical Properties") + 1:])
            listed = [_clean(x) for x in body.split("•")[1:]]
            listed = [x for x in listed if x]
    examples = []
    for page in doc:
        if "Atypical Property Examples" not in page.get_text():
            continue
        rows = page.find_tables().tables[0].extract()
        label_col = 4
        blocks = _driver_rows(rows, label_col)
        head = [j for j, c in enumerate(rows[0]) if j > label_col and _clean(c)]
        vm = blocks[0][1]
        # the headings and their value cells are not in the same PDF columns;
        # they pair up in order, one value column per heading
        cols = [j for j, c in enumerate(rows[vm]) if j > label_col and _clean(c)]
        if len(cols) != len(head):
            raise SystemExit(f"atypical table: {len(head)} headings but {len(cols)} value columns")
        for j, col in zip(head, cols):
            name = " ".join(_clean(rows[i][j]) for i in range(0, vm) if _clean(rows[i][j]))
            drivers = {}
            for label, a, b in blocks:
                cell = _clean(rows[a][col])
                drivers[label] = {"cell": cell, "values": _alternatives(cell)}
            examples.append({"name": name, "drivers": drivers})
    return {"listed": listed, "examples": examples}


def extract() -> dict:
    src = _source()
    doc = pymupdf.open(src)
    first = doc[0].get_text()
    version = re.search(r"Document Version\s+([\d.]+)", first)
    date = re.search(r"Version\s+[\d.]+\s+(\w+ \d+, \d{4})", first)
    # the mapping table, not the page describing its columns: its rows are
    # headed "Fannie Mae Number" in the first column
    page = next(p for p in doc if p.find_tables().tables and any(
        _clean(r[0]) == "Fannie Mae Number" for r in p.find_tables().tables[0].extract()))
    forms, drivers = _mapping(page)
    enums = _enumerations()
    for d in drivers:
        table = enums.get(d["uid"] or "", {})
        words = {v for f in forms for v in f["drivers"][d["label"]]["values"]}
        d["enumerations"] = {w: _to_enum(w, table) for w in sorted(words)} if table else {}
        d["not_applicable_when"] = _exception(d["note"])
    return {"source": {"file": src.name, "url": URL,
                       "version": version.group(1) if version else None,
                       "date": date.group(1) if date else None},
            "drivers": drivers, "forms": forms, "atypical": _atypical(doc)}


def main() -> int:
    data = extract()
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(data['forms'])} legacy forms, {len(data['drivers'])} drivers, "
          f"{len(data['atypical']['examples'])} atypical examples -> {OUT}")
    for f in data["forms"]:
        d = f["drivers"]
        print(f"  {f['fannie_mae']:<16} {f['freddie_mac']:<5} "
              + " | ".join(f"{k.split()[0]}={v['values']}" for k, v in d.items()))
    for d in data["drivers"]:
        print(f"  {d['label']:<30} {d['uid']} {d['fids']} {d['enumerations']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
