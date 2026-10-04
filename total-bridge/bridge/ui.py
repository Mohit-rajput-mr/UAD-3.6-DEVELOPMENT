"""Real input, for the parts of TOTAL that only answer to a person.

Most of TOTAL takes a value written into its data layer.  Some of it does not:
the Units and Structures panel, the room and level tables, anything built by a
handler that waits for a mouse.  Dispatching a DOM ``click`` reaches jQuery's
delegated handlers only some of the time -- it did nothing for **+ Add Level**
-- and setting an input's value and firing ``input`` puts a number on the
screen that the model never hears about; the panel put its old value back.

So these go through the Chrome DevTools input domain, which is what a mouse and
a keyboard are as far as the page can tell.
"""
from __future__ import annotations

import time

_CENTER = r"""
(function (sel, text, index) {
  let els = [...document.querySelectorAll(sel)].filter(e => e.getClientRects().length > 0);  // offsetParent is null inside fixed panels
  if (text) els = els.filter(e => (e.textContent || '').trim().replace(/\s+/g, ' ') === text);
  const el = els[index || 0];
  if (!el) return null;
  // 'instant': the navigation list scrolls smoothly, and a rect read during
  // the animation sends the click several items away (2026-10-01)
  el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
  const r = el.getBoundingClientRect();
  // CATALOG E-053: TOTAL zooms #report (CSS zoom 0.9).  On its Chromium the
  // rect is unzoomed while mouse input and elementFromPoint are visual, so a
  // raw centre misses by the zoom.  Take whichever centre actually lands on
  // the element (raw on an engine that already scales rects).
  let z = 1;
  for (let p = el; p; p = p.parentElement) { const v = parseFloat(getComputedStyle(p).zoom); if (v) z *= v; }
  const hit = (x, y) => { const t = document.elementFromPoint(x, y); return !!t && (t === el || el.contains(t) || t.contains(el)); };
  let x = r.x + r.width / 2, y = r.y + r.height / 2;
  // measured at 90 % and 110 %: mouse input is in visual pixels = CSS rect x
  // the element's cumulative zoom (elementFromPoint shares the rect's space,
  // so it cannot tell the two apart -- E-070)
  if (z !== 1) { x *= z; y *= z; }
  return {x, y, w: r.width, h: r.height, tag: el.tagName, count: els.length, zoom: z};
})
"""


def where(page, selector: str, text: str = "", index: int = 0):
    """The centre of the index-th visible element matching, or None."""
    import json
    return page.evaluate(f"({_CENTER})({json.dumps(selector)}, {json.dumps(text)}, {index})")


#: the bridge's own HUD panel (bridge/hud.py) floats over TOTAL's top-right
#: guidance panel -- exactly where "+ Add Level" / "+ Add Room" / "+ Add
#: Exhibit" appear -- and a real click there lands on the HUD (2026-10-01).
_HUD = "document.getElementById('uad36-bridge-hud')"


def _hud(page, visible: bool) -> None:
    page.evaluate(f"(() => {{ const h = {_HUD}; if (h) h.style.visibility = {'\"\"' if visible else '\"hidden\"'}; }})()")


def click(page, selector: str, text: str = "", index: int = 0, settle: float = 0.9) -> bool:
    """Click it the way a person would: move, press, release."""
    _hud(page, False)
    try:
        spot = where(page, selector, text, index)
        if not spot:
            return False
        x, y = spot["x"], spot["y"]
        page.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        page.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
                  button="left", clickCount=1)
        page.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
                  button="left", clickCount=1)
        time.sleep(settle)
        return True
    finally:
        _hud(page, True)


