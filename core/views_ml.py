"""API views: dataset versions, training, models, performance and exports."""
import csv
import io
import os
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta

from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from . import models as M
from . import serializers as S
from .api_common import audit, fail, reader_name, reader_role
from .services import datasets, grading, inference
from .services.config import BASE_DIR, DATA_DIR, DB_PATH
from .services.stats import percentile, wilson
from .views import get_or_404


# ================================================================== dataset versions
class DatasetViewSet(viewsets.GenericViewSet):
    queryset = M.DatasetVersion.objects.all()
    serializer_class = S.FreezeIn

    def list(self, request):
        return Response(S.DatasetVersionSerializer(M.DatasetVersion.objects.all(), many=True).data)

    @action(detail=False, methods=["get"], url_path="preview")
    def preview(self, request):
        q = request.query_params
        return Response(datasets.preview(q.get("include_single_read", "0") == "1", q.get("include_synthetic", "1") == "1"))

    @action(detail=False, methods=["post"], url_path="freeze")
    def freeze(self, request):
        f = S.FreezeIn(data=request.data)
        f.is_valid(raise_exception=True)
        v = f.validated_data
        try:
            ver, n_slides = datasets.freeze(v["name"].strip() or f"Dataset {datetime.now():%Y-%m-%d %H:%M}", v["seed"],
                                            v["include_single_read"], v["include_synthetic"], reader_name(request))
        except ValueError as e:
            fail(str(e))
        audit(reader_name(request), "dataset.freeze", f"v{ver.id} train={ver.n_train} val={ver.n_val} test={ver.n_test}")
        return Response({"id": ver.id, "name": ver.name, "n_train": ver.n_train, "n_val": ver.n_val,
                         "n_test": ver.n_test, "slides": n_slides})


# ================================================================== training
PROCS = {}       # run id -> subprocess started by this server


def _alive(run):
    p = PROCS.get(run.id)
    if p is not None:
        return p.poll() is None
    if not run.pid:
        return False
    try:                    # server was restarted: look the process up (works on Windows, Mac and Linux)
        import psutil
        pr = psutil.Process(run.pid)
        if pr.status() == psutil.STATUS_ZOMBIE:
            return False
        return "train_worker" in " ".join(pr.cmdline())
    except Exception:
        return False


def _kill(run):
    p = PROCS.get(run.id)
    try:
        import psutil
        pid = p.pid if p is not None else run.pid
        if pid:
            pr = psutil.Process(pid)
            for c in pr.children(recursive=True):
                c.terminate()
            pr.terminate()
    except Exception:
        if p is not None:
            p.terminate()


def refresh_runs():
    for r in M.TrainingRun.objects.filter(status__in=["queued", "running"]):
        if not _alive(r) and timezone.now() - (r.started_at or timezone.now()) > timedelta(seconds=5):
            r.refresh_from_db()
            if r.status in ("queued", "running"):
                M.TrainingRun.objects.filter(id=r.id).update(
                    status="failed", finished_at=timezone.now(), message="The training process stopped unexpectedly.")


class TrainingViewSet(viewsets.GenericViewSet):
    queryset = M.TrainingRun.objects.all()
    serializer_class = S.TrainIn

    def list(self, request):
        refresh_runs()
        return Response(S.TrainingRunSerializer(M.TrainingRun.objects.all()[:20], many=True).data)

    @action(detail=False, methods=["post"], url_path="start")
    def start(self, request):
        reader = reader_name(request)
        t = S.TrainIn(data=request.data)
        t.is_valid(raise_exception=True)
        v = t.validated_data
        refresh_runs()
        if M.TrainingRun.objects.filter(status__in=["queued", "running"]).exists():
            fail("A training run is already in progress.", 409)
        ds = get_or_404(M.DatasetVersion, v["dataset_version_id"], "Dataset version")
        if ds.n_train < 8:
            fail("The training split is too small to train on.")
        params = {"epochs": max(1, min(v["epochs"], 300)), "imgsz": max(160, min(v["imgsz"], 1280)),
                  "batch": max(1, min(v["batch"], 64)), "base": v["base"], "seed": 42}
        run = M.TrainingRun.objects.create(dataset_version=ds, params=params, status="queued", epochs=params["epochs"],
                                           started_at=timezone.now(), started_by=reader, message="Starting...")
        log = open(DATA_DIR / "runs" / f"run_{run.id}.log", "w")
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}      # no console window on Windows
        proc = subprocess.Popen([sys.executable, str(BASE_DIR / "manage.py"), "train_worker", str(run.id)],
                                cwd=str(BASE_DIR), stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy(), **kw)
        PROCS[run.id] = proc
        M.TrainingRun.objects.filter(id=run.id).update(pid=proc.pid)
        audit(reader, "training.start", f"run {run.id} dataset v{ds.id} {params}")
        return Response({"id": run.id})

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        run = get_or_404(M.TrainingRun, pk, "Run")
        if run.status not in ("queued", "running"):
            fail("That run is not active.", 409)
        _kill(run)
        M.TrainingRun.objects.filter(id=run.id).update(status="cancelled", finished_at=timezone.now(),
                                                       message="Cancelled by user.")
        audit(reader_name(request), "training.cancel", pk)
        return Response({"ok": True})


