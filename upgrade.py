"""Upgrade an existing SmearSight (v1) to v2 without losing data.

1. Extract the v2 zip OVER the old folder (choose "Replace"). Your data/ and .venv/ folders are not in the zip, so they stay.
2. Close SmearSight, then double-click upgrade_windows.bat  (or run ./upgrade.sh).

This script: backs up the database first, installs the one new package, updates the database, and checks the result.
Nothing is deleted. If anything goes wrong, copy the backup file back over data/smearsight.sqlite3.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smearsight_site.settings")


def say(msg=""):
    print(msg, flush=True)


from core.services.config import DATA_DIR, DB_PATH   # noqa: E402

say("\n  SmearSight upgrade to v2\n  ------------------------")
if not DB_PATH.exists():
    say(f"  No database found at {DB_PATH}.\n  This looks like a new install, so there is nothing to upgrade. Just run start_windows.bat.")
    sys.exit(0)

# 1. back up (SQLite's own backup call: safe even if the file is in use)
bdir = DATA_DIR / "backups"
bdir.mkdir(exist_ok=True)
bfile = bdir / f"before_v2_{time.strftime('%Y%m%d_%H%M%S')}.sqlite3"
src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(bfile)
with dst:
    src.backup(dst)
src.close()
dst.close()
say(f"  1/4  Database backed up to {bfile}")

# 2. packages
r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", "requirements.txt"])
if r.returncode:
    say("  Package install failed. Check the internet connection and run the upgrade again. Your data is untouched.")
    sys.exit(1)
say("  2/4  Packages up to date")

# 3. database
import django   # noqa: E402
django.setup()
from django.core.management import call_command   # noqa: E402
call_command("migrate", interactive=False, verbosity=0)
say("  3/4  Database updated")

# 4. check
from core import models as M   # noqa: E402
counts = {"slides": M.Slide.objects.count(), "images": M.Image.objects.count(), "models": M.MLModel.objects.count(),
          "readers": M.Reader.objects.count()}
M.MLModel.objects.filter(modality="").update(modality="zn")
bad = [k for k in ("slides", "images") if counts[k] == 0 and bfile.stat().st_size > 400_000]
say(f"  4/4  Check: {counts['slides']} slides, {counts['images']} images, {counts['models']} models, {counts['readers']} readers kept")
say("\n  Your existing slides, images and models are now Bright-field (Ziehl-Neelsen), exactly as before.")
say("  Start SmearSight as usual. New: phones as cameras, fluorescence microscopy, PPV/NPV, positive confirmation.\n")
if bad:
    say("  Warning: counts look empty. Do not use the app yet; copy the backup over data/smearsight.sqlite3 and ask for help.")