def click_part(page, selector: str, fx: float, fy: float = 0.5, settle: float = 0.9) -> bool:
    """Click at a fraction of the first visible match's box (e.g. the right
    half of a two-sided toggle label), zoom-corrected like `where` (E-053)."""
    import json
    _hud(page, False)
    try:
        spot = page.evaluate("""((sel, fx, fy) => {
          const el = [...document.querySelectorAll(sel)].find(e => e.getClientRects().length > 0);
          if (!el) return null;
          el.scrollIntoView({block: 'center', behavior: 'instant'});
          const r = el.getBoundingClientRect();
          let z = 1; for (let p = el; p; p = p.parentElement) { const v = parseFloat(getComputedStyle(p).zoom); if (v) z *= v; }
          const hit = (x, y) => { const t = document.elementFromPoint(x, y); return !!t && (t === el || el.contains(t)); };
          let x = r.x + r.width * fx, y = r.y + r.height * fy;
          if (z !== 1) { x *= z; y *= z; }
          return {x, y}; })(%s, %f, %f)""" % (json.dumps(selector), fx, fy))
        if not spot:
            return False
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            kw = {} if t == "mouseMoved" else {"button": "left", "clickCount": 1}
            page.send("Input.dispatchMouseEvent", type=t, x=spot["x"], y=spot["y"], **kw)
        time.sleep(settle)
        return True
    finally:
        _hud(page, True)


def clear(page, selector: str, index: int = 0, settle: float = 0.6) -> bool:
    """Empty a field the way a person does: select what is in it, delete, leave.

    ``Input.insertText`` with an empty string inserts nothing, so it cannot
    empty a box; the deletion has to be a key.  Leaving the field with Tab is
    what makes TOTAL run the calculation that depends on it -- a grid's net
    adjustment is the form's own sum, and it is only recomputed when a cell it
    reads is left, not when a value appears in the data layer underneath it.
    """
    import json
    spot = where(page, selector, "", index)
    if not spot:
        return False
    x, y = spot["x"], spot["y"]
    page.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
              button="left", clickCount=1)
    page.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
              button="left", clickCount=1)
    page.evaluate(f"""(() => {{
        const els = [...document.querySelectorAll({json.dumps(selector)})]
                      .filter(e => e.getClientRects().length > 0);
        const el = els[{index}];
        if (!el) return;
        el.focus();
        // Not every cell is an <input>: a grid cell can be a contenteditable
        // or a control with no select(), and calling it blindly throws.
        if (typeof el.select === 'function') el.select();
        else {{
          const range = document.createRange();
          range.selectNodeContents(el);
          const sel = window.getSelection();
          sel.removeAllRanges(); sel.addRange(range);
        }}
    }})()""")
    for key, code, vk in (("Delete", "Delete", 46), ("Backspace", "Backspace", 8)):
        page.send("Input.dispatchKeyEvent", type="keyDown", key=key, code=code,
                  windowsVirtualKeyCode=vk)
        page.send("Input.dispatchKeyEvent", type="keyUp", key=key, code=code,
                  windowsVirtualKeyCode=vk)
    page.send("Input.dispatchKeyEvent", type="keyDown", key="Tab", code="Tab",
              windowsVirtualKeyCode=9)
    page.send("Input.dispatchKeyEvent", type="keyUp", key="Tab", code="Tab",
              windowsVirtualKeyCode=9)
    time.sleep(settle)
    return True


def type_into(page, selector: str, value: str, index: int = 0, settle: float = 0.6) -> bool:
    """Focus the field, select only what is in it, and type over it.

    Ctrl+A is not used: with the page focused it selects the *page*, and the
    keystrokes then go nowhere.  The field is focused and its own text selected
    from inside, and the characters go in through the input domain -- which the
    panel treats as typing, unlike a value assigned from script.
    """
    import json
    spot = where(page, selector, "", index)
    if not spot:
        return False
    x, y = spot["x"], spot["y"]
    page.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
              button="left", clickCount=1)
    page.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
              button="left", clickCount=1)
    page.evaluate(f"""(() => {{
        const els = [...document.querySelectorAll({json.dumps(selector)})]
                      .filter(e => e.getClientRects().length > 0);
        const el = els[{index}];
        if (!el) return;
        el.focus();
        if (typeof el.select === 'function') el.select();
        else {{
          const range = document.createRange();
          range.selectNodeContents(el);
          const sel = window.getSelection();
          sel.removeAllRanges(); sel.addRange(range);
        }}
    }})()""")
    page.send("Input.insertText", text=str(value))
    page.send("Input.dispatchKeyEvent", type="keyDown", key="Tab", code="Tab",
              windowsVirtualKeyCode=9)
    page.send("Input.dispatchKeyEvent", type="keyUp", key="Tab", code="Tab",
              windowsVirtualKeyCode=9)
    time.sleep(settle)
    return True
