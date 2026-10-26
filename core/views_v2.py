"""v2 API: phones as cameras, feedback, health, settings and the positive-confirmation workflow."""
import hashlib
import secrets
import shutil
import time
from datetime import timedelta

import segno
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import models as M
from . import serializers as S
from .api_common import audit, fail, reader_name, reader_role
from .services import confirm, grading, imaging, inference, settings_store
from .services.acquisition import add_field_images
from .services.config import DATA_DIR, STATIC_DIR, pin
from .services.network import lan_enabled, lan_ip, parse_user_agent, server_port
from .views import VERSION, get_or_404, slide_detail

CODE_MINUTES = 10
ONLINE_SECONDS = 90
MAX_PHONE_UPLOAD = 15 * 1024 * 1024
UPLOADS_PER_HOUR = 600           # per phone; far above any real use, stops a runaway script


def _event(device, kind, detail=""):
    M.CaptureEvent.objects.create(device=device, kind=kind, detail=str(detail)[:500])


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _ip(request):
    return request.META.get("REMOTE_ADDR", "")


# ================================================================== computer side: phones
def network_info(request=None):
    ip, port = lan_ip(), server_port()
    return {"lan_enabled": lan_enabled(), "lan_ip": ip, "port": port, "pin_enabled": bool(pin()),
            "phone_url": f"http://{ip}:{port}/phone" if ip else None,
            "warnings": ([] if lan_enabled() else
                         ["The server is only listening on this computer. Restart it with:  python run.py --lan --pin 1234"])
                        + ([] if pin() else ["No access PIN is set. Phones are paired by code, but everyone on this "
                                             "Wi-Fi could still open the app itself. Set a PIN."])}


@api_view(["GET"])
def devices_list(request):
    devs = M.CaptureDevice.objects.order_by("revoked", "-last_seen", "-id")
    return Response({"devices": [S.device_brief(d, ONLINE_SECONDS) for d in devs], "network": network_info(request)})


@api_view(["POST"])
def devices_pairing(request):
    """Make a six-digit, single-use code (valid ten minutes) and the QR code for the phone page."""
    now = timezone.now()
    M.PairingCode.objects.filter(expires_at__lt=now - timedelta(hours=1)).delete()
    if M.PairingCode.objects.filter(used=False, expires_at__gt=now).count() >= 5:
        fail("Several pairing codes are already open. Use one, or wait a few minutes.", 429)
    active = set(M.PairingCode.objects.filter(used=False, expires_at__gt=now).values_list("code", flat=True))
    code = f"{secrets.randbelow(10 ** 6):06d}"
    while code in active:
        code = f"{secrets.randbelow(10 ** 6):06d}"
    pc = M.PairingCode.objects.create(code=code, created_by=reader_name(request),
                                      expires_at=now + timedelta(minutes=CODE_MINUTES))
    net = network_info(request)
    base = net["phone_url"] or f"http://{request.get_host()}/phone"
    url = f"{base}?code={code}"
    qr = segno.make(url, error="m").svg_inline(scale=5, border=2, dark="#0F2A33", light="#ffffff", omitsize=True)
    audit(reader_name(request), "phone.pair_code", "code created")
    return Response({"code": code, "expires_at": pc.expires_at.timestamp(), "minutes": CODE_MINUTES, "url": url,
                     "qr_svg": qr, "network": net})


@api_view(["PATCH", "DELETE"])
def device_detail(request, pk):
    dev = get_or_404(M.CaptureDevice, pk, "Phone")
    if request.method == "DELETE":
        dev.revoked = True
        dev.save(update_fields=["revoked"])
        M.Slide.objects.filter(capture_device=dev, status="open").update(capture_device=None)
        _event(dev, "revoke", f"by {reader_name(request)}")
        audit(reader_name(request), "phone.revoke", dev.name)
        return Response(S.device_brief(dev, ONLINE_SECONDS))
    r = S.RenameIn(data=request.data)
    r.is_valid(raise_exception=True)
    old, dev.name = dev.name, r.validated_data["name"].strip()
    dev.save(update_fields=["name"])
    audit(reader_name(request), "phone.rename", f"{old} -> {dev.name}")
    return Response(S.device_brief(dev, ONLINE_SECONDS))


