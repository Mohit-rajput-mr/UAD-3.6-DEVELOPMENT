"""Label/value extraction for the flat text of MLS and data-vendor sheets.

These PDFs are laid out as label/value pairs, but the text layer breaks them
apart inconsistently: sometimes "Status:" and "Pending" land on one line,
sometimes on two, and occasionally a value spills over several lines before the
next known label starts.  Rather than guess per document, callers hand in the
set of labels they expect and we slice the text between them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


def _normalise(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


@dataclass
class LabeledText:
    """A sheet's text, indexed so any known label can be looked up."""

    lines: list[str]

    @classmethod
    def from_text(cls, text: str) -> "LabeledText":
        return cls([_normalise(ln) for ln in text.splitlines()])

    def find(self, label: str, *, stop_labels: tuple[str, ...] = ()) -> str | None:
        """Value following ``label``, whether inline or on the lines beneath it.

        ``stop_labels`` bounds a multi-line value; without it we take the single
        next non-empty line, which is the common case.
        """
        target = label.rstrip(":").lower()
        for i, line in enumerate(self.lines):
            stripped = line.rstrip()
            low = stripped.lower()
            if not (low == f"{target}:" or low.startswith(f"{target}:")):
                continue

            inline = stripped[len(target) + 1 :].strip()
            if inline:
                return inline
            if not stop_labels:
                return next(
                    (self.lines[j] for j in range(i + 1, len(self.lines)) if self.lines[j]),
                    None,
                )

            collected: list[str] = []
            stops = tuple(s.rstrip(":").lower() for s in stop_labels)
            for follow in self.lines[i + 1 :]:
                low_follow = follow.lower()
                if any(low_follow.startswith(f"{s}:") for s in stops):
                    break
                if follow:
                    collected.append(follow)
            return " ".join(collected) or None
        return None

    def find_bare(
        self,
        label: str,
        *,
        skip: int = 0,
        captions: frozenset[str] = frozenset(),
    ) -> str | None:
        """Value for a label that sits alone on its own line, with no colon.

        Data-vendor reports (ATTOM and assessor extracts) print a caption line
        followed by its value line rather than "Label: value".  When a field is
        blank the next line is the *following caption*, so callers pass the
        caption vocabulary and we return None rather than the neighbour's name.
        """
        target = label.lower()
        blocked = {c.lower() for c in captions} - {target}
        for i, line in enumerate(self.lines):
            if line.lower() != target:
                continue
            found = 0
            for follow in self.lines[i + 1 :]:
                if not follow:
                    continue
                if follow.lower() in blocked:
                    break  # field was empty
                if found < skip:
                    found += 1
                    continue
                return follow
        return None

    def find_all(self, *labels: str) -> dict[str, str]:
        return {label: value for label in labels if (value := self.find(label))}

    def contains(self, needle: str) -> bool:
        needle = needle.lower()
        return any(needle in line.lower() for line in self.lines)


# ------------------------------------------------------------------ coercion
_MONEY = re.compile(r"-?\$?\s*([\d,]+(?:\.\d+)?)")
_INT = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def money(value: str | None) -> float | None:
    """'$1,854,000' -> 1854000.0"""
    if not value:
        return None
    m = _MONEY.search(value.replace(" ", ""))
    return float(m.group(1).replace(",", "")) if m else None


def number(value: str | None) -> float | None:
    """'3,400 Public Records' -> 3400.0"""
    if not value:
        return None
    m = _INT.search(value)
    return float(m.group(0).replace(",", "")) if m else None


def integer(value: str | None) -> int | None:
    n = number(value)
    return int(n) if n is not None else None


_BATHS = re.compile(r"(\d+)\s*\(\s*(\d+)\s+(\d+)\s*\)")


def baths(value: str | None) -> tuple[int, int] | None:
    """OneKey writes '4 (3 1)' meaning 4 total = 3 full + 1 half."""
    if not value:
        return None
    m = _BATHS.search(value)
    if m:
        return int(m.group(2)), int(m.group(3))
    n = integer(value)
    return (n, 0) if n is not None else None


_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")


def date(value: str | None) -> str | None:
    """Any M/D/Y in the value -> ISO 'YYYY-MM-DD'."""
    if not value:
        return None
    m = _DATE.search(value)
    if not m:
        return None
    month, day, year = (int(g) for g in m.groups())
    if year < 100:
        year += 2000
    return f"{year:04d}-{month:02d}-{day:02d}"
