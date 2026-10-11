"""When and at what altitude a photograph was taken, read from the file (T-906).

A-1 makes ImageDatetime ("YYYY-MM-DDThh:mm:ssZ") and
AltitudeElevationLinearMeasure conditional on the image, and says "Deliver
@LinearUnitOfMeasureType when AltitudeElevationLinearMeasure is provided"
(D-1 Condo1: ``<AltitudeElevationLinearMeasure LinearUnitOfMeasureType="Feet">25``).
The altitude went out with no unit; a camera's local time went out as UTC.

Run:  python -m pytest -q engine/tests/test_photo_exif.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, delivery, schema, templates


def _photo(path: Path, *, offset: str | None = "-07:00", altitude: float | None = 7.62) -> Path:
    from PIL import Image
    img = Image.new("RGB", (60, 40), "white")
    exif = img.getexif()
    sub = exif.get_ifd(0x8769)
    sub[36867] = "2019:09:05 15:45:34"                      # DateTimeOriginal, local
    if offset:
        sub[36881] = offset                                 # OffsetTimeOriginal
    if altitude is not None:
        gps = exif.get_ifd(0x8825)
        gps[5] = 0                                          # above sea level
        gps[6] = altitude                                   # metres
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    path.write_bytes(buf.getvalue())
    return path


def test_the_time_is_moved_to_utc_by_the_cameras_own_offset(tmp_path):
    meta = delivery.exif(_photo(tmp_path / "a.jpg"))
    assert meta["ImageDatetime"] == "2019-09-05T22:45:34Z"
    assert meta["AltitudeElevationLinearMeasure"] == "25"   # 7.62 m


def test_without_an_offset_the_time_is_as_taken(tmp_path):
    meta = delivery.exif(_photo(tmp_path / "b.jpg", offset=None, altitude=None))
    assert meta == {"ImageDatetime": "2019-09-05T15:45:34Z"}


def test_nothing_is_invented_for_a_photo_that_says_nothing(tmp_path):
    from PIL import Image
    Image.new("RGB", (10, 10)).save(tmp_path / "c.png")
    assert delivery.exif(tmp_path / "c.png") == {}


def test_the_altitude_ships_with_its_unit(tmp_path):
    _photo(tmp_path / "access.jpg")
    item = SimpleNamespace(media_id="m1", category="other", filename="access.jpg",
                           caption="Property Access (Street Scene)", section=4, comparable=0,
                           provenance="")
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    out = delivery.build(tree, [item], tmp_path)
    mine = [i for i in bind.subject(out.tree.getroot()).iter("{*}IMAGE")
            if (i.findtext("{*}ImageFileLocationIdentifier") or "").endswith("access.jpg")]
    assert len(mine) == 1
    alt = mine[0].find("{*}AltitudeElevationLinearMeasure")
    assert (alt.text, alt.get("LinearUnitOfMeasureType")) == ("25", "Feet")
    assert mine[0].findtext("{*}ImageDatetime") == "2019-09-05T22:45:34Z"
    assert schema.validate(out.tree) == []