@api_view(["PUT"])
def slide_capture_device(request, pk):
    """Choose which phone takes the pictures for this slide (or null = upload from this computer)."""
    s = S.SelectDeviceIn(data=request.data)
    s.is_valid(raise_exception=True)
    slide = get_or_404(M.Slide, pk, "Slide")
    if slide.status != "open":
        fail("This slide is already confirmed.", 409)
    did = s.validated_data["device_id"]
    dev = None
    if did is not None:
        dev = M.CaptureDevice.objects.filter(pk=did, revoked=False).first()
        if not dev:
            fail("That phone is not paired (or was revoked).", 404)
    with transaction.atomic():
        if dev:                                    # one phone serves one open slide at a time
            M.Slide.objects.filter(capture_device=dev, status="open").exclude(pk=slide.pk).update(capture_device=None)
        slide.capture_device = dev
        slide.save(update_fields=["capture_device"])
    _event(dev, "select", f"slide {slide.code}" if dev else f"slide {slide.code}: computer upload")
    audit(reader_name(request), "phone.select", f"{slide.code} -> {dev.name if dev else 'this computer'}")
    return Response(slide_detail(slide))


@api_view(["GET"])
def slide_capture_status(request, pk):
    """Cheap poll while a phone is photographing: has anything new arrived?"""
    slide = get_or_404(M.Slide, pk, "Slide")
    agg = slide.images.aggregate(n=Max("field_no"), last=Max("id"))
    dev = slide.capture_device
    return Response({"n_fields": slide.images.count(), "last_image_id": agg["last"], "status": slide.status,
                     "device": S.device_brief(dev, ONLINE_SECONDS) if dev else None})


@api_view(["GET"])
def capture_events(request):
    limit = min(int(request.query_params.get("limit", 100)), 500)
    rows = M.CaptureEvent.objects.select_related("device")[:limit]
    since = timezone.now() - timedelta(hours=24)
    last = M.CaptureEvent.objects.filter(created_at__gte=since)
    return Response({
        "events": [{"id": e.id, "kind": e.kind, "detail": e.detail, "created_at": e.created_at.timestamp(),
                    "device": e.device.name if e.device else None} for e in rows],
        "last_24h": {k: last.filter(kind=k).count() for k in ("pair", "pair_fail", "upload_ok", "upload_fail", "revoke")}})


# ================================================================== phone side (device token, no PIN)
_pair_fails = {}       # ip -> [timestamps]
_pair_fails_all = []


def _rate_limited(ip):
    now = time.time()
    mine = [t for t in _pair_fails.get(ip, []) if now - t < 300]
    _pair_fails[ip] = mine
    allf = [t for t in _pair_fails_all if now - t < 600]
    _pair_fails_all[:] = allf
    return len(mine) >= 5 or len(allf) >= 25


def _device(request):
    h = request.headers.get("Authorization", "")
    token = h[7:].strip() if h.lower().startswith("bearer ") else ""
    dev = M.CaptureDevice.objects.filter(token_hash=_hash(token)).first() if token else None
    if not dev:
        fail("This phone is not paired. Open the pairing page and enter the code shown on the computer.", 401)
    if dev.revoked:
        fail("This phone was removed from the lab computer. Pair it again if it should be used.", 401)
    now = timezone.now()
    if not dev.last_seen or (now - dev.last_seen).total_seconds() > 10:
        M.CaptureDevice.objects.filter(pk=dev.pk).update(last_seen=now, last_ip=_ip(request))
        dev.last_seen = now
    return dev


def _phone_slide(dev):
    return M.Slide.objects.filter(capture_device=dev, status="open").order_by("-started_at").first()


def _slide_for_phone(slide):
    if not slide:
        return None
    return {"id": slide.id, "code": slide.code, "stain": slide.stain, "magnification": slide.magnification,
            "modality": slide.modality, "n_fields": slide.images.count(),
            "target_fields": grading.standard_fields(slide.modality, slide.magnification)}


