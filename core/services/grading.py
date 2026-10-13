"""Slide grading from per-field bacilli counts, following the WHO / IUATLD scale for
Ziehl-Neelsen smears read at 1000x.

  0 AFB per 100 fields ............................. negative
  1-9 AFB per 100 fields ........................... scanty (report the exact count)
  10-99 AFB per 100 fields ......................... 1+
  1-10 AFB per field in at least 50 fields ......... 2+
  more than 10 AFB per field in at least 20 fields . 3+

A full reading is 100 fields. With fewer fields the result is marked provisional and the
counts are scaled to 100 fields for the scanty / 1+ decision.
"""

GRADES = ["negative", "scanty", "1+", "2+", "3+"]


def grade_slide(field_counts):
    """field_counts: list of AFB counts, one per scanned field."""
    n = len(field_counts)
    if n == 0:
        return {"grade": None, "total": 0, "fields": 0, "provisional": True,
                "explanation": "No fields scanned yet."}
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
            "provisional": provisional, "explanation": why}


def is_positive(grade):
    return grade not in (None, "negative")
