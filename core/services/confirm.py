"""Confirming a positive smear: blind second reading, referee, ZN re-stain, molecular test, culture.

The discordance rules follow the external-quality-assessment rechecking procedure (a first
controller's result is discordant with the laboratory's when one is positive/scanty and the other
negative, or when the grades differ by two or more steps; a second-level controller acts as the
referee). The step list per grade is LOCAL POLICY that the laboratory lead should review: the
program defaults below are a starting point, not a WHO requirement.
"""
from . import grading

# What each grade needs before a positive is reported as "confirmed".
POLICY = {
    "3+": {"required": ["blind_reread"], "recommended": ["xpert"],
           "why": "High bacillary load: a second reader's agreement is enough to report. Send a sample for "
                  "Xpert MTB/RIF Ultra anyway, because rifampicin-resistance testing is needed for confirmed TB."},
    "2+": {"required": ["blind_reread"], "recommended": ["xpert"],
           "why": "As for 3+: second reader, then molecular test for rifampicin resistance."},
    "1+": {"required": ["blind_reread", "molecular"], "recommended": ["zn_restain"],
           "why": "Moderate load. Fluorescence 1+ and low counts can be false positives, so a molecular test "
                  "(or culture) is required before the result is treated as confirmed."},
    "scanty": {"required": ["blind_reread", "molecular"], "recommended": ["zn_restain"],
               "why": "Scanty results have the highest false-positive risk. Needs a second reader and a molecular "
                      "test or culture. Fluorescence scanty slides should also be re-stained with Ziehl-Neelsen "
                      "and re-read."},
}
METHOD_LABELS = {
    "blind_reread": "Blind second reading (a different reader)",
    "referee_reread": "Referee reading (senior reader or lead)",
    "zn_restain": "Ziehl-Neelsen re-stain and re-read",
    "xpert": "Xpert MTB/RIF Ultra",
    "culture": "Culture",
    "other": "Lead decision (no further test available)",
}


def concordance(a, b):
    """'concordant' | 'minor' (one grade apart) | 'discordant' (positive vs negative, or two or more grades)."""
    if a == b:
        return "concordant"
    if grading.is_positive(a) != grading.is_positive(b):
        return "discordant"
    return "minor" if grading.step_difference(a, b) == 1 else "discordant"


def error_type(registered, final):
    """Rechecking error name for the first result against the referee's result."""
    pr, pf = grading.is_positive(registered), grading.is_positive(final)
    if not pr and pf:
        return "LFP (low false positive)" if final == "scanty" else "HFP (high false positive)"
    if pr and not pf:
        return "LFN (low false negative)" if registered == "scanty" else "HFN (high false negative)"
    if pr and pf and grading.step_difference(registered, final) >= 2:
        return "QE (quantification error)"
    return None


def molecular_outcome(cons):
    """Latest culture result wins over Xpert. Returns 'positive' | 'negative' | 'unclear' | None."""
    cult = [c for c in cons if c.method == "culture" and c.result in ("positive", "negative")]
    if cult:
        return "positive" if cult[-1].result == "positive" else "negative"
    xp = [c for c in cons if c.method == "xpert"]
    if not xp:
        return None
    last = xp[-1]
    if last.result == "detected":
        return "positive"
    if last.result == "not_detected":
        return "negative"
    return "unclear"          # trace / invalid: neither confirms nor refutes


