"""Training worker, started by the web app as a separate process:

    python manage.py train_worker <run_id>

Trains a YOLOv8 nano model on a frozen dataset version, then evaluates it on the held-out
TEST split (slides the model never saw) and stores a candidate model. Promotion to "active"
is a separate, signed-off step in the app.
"""
import shutil
import statistics
import traceback
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import MLModel, TrainingRun
from core.services import settings_store
from core.services.config import MODELS_DIR, RUNS_DIR


def update_run(run_id, **kw):
    TrainingRun.objects.filter(id=run_id).update(**kw)


def pick_base(requested):
    """Use pretrained yolov8n.pt if it is on disk or can be fetched; otherwise train from scratch."""
    local = MODELS_DIR / "base" / "yolov8n.pt"
    if requested == "scratch":
        return "yolov8n.yaml", False, "Training from scratch (no pretrained weights requested)."
    if local.exists():
        return str(local), True, "Using pretrained yolov8n.pt from the models folder."
    try:
        from ultralytics import YOLO
        YOLO("yolov8n.pt")
        src = Path("yolov8n.pt")
        if src.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), local)
            return str(local), True, "Downloaded pretrained yolov8n.pt."
    except Exception:
        pass
    return "yolov8n.yaml", False, ("Pretrained weights were not available offline, so training starts from scratch. "
                                   "With real data, put yolov8n.pt in data/models/base/ for better results.")


CUTOFF_GRID = [round(0.25 + 0.05 * i, 2) for i in range(14)]        # 0.25 ... 0.90


def cutoff_table(rows, grid=CUTOFF_GRID):
    """rows: [(truth_positive, max_confidence_in_image)] -> one line per image-level cut-off.
    An image is called positive when its most confident detection is at or above the cut-off."""
    table = []
    for t in grid:
        tp = sum(1 for tr, c in rows if tr and c >= t)
        fn = sum(1 for tr, c in rows if tr and c < t)
        fp = sum(1 for tr, c in rows if not tr and c >= t)
        tn = sum(1 for tr, c in rows if not tr and c < t)
        div = lambda a, b: (a / b) if b else None            # noqa: E731
        table.append({"cutoff": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                      "sensitivity": div(tp, tp + fn), "specificity": div(tn, tn + fp),
                      "ppv": div(tp, tp + fp), "npv": div(tn, tn + fn)})
    return table


def evaluate(best, data_yaml, ds_root, imgsz, modality="zn"):
    from ultralytics import YOLO
    model = YOLO(str(best))
    test_imgs = sorted((ds_root / "images" / "test").glob("*.jpg"))
    out = {"test_images": len(test_imgs)}
    if not test_imgs:
        return out
    try:
        m = model.val(data=str(data_yaml), split="test", imgsz=imgsz, conf=0.001, plots=False,
                      verbose=False, device="cpu", workers=0,
                      project=str(RUNS_DIR / "eval"), name="test", exist_ok=True)
        out.update(map50=float(m.box.map50), map50_95=float(m.box.map),
                   precision=float(m.box.mp), recall=float(m.box.mr))
    except Exception as e:   # tiny test sets can break the box-level metric; keep the rest
        out["map_error"] = str(e)[:200]
    rows, times = [], []
    for p in test_imgs:
        lab = ds_root / "labels" / "test" / f"{p.stem}.txt"
        truth = lab.exists() and lab.read_text().strip() != ""
        r = model.predict(str(p), imgsz=imgsz, conf=settings_store.FLOOR, verbose=False, device="cpu")[0]
        times.append(r.speed.get("preprocess", 0) + r.speed.get("inference", 0) + r.speed.get("postprocess", 0))
        top = float(r.boxes.conf.max()) if (r.boxes is not None and len(r.boxes)) else 0.0
        rows.append((bool(truth), top))
    table = cutoff_table(rows)
    thr = settings_store.thresholds(modality)["positive"]
    at = min(table, key=lambda x: abs(x["cutoff"] - thr))
    out.update(tp=at["tp"], fp=at["fp"], fn=at["fn"], tn=at["tn"], sensitivity=at["sensitivity"],
               specificity=at["specificity"], ppv=at["ppv"], npv=at["npv"],
               test_positive_share=sum(1 for t, _ in rows if t) / len(rows),
               median_inference_ms=statistics.median(times) if times else None,
               image_threshold=at["cutoff"], cutoffs=table)
    return out


