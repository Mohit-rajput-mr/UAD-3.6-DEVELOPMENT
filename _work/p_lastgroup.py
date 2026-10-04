import pathlib
p=pathlib.Path("engine/uad/report/comparables.py"); s=p.read_text(encoding="utf-8")
old = '''            if row.label == ADDITIONAL_ROW:'''
new = '''            if row.label == ADDITIONAL_ROW:
                # MISMO keeps every additional line item of a grid under one
                # ComparableAdjustmentType -- there are only three in A-1, and
                # none of them names the group the row printed in -- so the
                # group cannot be read back from the document.  The row is
                # therefore printed once, at the last place the workbook offers
                # it, which is where both samples that use the feature print
                # theirs: after the property's own rows and before Quality and
                # Condition.
                if row.order != last_additional.get(line_item_type(row)):
                    continue'''
assert old in s; s=s.replace(old,new,1)

old = '''    subject = bind.subject(root)
    spec = rows(kind)'''
new = '''    subject = bind.subject(root)
    spec = rows(kind)
    last_additional: dict[str, int] = {}
    for r in spec:
        if r.label == ADDITIONAL_ROW:
            last_additional[line_item_type(r)] = r.order'''
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
