"""Run the active model on an image and time it."""
import threading
import time

from ..models import MLModel
from .config import CONF_FLOOR

_lock = threading.Lock()
_cache = {"model_id": None, "model": None, "imgsz": 512}


def active_model():
    return MLModel.objects.filter(status="active").order_by("-approved_at", "-id").first()


def _load(m):
    from ultralytics import YOLO   # imported lazily: starting the web app does not need torch
    with _lock:
        if _cache["model_id"] != m.id:
            model = YOLO(m.path)
            imgsz = int((m.metrics or {}).get("imgsz", 512))
            _cache.update(model_id=m.id, model=model, imgsz=imgsz)
            # warm-up so the first real slide is not slower than the rest
            import numpy as np
            model.predict(np.zeros((imgsz, imgsz, 3), np.uint8), imgsz=imgsz, conf=0.9, verbose=False, device="cpu")
        return _cache["model"], _cache["imgsz"]


def forget():
    with _lock:
        _cache.update(model_id=None, model=None)


def detect(image_path, m=None):
    """Returns (detections, inference_ms, total_ms). Boxes are normalised YOLO centre format."""
    m = m or active_model()
    if not m:
        return None
    model, imgsz = _load(m)
    t0 = time.perf_counter()
    res = model.predict(image_path, imgsz=imgsz, conf=CONF_FLOOR, iou=0.5, max_det=300, verbose=False, device="cpu")[0]
    total_ms = (time.perf_counter() - t0) * 1000
    sp = res.speed
    inference_ms = float(sp.get("preprocess", 0) + sp.get("inference", 0) + sp.get("postprocess", 0))
    dets = []
    if res.boxes is not None and len(res.boxes):
        xywhn = res.boxes.xywhn.cpu().numpy()
        conf = res.boxes.conf.cpu().numpy()
        for (cx, cy, w, h), c in zip(xywhn, conf):
            dets.append({"cx": float(cx), "cy": float(cy), "w": float(w), "h": float(h), "conf": float(c)})
    return dets, inference_ms, total_ms