# ================================================================== models
class ModelViewSet(viewsets.GenericViewSet):
    queryset = M.MLModel.objects.all()
    serializer_class = S.PromoteIn

    def list(self, request):
        return Response(S.MLModelSerializer(M.MLModel.objects.all(), many=True).data)

    @action(detail=True, methods=["post"], url_path="promote")
    def promote(self, request, pk=None):
        p = S.PromoteIn(data=request.data)
        p.is_valid(raise_exception=True)
        by = p.validated_data["approved_by"]
        m = get_or_404(M.MLModel, pk, "Model")
        if m.status == "active":
            fail("Already active.", 409)
        if reader_role(by) not in ("senior", "lead"):
            fail("Only a senior reader or the laboratory lead can approve a model.", 403)
        metrics = m.metrics or {}
        cur = M.MLModel.objects.filter(status="active").first()
        if m.status == "candidate":
            if not metrics.get("test_images"):
                fail("No held-out test result for this model, so it cannot be approved.", 409)
            if cur:
                cm = cur.metrics or {}
                if (cm.get("sensitivity") is not None and metrics.get("sensitivity") is not None
                        and metrics["sensitivity"] < cm["sensitivity"]):
                    fail(f"Blocked: sensitivity {metrics['sensitivity']:.1%} is lower than the active "
                         f"model's {cm['sensitivity']:.1%}.", 409)
        if cur:
            M.MLModel.objects.filter(id=cur.id).update(status="archived")
        M.MLModel.objects.filter(id=m.id).update(status="active", approved_by=by, approved_at=timezone.now())
        audit(reader_name(request), "model.promote", f"{m.name} approved by {by}")
        inference.forget()
        return Response({"ok": True})


# ================================================================== dashboard + performance
def confirmed_slides(include_demo, days):
    qs = M.Slide.objects.filter(status="confirmed")
    if not include_demo:
        qs = qs.filter(demo=False)
    if days:
        qs = qs.filter(confirmed_at__gte=timezone.now() - timedelta(days=days))
    return list(qs)


