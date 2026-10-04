"""Is the report ready to sign?  All three of TOTAL's gates, measured honestly.

1. **Field validation** -- only true after every section has been rendered
   (the list depends on what has been shown, E-035), and read with the form
   left on a neutral section.
2. **Schema** -- the delivered document against the GSE subschema, twice: an
   export taken mid-render once reported a phantom error.
3. **UAD rules** (H-1, the E&O panel's "UAD Errors") -- TOTAL runs them only
   once field validation is zero.  With field validation at 3 the panel read
   "UAD Errors: 0"; at 0 the same report read 18 (E-051).  So a UAD count is
   only reported as real when field validation is zero.

    from bridge import certify
    print(certify.run(report))
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import eo, formkit, rtv, schema


@dataclass
class Verdict:
    field_validation: list = field(default_factory=list)
    schema: list = field(default_factory=list)
    uad: list = field(default_factory=list)
    uad_ran: bool = False
    headline: str = ""

    @property
    def ready(self) -> bool:
        return not self.field_validation and not self.schema and self.uad_ran and not self.uad

    def __str__(self) -> str:
        lines = [f"field validation : {len(self.field_validation)}",
                 f"schema           : {len(self.schema)}",
                 "UAD rules        : " + (f"{len(self.uad)}" if self.uad_ran
                                           else "not run (TOTAL runs them only when field validation is 0)"),
                 f"READY TO SIGN    : {'YES' if self.ready else 'NO'}"]
        for p in self.field_validation[:40]:
            lines.append(f"   FV  {p.field}#{p.instance} [{p.section}] {p.message[:90]}")
        for e in self.schema[:20]:
            lines.append(f"   XSD {e[:120]}")
        for m in self.uad[:40]:
            lines.append(f"   UAD {m.rule} {m.item}: {m.message[:110]}")
        return "\n".join(lines)


def run(report, sweep: bool = True) -> Verdict:
    if sweep:
        for s in report.sections():
            try:
                report.goto(s, settle=0.35)
            except Exception:
                pass
    formkit.settle_neutral(report)
    v = Verdict(field_validation=rtv.problems(report))
    first = schema.check(report)
    v.schema = first and schema.check(report)       # a real error survives a second export
    if not v.field_validation:
        v.uad = eo.messages(report)
        v.headline = eo.headline(report)
        v.uad_ran = True
        formkit.settle_neutral(report)
    return v