def status(slide, cons):
    """Work out where a confirmed slide stands. `cons` = list of SlideConfirmation in order."""
    grade, modality = slide.final_grade, slide.modality
    base = {"slide_id": slide.id, "grade": grade, "modality": modality, "steps": [], "recommendations": [],
            "reconciled_grade": grade, "level": None, "policy": None, "error_type": None}
    if slide.status != "confirmed" or not grading.is_positive(grade):
        return {**base, "applicable": False, "state": "not_applicable",
                "label": "Not a positive result" if slide.status == "confirmed" else "Slide not confirmed yet"}

    pol = POLICY[grade]
    base.update(applicable=True, policy=pol["why"])
    low_tier = "molecular" in pol["required"] or modality == "fm"
    reads = [c for c in cons if c.method == "blind_reread"]
    refs = [c for c in cons if c.method == "referee_reread"]
    restain = [c for c in cons if c.method == "zn_restain"]
    mol = molecular_outcome(cons)
    accepted = [c for c in cons if c.method == "other" and c.result == "accepted"]

    steps = []
    first = reads[0] if reads else None
    steps.append({"key": "blind_reread", "title": METHOD_LABELS["blind_reread"], "required": True,
                  "done": bool(first), "result": (f"{first.grade} by {first.by}" if first else None),
                  "concordance": concordance(grade, first.grade) if first else None})
    reconciled = grade
    state, label, level = None, None, None

    disc = bool(first) and concordance(grade, first.grade) == "discordant"
    ref = refs[-1] if refs else None
    steps.append({"key": "referee_reread", "title": METHOD_LABELS["referee_reread"], "required": disc,
                  "done": bool(ref), "result": (f"{ref.grade} by {ref.by}" if ref else None), "hidden": not disc})
    if disc and ref:
        reconciled = ref.grade
        base["error_type"] = error_type(grade, ref.grade)
    base["reconciled_grade"] = reconciled

    need_mol = low_tier
    steps.append({"key": "molecular", "title": "Molecular test (Xpert MTB/RIF Ultra) or culture",
                  "required": need_mol, "done": mol == "positive",
                  "result": {"positive": "positive", "negative": "negative", "unclear": "trace/invalid: repeat"}.get(mol)})
    rif = next((c.rif_result for c in reversed(cons) if c.method == "xpert" and c.rif_result), "")
    steps.append({"key": "rif", "title": "Rifampicin-resistance result", "required": False,
                  "done": bool(rif), "result": rif or None})
    if modality == "fm" or pol.get("recommended") and "zn_restain" in pol["recommended"]:
        z = restain[-1] if restain else None
        steps.append({"key": "zn_restain", "title": METHOD_LABELS["zn_restain"], "required": False,
                      "done": bool(z), "result": (f"{z.grade} by {z.by}" if z else None)})

    if not first:
        state, label = "awaiting_reread", "Waiting for a blind second reading"
    elif disc and not ref:
        state, label = "awaiting_referee", "Readers disagree: waiting for a referee reading"
    elif not grading.is_positive(reconciled):
        state, label, level = "overturned", "Referee read the slide as negative: positive not confirmed", None
    elif mol == "negative":
        state, label = "needs_investigation", "Smear positive but molecular/culture negative: investigate"
    elif mol == "positive":
        state, label, level = "confirmed", "Confirmed by molecular test or culture", "molecular"
    elif accepted:
        state, label, level = "confirmed", "Accepted by the lead without a molecular test", "lead_accepted"
    elif need_mol:
        state = "awaiting_molecular"
        label = ("Smear confirmed by readers; molecular test or culture still needed"
                 if mol is None else "Trace or invalid molecular result: repeat on a new sample")
    else:
        state, label, level = "confirmed", "Confirmed by two readers", "readers"

    rec = []
    if state == "awaiting_reread":
        rec.append("Ask a different reader to grade the slide without seeing the first grade (Blind re-read page).")
    if state == "awaiting_referee":
        rec.append("A senior reader or the lead (not either earlier reader) reads the slide; re-stain with "
                   "Ziehl-Neelsen first if the slide was fluorescence.")
    if state == "awaiting_molecular" or (state == "confirmed" and level == "readers" and not rif):
        rec.append("Send a fresh sputum sample for Xpert MTB/RIF Ultra. Record the result here so the "
                   "rifampicin result and the PPV/NPV reference are kept.")
    if state == "needs_investigation":
        rec.append("Check for specimen mix-up or a stain precipitate, re-stain and re-read the slide, repeat Xpert on "
                   "a new sample, and consider culture. The lab lead decides how to report.")
    if state == "overturned":
        rec.append("Report the referee grade, record the discordance for the supervisor's quality review.")
    if rif == "detected":
        rec.append("Rifampicin resistance detected: follow the national DR-TB pathway.")
    if mol == "positive" and modality == "fm":
        pass
    base.update(state=state, label=label, level=level, steps=steps, recommendations=rec, molecular=mol,
                rif_result=rif or None, tier="low" if low_tier else "high")
    return base


def reference_from(cons, current_method=None):
    """Reference result (pos/neg) and method taken from the strongest evidence so far, or (None, None)."""
    cult = [c for c in cons if c.method == "culture" and c.result in ("positive", "negative")]
    if cult:
        return ("pos" if cult[-1].result == "positive" else "neg"), "Culture"
    xp = [c for c in cons if c.method == "xpert" and c.result in ("detected", "not_detected")]
    if xp:
        return ("pos" if xp[-1].result == "detected" else "neg"), "Xpert MTB/RIF Ultra"
    return None, None


VALID_RESULTS = {
    "blind_reread": None, "referee_reread": None, "zn_restain": None,    # these carry a grade
    "xpert": ["detected", "trace", "not_detected", "invalid"],
    "culture": ["positive", "negative", "contaminated"],
    "other": ["accepted"],
}