def _tips(modality):
    if modality == "fm":
        return ["Work in a dim room. Focus on the bright background specks first, then take the picture.",
                "Keep the phone flat against the eyepiece adapter and hold still for one second."]
    return ["Keep the phone flat against the eyepiece adapter and hold still for one second.",
            "Use the same light setting for every field of the slide."]


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def phone_pair(request):
    ip = _ip(request)
    if _rate_limited(ip):
        _event(None, "pair_fail", f"rate limited {ip}")
        fail("Too many wrong codes. Wait five minutes and ask for a new code on the computer.", 429)
    p = S.PairIn(data=request.data)
    p.is_valid(raise_exception=True)
    code = "".join(ch for ch in p.validated_data["code"] if ch.isdigit())
    now = timezone.now()
    with transaction.atomic():
        pc = M.PairingCode.objects.select_for_update().filter(code=code, used=False, expires_at__gt=now).first() \
            if len(code) == 6 else None
        if not pc:
            _pair_fails.setdefault(ip, []).append(time.time())
            _pair_fails_all.append(time.time())
            _event(None, "pair_fail", f"bad or expired code from {ip}")
            fail("That code is wrong or has expired. Ask for a new code on the computer.", 403)
        ua = request.headers.get("User-Agent", "")
        platform, browser, suggested = parse_user_agent(ua)
        token = secrets.token_urlsafe(32)
        name = p.validated_data["name"].strip() or suggested
        dev = M.CaptureDevice.objects.create(
            name=name, model_label=suggested, platform=platform, browser=browser, token_hash=_hash(token),
            paired_by=pc.created_by, last_seen=now, last_ip=ip)
        pc.used, pc.device = True, dev
        pc.save(update_fields=["used", "device"])
    _event(dev, "pair", f"{platform} {browser}")
    audit(f"phone:{dev.name}", "phone.paired", f"{platform} {browser}")
    return Response({"token": token, "device": S.device_brief(dev, ONLINE_SECONDS)})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def phone_status(request):
    dev = _device(request)
    slide = _phone_slide(dev)
    return Response({"device": {"id": dev.id, "name": dev.name}, "slide": _slide_for_phone(slide),
                     "tips": _tips(slide.modality) if slide else [], "server_time": time.time(),
                     "accepts_upload": bool(slide)})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def phone_upload(request):
    dev = _device(request)
    if M.CaptureEvent.objects.filter(device=dev, kind="upload_ok",
                                     created_at__gte=timezone.now() - timedelta(hours=1)).count() >= UPLOADS_PER_HOUR:
        fail("Too many photos in the last hour. Wait a little.", 429)
    slide = _phone_slide(dev)
    if not slide:
        fail("No slide is waiting for this phone. On the computer, open the slide and choose this phone.", 409)
    f = request.FILES.get("file")
    if not f:
        fail("No photo was sent.")
    if f.size > MAX_PHONE_UPLOAD:
        fail("The photo is too large (over 15 MB). Lower the camera resolution and try again.", 413)
    data = f.read()
    force = str(request.data.get("force", "")).lower() in ("1", "true", "yes")
    try:
        info = imaging.save_image(data, slide.modality)
    except imaging.BadImage as e:
        _fail(dev, str(e))
        fail(str(e))
    if info["quality_flag"] and not force:
        msgs = {"blurry": "The picture looks blurry. Focus on the smear and retake it.",
                "too dark": "The picture is too dark. Increase the light and retake it.",
                "too bright": "The picture is washed out. Reduce the light and retake it.",
                "washed out": "The picture looks hazy. Check the filter and the room light, then retake it."}
        _event(dev, "retake", f"{slide.code}: {info['quality_flag']}")
        return Response({"ok": False, "retake": True, "quality_flag": info["quality_flag"],
                         "message": msgs.get(info["quality_flag"], "The picture may be poor. Retake it."),
                         "n_fields": slide.images.count()})
    reader = f"phone: {dev.name}"
    results, model_missing = add_field_images(slide, [(f.name or "phone.jpg", data)], reader, device=dev)
    r = results[0]
    if "image_id" not in r:
        _fail(dev, r.get("error", "failed"))
        fail(r.get("error", "The photo could not be added."), 409)
    M.CaptureDevice.objects.filter(pk=dev.pk).update(upload_count=dev.upload_count + 1)
    _event(dev, "upload_ok", f"{slide.code} field {r['field_no']}")
    audit(reader, "slide.fields", f"{slide.code} +1 field (phone)")
    return Response({"ok": True, "field_no": r["field_no"], "quality_flag": r.get("quality_flag"),
                     "n_fields": slide.images.count(), "analysed": not model_missing,
                     "message": ("Saved." if not model_missing else
                                 "Saved. The computer has no approved model for this slide type yet, so it will "
                                 "not be analysed.")})


def _fail(dev, msg):
    M.CaptureDevice.objects.filter(pk=dev.pk).update(fail_count=dev.fail_count + 1, last_error=str(msg)[:300])
    _event(dev, "upload_fail", msg)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def phone_feedback(request):
    dev = _device(request)
    f = S.FeedbackIn(data=request.data)
    f.is_valid(raise_exception=True)
    M.Feedback.objects.create(device=dev, reader=dev.name, source="phone", **f.validated_data)
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def phone_forget(request):
    """The phone owner removes this phone (stops it uploading)."""
    dev = _device(request)
    M.CaptureDevice.objects.filter(pk=dev.pk).update(revoked=True)
    M.Slide.objects.filter(capture_device=dev, status="open").update(capture_device=None)
    _event(dev, "revoke", "removed from the phone")
    return Response({"ok": True})


