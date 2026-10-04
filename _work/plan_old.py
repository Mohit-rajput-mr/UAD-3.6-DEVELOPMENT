# ------------------------------------------------------------------ the plan
def plan(target: etree._ElementTree, source: etree._Element,
         folder: Path | None = None, source_folder: Path | None = None,
         media: Iterable[Any] = ()) -> list[Step]:
    """The steps that bring a case's values into this report, in report order."""
    steps: list[Step] = []
    names = dict(bind.SECTIONS)
    seen: set[tuple[str, str, str]] = set()
    source_tree = source.getroottree()

    def add(**kw) -> None:
        steps.append(Step(n=len(steps) + 1, **kw))

    # The source is read for its rows, because a blank report has none of them
    # yet: its own controls are the list of everything that has to be entered.
    for c in controls(source_tree, folder=source_folder):
        if c["secn"] in SKIP_SECTIONS or c["kind"] == GRID:
            continue
        section = c["section"] or names.get(c["secn"], "")
        if c["kind"] == CELL:
            node = bind.find_path(source, c["key"]) if c["key"] else None
            if node is None:
                continue
            writes, display = _in_instance(node, c["fid"], c["data_point"])
            mark = (c["fid"], c["key"], c["data_point"])
            if not writes or mark in seen:
                continue
            seen.add(mark)
            add(secn=c["secn"], section=section, label=_label(c["fid"]),
                fid=c["fid"], kind=CELL, value=writes[0]["value"], display=display,
                data_point=c["data_point"], path=c["key"],
                row_label=c["row_label"], writes=writes)
            continue
        if parties.name_role(c["fid"]) and not c["data_point"]:
            # a party's name is written as a name -- one party per name, the
            # person or the organisation -- not as a first and a last
            display = _party_name(source, c["fid"])
            if display and (c["fid"], "", "name") not in seen:
                seen.add((c["fid"], "", "name"))
                add(secn=c["secn"], section=section, label=_label(c["fid"]),
                    fid=c["fid"], kind=c["kind"], value=display, display=display)
            continue
        writes, display = _read(source, c["fid"], c["data_point"])
        value = writes[0]["value"] if writes else ""
        if not value:
            continue
        if c["kind"] == CHECK:
            if c["pick"] != value:
                continue                     # one box of the run carries it
            display = ""
            writes = [{"data_point": writes[0]["data_point"], "value": c["pick"]}]
        mark = (c["fid"], c["kind"], c["pick"])
        if mark in seen:
            continue
        seen.add(mark)
        add(secn=c["secn"], section=section, label=_label(c["fid"]),
            fid=c["fid"], kind=c["kind"],
            value=c["pick"] if c["kind"] == CHECK else value,
            display=display, data_point=c["data_point"], writes=writes)

    steps.sort(key=lambda s: (s.secn, s.n))
    steps += _grid_steps(target, source, len(steps))
    steps += _photo_steps(media, len(steps))
    for n, step in enumerate(steps, start=1):
        step.n = n
    return steps


def _grid_steps(target: etree._ElementTree, source: etree._Element,
                start: int) -> list[Step]:
    """The comparable grids: the comparables themselves, then every cell."""
    out: list[Step] = []
    root = target.getroot() if hasattr(target, "getroot") else target
    subject = bind.subject(source)
    for kind, (_sheet, role, section) in comparables.SHEETS.items():
        if kind == "not_used":
            continue
        props = comparables.properties(source, role)
        if not props:
            continue
        have = len(comparables.properties(root, role))
        secn = form.SECTION_NUMBER.get(section, 22)
        rows = [r for r in comparables.rows(kind) if not r.heading]

        def step(**kw) -> None:
            out.append(Step(n=start + len(out) + 1, secn=secn, section=section,
                            comp_kind=kind, **kw))

        if subject is not None:
            for row in rows:                       # the subject's own column
                if not row.subject_fid:
                    continue
                text = comparables.value_for(source, row.subject_fid, subject, row)
                if text:
                    step(label=row.label, fid=row.subject_fid, kind=GRID,
                         value=text, display=text, column=0,
                         writes=_grid_writes(source, row.subject_fid, subject, row))
        for number, prop in enumerate(props, start=1):
            if number > have:
                step(label=f"Comparable #{number}", fid="", kind=COMP,
                     value=str(number), display=f"Comparable #{number}",
                     column=number)
            for row in rows:
                if row.comp_fid:
                    text = comparables.value_for(source, row.comp_fid, prop, row)
                    if text:
                        step(label=row.label, fid=row.comp_fid, kind=GRID,
                             value=text, display=text, column=number,
                             writes=_grid_writes(source, row.comp_fid, prop, row))
                if row.adjust_fid:
                    amount = comparables.adjustment_value(prop, row.adjust_type)
                    if amount:
                        step(label=row.label, fid=row.adjust_fid, kind=GRID,
                             value=amount, column=number, adjust=row.adjust_type,
                             display=comparables.adjustment_for(source, row, prop))
    return out


def _grid_writes(source: etree._Element, fid: str, scope: etree._Element,
                 row) -> list[dict]:
    """The data points behind one grid cell, and the type that names its row."""
    binding = bind.binding_for(fid)
    if binding is None:
        return []
    marks = comparables._row_marks(row, binding)
    out: list[dict] = []
    for name, node in bind._walk(source, binding, scope, 1, marks):
        text = (node.text or "").strip()
        if not text or name in marks:
            continue
        out.append({"data_point": name, "value": text,
                    "unit": node.get("AreaUnitOfMeasureType") or ""})
    for key, want in marks.items():
        out.insert(0, {"data_point": key, "value": want, "unit": ""})
    return out


