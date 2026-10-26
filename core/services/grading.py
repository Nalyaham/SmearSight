"""Slide grading from per-field bacilli counts.

Bright-field Ziehl-Neelsen at 1000x (WHO / IUATLD, one length = 100 fields):

  0 AFB per 100 fields ............................. negative
  1-9 AFB per 100 fields ........................... scanty (report the exact count)
  10-99 AFB per 100 fields ......................... 1+
  1-10 AFB per field in at least 50 fields ......... 2+
  more than 10 AFB per field in at least 20 fields . 3+

Fluorescence (auramine O), the scale in the WHO-aligned LED-FM literature:

                    200x / 250x                400x
  negative          0 AFB / length             0 AFB / length
  scanty            1-29 AFB / length          1-19 AFB / length
  1+                30-299 AFB / length        20-199 AFB / length
  2+                10-100 AFB / field         5-50 AFB / field (average)
  3+                more than 100 AFB / field  more than 50 AFB / field (average)
  one length =      300 fields                 40 fields

A full reading is one length. With fewer fields the result is marked provisional and counts
are scaled to a full length for the scanty / 1+ decision.
"""

GRADES = ["negative", "scanty", "1+", "2+", "3+"]
MODALITIES = {"zn": "Bright-field (Ziehl-Neelsen / Kinyoun)", "fm": "Fluorescence (Auramine O)"}
STAINS = {"zn": ["Ziehl-Neelsen", "Kinyoun"], "fm": ["Auramine O", "Auramine-rhodamine"]}
MAGNIFICATIONS = {"zn": ["1000x"], "fm": ["200x", "250x", "400x"]}

FM_SCALES = {
    "200": {"fields_per_length": 300, "scanty_max": 29, "one_plus_min": 30, "one_plus_max": 299,
            "two_plus_field_min": 10, "three_plus_field_over": 100, "label": "Auramine FM 200-250x (1 length = 300 fields)"},
    "400": {"fields_per_length": 40, "scanty_max": 19, "one_plus_min": 20, "one_plus_max": 199,
            "two_plus_field_min": 5, "three_plus_field_over": 50, "label": "Auramine FM 400x (1 length = 40 fields)"},
}


def modality_for_stain(stain):
    s = (stain or "").lower()
    return "fm" if "auramine" in s or "fluoresc" in s else "zn"


def fm_scale(magnification):
    return FM_SCALES["400"] if str(magnification).startswith("400") else FM_SCALES["200"]


def standard_fields(modality="zn", magnification="1000x"):
    return fm_scale(magnification)["fields_per_length"] if modality == "fm" else 100


def scale_label(modality="zn", magnification="1000x"):
    return fm_scale(magnification)["label"] if modality == "fm" else "WHO/IUATLD Ziehl-Neelsen 1000x (100 fields)"


def grade_slide(field_counts, modality="zn", magnification="1000x"):
    """field_counts: list of AFB counts, one per scanned field."""
    if modality == "fm":
        return _grade_fm(field_counts, magnification)
    return _grade_zn(field_counts)


def _grade_zn(field_counts):
    n = len(field_counts)
    if n == 0:
        return {"grade": None, "total": 0, "fields": 0, "provisional": True,
                "explanation": "No fields scanned yet.", "scale": scale_label("zn")}
    total = int(sum(field_counts))
    with_any = sum(1 for c in field_counts if c >= 1)
    over10 = sum(1 for c in field_counts if c > 10)
    per100 = total * 100.0 / n
    provisional = n < 100

    if total == 0:
        grade, why = "negative", f"No AFB seen in {n} fields."
    elif over10 >= 20:
        grade, why = "3+", f"More than 10 AFB per field in {over10} fields (needs 20 or more)."
    elif with_any >= 50:
        grade, why = "2+", f"AFB seen in {with_any} fields, 1-10 per field (needs 50 or more)."
    elif per100 >= 10:
        grade, why = "1+", f"About {per100:.0f} AFB per 100 fields (10-99 is 1+)."
    else:
        grade, why = "scanty", f"{total} AFB in {n} fields. Report the exact count (1-9 per 100 fields is scanty)."

    if provisional:
        why += f" Provisional: the standard reading is 100 fields and only {n} were scanned."
    return {"grade": grade, "total": total, "fields": n, "fields_with_afb": with_any,
            "provisional": provisional, "explanation": why, "scale": scale_label("zn")}


def _grade_fm(field_counts, magnification):
    sc = fm_scale(magnification)
    n = len(field_counts)
    if n == 0:
        return {"grade": None, "total": 0, "fields": 0, "provisional": True,
                "explanation": "No fields scanned yet.", "scale": sc["label"]}
    total = int(sum(field_counts))
    with_any = sum(1 for c in field_counts if c >= 1)
    mean = total / n
    per_length = total * sc["fields_per_length"] / n
    provisional = n < sc["fields_per_length"]

    if total == 0:
        grade, why = "negative", f"No AFB seen in {n} fields."
    elif mean > sc["three_plus_field_over"]:
        grade, why = "3+", f"Average {mean:.0f} AFB per field (3+ is more than {sc['three_plus_field_over']})."
    elif mean >= sc["two_plus_field_min"]:
        grade, why = "2+", f"Average {mean:.1f} AFB per field (2+ starts at {sc['two_plus_field_min']})."
    elif per_length >= sc["one_plus_min"]:
        grade = "1+"
        why = f"About {per_length:.0f} AFB per length (1+ is {sc['one_plus_min']}-{sc['one_plus_max']})."
        if per_length > sc["one_plus_max"]:
            grade = "2+"
            why = (f"About {per_length:.0f} AFB per length, above the 1+ band but below the 2+ per-field band "
                   f"of the published scale; reported as 2+ (the nearest higher band). The lab lead should confirm this local rule.")
    else:
        grade = "scanty"
        why = (f"About {per_length:.0f} AFB per length ({total} counted in {n} fields). "
               f"Report the exact count (1-{sc['scanty_max']} per length is scanty).")
    if provisional:
        why += f" Provisional: a full reading is {sc['fields_per_length']} fields and only {n} were scanned."
    return {"grade": grade, "total": total, "fields": n, "fields_with_afb": with_any,
            "provisional": provisional, "explanation": why, "scale": sc["label"]}


def is_positive(grade):
    return grade not in (None, "negative")


def step_difference(a, b):
    """Number of steps between two grades on negative < scanty < 1+ < 2+ < 3+."""
    return abs(GRADES.index(a) - GRADES.index(b))
