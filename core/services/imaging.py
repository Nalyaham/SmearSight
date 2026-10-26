"""Image helpers: save uploads, quality checks, thumbnails and crops."""
import hashlib
from pathlib import Path

import cv2
import numpy as np

from .config import DATA_DIR, IMAGES_DIR

MAX_SIDE = 1920
THUMB_DIR = DATA_DIR / "thumbs"
THUMB_DIR.mkdir(exist_ok=True)

# Quality flags are a first-pass warning, not a verdict. The defaults are NOT tuned on real smears:
# check them against a handful of your own good and bad photos and adjust through environment variables.
import os
BLUR_THRESHOLD = float(os.environ.get("SMEARSIGHT_BLUR_MIN", 10.0))   # variance of Laplacian on a 640 px copy
DARK_THRESHOLD = float(os.environ.get("SMEARSIGHT_DARK_MAX", 60.0))
BRIGHT_THRESHOLD = float(os.environ.get("SMEARSIGHT_BRIGHT_MIN", 245.0))
# Fluorescence fields are mostly black with a few bright rods, so the bright-field rules do not apply.
BLUR_THRESHOLD_FM = float(os.environ.get("SMEARSIGHT_BLUR_MIN_FM", 2.0))
HAZE_THRESHOLD_FM = float(os.environ.get("SMEARSIGHT_HAZE_MAX_FM", 110.0))   # mean grey above this = washed out


class BadImage(Exception):
    pass


def decode(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise BadImage("File is not a readable image (use JPG or PNG).")
    return img


def quality(img, modality="zn"):
    h, w = img.shape[:2]
    scale = 640.0 / max(w, 1)
    small = cv2.resize(img, (640, max(1, int(h * scale)))) if w != 640 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mean = float(gray.mean())
    flag = None
    if modality == "fm":
        if mean > HAZE_THRESHOLD_FM:
            flag = "washed out"
        elif blur < BLUR_THRESHOLD_FM:
            flag = "blurry"
        return blur, flag
    if blur < BLUR_THRESHOLD:
        flag = "blurry"
    elif mean < DARK_THRESHOLD:
        flag = "too dark"
    elif mean > BRIGHT_THRESHOLD:
        flag = "too bright"
    return blur, flag


def save_image(data: bytes, modality="zn"):
    """Decode, downscale if huge, store as JPEG named by content hash.
    Returns dict(path, sha256, width, height, blur_score, quality_flag)."""
    img = decode(data)
    sha = hashlib.sha256(data).hexdigest()
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
    sub = IMAGES_DIR / sha[:2]
    sub.mkdir(exist_ok=True)
    path = sub / f"{sha}.jpg"
    if not path.exists():
        cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    blur, flag = quality(img, modality)
    return {"path": str(path), "sha256": sha, "width": w, "height": h,
            "blur_score": blur, "quality_flag": flag}


def thumb_bytes(path: str, size: int = 220):
    p = Path(path)
    t = THUMB_DIR / f"{p.stem}_{size}.jpg"
    if not t.exists():
        img = cv2.imread(path)
        if img is None:
            raise BadImage("Missing image file.")
        h, w = img.shape[:2]
        s = size / max(h, w)
        img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(t), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return t.read_bytes()


def crop_bytes(path: str, cx, cy, w, h, pad=1.6, out=260):
    img = cv2.imread(path)
    if img is None:
        raise BadImage("Missing image file.")
    H, W = img.shape[:2]
    bw, bh = max(w * W, 24), max(h * H, 24)
    side = max(bw, bh) * pad
    x1 = int(max(0, cx * W - side / 2)); x2 = int(min(W, cx * W + side / 2))
    y1 = int(max(0, cy * H - side / 2)); y2 = int(min(H, cy * H + side / 2))
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        crop = img
    s = out / max(crop.shape[:2])
    crop = cv2.resize(crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))),
                      interpolation=cv2.INTER_CUBIC)
    # draw the box outline in the crop so readers see exactly what is being asked about
    bx1 = int((cx * W - bw / 2 - x1) * s); bx2 = int((cx * W + bw / 2 - x1) * s)
    by1 = int((cy * H - bh / 2 - y1) * s); by2 = int((cy * H + bh / 2 - y1) * s)
    cv2.rectangle(crop, (bx1, by1), (bx2, by2), (12, 65, 194), 2)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()
