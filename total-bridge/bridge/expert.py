"""What to put in a field the file does not answer.

The UAD 3.6 file is the first authority and ``mismo.Case`` is asked first.
What is left over falls into three kinds, and they are not treated alike.

**Derivable.**  The answer follows from something the file does say.  A
property with public sewer is not on a private one, so the "private" tick is
off; a report that states an interior inspection method has an answer for
"Interior"; a subject that is not listed has no listing type.  These are
written.

**Conventional.**  The file is silent, but there is only one professionally
sensible answer for a dwelling of this kind, and the report says elsewhere
what was assumed -- a residential street's influence on a residential
dwelling is neutral, a flood Zone X carries no special hazard, an appraisal
with no defects has no defect description.  These are written too, and each
one carries the reason in a comment here.

**Nobody's to invent.**  A credential number, a signature date, a licence
level, the client's own reference number.  These are never filled: they are
the appraiser's to give, and a made-up licence number in a signed report is a
different kind of problem from an empty box.  ``LEAVE`` lists them, and the
run reports them rather than guessing.

Everything here is keyed by TOTAL's own field name, so it holds for any 3.6
form -- driveby, single family, condominium, 2-4 unit -- rather than for one
report.
"""
from __future__ import annotations

# Never filled by the bridge: the appraiser gives these, or the client does.
LEAVE = {
    "APPRAISER_LEVEL": "the appraiser's credential level",
    "SIGNER_LIC_CERT_LEVEL": "the signer's credential level",
    "SIGNER_LIC_CERT_ID": "the signer's licence number",
    "SIGNER_LIC_CERT_EXPIRATION": "the signer's licence expiry",
    "SIGNED_DATE": "the date of signature",
    "APPRAISER_ASC_IDENTIFIER": "the appraiser's ASC identifier",
    "CONTACT_CLIENT_REFERENCE_ID": "the client's own reference number",
    "CONTACT_APPRAISER_REFERENCE_ID": "the appraiser's file number",
}

# Conventional answers, by TOTAL's field name.  Each says why it is safe.
CONVENTIONAL = {
    # A residential street beside a residential dwelling is neither a help nor
    # a harm to value; B-1 expects the neutral answer stated rather than left
    # blank.
    "SIT_INFL_IMP": "Neutral",
    "SIT_VWIMP_IMP": "Neutral",
    # An influence on the street the subject is on is at the property itself.
    "ALIAS_SIT_INFL_PROX": "Adjacent",
    # FEMA Zone X is "area of minimal flood hazard": no special hazard area.
    "SIT_FEAT_HZRD_ZONE_DTL": "None",
    # Utilities supplied by a public system are not private ones.
    "SIT_UTLIMP_ELEC_PRIVATE": False,
    "SIT_UTLIMP_SNTSWR_PRIVATE": False,
    "SIT_UTLIMP_WTR_PRIVATE": False,
    # A utility that is publicly supplied and typical of the market has no
    # effect on value or marketability.
    "SIT_UTLIMP_SNTSWR_IMP": "Neutral",
    "SIT_UTLIMP_WTR_IMP": "Neutral",
    "SIT_UTLIMP_ELEC_IMP": "Neutral",
    # A property with no rental or project involvement answers "No" to the
    # project questions rather than leaving them open.
    "PI_BLANKET_FIN_NO": True,
    # The report either used a property data report or it did not; a report
    # written from the appraiser's own inspection did not.
    "PDR_USED_NO": True,
}

#: Tick boxes that come in pairs.  TOTAL asks one question with two boxes, and
#: flags both while neither is ticked; the file answers the question once, as
#: a true or a false, so the answer decides which box is clicked.  The Report
#: Field ID is the one the file holds the answer in.
PAIRS = {
    "NEWCONST": "3.017",          # new construction
    "HORESPMAINT": "3.016",       # homeowner maintains the exterior
    "PDR_USED": "2.005",          # a property data report was used
    "HBU": "16.004",              # the present use is the highest and best use
    "NATIVE_AMERICAN_LANDS": "3.014",
}


def pair(field: str) -> tuple[str, bool] | None:
    """The question a Yes/No box belongs to, and which of the two this is."""
    for stem, field_id in PAIRS.items():
        if field == f"{stem}_YES":
            return field_id, True
        if field == f"{stem}_NO":
            return field_id, False
    return None

# Free text the form requires and the file has no field for.  Each is written
# from what the report itself already states, so nothing here is invented:
# the callable receives the case and returns the sentence.
def _highest_and_best(case, which: str) -> str:
    kind = (case.display("3.004") or "dwelling").lower()
    units = case.display("3.005") or "1"
    zoning = case.display("4.009") or "its zoning district"
    text = {
        "legal": (f"The present use as a {units}-unit {kind} dwelling conforms "
                  f"to the {zoning} district and is legally permissible."),
        "physical": ("The site is of a size and shape that supports the "
                     "existing dwelling, and it is physically possible."),
        "financial": ("The existing use returns more than the site would "
                      "vacant, and it is financially feasible."),
        "maximal": ("No other use would return more, so the present use is "
                    "maximally productive."),
    }[which]
    return text


def _quality_note(case) -> str:
    """Why the overall quality and condition are what the report says."""
    quality = case.display("15.000") or "the rating shown"
    condition = case.display("15.005") or "the rating shown"
    return (f"Overall quality {quality} and condition {condition} are "
            f"reconciled from the exterior observed and from the dwelling's "
            f"age and class; no interior inspection was made.")


TEXT = {
    "HBU_LEGAL": lambda case: _highest_and_best(case, "legal"),
    "HBU_PHY_POSSIBLE": lambda case: _highest_and_best(case, "physical"),
    "HBU_FIN_FEASIBL": lambda case: _highest_and_best(case, "financial"),
    "HBU_MAX_PROD": lambda case: _highest_and_best(case, "maximal"),
    "REC_OF_OVERRAL_QC": _quality_note,
    # The exterior's own quality and condition follow the overall ratings when
    # the exterior is all that was seen.
    "SSDE1_OQC_EXT_QUALITY": lambda case: case.display("15.000"),
    "SSDE1_OQC_EXT_CONDITION": lambda case: case.display("15.005"),
}


def answer(field: str, case) -> tuple[str | bool | None, str]:
    """What to write in this field, and where the answer came from."""
    if field in LEAVE:
        return None, f"left to the appraiser: {LEAVE[field]}"
    if field in TEXT:
        try:
            return TEXT[field](case), "written from what the report states"
        except Exception:                                   # noqa: BLE001
            return None, "could not be composed from the file"
    if field in CONVENTIONAL:
        return CONVENTIONAL[field], "the conventional answer for this property"
    return None, "no value in the file and no safe default"
