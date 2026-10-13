# SmearSight (Django REST Framework edition)

A web application for TB smear reading support. It runs on one laboratory computer, with no internet needed after the
one-time install. A technician photographs microscope fields of a Ziehl-Neelsen smear, a YOLOv8 model marks suspected
acid-fast bacilli (AFB), the technician checks and corrects the boxes, and the app suggests a WHO/IUATLD grade.
It also stores images for a dataset, supports two-reader labelling, retrains the model, and records time per slide.

**A person always makes the final call.** This is a research tool, not a validated diagnostic device.

Built with Django 5, Django REST Framework, SQLite, YOLOv8 (Ultralytics) and a plain-JavaScript interface.

## Install and run

### Windows

1. Install **Python 3.12** from https://www.python.org/downloads/ . On the first installer screen tick **"Add python.exe to PATH"**.
2. Right-click the zip, **Extract All**, and open the extracted `smearsight_drf` folder.
3. Double-click **`install_windows.bat`**. It needs internet and takes 5 to 20 minutes the first time (a large download, about 1 to 2 GB).
   If the window shows an error, it explains the usual causes and keeps a log in `install_log.txt`. Running it again continues where it stopped.
4. When it finishes, SmearSight starts and your browser opens at http://localhost:8000.
5. Next time: double-click **`start_windows.bat`**. Keep the black window open while you work; closing it stops the app.

### Mac / Linux

    ./install.sh        # first time only (then it starts the app)
    ./start.sh          # every other time

Then open http://localhost:8000.

### Using phones as the camera

Start with `start_windows.bat --lan --pin 1234` (or `./start.sh --lan --pin 1234`). Connect the phone to the same Wi-Fi and open the
address the window prints. In **Analyze slide**, **Take photo** opens the phone camera. Always set a PIN when you use `--lan`.

## Workflow

1. **Dataset**: upload field images (tick the consent box only if consent or an ethics waiver covers training use), import a
   YOLO-format zip, or press *Generate demo images* to try the app with synthetic pictures.
2. Label images by drawing boxes. A *different* reader verifies them. Only verified images are used for training.
3. **Freeze a version.** Images are split into train, validation and test by slide, so one slide is never in both training and test.
4. **Model training**: trains YOLOv8n on the CPU and evaluates on the held-out test slides. For real data put `yolov8n.pt` in
   `data/models/base/` to start from pretrained weights; otherwise training starts from scratch.
5. A senior reader or the lab lead **approves** the candidate. Approval is blocked if its sensitivity is lower than the active
   model's. Older models can be rolled back to.
6. **Analyze slide**: photograph fields, tap boxes to count or uncount them, drag to add missed bacilli, confirm a final grade.
   A reason is required when you override the suggestion.
7. **Expert review**: detections below 0.60 confidence queue for two readers to vote on; disagreements go to a senior reader.
8. **Performance**: time per slide (app vs your manual time), sensitivity and specificity against culture or Xpert results
   with 95% confidence intervals, by site, CSV export.

All data is in the `data/` folder (database, images, datasets, models). Use *Settings and audit, Download full backup*, or copy that folder.

## For developers

* REST API under `/api/` (Django REST Framework ViewSets and serializers, JSON, with the browsable API in a browser):
  `slides`, `images`, `detections`, `review`, `datasets`, `training`, `models`, plus `state`, `performance`, `summary`,
  `audit`, `export/slides.csv`, `backup.zip`. Errors are always `{"detail": "readable message"}`.
* Django admin at `/admin/` to inspect or fix records: run `python manage.py createsuperuser` once (inside the virtual environment).
* Reader identity is the `X-Reader` request header (the interface sends it). Optional access PIN via `--pin` or `SMEARSIGHT_PIN`.
* Training runs as a separate process: `python manage.py train_worker <run_id>`.
* Tests: `python manage.py test core` (uses a temporary data folder, includes a real two-epoch training run).
* Settings through environment variables: `SMEARSIGHT_DATA` (data folder), `SMEARSIGHT_PIN`, `SMEARSIGHT_TZ`,
  `SMEARSIGHT_BLUR_MIN`, `SMEARSIGHT_DARK_MAX`, `SMEARSIGHT_BRIGHT_MIN`.

      smearsight_site/   Django project (settings, urls)
      core/              models, serializers, API views, services (grading, imaging, datasets, inference), train_worker command
      static/            the web interface
      data/              created on first run

## Troubleshooting

* **"Python was not found"**: install Python 3.12 and tick *Add python.exe to PATH*.
* **Install fails or stops**: run the installer again. Try a phone hotspot if a network blocks downloads. You need about 3 GB of free disk space.
  If it still fails on PyTorch or Ultralytics, install Python 3.12, delete the `.venv` folder, and run the installer again.
* **"DLL load failed" or an error mentioning torch when training or analysing (Windows)**: install the free "Microsoft Visual C++ Redistributable (x64)" from Microsoft, then start the app again.
* **"Port 8000 already in use"**: `start_windows.bat --port 8010`, then open http://localhost:8010.
* **Phone cannot connect**: the phone and computer must be on the same Wi-Fi, and Windows may ask to allow Python through the firewall: allow it on private networks.

## Honest limits

* Demo images are computer-drawn. A model trained on them (marked DEMO everywhere) proves the software works, nothing more.
  Real performance needs real, consented, expert-labelled slides and a prospective evaluation against culture or Xpert.
* Grading follows the WHO/IUATLD scale for 100 fields; fewer fields are marked *provisional*.
* The app stores no patient names. Use anonymous lab codes.
* Sensitivity and specificity shown are only as good as the reference results entered, and small samples give wide intervals.
* The blur, dark and bright image flags use untuned default thresholds. Check them against a few of your own photos and adjust with the
  environment variables above. Flagged images are excluded from training.
