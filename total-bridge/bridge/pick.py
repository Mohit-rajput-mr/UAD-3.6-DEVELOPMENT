"""Choosing an exhibit's category from the list the report offers.

TOTAL builds the category list from the room schedule: if the subject has three
bedrooms on level 2, the list offers ``Level 2 - Bedroom (1)``, ``(2)`` and
``(3)``.  A photograph arriving from a file is captioned in the appraiser's own
words -- ``BEDROOM 3``, ``BASEMENT FAMILY ROOM``, ``HALF BATH`` -- so the two
have to be matched rather than looked up.

The matching is deliberately conservative.  A wrong category files a bathroom
photograph as a bedroom, which is worse than leaving it unset for a person to
finish: an unset category is visibly unset, and a wrong one is not.  So a
choice is only made when the words genuinely agree, and each option is used at
most once -- three bedroom photographs fill the three bedroom slots in order
rather than all landing on the first.
"""
from __future__ import annotations

import json
import re

# Words that mean the same room in two vocabularies.  A caption says
# "BASEMENT"; the schedule says "B1".
SAME = {
    "basement": {"b1", "basement"},
    "b1": {"b1", "basement"},
    "bathroom": {"bath", "bathroom"},
    "bath": {"bath", "bathroom"},
    "halfbath": {"half", "bath"},
    "powder": {"half", "bath"},
    "bed": {"bedroom", "bed"},
    "bedroom": {"bedroom", "bed"},
    "utility": {"utility", "laundry"},
    "laundry": {"utility", "laundry"},
    "lounge": {"living"},
    "den": {"family"},
}

# Words that carry no room meaning and should not earn a match on their own.
NOISE = {"level", "room", "the", "a", "of", "and", "-", "unit", "photo"}

_WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in NOISE]


def expand(tokens: list[str]) -> set[str]:
    out: set[str] = set()
    for token in tokens:
        out.add(token)
        out |= SAME.get(token, set())
    return out


def ordinal(tokens: list[str]) -> int | None:
    """The number in a caption or option, if it has one."""
    for token in tokens:
        if token.isdigit():
            return int(token)
    return None


def score(caption: str, option: str) -> float:
    """How strongly a caption and an option agree, 0 to 1.

    Only the words that mean a room count.  Two captions that share nothing but
    "Level" and "Room" score zero, which is what keeps a boiler out of a
    bedroom.
    """
    left, right = words(caption), words(option)
    if not left or not right:
        return 0.0
    a, b = expand(left), expand(right)
    named_a = {t for t in a if not t.isdigit()}
    named_b = {t for t in b if not t.isdigit()}
    if not named_a or not named_b:
        return 0.0
    shared = named_a & named_b
    if not shared:
        return 0.0
    # Numbers are deliberately ignored.  "Level 2 - Bedroom (1)" carries two of
    # them and neither means what a caption's "BEDROOM 2" means -- the 2 is the
    # storey.  Reading one as the other files photographs in the wrong rooms
    # while looking confident.  Rooms of a kind are instead filled in the order
    # the captions arrive, which is defensible and repeatable.
    return min(len(shared) / max(len(named_a), len(named_b)), 1.0)


def match(caption: str, options: list[str], taken: set[str],
          floor: float = 0.5) -> str | None:
    """The option this caption belongs to, or None when nothing fits well."""
    best, best_score = None, 0.0
    for option in options:
        if option in taken:
            continue
        value = score(caption, option)
        if value > best_score:
            best, best_score = option, value
    return best if best_score >= floor else None


# --------------------------------------------------------------------- page
_OPEN = """
(async () => {
  const el = document.querySelector('[fn="%(fn)s"][instance="%(inst)s"]');
  if (!el) return {ok: false, why: 'no such control'};
  const box = el.getBoundingClientRect();
  const opts = {bubbles: true, cancelable: true, view: window,
                clientX: box.left + box.width / 2,
                clientY: box.top + box.height / 2};
  el.focus();
  // A bare click does not open this control; it wants the whole sequence.
  for (const kind of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    el.dispatchEvent(kind.startsWith('pointer')
        ? new PointerEvent(kind, opts) : new MouseEvent(kind, opts));
  }
  await new Promise(done => setTimeout(done, 700));
  const labels = Array.from(document.querySelectorAll('label'))
      .filter(n => n.offsetParent !== null)
      .map(n => (n.textContent || '').trim())
      .filter(t => t);
  return {ok: true, options: Array.from(new Set(labels))};
})()
"""

_CHOOSE = """
(async () => {
  const wanted = %(wanted)s;
  // Open this control's own list first.  Reading the options earlier does not
  // leave it open, and clicking an option that is not on screen does nothing
  // while reporting nothing wrong.
  const el = document.querySelector('[fn="%(fn)s"][instance="%(inst)s"]');
  if (!el) return {ok: false, why: 'no such control'};
  const box = el.getBoundingClientRect();
  const opts = {bubbles: true, cancelable: true, view: window,
                clientX: box.left + box.width / 2,
                clientY: box.top + box.height / 2};
  el.focus();
  for (const kind of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    el.dispatchEvent(kind.startsWith('pointer')
        ? new PointerEvent(kind, opts) : new MouseEvent(kind, opts));
  }
  await new Promise(done => setTimeout(done, 650));

  const hit = Array.from(document.querySelectorAll('label'))
      .filter(n => n.offsetParent !== null)
      .find(n => (n.textContent || '').trim() === wanted);
  if (!hit) return {ok: false, why: 'option not on screen'};
  hit.click();
  await new Promise(done => setTimeout(done, 550));
  const got = (el.getAttribute('data-value') || el.textContent || '').trim();
  el.blur();
  document.body.click();
  await new Promise(done => setTimeout(done, 150));
  return {ok: got === wanted || got.includes(wanted), got: got};
})()
"""


def options(report, fn: str, instance: str) -> list[str]:
    """Open a category control and read what it offers."""
    result = report.page.evaluate(_OPEN % {"fn": fn, "inst": instance},
                                  await_promise=True) or {}
    return result.get("options", []) if result.get("ok") else []


def choose(report, fn: str, instance: str, wanted: str) -> dict:
    """Pick one option, and read back what the control kept."""
    return report.page.evaluate(
        _CHOOSE % {"fn": fn, "inst": instance, "wanted": json.dumps(wanted)},
        await_promise=True) or {"ok": False, "why": "no answer"}