def run_training(run_id):
    run = TrainingRun.objects.select_related("dataset_version").get(id=run_id)
    ds = run.dataset_version
    modality = ds.modality or "zn"
    params = run.params or {}
    epochs = int(params.get("epochs", 30))
    imgsz = int(params.get("imgsz", 512))
    batch = int(params.get("batch", 8))
    ds_root = Path(ds.path)
    data_yaml = ds_root / "data.yaml"
    update_run(run_id, status="running", started_at=timezone.now(), epochs=epochs, epoch=0, message="Preparing model...")
    try:
        from ultralytics import YOLO
        base, pretrained, note = pick_base(params.get("base", "auto"))
        update_run(run_id, message=note)
        model = YOLO(base)
        history = []

        def on_epoch_end(trainer):
            ep = int(trainer.epoch) + 1
            if ep > epochs:      # ultralytics fires the callback once more after the final validation
                return
            tl = getattr(trainer, "tloss", None)

            def tv(k, i):        # newer versions give a dict, older ones a tensor
                try:
                    return float(tl[k]) if isinstance(tl, dict) else float(tl[i])
                except Exception:
                    return None
            mt = trainer.metrics or {}
            entry = {"epoch": ep, "train_box": tv("box_loss", 0), "train_cls": tv("cls_loss", 1),
                     "val_box": mt.get("val/box_loss"), "val_cls": mt.get("val/cls_loss"),
                     "map50": mt.get("metrics/mAP50(B)")}
            if history and history[-1]["epoch"] == ep:
                history[-1] = entry
            else:
                history.append(entry)
            update_run(run_id, epoch=ep, history=list(history), message=f"Epoch {ep} of {epochs}")

        model.add_callback("on_fit_epoch_end", on_epoch_end)
        project = RUNS_DIR / str(run_id)
        model.train(data=str(data_yaml), epochs=epochs, imgsz=imgsz, batch=batch, device="cpu",
                    workers=0, project=str(project), name="train", exist_ok=True, plots=False,
                    amp=False, patience=max(10, epochs // 2), seed=params.get("seed", 42),
                    pretrained=pretrained, verbose=False, hsv_h=0.01, hsv_s=0.3, hsv_v=0.3,
                    degrees=180, flipud=0.5, fliplr=0.5, mosaic=1.0, val=True)
        best = project / "train" / "weights" / "best.pt"
        if not best.exists():
            best = project / "train" / "weights" / "last.pt"
        update_run(run_id, message="Evaluating on the held-out test slides...")
        metrics = evaluate(best, data_yaml, ds_root, imgsz, modality)
        metrics.update(modality=modality, imgsz=imgsz, epochs=epochs, pretrained=pretrained, base=base,
                       train_images=ds.n_train, val_images=ds.n_val, dataset_version=ds.id)
        ver = MLModel.objects.count() + 1
        tag = "fm" if modality == "fm" else "zn"
        dest = MODELS_DIR / f"model_{tag}_v{ver}.pt"
        shutil.copy(best, dest)
        m = MLModel.objects.create(name=f"{tag}-v{ver}", modality=modality, path=str(dest), base="YOLOv8n", dataset_version=ds, run_id=run_id,
                                   metrics=metrics, status="candidate", demo=ds.includes_synthetic, notes=note)
        update_run(run_id, status="completed", finished_at=timezone.now(), model_id=m.id,
                   message="Done. Candidate model created.")
    except Exception as e:
        update_run(run_id, status="failed", finished_at=timezone.now(), error=traceback.format_exc()[-1500:],
                   message=f"Failed: {e}")
        raise


class Command(BaseCommand):
    help = "Train a detector for a queued TrainingRun (started by the web app)."

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int)

    def handle(self, *args, **opts):
        run_training(opts["run_id"])
