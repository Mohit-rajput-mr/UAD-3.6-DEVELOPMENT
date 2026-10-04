import pathlib
p=pathlib.Path("engine/uad/bind.py"); s=p.read_text(encoding="utf-8")

old = '''    days = _days_text(parts)
    if days:
        return days'''
new = '''    days = _days_text(parts)
    if days:
        return days
    address = _address_text(parts)
    if address:
        return address'''
assert old in s; s=s.replace(old,new,1)

helper = '''# An address is not the sum of its data points in the order A-1 lists them.
# Every sample sets it as the street on one line and "City, ST ZIP" on the
# next, which is how a reader expects to see one; joining the parts in the
# order they are declared prints "Treeville 12345 VA".
ADDRESS_PARTS = {"AddressLineText", "AddressUnitDesignatorType",
                 "AddressUnitIdentifier", "CityName", "StateCode", "PostalCode"}


def _address_text(parts: list[tuple[str, str]]) -> str:
    named = {name: value for name, value in parts if value}
    if not named or not set(named) <= ADDRESS_PARTS or "AddressLineText" not in named:
        return ""
    street = named["AddressLineText"]
    unit = " ".join(x for x in (named.get("AddressUnitDesignatorType"),
                                named.get("AddressUnitIdentifier")) if x)
    if unit:
        street = f"{street} {unit}"
    town = named.get("CityName", "")
    state = named.get("StateCode", "")
    postal = named.get("PostalCode", "")
    tail = ", ".join(x for x in (town, " ".join(y for y in (state, postal) if y)) if x)
    return "\n".join(x for x in (street, tail) if x)


NAME_ORDER = ("FirstName", "MiddleName", "LastName", "SuffixName")'''
s=s.replace('NAME_ORDER = ("FirstName", "MiddleName", "LastName", "SuffixName")', helper, 1)
p.write_text(s,encoding="utf-8")

# the report prints the break the address carries
p=pathlib.Path("engine/uad/report/form.py"); s=p.read_text(encoding="utf-8")
old = '''def esc(text: Any) -> str:
    return _html.escape(str(text if text is not None else ""), quote=True)'''
new = '''def esc(text: Any) -> str:
    """HTML for a value, keeping the line break an address carries."""
    return _html.escape(str(text if text is not None else ""), quote=True).replace(
        "\n", "<br>")'''
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