def phone_page(request):
    resp = HttpResponse(open(STATIC_DIR / "phone.html", "rb").read(), content_type="text/html")
    resp["Cache-Control"] = "no-cache"
    resp["Referrer-Policy"] = "no-referrer"
    return resp


# ================================================================== feedback, health, settings
@api_view(["GET", "POST"])
def feedback(request):
    if request.method == "POST":
        f = S.FeedbackIn(data=request.data)
        f.is_valid(raise_exception=True)
        M.Feedback.objects.create(reader=reader_name(request), source="desktop", **f.validated_data)
        return Response({"ok": True})
    rows = list(M.Feedback.objects.all()[:200])
    rated = [r.rating for r in rows]
    by_src = {}
    for r in rows:
        by_src.setdefault(r.source, []).append(r.rating)
    return Response({"n": len(rows), "mean": (sum(rated) / len(rated)) if rated else None,
                     "by_source": {k: {"n": len(v), "mean": sum(v) / len(v)} for k, v in by_src.items()},
                     "items": [{"id": r.id, "source": r.source, "reader": r.reader, "rating": r.rating,
                                "comment": r.comment, "context": r.context, "created_at": r.created_at.timestamp()}
                               for r in rows[:60]]})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def healthz(request):
    """Minimal answer for an uptime check; leaks nothing."""
    return Response({"ok": True})


@api_view(["GET"])
def health(request):
    try:
        M.Reader.objects.count()
        db_ok = True
    except Exception:
        db_ok = False
    du = shutil.disk_usage(DATA_DIR)
    since = timezone.now() - timedelta(hours=24)
    ev = M.CaptureEvent.objects.filter(created_at__gte=since)
    ok_n, bad_n = ev.filter(kind="upload_ok").count(), ev.filter(kind="upload_fail").count()
    models = inference.active_models()
    last_up = M.Image.objects.filter(device__isnull=False).aggregate(m=Max("added_at"))["m"]
    problems = []
    if not db_ok:
        problems.append("Database not reachable.")
    if du.free < 2 * 1024 ** 3:
        problems.append("Less than 2 GB free on the data disk.")
    if ok_n + bad_n >= 10 and bad_n / (ok_n + bad_n) > 0.2:
        problems.append("More than 20% of phone uploads failed in the last 24 hours.")
    return Response({
        "ok": not problems, "problems": problems, "version": VERSION, "database": db_ok,
        "disk_free_gb": round(du.free / 1024 ** 3, 1),
        "active_models": {k: (v.name if v else None) for k, v in models.items()},
        "phones": {"paired": M.CaptureDevice.objects.filter(revoked=False).count(),
                   "online": M.CaptureDevice.objects.filter(
                       revoked=False, last_seen__gte=timezone.now() - timedelta(seconds=ONLINE_SECONDS)).count(),
                   "uploads_24h": ok_n, "failed_24h": bad_n,
                   "last_upload": last_up.timestamp() if last_up else None},
        "open_slides": M.Slide.objects.filter(status="open").count(),
        "training_running": M.TrainingRun.objects.filter(status__in=["queued", "running"]).exists()})


@api_view(["GET", "PUT"])
def app_settings(request):
    if request.method == "GET":
        return Response({"thresholds": {m: settings_store.thresholds(m) for m in ("zn", "fm")},
                         "targets": settings_store.targets(), "prevalence": settings_store.prevalence(),
                         "network": network_info(request)})
    s = S.SettingsIn(data=request.data)
    s.is_valid(raise_exception=True)
    v = s.validated_data
    by, role = v["approved_by"], reader_role(v["approved_by"])
    try:
        if "positive" in v or "review" in v:
            if role not in ("senior", "lead"):
                fail("Only a senior reader or the laboratory lead can change the count cut-offs.", 403)
            cur = settings_store.thresholds(v["modality"])
            settings_store.set_thresholds(v["modality"], v.get("positive", cur["positive"]), v.get("review"))
        if "targets" in v or "prevalence" in v:
            if role != "lead":
                fail("Only the laboratory lead can change the acceptance targets and the prevalence.", 403)
            if "targets" in v:
                settings_store.set_targets(v["targets"])
            if "prevalence" in v:
                settings_store.set_prevalence(v["prevalence"])
    except ValueError as e:
        fail(str(e))
    audit(reader_name(request), "settings.save", f"by {by}: {dict(request.data)}")
    return Response({"thresholds": {m: settings_store.thresholds(m) for m in ("zn", "fm")},
                     "targets": settings_store.targets(), "prevalence": settings_store.prevalence()})


