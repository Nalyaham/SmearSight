"""Synthetic demo images.

These are DRAWN pictures with known box positions. They exist only so the whole pipeline
(upload, label, freeze, train, analyse, report) can be tested before real labelled slides
are available. A model trained on them cannot detect real tuberculosis bacilli. Everything
made here is flagged synthetic=1 and models trained on it are flagged DEMO.
"""
import math
import random

import cv2
import numpy as np


def _noise(rng, shape, sigma):
    return rng.normal(0, sigma, shape)


def make_field(seed: int, size: int = 512, n_rods=None, tint=None):
    """Return (image BGR uint8, boxes [(cx, cy, w, h) normalised])."""
    r = random.Random(seed)
    rng = np.random.default_rng(seed)
    tint = tint or (r.uniform(-10, 10), r.uniform(-8, 8), r.uniform(-10, 10))
    bg = np.array([247 + tint[0], 238 + tint[1], 227 + tint[2]], dtype=np.float32)  # BGR, pale blue
    img = np.ones((size, size, 3), np.float32) * bg
    # uneven illumination
    yy, xx = np.mgrid[0:size, 0:size]
    cx0, cy0 = r.uniform(0.3, 0.7) * size, r.uniform(0.3, 0.7) * size
    falloff = 1 - 0.18 * (((xx - cx0) ** 2 + (yy - cy0) ** 2) / (size ** 2))
    img *= falloff[..., None]
    # large pale smudges (mucus / debris)
    for _ in range(r.randint(6, 12)):
        c = (int(r.uniform(0, size)), int(r.uniform(0, size)))
        ax = (r.randint(14, 46), r.randint(6, 20))
        col = (bg - np.array([r.uniform(14, 30), r.uniform(12, 24), r.uniform(8, 18)])).tolist()
        cv2.ellipse(img, c, ax, r.uniform(0, 180), 0, 360, col, -1, cv2.LINE_AA)
    img = cv2.GaussianBlur(img, (0, 0), 3)
    # hard negatives: round or squat red/purple particles that are NOT bacilli
    for _ in range(r.randint(2, 8)):
        c = (int(r.uniform(10, size - 10)), int(r.uniform(10, size - 10)))
        col = (r.randint(70, 110), r.randint(20, 60), r.randint(120, 170))
        if r.random() < 0.5:
            cv2.circle(img, c, r.randint(3, 6), col, -1, cv2.LINE_AA)
        else:
            cv2.ellipse(img, c, (r.randint(5, 8), r.randint(4, 6)), r.uniform(0, 180), 0, 360, col, -1, cv2.LINE_AA)
    # bacilli: slim, slightly curved red rods
    boxes = []
    count = n_rods if n_rods is not None else (0 if r.random() < 0.4 else r.randint(1, 9))
    placed = []
    for _ in range(count):
        for _try in range(30):
            c = (r.uniform(24, size - 24), r.uniform(24, size - 24))
            if all(math.hypot(c[0] - p[0], c[1] - p[1]) > 34 for p in placed):
                break
        placed.append(c)
        length = r.uniform(16, 30)
        thick = r.uniform(3.0, 4.6)
        ang = r.uniform(0, math.pi)
        bend = r.uniform(-0.18, 0.18)
        pts = []
        for t in np.linspace(-0.5, 0.5, 9):
            a = ang + bend * t * 2
            pts.append((c[0] + math.cos(ang) * t * length + math.sin(ang) * bend * length * (t * t) * 2,
                        c[1] + math.sin(ang) * t * length - math.cos(ang) * bend * length * (t * t) * 2))
        pts = np.array(pts, np.int32).reshape(-1, 1, 2)
        col = (r.randint(55, 85), r.randint(15, 40), r.randint(150, 190))   # carbol fuchsin red (BGR)
        cv2.polylines(img, [pts], False, col, int(round(thick)), cv2.LINE_AA)
        xs, ys = pts[:, 0, 0], pts[:, 0, 1]
        pad = 5
        x1, x2 = max(0, xs.min() - pad), min(size, xs.max() + pad)
        y1, y2 = max(0, ys.min() - pad), min(size, ys.max() + pad)
        boxes.append(((x1 + x2) / 2 / size, (y1 + y2) / 2 / size, (x2 - x1) / size, (y2 - y1) / size))
    img = cv2.GaussianBlur(img, (0, 0), 0.9)
    img += _noise(rng, img.shape, 2.2)
    return np.clip(img, 0, 255).astype(np.uint8), boxes


def encode_jpeg(img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()
