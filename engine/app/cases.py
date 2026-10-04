"""Cases, their durable state, and the sign-off gate.

A case is a MISMO document plus the media and decisions around it.  Keeping the
document itself as the store -- rather than a private shape that is converted
at the end -- means the file an appraiser edits is the file that ships, and it
is schema-checkable at every moment in between.

The sign-off gate is a state machine, and it is the point of this module.  A
package cannot be exported unless the case is signed; it cannot be signed
unless every section has been acknowledged by the appraiser *and* the Review
Master reports no fatal finding and a valid schema; and any edit after signing
returns the case to review and voids the signature.  That is what makes it
structurally impossible to ship a package nobody reviewed -- the export path
has no branch that skips the check.

State is held in SQLite in WAL mode so several windows on the same case agree,
and survives a restart.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from uad import bind, compliance, integrity, review, schema, templates

# ---------------------------------------------------------------- lifecycle
DRAFT = "draft"
IN_REVIEW = "in_review"
SIGNED = "signed"
EXPORTED = "exported"

# What a case may do next, and nothing else.  Export is reachable only from
# SIGNED, so there is no path that delivers an unreviewed package.
TRANSITIONS = {
    DRAFT: {IN_REVIEW},
    IN_REVIEW: {DRAFT, SIGNED},
    SIGNED: {IN_REVIEW, EXPORTED},
    EXPORTED: {IN_REVIEW},
}

class SchemaRegression(ValueError):
    """A write that would make the MISMO document invalid against the schema."""


def _plain_schema_message(message: str) -> str:
    text = re.sub(r"\{[^}]*\}", "", message)
    return ("That value would make the MISMO document invalid, so nothing was saved: "
            + text.strip())


MEDIA_CATEGORIES = (
    "subject", "comparable", "sketch", "floor_plan", "mls", "map",
    "license", "signature", "other",
)

# Where an image came from.  A sample case is opened from one of the GSEs' own
# D-1 scenarios and carries their photographs; those illustrate the form and
# must never ship inside somebody's appraisal, so they are marked at the point
# they are copied in and the integrity check refuses to let them past.
APPRAISER = "appraiser"
TEMPLATE = "template"


class GateError(RuntimeError):
    """A transition the state machine does not allow."""

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.reasons = reasons or []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Locked:
    """A sqlite connection whose every call holds the store's lock, and whose
    queries are read to the end while it is held."""

    def __init__(self, conn: sqlite3.Connection, lock) -> None:
        self._conn, self._lock = conn, lock

    def execute(self, *args, **kwargs):
        with self._lock:
            return _Rows(self._conn.execute(*args, **kwargs).fetchall())

    def executescript(self, *args, **kwargs):
        with self._lock:
            return self._conn.executescript(*args, **kwargs)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _Rows(list):
    def fetchall(self):
        return list(self)

    def fetchone(self):
        return self[0] if self else None


@dataclass
class Media:
    media_id: str
    category: str
    filename: str
    caption: str = ""
    order: int = 0
    comparable: int = 0          # 0 = subject, 1..n = comparable number
    comp_key: str = ""           # the comparable's durable xlink:label
    section: int = 0             # the report section this image prints under
    size: int = 0
    content_type: str = ""
    provenance: str = APPRAISER  # who this image came from

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Case:
    case_id: str
    name: str
    template: str
    property_type: str
    state: str = DRAFT
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    signed_by: str = ""
    signed_at: str = ""
    acknowledged: list[int] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out = self.__dict__.copy()
        out["can"] = sorted(TRANSITIONS.get(self.state, set()))
        return out


class Store:
    """Every case on this machine, and everything that belongs to one."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "cases.db"
        self._lock = threading.RLock()
        self._connect()

    # ------------------------------------------------------------- storage
    def _connect(self) -> None:
        raw = sqlite3.connect(self.db, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        # The background renderer reads cases from its own thread while
        # requests write them; one connection shared that way must be used by
        # one thread at a time, reads included.
        self.conn = _Locked(raw, self._lock)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY, name TEXT, template TEXT,
            property_type TEXT, state TEXT, created TEXT, updated TEXT,
            signed_by TEXT, signed_at TEXT, acknowledged TEXT);
        CREATE TABLE IF NOT EXISTS media (
            media_id TEXT PRIMARY KEY, case_id TEXT, category TEXT,
            filename TEXT, caption TEXT, ordinal INTEGER, comparable INTEGER,
            size INTEGER, content_type TEXT, section INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, at TEXT,
            actor TEXT, action TEXT, detail TEXT);
        CREATE INDEX IF NOT EXISTS media_case ON media(case_id);
        CREATE INDEX IF NOT EXISTS history_case ON history(case_id);
        """)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(media)")}
        if "section" not in cols:
            self.conn.execute("ALTER TABLE media ADD COLUMN section INTEGER DEFAULT 0")
        if "comp_key" not in cols:
            self.conn.execute("ALTER TABLE media ADD COLUMN comp_key TEXT DEFAULT ''")
        if "provenance" not in cols:
            self.conn.execute("ALTER TABLE media ADD COLUMN provenance TEXT"
                              f" DEFAULT '{APPRAISER}'")
        self.conn.commit()

    def folder(self, case_id: str) -> Path:
        path = self.root / case_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def xml_path(self, case_id: str) -> Path:
        return self.folder(case_id) / "mismo.xml"

    def media_dir(self, case_id: str) -> Path:
        path = self.folder(case_id) / "Images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # --------------------------------------------------------------- cases
    def create(self, *, template: str, name: str = "", blank: bool = True,
               actor: str = "appraiser") -> Case:
        tpl = templates.get(template)
        case_id = uuid.uuid4().hex[:12]
        tree = templates.load(template, blank=blank)
        # the producing software is this platform, whatever the template said
        from uad import delivery
        delivery.stamp_software(tree.getroot())
        self.folder(case_id)
        tree.write(str(self.xml_path(case_id)), encoding="utf-8",
                   xml_declaration=True, pretty_print=True)
        case = Case(case_id=case_id, name=name or tpl.name,
                    template=template, property_type=tpl.property_type)
        with self._lock:
            self.conn.execute(
                "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)",
                (case.case_id, case.name, case.template, case.property_type,
                 case.state, case.created, case.updated, "", "", "[]"))
            self.conn.commit()
        self.log(case_id, actor, "created",
                 f"from template {template} ({'blank' if blank else 'with sample data'})")
        # Templates ship with the GSE's own images; a blank case starts empty.
        if not blank and tpl.images:
            self._copy_template_images(case_id, tpl)
        return case

    def _copy_template_images(self, case_id: str, tpl) -> None:
        target = self.media_dir(case_id)
        for order, src in enumerate(tpl.images[:60], start=1):
            dst = target / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
            self.add_media(case_id, category="other", filename=src.name,
                           order=order, size=dst.stat().st_size,
                           content_type="image/jpeg", provenance=TEMPLATE)

    def get(self, case_id: str) -> Case:
        row = self.conn.execute(
            "SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        return Case(case_id=row["case_id"], name=row["name"],
                    template=row["template"], property_type=row["property_type"],
                    state=row["state"], created=row["created"],
                    updated=row["updated"], signed_by=row["signed_by"],
                    signed_at=row["signed_at"],
                    acknowledged=json.loads(row["acknowledged"] or "[]"))

    def list(self) -> list[Case]:
        rows = self.conn.execute(
            "SELECT case_id FROM cases ORDER BY updated DESC").fetchall()
        return [self.get(r["case_id"]) for r in rows]

    def delete(self, case_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM cases WHERE case_id=?", (case_id,))
            self.conn.execute("DELETE FROM media WHERE case_id=?", (case_id,))
            self.conn.commit()
        shutil.rmtree(self.folder(case_id), ignore_errors=True)

    def touch(self, case_id: str) -> None:
        with self._lock:
            self.conn.execute("UPDATE cases SET updated=? WHERE case_id=?",
                              (_now(), case_id))
            self.conn.commit()
        # every write to a case passes through here, so this is where the
        # background renderer learns there is something new to lay out
        for listener in list(getattr(self, "listeners", [])):
            try:
                listener(case_id)
            except Exception:
                pass

    # ------------------------------------------------------------ document
    def tree(self, case_id: str) -> etree._ElementTree:
        return etree.parse(str(self.xml_path(case_id)))

    def save_tree(self, case_id: str, tree, *, allow_invalid: bool = False) -> None:
        """Write the document.  Every edit, from every route, arrives here, so
        this is where a write that would make the document invalid against the
        GSE subschema is refused -- one that adds a schema error the document
        did not already have.  (A document that is already invalid can still
        be edited; its existing errors are the Review Master's to report.)"""
        path = self.xml_path(case_id)
        if not allow_invalid and path.exists():
            from collections import Counter
            before = self._memo("schema-messages", case_id,
                                lambda: Counter(e.message for e in schema.validate(self.tree(case_id))))
            after = Counter(e.message for e in schema.validate(tree))
            added = after - before
            if added:
                raise SchemaRegression(_plain_schema_message(next(iter(added))))
        tree.write(str(path), encoding="utf-8", xml_declaration=True, pretty_print=True)
        self.touch(case_id)

    def import_xml(self, case_id: str, data: bytes, actor: str = "appraiser") -> None:
        tree = etree.fromstring(data).getroottree()
        # an imported document is taken as it is; its errors are reported
        self.save_tree(case_id, tree, allow_invalid=True)
        self.invalidate(case_id, actor, "imported a MISMO document")

    # ---------------------------------------------------------------- media
    def add_media(self, case_id: str, *, category: str, filename: str,
                  caption: str = "", order: int = 0, comparable: int = 0,
                  comp_key: str = "", section: int = 0, size: int = 0,
                  content_type: str = "", provenance: str = APPRAISER) -> Media:
        if category not in MEDIA_CATEGORIES:
            raise ValueError(f"unknown media category {category!r}")
        item = Media(media_id=uuid.uuid4().hex[:12], category=category,
                     filename=filename, caption=caption, order=order,
                     comparable=comparable, comp_key=comp_key, section=section,
                     size=size, content_type=content_type,
                     provenance=provenance)
        with self._lock:
            self.conn.execute(
                "INSERT INTO media (media_id, case_id, category, filename,"
                " caption, ordinal, comparable, comp_key, size, content_type,"
                " section, provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.media_id, case_id, item.category, item.filename,
                 item.caption, item.order, item.comparable, item.comp_key,
                 item.size, item.content_type, item.section, item.provenance))
            self.conn.commit()
        self.touch(case_id)
        return item

    def media(self, case_id: str, category: str = "") -> list[Media]:
        sql = "SELECT * FROM media WHERE case_id=?"
        args: list[Any] = [case_id]
        if category:
            sql += " AND category=?"
            args.append(category)
        sql += " ORDER BY category, comparable, ordinal, media_id"
        return [Media(media_id=r["media_id"], category=r["category"],
                      filename=r["filename"], caption=r["caption"],
                      order=r["ordinal"], comparable=r["comparable"],
                      comp_key=(r["comp_key"] if "comp_key" in r.keys() else "") or "",
                      section=(r["section"] if "section" in r.keys() else 0) or 0,
                      size=r["size"], content_type=r["content_type"],
                      provenance=(r["provenance"] if "provenance" in r.keys()
                                  else APPRAISER) or APPRAISER)
                for r in self.conn.execute(sql, args)]

    def set_media_caption(self, case_id: str, media_id: str, caption: str) -> None:
        """An exhibit's name, which prints above it (B-1: bold, above the image)."""
        with self._lock:
            self.conn.execute("UPDATE media SET caption=? WHERE media_id=? AND case_id=?",
                              (caption, media_id, case_id))
            self.conn.commit()
        self.touch(case_id)

    # A comparable is referred to by its number everywhere -- the grid, the
    # transfer history, the map, the photograph -- but the number is its
    # position, so reordering changes it.  Anything keyed by the number has to
    # be moved in the same breath, or comparable #1 prints another property's
    # photograph.
    AUTO_CAPTION = "Comparable #"

    def drop_comparable_media(self, case_id: str, number: int) -> None:
        """Delete the images belonging to a comparable that no longer exists."""
        for item in self.media(case_id):
            if item.comparable == number:
                self.remove_media(case_id, item.media_id)

    def backfill_comparable_keys(self, case_id: str, labels: list[str]) -> None:
        """Give older rows the identifier they predate, from the order they
        were stored under, so they can be renumbered like any other."""
        with self._lock:
            for number, label in enumerate(labels, start=1):
                if not label:
                    continue
                self.conn.execute(
                    "UPDATE media SET comp_key=? WHERE case_id=? AND comparable=?"
                    " AND (comp_key IS NULL OR comp_key='')",
                    (label, case_id, number))
            self.conn.commit()

    def renumber_comparable_media(self, case_id: str,
                                  labels: list[str]) -> None:
        """Derive each photograph's comparable number from the case's order.

        ``labels`` is the comparables' durable identifiers in the order the
        report now numbers them, so the number is recomputed rather than
        tracked -- which is what keeps a photograph with its property however
        the grid is rearranged.
        """
        numbers = {label: i for i, label in enumerate(labels, start=1) if label}
        if not numbers:
            return
        with self._lock:
            for label, number in numbers.items():
                self.conn.execute(
                    "UPDATE media SET comparable=? WHERE case_id=? AND comp_key=?",
                    (number, case_id, label))
            for label, number in numbers.items():
                self.conn.execute(
                    "UPDATE media SET caption=? WHERE case_id=? AND comp_key=?"
                    " AND caption LIKE ?",
                    (f"{self.AUTO_CAPTION}{number}", case_id, label,
                     f"{self.AUTO_CAPTION}%"))
            self.conn.commit()
        self.touch(case_id)

    def remove_media(self, case_id: str, media_id: str) -> None:
        row = self.conn.execute(
            "SELECT filename FROM media WHERE media_id=? AND case_id=?",
            (media_id, case_id)).fetchone()
        with self._lock:
            self.conn.execute("DELETE FROM media WHERE media_id=? AND case_id=?",
                              (media_id, case_id))
            self.conn.commit()
        if row:
            path = self.media_dir(case_id) / row["filename"]
            if path.exists() and not self.conn.execute(
                    "SELECT 1 FROM media WHERE case_id=? AND filename=?",
                    (case_id, row["filename"])).fetchone():
                path.unlink(missing_ok=True)
        self.touch(case_id)

    # -------------------------------------------------------------- history
    def log(self, case_id: str, actor: str, action: str, detail: str = "") -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO history (case_id, at, actor, action, detail)"
                " VALUES (?,?,?,?,?)", (case_id, _now(), actor, action, detail))
            self.conn.commit()

    def history(self, case_id: str, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT at, actor, action, detail FROM history WHERE case_id=?"
            " ORDER BY id DESC LIMIT ?", (case_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------- bundles
    # A case, whole, in one ZIP: the MISMO document, the editor's state, every
    # other file in the case folder, the media rows and the history -- and,
    # when asked, the images.  It is how a case survives the loss of the
    # server that held it (a serverless instance is recycled; a disk dies),
    # how it moves to another machine, and what the browser keeps as its
    # recovery copy.  ``_render`` is a cache and is left out.
    BUNDLE_FORMAT = "uad36-case-bundle/1"
    _CASE_ID = re.compile(r"[0-9a-f]{12}")

    def bundle(self, case_id: str, *, images: bool = True) -> bytes:
        import io
        import zipfile
        case = self.get(case_id)
        folder = self.folder(case_id)
        meta = {"format": self.BUNDLE_FORMAT, "case": case.__dict__.copy(),
                "media": [m.to_json() for m in self.media(case_id)],
                "history": list(reversed(self.history(case_id, limit=5000)))}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("case.json", json.dumps(meta, indent=1))
            for path in sorted(folder.rglob("*")):
                rel = path.relative_to(folder)
                if not path.is_file() or rel.parts[0] == "_render":
                    continue
                if rel.parts[0] == "Images" and not images:
                    continue
                z.write(path, "files/" + rel.as_posix())
        return buf.getvalue()

    def restore(self, data: bytes, *, actor: str = "appraiser",
                replace: bool = False) -> Case:
        """Recreate a case from its bundle, under the same case ID.

        An existing case is never overwritten unless ``replace`` is given (an
        explicit choice by the appraiser), so a stale copy can not clobber
        newer work.  A bundle is outside data: paths are confined to the case
        folder, and a signature does not survive the trip -- a restored case
        that was signed or exported returns to review and must be signed
        again, so a hand-edited bundle can never carry a signature past the
        gate."""
        import io
        import zipfile
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            meta = json.loads(z.read("case.json"))
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise ValueError(f"not a case bundle: {exc}")
        if meta.get("format") != self.BUNDLE_FORMAT:
            raise ValueError(f"unknown bundle format {meta.get('format')!r}")
        info = meta.get("case") or {}
        case_id = str(info.get("case_id", ""))
        if not self._CASE_ID.fullmatch(case_id):
            raise ValueError("the bundle names no valid case ID")
        exists = self.conn.execute("SELECT 1 FROM cases WHERE case_id=?",
                                   (case_id,)).fetchone() is not None
        if exists and not replace:
            raise FileExistsError(case_id)
        if "files/mismo.xml" not in z.namelist():
            raise ValueError("the bundle carries no MISMO document")
        etree.fromstring(z.read("files/mismo.xml"))         # must parse
        if exists:
            self.delete(case_id)
            with self._lock:
                self.conn.execute("DELETE FROM history WHERE case_id=?", (case_id,))
                self.conn.commit()
        folder = self.folder(case_id).resolve()
        for name in z.namelist():
            if not name.startswith("files/") or name.endswith("/"):
                continue
            target = (folder / name[len("files/"):]).resolve()
            if folder not in target.parents:
                raise ValueError(f"unsafe path in bundle: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
        state = info.get("state", DRAFT)
        signed_by, signed_at = info.get("signed_by", ""), info.get("signed_at", "")
        voided = state in (SIGNED, EXPORTED)
        if voided or state not in TRANSITIONS:
            state, signed_by, signed_at = (IN_REVIEW if voided else DRAFT), "", ""
        acked = [int(n) for n in (info.get("acknowledged") or []) if str(n).isdigit()]
        with self._lock:
            self.conn.execute(
                "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)",
                (case_id, str(info.get("name", ""))[:300], str(info.get("template", "")),
                 str(info.get("property_type", "")), state,
                 str(info.get("created") or _now()), str(info.get("updated") or _now()),
                 signed_by, signed_at, json.dumps(sorted(set(acked)))))
            for m in meta.get("media") or []:
                if m.get("category") not in MEDIA_CATEGORIES:
                    continue
                fname = Path(str(m.get("filename", ""))).name
                self.conn.execute(
                    "INSERT OR REPLACE INTO media (media_id, case_id, category, filename,"
                    " caption, ordinal, comparable, comp_key, size, content_type,"
                    " section, provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(m.get("media_id", ""))[:40] or uuid.uuid4().hex[:12], case_id,
                     m["category"], fname, str(m.get("caption", "")),
                     int(m.get("order") or 0), int(m.get("comparable") or 0),
                     str(m.get("comp_key") or ""), int(m.get("size") or 0),
                     str(m.get("content_type") or ""), int(m.get("section") or 0),
                     TEMPLATE if m.get("provenance") == TEMPLATE else APPRAISER))
            for h in meta.get("history") or []:
                self.conn.execute(
                    "INSERT INTO history (case_id, at, actor, action, detail) VALUES (?,?,?,?,?)",
                    (case_id, str(h.get("at", "")), str(h.get("actor", "")),
                     str(h.get("action", "")), str(h.get("detail", ""))))
            self.conn.commit()
        # a template's own photographs can be fetched again from the template
        tpl = None
        try:
            tpl = templates.get(str(info.get("template", "")))
        except KeyError:
            pass
        if tpl is not None:
            by_name = {p.name: p for p in tpl.images}
            for m in self.media(case_id):
                dst = self.media_dir(case_id) / m.filename
                if m.provenance == TEMPLATE and not dst.exists() and m.filename in by_name:
                    shutil.copy2(by_name[m.filename], dst)
        self.log(case_id, actor, "restored",
                 "from a case bundle" + ("; the signature was voided and the case "
                                         "returned to review" if voided else ""))
        self.touch(case_id)
        return self.get(case_id)

    def missing_media(self, case_id: str) -> list[Media]:
        """Media rows whose file is not on this server (after a restore without images)."""
        return [m for m in self.media(case_id)
                if not (self.media_dir(case_id) / m.filename).is_file()]

    def put_media_file(self, case_id: str, media_id: str, data: bytes) -> Media:
        """Put back the file of a media row that lacks one; never replace one."""
        item = next((m for m in self.media(case_id) if m.media_id == media_id), None)
        if item is None:
            raise KeyError(media_id)
        path = self.media_dir(case_id) / Path(item.filename).name
        if not path.is_file():
            path.write_bytes(data)
            self.touch(case_id)
        return item

    # ------------------------------------------------------------ the gate
    def acknowledge(self, case_id: str, section: int, actor: str,
                    on: bool = True) -> Case:
        case = self.get(case_id)
        acked = set(case.acknowledged)
        acked.add(section) if on else acked.discard(section)
        with self._lock:
            self.conn.execute(
                "UPDATE cases SET acknowledged=?, updated=? WHERE case_id=?",
                (json.dumps(sorted(acked)), _now(), case_id))
            self.conn.commit()
        self.log(case_id, actor,
                 "acknowledged" if on else "withdrew acknowledgement",
                 f"section {section}")
        return self.get(case_id)

    def blockers(self, case_id: str) -> list[str]:
        """Everything standing between this case and a signature."""
        case = self.get(case_id)
        report = self.review(case_id)
        out: list[str] = []
        if report.counts.get("schema"):
            out.append(f"{report.counts['schema']} schema error(s): the MISMO "
                       "document is not valid against the GSE subschema")
        if report.counts.get("fatal"):
            out.append(f"{report.counts['fatal']} fatal compliance finding(s)")
        # A borrowed photograph or a photograph on the wrong comparable is not
        # a compliance rule, but it is just as much a reason not to ship.
        for finding in integrity.check(self.tree(case_id), self.media(case_id)):
            if finding.severity == integrity.FATAL:
                out.append(f"{finding.message} ({finding.detail})"
                           if finding.detail else finding.message)
        drawn = self.sections_present(case_id)
        missing = [n for n in drawn if n not in set(case.acknowledged)]
        if missing:
            names = ", ".join(review.SECTIONS.get(n, str(n)) for n in missing[:4])
            more = f" and {len(missing) - 4} more" if len(missing) > 4 else ""
            out.append(f"{len(missing)} section(s) not yet reviewed: {names}{more}")
        return out

    # ------------------------------------------------ work done once per version
    def _version(self, case_id: str) -> tuple:
        path = self.xml_path(case_id)
        if not path.exists():
            return (case_id, 0, 0)
        stat = path.stat()
        return (case_id, stat.st_mtime_ns, stat.st_size)

    def _memo(self, name: str, case_id: str, compute):
        """A result that depends only on the document, kept until it changes."""
        cache = self.__dict__.setdefault("_memos", {})
        key = (name,) + self._version(case_id)
        if key not in cache:
            for old in [k for k in cache if k[0] == name and k[1] == case_id]:
                cache.pop(old, None)
            cache[key] = compute()
        return cache[key]

    def review(self, case_id: str, include_review: bool = True):
        return self._memo(f"review:{include_review}", case_id,
                          lambda: review.build(self.tree(case_id), include_review=include_review))

    def sections_present(self, case_id: str) -> list[int]:
        """Section numbers this case actually prints, so review covers them all.

        Read from the renderer that prints the report (``report/form.py``),
        not the retired one, which listed sections the page never showed.
        """
        from uad.report import form

        def compute():
            blocks = form.build(self.tree(case_id))
            return sorted({form.section_number(b.section) for b in blocks
                           if b.visible and form.section_number(b.section)})
        return self._memo("sections", case_id, compute)

    def transition(self, case_id: str, to: str, actor: str,
                   *, force: bool = False) -> Case:
        case = self.get(case_id)
        allowed = TRANSITIONS.get(case.state, set())
        if to not in allowed:
            raise GateError(
                f"a {case.state} case cannot move to {to}; it may move to "
                f"{sorted(allowed) or 'nothing'}")
        if to == SIGNED and not force:
            reasons = self.blockers(case_id)
            if reasons:
                raise GateError("this case cannot be signed yet", reasons)
        signed_by = case.signed_by
        signed_at = case.signed_at
        if to == SIGNED:
            signed_by, signed_at = actor, _now()
        elif to in (DRAFT, IN_REVIEW):
            signed_by, signed_at = "", ""
        with self._lock:
            self.conn.execute(
                "UPDATE cases SET state=?, updated=?, signed_by=?, signed_at=?"
                " WHERE case_id=?", (to, _now(), signed_by, signed_at, case_id))
            self.conn.commit()
        self.log(case_id, actor, f"state -> {to}")
        return self.get(case_id)

    def invalidate(self, case_id: str, actor: str, why: str) -> None:
        """Any change to a signed case voids the signature.

        The appraiser signed a particular document.  Once it changes, that
        signature no longer describes what would ship, so the case drops back
        to review and has to be signed again.
        """
        case = self.get(case_id)
        self.touch(case_id)
        if case.state in (SIGNED, EXPORTED):
            with self._lock:
                self.conn.execute(
                    "UPDATE cases SET state=?, signed_by='', signed_at='',"
                    " updated=? WHERE case_id=?", (IN_REVIEW, _now(), case_id))
                self.conn.commit()
            self.log(case_id, actor, "signature voided", why)

    def exportable(self, case_id: str) -> tuple[bool, list[str]]:
        case = self.get(case_id)
        if case.state in (SIGNED, EXPORTED):
            return True, []
        return False, (self.blockers(case_id)
                       or [f"the case is {case.state}; it must be signed first"])
