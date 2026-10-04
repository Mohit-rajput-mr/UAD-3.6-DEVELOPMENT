import pathlib

p = pathlib.Path("engine/uad/report/form.py")
s = p.read_text(encoding="utf-8")

old = """        if kind == "slot" and base in FIXED_TEXT:
            # a slot in the margin opens the paragraph that follows it; it
            # carries the rule that decides whether the paragraph prints
            if el.get("x0", 99) < 46:
                ctx.placeholders["rule_fid"] = (el.get("ids") or [""])[0]
                continue"""
new = """        if kind == "slot" and base in FIXED_TEXT:
            # A slot in the margin opens the paragraph that follows it and
            # carries the rule that decides whether the paragraph prints.  Some
            # of those fields are also the appraiser's to answer -- whether
            # they have performed prior services, what the additional scope of
            # work was, the date of signature -- so where the field holds a
            # value of its own it is drawn as well as read.
            if el.get("x0", 99) < 46:
                anchor = (el.get("ids") or [""])[0]
                ctx.placeholders["rule_fid"] = anchor
                answer = _fixed_text_answer(ctx, anchor, printed)
                if answer is not None:
                    flush()
                    out.append(answer)
                continue"""
assert old in s, "margin slot"
s = s.replace(old, new, 1)

helper = '''def _fixed_text_answer(ctx: "Ctx", fid: str, printed: str) -> "Block | None":
    """The appraiser's own answer inside a section of fixed wording.

    Most of the Certifications is the report's own text, but a few of its
    slots are questions: "Have you performed services on this property in the
    prior three years?", the description that follows it, the date of
    signature.  Those are drawn with the label A-1 gives them so they can be
    answered, and print once they are.
    """
    b = binding(fid)
    if b is None or not b.data_points:
        return None
    if commentary_category(fid):
        return None                      # commentary has its own box already
    value = text_of(ctx, [fid], " ")
    if not value and not ctx.edit:
        return None
    label = b.label if b.label not in ("{No Label}", "") else b.subsection
    control = _value_control(ctx, fid, value) if ctx.edit else None
    if control is None:
        if ctx.edit:
            control = (f"<span class='v' data-fid='{esc(fid)}' contenteditable='true'"
                       f" spellcheck='true' data-ph='Answer'>{esc(value)}</span>")
        else:
            control = esc(value)
    return Block("text", section=printed, visible=True, fids=[fid],
                 html=(f"<div class='txc certans'><span class='cl'>{esc(label)}</span>"
                       f"{control}</div>"))


def _value_control(ctx: Ctx | None, fid: str, shown: str) -> str | None:'''
s = s.replace("def _value_control(ctx: Ctx | None, fid: str, shown: str) -> str | None:",
              helper, 1)

# a little styling for the answer line
old = """/* a grid row the appraiser adds and names */"""
new = """/* a question the appraiser answers inside a section of fixed wording */
.certans{margin:1.5pt 0}
.certans .cl{font-weight:700;margin-right:4pt}
/* a grid row the appraiser adds and names */"""
assert old in s, "css"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
