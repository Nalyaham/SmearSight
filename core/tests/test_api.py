import io
import time
import zipfile

import numpy as np
from django.test import TestCase
from rest_framework.test import APIClient

from core import models as M
from core.services import datasets, grading, synth

H = lambda n: {"HTTP_X_READER": n}      # noqa: E731


def grainy(seed, n_rods=None):
    im = synth.make_field(seed, n_rods=n_rods)[0].astype(np.float32)
    im = np.clip(im + np.random.default_rng(0).normal(0, 6, im.shape), 0, 255).astype(np.uint8)   # camera-like grain
    return synth.encode_jpeg(im)


class GradingTests(TestCase):
    def test_scale(self):
        g = grading.grade_slide
        self.assertEqual(g([0] * 100)["grade"], "negative")
        self.assertEqual(g([1] + [0] * 99)["grade"], "scanty")
        self.assertEqual(g([1] * 10 + [0] * 90)["grade"], "1+")
        self.assertEqual(g([3] * 50 + [0] * 50)["grade"], "2+")
        self.assertEqual(g([15] * 20 + [0] * 80)["grade"], "3+")
        self.assertTrue(g([0, 0, 1])["provisional"])
        self.assertIsNone(g([])["grade"])


class ApiTests(TestCase):
    def setUp(self):
        self.c = APIClient()

    def test_state_and_errors_are_readable(self):
        s = self.c.get("/api/state").json()
        self.assertEqual([r["role"] for r in s["readers"]], ["technician", "senior", "lead"])
        r = self.c.post("/api/slides", {"code": ""}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Slide ID is required", r.json()["detail"])
        r = self.c.post("/api/readers", {"name": "X", "role": "boss"}, format="json")
        self.assertEqual((r.status_code, r.json()["detail"]), (400, "Role must be technician, reader, senior or lead."))
        self.assertEqual(self.c.get("/api/slides/9999").status_code, 404)

    def test_freeze_splits_by_slide(self):
        self.assertEqual(self.c.post("/api/synthetic", {"count": 80, "seed": 7}, format="json").json()["made"], 80)
        r = self.c.post("/api/datasets/freeze", {"name": "t"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        by = {}
        for d in M.DatasetImage.objects.filter(version_id=r.json()["id"]).select_related("image"):
            by.setdefault(d.image.slide_id, set()).add(d.split)
        self.assertTrue(all(len(v) == 1 for v in by.values()), "a slide leaked across splits")

    def test_two_reader_rule_and_consent(self):
        up = self.c.post("/api/images/upload", {"files": io.BytesIO(grainy(999)), "consent": 0}, format="multipart", **H("Lab technician"))
        self.assertEqual(up.json()["added"], 1, up.content)
        iid = self.c.get("/api/images?status=unlabelled").json()["items"][0]["id"]
        self.c.put(f"/api/images/{iid}/annotations", {"boxes": [{"cx": .5, "cy": .5, "w": .05, "h": .02}]}, format="json", **H("Lab technician"))
        self.assertEqual(self.c.post(f"/api/images/{iid}/verify", **H("Lab technician")).status_code, 409)
        self.assertEqual(self.c.post(f"/api/images/{iid}/verify", **H("Senior reader")).status_code, 200)
        self.assertNotIn(iid, [i.id for i in datasets.eligible_images()], "no consent, must not be eligible")
        self.c.post(f"/api/images/{iid}/consent")
        self.assertIn(iid, [i.id for i in datasets.eligible_images()])

    def test_review_quorum_and_dispute(self):
        self.c.post("/api/synthetic", {"count": 8, "seed": 2}, format="json")
        im = M.Image.objects.first()
        it = M.ReviewItem.objects.create(image=im, cx=.5, cy=.5, w=.05, h=.02, conf=.4)
        vote = lambda who, v: self.c.post(f"/api/review/{it.id}/vote", {"vote": v}, format="json", **H(who))   # noqa: E731
        self.assertIsNone(vote("Lab technician", "afb").json()["resolution"])
        self.assertEqual(vote("Lab technician", "afb").status_code, 409)               # no double vote
        self.assertEqual(vote("Laboratory lead", "not_afb").json()["resolution"], "disputed")
        # the lead already voted in the first round, so the senior reader settles the dispute
        self.assertEqual(vote("Senior reader", "afb").json()["resolution"], "afb")

    def test_pin_gate(self):
        import os
        os.environ["SMEARSIGHT_PIN"] = "4321"
        try:
            c = APIClient()
            self.assertEqual(c.get("/api/state").status_code, 401)
            self.assertEqual(c.get("/").status_code, 302)
            self.assertEqual(c.post("/login", {"pin": "0000"}).status_code, 401)
            self.assertEqual(c.post("/login", {"pin": "4321"}).status_code, 302)
            self.assertEqual(c.get("/api/state").status_code, 200)
        finally:
            os.environ.pop("SMEARSIGHT_PIN")

    def test_front_end_is_served(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"SmearSight", b"".join(r.streaming_content))


class TrainingFlowTests(TestCase):
    """Real (tiny) training run, then approval, analysis, confirmation and reporting."""

    def test_full_flow(self):
        from core.management.commands.train_worker import run_training
        from core.views_ml import refresh_runs
        c = APIClient()
        c.post("/api/synthetic", {"count": 80, "seed": 9}, format="json")
        fr = c.post("/api/datasets/freeze", {"name": "tiny"}, format="json").json()
        run = M.TrainingRun.objects.create(dataset_version_id=fr["id"], status="queued", started_at=None,
                                           params={"epochs": 2, "imgsz": 160, "batch": 8, "base": "scratch"})
        run_training(run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed", run.error)
        self.assertTrue(run.history and run.history[0]["train_box"] is not None, "loss history missing")
        m = c.get("/api/models").json()[0]
        self.assertEqual((m["status"], m["demo"]), ("candidate", True))
        self.assertGreater(m["metrics"]["test_images"], 0)
        self.assertEqual(c.post(f"/api/models/{m['id']}/promote", {"approved_by": "Lab technician"}, format="json").status_code, 403)
        self.assertEqual(c.post(f"/api/models/{m['id']}/promote", {"approved_by": "Senior reader"}, format="json").status_code, 200)
        refresh_runs()                                  # must not disturb a finished run
        # analyse a slide
        s = c.post("/api/slides", {"code": "T-1", "site": "Test"}, format="json", **H("Lab technician")).json()
        d = c.post(f"/api/slides/{s['id']}/fields", {"files": io.BytesIO(grainy(4242, 6))}, format="multipart", **H("Lab technician")).json()
        self.assertEqual(len(d["fields"]), 1)
        self.assertGreater(d["fields"][0]["analysis"]["inference_ms"], 0)
        self.assertEqual(c.post("/api/slides", {"code": "T-1"}, format="json").status_code, 409)
        sug = d["suggested"]["grade"]
        other = "3+" if sug != "3+" else "negative"
        post = lambda body: c.post(f"/api/slides/{s['id']}/confirm", body, format="json", **H("Lab technician"))   # noqa: E731
        self.assertEqual(post({"final_grade": other}).status_code, 400)                     # override needs a reason
        self.assertEqual(post({"final_grade": "5+"}).status_code, 400)
        self.assertEqual(post({"final_grade": sug, "add_to_dataset": True}).status_code, 400)   # needs consent box
        ok = post({"final_grade": sug, "manual_seconds": 400})
        self.assertEqual((ok.status_code, ok.json()["status"]), (200, "confirmed"), ok.content)
        c.patch(f"/api/slides/{s['id']}/reference", {"reference_result": "pos", "reference_method": "Xpert"}, format="json")
        p = c.get("/api/performance?include_demo=1").json()
        self.assertEqual((p["slides"], p["manual_median_seconds"]), (1, 400))
        csv = c.get("/api/export/slides.csv?include_demo=1").content.decode()
        self.assertEqual(csv.count("T-1"), 1)
        b = c.get("/api/backup.zip")
        names = zipfile.ZipFile(io.BytesIO(b"".join(b.streaming_content))).namelist()
        self.assertTrue(any(n.startswith("models/") for n in names), names)
        self.assertGreater(len(c.get("/api/audit").json()), 3)
