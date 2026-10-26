"""Editable cut-offs and acceptance targets, stored in the database (AppSetting).

Everything here has a safe default, so a fresh install works with no set-up. The defaults for
the acceptance targets are PLACEHOLDERS chosen so the screen has something to compare with; they
are not published WHO requirements. The laboratory lead should set the targets that the
laboratory's own validation protocol requires.
"""
import time

from ..models import AppSetting

DEFAULT_THRESHOLDS = {"floor": 0.25, "review": 0.60, "positive": 0.50}
DEFAULT_TARGETS = {"sensitivity": 0.80, "specificity": 0.95, "ppv": 0.90, "npv": 0.90}
DEFAULT_PREVALENCE = 0.10            # smear-positive share among people tested; replace with the site's figure
FLOOR = 0.25                         # detections below this are never stored (set when the model runs)

_cache = {"t": 0.0, "data": {}}


def _all():
    if time.time() - _cache["t"] > 3:
        _cache["data"] = dict(AppSetting.objects.values_list("key", "value"))
        _cache["t"] = time.time()
    return _cache["data"]


def invalidate():
    _cache["t"] = 0.0


def get(key, default=None):
    return _all().get(key, default)


def put(key, value):
    AppSetting.objects.update_or_create(key=key, defaults={"value": value})
    invalidate()


def thresholds(modality="zn"):
    """{"floor","review","positive"} for one microscopy type."""
    out = dict(DEFAULT_THRESHOLDS)
    out.update((get("thresholds", {}) or {}).get(modality, {}) or {})
    out["floor"] = FLOOR
    return out


def set_thresholds(modality, positive, review=None):
    positive = round(float(positive), 3)
    if not FLOOR <= positive <= 0.95:
        raise ValueError(f"The count threshold must be between {FLOOR} and 0.95.")
    cur = thresholds(modality)
    review = round(float(review if review is not None else max(cur["review"], positive)), 3)
    if review < positive:
        review = positive
    allv = dict(get("thresholds", {}) or {})
    allv[modality] = {"positive": positive, "review": min(review, 1.0)}
    put("thresholds", allv)
    return thresholds(modality)


def targets():
    out = dict(DEFAULT_TARGETS)
    out.update(get("targets", {}) or {})
    return out


def set_targets(values):
    clean = {}
    for k in DEFAULT_TARGETS:
        if k in values and values[k] is not None:
            v = float(values[k])
            if not 0 < v <= 1:
                raise ValueError(f"The {k} target must be between 0 and 1.")
            clean[k] = round(v, 3)
    put("targets", {**targets(), **clean})
    return targets()


def prevalence():
    return float(get("prevalence", DEFAULT_PREVALENCE))


def set_prevalence(v):
    v = float(v)
    if not 0 < v < 1:
        raise ValueError("Prevalence must be between 0 and 1 (for example 0.10 for 10%).")
    put("prevalence", round(v, 4))
    return prevalence()
