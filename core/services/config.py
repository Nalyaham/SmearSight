"""Paths and settings for SmearSight. Everything is stored under one data folder."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SMEARSIGHT_DATA", BASE_DIR / "data")).resolve()
IMAGES_DIR = DATA_DIR / "images"
DATASETS_DIR = DATA_DIR / "datasets"
MODELS_DIR = DATA_DIR / "models"
RUNS_DIR = DATA_DIR / "runs"
DB_PATH = DATA_DIR / "smearsight.sqlite3"
STATIC_DIR = BASE_DIR / "static"


def pin():
    """Optional access PIN, read at request time so `run.py --pin` works."""
    return os.environ.get("SMEARSIGHT_PIN", "").strip()


# Detection thresholds
CONF_FLOOR = 0.25      # detections below this are never stored
CONF_REVIEW = 0.60     # detections between floor and this go to the expert review queue
CONF_POSITIVE = 0.50   # detections at or above this count as bacilli in grading

for d in (DATA_DIR, IMAGES_DIR, DATASETS_DIR, MODELS_DIR, RUNS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Keep ultralytics settings and caches inside the data folder, and never try to
# auto-install packages or phone home.
os.environ.setdefault("YOLO_CONFIG_DIR", str(DATA_DIR / "yolo_config"))
os.environ.setdefault("YOLO_AUTOINSTALL", "False")