# ================================================================== positive confirmation
@api_view(["GET", "POST"])
def slide_confirmation(request, pk):
    slide = get_or_404(M.Slide, pk, "Slide")
    if request.method == "GET":
        cons = list(slide.confirmations.order_by("id"))
        return Response({"status": confirm.status(slide, cons), "history": S.ConfirmationSerializer(cons, many=True).data,
                         "methods": confirm.METHOD_LABELS})
    c = S.ConfirmationIn(data=request.data)
    c.is_valid(raise_exception=True)
    v = c.validated_data
    reader = reader_name(request)
    role = reader_role(reader)
    if slide.status != "confirmed":
        fail("Confirm the slide first; confirmation steps come after the reading is signed off.", 409)
    cons = list(slide.confirmations.order_by("id"))
    st = confirm.status(slide, cons)
    method = v["method"]
    allowed = confirm.VALID_RESULTS[method]
    if allowed is not None and v["result"] not in allowed:
        fail("Result must be one of: " + ", ".join(allowed) + ".")
    if allowed is None and not v["grade"]:
        fail("Choose the grade this reader found.")
    if method in ("blind_reread", "referee_reread", "zn_restain", "other") and not st["applicable"]:
        fail("Only positive slides go through reader confirmation.", 409)
    if method == "blind_reread":
        if any(x.method == "blind_reread" for x in cons):
            fail("A blind second reading is already recorded for this slide.", 409)
        if reader == slide.confirmed_by:
            fail("The blind re-read must be done by a different reader than the one who signed the slide.", 409)
    if method == "referee_reread":
        if st["state"] != "awaiting_referee":
            fail("A referee reading is only needed when the first two readings disagree.", 409)
        if role not in ("senior", "lead"):
            fail("Only a senior reader or the laboratory lead can act as referee.", 403)
        if reader == slide.confirmed_by or any(x.by == reader for x in cons if x.method == "blind_reread"):
            fail("The referee must be a different person from both earlier readers.", 409)
    if method == "other":
        if role not in ("senior", "lead"):
            fail("Only a senior reader or the laboratory lead can close a confirmation without a further test.", 403)
        if st["state"] not in ("awaiting_molecular", "needs_investigation"):
            fail("This slide is not waiting for a molecular result.", 409)
        if not v["notes"].strip():
            fail("Write the reason (for example: no Xpert cartridge available, patient started treatment).")
    conc = None
    if method == "blind_reread":
        conc = confirm.concordance(slide.final_grade, v["grade"])
    with transaction.atomic():
        row = M.SlideConfirmation.objects.create(
            slide=slide, method=method, result=v["result"] or (v["grade"] or ""), grade=v["grade"], by=reader,
            notes=v["notes"].strip(), concordance=conc, rif_result=v["rif_result"] if method == "xpert" else "")
        cons.append(row)
        ref, how = confirm.reference_from(cons)
        if ref and (method in ("xpert", "culture")):
            slide.reference_result, slide.reference_method = ref, how
            slide.save(update_fields=["reference_result", "reference_method"])
    audit(reader, "slide.confirmation", f"{slide.code} {method} {v['result'] or v['grade']} {conc or ''}")
    out = slide_detail(slide)
    out["confirmation_history"] = S.ConfirmationSerializer(slide.confirmations.order_by("id"), many=True).data
    return Response(out)


@api_view(["GET"])
def slide_blind(request, pk):
    """What a second reader may see: pictures only. No AI marks, no first grade."""
    slide = get_or_404(M.Slide, pk, "Slide")
    if slide.status != "confirmed" or not grading.is_positive(slide.final_grade):
        fail("This slide does not need a blind re-read.", 409)
    imgs = list(slide.images.order_by("field_no", "id").values("id", "field_no"))
    return Response({"slide_id": slide.id, "code": slide.code, "stain": slide.stain, "modality": slide.modality,
                     "magnification": slide.magnification, "standard_fields": grading.standard_fields(slide.modality, slide.magnification),
                     "fields": imgs, "scale": grading.scale_label(slide.modality, slide.magnification),
                     "signed_by": slide.confirmed_by})


@api_view(["POST"])
def grade_preview(request):
    """Grade a list of per-field counts (used by the blind re-read page for the second reader's own tally)."""
    counts = request.data.get("counts")
    if not isinstance(counts, list) or not all(isinstance(x, int) and 0 <= x < 10000 for x in counts):
        fail("Send counts as a list of whole numbers.")
    modality = request.data.get("modality", "zn")
    if modality not in grading.MODALITIES:
        fail("Microscopy must be zn or fm.")
    return Response(grading.grade_slide(counts, modality, str(request.data.get("magnification", "1000x"))))
