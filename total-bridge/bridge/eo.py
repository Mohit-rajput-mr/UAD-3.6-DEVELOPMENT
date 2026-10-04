"""TOTAL's E&O panel, read as data.

The panel has two lists.  The live one -- "Field Validation Errors" -- is the
``realTimeValidation`` rule set that ``validate.sweep`` reads.  The other is
**UAD Errors**, TOTAL's own run of the H-1 rules over the MISMO document it
would deliver.  It only exists after **Rerun**, which is why a report can read
"2 errors" until somebody presses the button and then read "71": nothing new
went wrong, a second engine was asked.

Every message carries its H-1 rule (``data-tippy-content="UAD-1078"``) and an
item id (``H1-UAD1078-A-1``), so a message can be traced to a data point in the
delivery specification instead of being read as prose.

Because the rules run over the *delivered XML*, ``Report.mismo()`` is the
quickest way to see what a message is really about: the element is missing
from that document, whatever the screen shows.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import ui

_READ = r"""
(() => {
  const c = document.getElementById('e-and-o-result-container');
  if (!c) return [];
  const rows = [];
  let section = '';
  const walker = document.createTreeWalker(c, NodeFilter.SHOW_ELEMENT);
  let n;
  while ((n = walker.nextNode())) {
    if (n.classList && n.classList.contains('e-and-o-message')) {
      const a = n.querySelector('a');
      rows.push({section, item: n.getAttribute('data-item') || '',
                 rule: a ? (a.getAttribute('data-tippy-content') || '') : '',
                 message: (a ? a.textContent : n.textContent).split(/\s+/).join(' ').trim()});
    } else if (n.children.length === 0 && n.tagName !== 'A' && !n.closest('.e-and-o-message')) {
      const t = (n.textContent || '').trim();
      if (t && t.length < 60) section = t;
    }
  }
  return rows;
})()
"""

_BUSY = "(() => /Generating E&O/.test(document.body.innerText))()"
_HEAD = ("(() => { const h = document.getElementById('e-and-o-warnings-container');"
         " return h ? h.innerText.split(/\\s+/).join(' ') : ''; })()")


@dataclass
class Message:
    section: str
    rule: str
    item: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule:9} [{self.section[:24]:24}] {self.message[:110]}"


def rerun(report, timeout: float = 90.0) -> None:
    """Press Rerun, and wait for TOTAL to finish generating its results."""
    ui.click(report.page, "#e-and-o-refresh", "", 0, settle=3.0)
    end = time.time() + timeout
    while time.time() < end and report.page.evaluate(_BUSY):
        time.sleep(2)
    time.sleep(1.5)


def messages(report, *, fresh: bool = True) -> list[Message]:
    """Every UAD error TOTAL currently lists, with the rule behind each."""
    if fresh:
        rerun(report)
    return [Message(r["section"], r["rule"], r["item"], r["message"])
            for r in (report.page.evaluate(_READ) or [])]


def headline(report) -> str:
    return report.page.evaluate(_HEAD) or ""