@api_view(["GET"])
def performance(request):
    days, include_demo = int(request.query_params.get("days", 0)), int(request.query_params.get("include_demo", 0))
    sl = confirmed_slides(include_demo, days)
    sess = [s.session_seconds for s in sl if s.session_seconds is not None]
    manual = [s.manual_seconds for s in sl if s.manual_seconds]
    bins = [(0, 30, "under 0:30"), (30, 60, "0:30 to 1:00"), (60, 90, "1:00 to 1:30"), (90, 120, "1:30 to 2:00"),
            (120, 180, "2:00 to 3:00"), (180, 300, "3:00 to 5:00"), (300, 1e9, "over 5:00")]
    hist = [{"label": b[2], "count": sum(1 for x in sess if b[0] <= x < b[1])} for b in bins]

    def conf(attr):
        c = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for s in sl:
            g = getattr(s, attr)
            if s.reference_result in ("pos", "neg") and g:
                pred, truth = grading.is_positive(g), s.reference_result == "pos"
                c["tp" if pred and truth else "fp" if pred else "fn" if truth else "tn"] += 1
        pos, neg = c["tp"] + c["fn"], c["tn"] + c["fp"]
        c["sensitivity"] = c["tp"] / pos if pos else None
        c["specificity"] = c["tn"] / neg if neg else None
        c["sens_ci"], c["spec_ci"] = wilson(c["tp"], pos), wilson(c["tn"], neg)
        c["n_with_reference"] = pos + neg
        return c
    weeks = {}
    for s in sl:
        if s.session_seconds is None:
            continue
        wk = timezone.localtime(s.confirmed_at).strftime("%G-W%V")
        weeks.setdefault(wk, {"app": [], "manual": []})
        weeks[wk]["app"].append(s.session_seconds)
        if s.manual_seconds:
            weeks[wk]["manual"].append(s.manual_seconds)
    trend = [{"week": k, "app": statistics.median(v["app"]),
              "manual": statistics.median(v["manual"]) if v["manual"] else None, "n": len(v["app"])}
             for k, v in sorted(weeks.items())][-12:]
    sites = {}
    for s in sl:
        sites.setdefault(s.site or "(no site)", []).append(s)
    by_site = []
    for name, ss in sorted(sites.items()):
        t = [x.session_seconds for x in ss if x.session_seconds is not None]
        ref = [x for x in ss if x.reference_result in ("pos", "neg") and x.ai_grade]
        tp = sum(1 for x in ref if x.reference_result == "pos" and grading.is_positive(x.ai_grade))
        pos = sum(1 for x in ref if x.reference_result == "pos")
        by_site.append({"site": name, "slides": len(ss), "median_seconds": statistics.median(t) if t else None,
                        "overrides": sum(1 for x in ss if x.ai_grade and x.final_grade != x.ai_grade),
                        "with_ai": sum(1 for x in ss if x.ai_grade),
                        "sensitivity": tp / pos if pos else None, "positives_with_reference": pos})
    an = M.Analysis.objects.filter(inference_ms__isnull=False)
    if not include_demo:
        an = an.exclude(slide__demo=True)
    inf = list(an.values_list("inference_ms", flat=True))
    return Response({
        "slides": len(sl), "median_seconds": statistics.median(sess) if sess else None,
        "p90_seconds": percentile(sess, 0.9), "manual_median_seconds": statistics.median(manual) if manual else None,
        "manual_n": len(manual), "histogram": hist, "trend": trend, "ai": conf("ai_grade"),
        "assisted": conf("final_grade"), "by_site": by_site,
        "overrides": sum(1 for s in sl if s.ai_grade and s.final_grade != s.ai_grade),
        "with_ai": sum(1 for s in sl if s.ai_grade),
        "inference_median_ms": statistics.median(inf) if inf else None, "inference_p90_ms": percentile(inf, 0.9)})


@api_view(["GET"])
def summary(request):
    sl = confirmed_slides(True, 30)
    sess = [s.session_seconds for s in sl if s.session_seconds is not None]
    manual = [s.manual_seconds for s in sl if s.manual_seconds]
    return Response({
        "slides_30d": len(sl),
        "median_seconds": statistics.median(sess) if sess else None,
        "manual_median_seconds": statistics.median(manual) if manual else None,
        "flagged_positive": sum(1 for s in sl if s.ai_grade and grading.is_positive(s.ai_grade)),
        "awaiting_review": M.ReviewItem.objects.filter(status__in=["open", "disputed"]).count(),
        "open_slides": M.Slide.objects.filter(status="open").count(),
        "images": M.Image.objects.filter(consent=True).count(),
        "active_model": S.MLModelSerializer(inference.active_model()).data if inference.active_model() else None})


@api_view(["GET"])
def export_slides(request):
    include_demo = request.query_params.get("include_demo", "0") in ("1", "true")
    cols = ["code", "site", "stain", "magnification", "started_by", "confirmed_by", "session_seconds", "manual_seconds",
            "ai_grade", "ai_bacilli", "ai_fields", "final_grade", "override_reason", "reference_result",
            "reference_method", "demo"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for s in M.Slide.objects.filter(status="confirmed").order_by("confirmed_at"):
        if s.demo and not include_demo:
            continue
        w.writerow(["" if getattr(s, c) is None else getattr(s, c) for c in cols])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = "attachment; filename=smearsight_slides.csv"
    return resp


@api_view(["GET"])
def audit_log(request):
    limit = int(request.query_params.get("limit", 200))
    return Response(S.AuditSerializer(M.AuditLog.objects.all()[:limit], many=True).data)


@api_view(["GET"])
def backup(request):
    tmp = tempfile.TemporaryFile()               # deleted automatically once it has been sent
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("images", "models"):
            for p in (DATA_DIR / sub).rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(DATA_DIR))
        if DB_PATH.exists():                     # consistent snapshot of the live database
            snap = DATA_DIR / "backup_snapshot.sqlite3"
            src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(snap)
            with dst:
                src.backup(dst)
            src.close(); dst.close()
            z.write(snap, "smearsight.sqlite3")
            snap.unlink()
    tmp.seek(0)
    audit(reader_name(request), "backup.download", "")
    return FileResponse(tmp, as_attachment=True, filename=f"smearsight_backup_{datetime.now():%Y%m%d_%H%M}.zip",
                        content_type="application/zip")
