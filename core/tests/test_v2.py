"""Tests for v2: fluorescence grading, PPV/NPV, phone pairing and upload, confirmation workflow."""
import io
import os
from types import SimpleNamespace

import cv2
import numpy as np
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core import models as M
from core.management.commands.train_worker import cutoff_table
from core.services import confirm, grading, settings_store, synth
from core.services.network import parse_user_agent
from core.views_ml import adjusted_predictive_values, predictive_values

H = lambda n: {"HTTP_X_READER": n}      # noqa: E731
TECH, SENIOR, LEAD = "Lab technician", "Senior reader", "Laboratory lead"


def jpeg(img):
    return synth.encode_jpeg(img)


def fm_jpeg(seed=3):
    return jpeg(synth.make_field_fm(seed, n_rods=4)[0])


def zn_jpeg(seed=5):
    im = synth.make_field(seed, n_rods=3)[0].astype(np.float32)
    im = np.clip(im + np.random.default_rng(0).normal(0, 6, im.shape), 0, 255).astype(np.uint8)
    return jpeg(im)


def f(data, name="p.jpg"):
    b = io.BytesIO(data)
    b.name = name
    return b


class FluorescenceGradingTests(TestCase):
    def test_fm_200x(self):
        g = lambda c: grading.grade_slide(c, "fm", "200x")["grade"]          # noqa: E731
        self.assertEqual(g([0] * 300), "negative")
        self.assertEqual(g([1] * 29 + [0] * 271), "scanty")                  # 29 per length
        self.assertEqual(g([1] * 30 + [0] * 270), "1+")                      # 30 per length
        self.assertEqual(g([1] * 299 + [0]), "1+")
        self.assertEqual(g([10] * 300), "2+")                                # 10 per field
        self.assertEqual(g([101] * 300), "3+")                               # more than 100 per field

    def test_fm_400x(self):
        g = lambda c: grading.grade_slide(c, "fm", "400x")["grade"]          # noqa: E731
        self.assertEqual(g([1] * 19 + [0] * 21), "scanty")
        self.assertEqual(g([1] * 20 + [0] * 20), "1+")
        self.assertEqual(g([5] * 40), "2+")
        self.assertEqual(g([51] * 40), "3+")

    def test_fm_gap_goes_up_and_is_flagged(self):
        r = grading.grade_slide([4] * 300, "fm", "200x")                    # 4 per field = 1200 per length: above 1+, below 2+
        self.assertEqual(r["grade"], "2+")
        self.assertIn("lab lead should confirm", r["explanation"])

    def test_fm_provisional_when_short(self):
        r = grading.grade_slide([0, 1, 0], "fm", "200x")
        self.assertTrue(r["provisional"])
        self.assertEqual(r["scale"], grading.FM_SCALES["200"]["label"])

    def test_zn_unchanged(self):
        self.assertEqual(grading.grade_slide([1] * 10 + [0] * 90)["grade"], "1+")
        self.assertEqual(grading.modality_for_stain("Auramine O"), "fm")
        self.assertEqual(grading.modality_for_stain("Ziehl-Neelsen"), "zn")

    def test_synthetic_fm_is_dark_and_not_flagged_dark(self):
        from core.services import imaging
        img, boxes = synth.make_field_fm(11, n_rods=5)
        self.assertLess(img.mean(), 60)
        self.assertEqual(len(boxes), 5)
        self.assertIsNone(imaging.quality(img, "fm")[1])
        self.assertEqual(imaging.quality(img, "zn")[1], "blurry" if imaging.quality(img, "zn")[0] < imaging.BLUR_THRESHOLD else "too dark")


class PredictiveValueTests(TestCase):
    def test_cutoff_table(self):
        rows = [(True, 0.9), (True, 0.6), (True, 0.3), (False, 0.55), (False, 0.1), (False, 0.0)]
        t = {r["cutoff"]: r for r in cutoff_table(rows)}
        self.assertEqual((t[0.5]["tp"], t[0.5]["fn"], t[0.5]["fp"], t[0.5]["tn"]), (2, 1, 1, 2))
        self.assertAlmostEqual(t[0.5]["ppv"], 2 / 3)
        self.assertAlmostEqual(t[0.5]["npv"], 2 / 3)
        self.assertEqual((t[0.7]["tp"], t[0.7]["fp"]), (1, 0))
        self.assertEqual(t[0.7]["ppv"], 1.0)
        self.assertIsNone(cutoff_table([(True, 0.9)])[0]["specificity"])

    def test_bayes(self):
        ppv, npv = predictive_values(0.9, 0.95, 0.10)
        self.assertAlmostEqual(ppv, 0.09 / (0.09 + 0.045), places=6)
        self.assertAlmostEqual(npv, 0.855 / (0.855 + 0.01), places=6)

    def test_adjusted_range_orders(self):
        c = {"sensitivity": 0.9, "specificity": 0.95, "sens_ci": [0.8, 0.95], "spec_ci": [0.9, 0.98]}
        a = adjusted_predictive_values(c, 0.05)
        self.assertLess(a["ppv_range"][0], a["ppv"])
        self.assertGreater(a["ppv_range"][1], a["ppv"])
        self.assertLess(a["npv_range"][0], a["npv"])

    def _slide(self, code, ai, final, ref):
        return M.Slide.objects.create(code=code, status="confirmed", ai_grade=ai, final_grade=final,
                                      reference_result=ref, session_seconds=60)

    def test_performance_has_ppv_npv_and_target_status(self):
        for i in range(8):
            self._slide(f"P{i}", "1+", "1+", "pos")
        for i in range(2):
            self._slide(f"FP{i}", "scanty", "scanty", "neg")
        for i in range(8):
            self._slide(f"N{i}", "negative", "negative", "neg")
        self._slide("FN", "negative", "negative", "pos")
        r = APIClient().get("/api/performance?include_demo=1").json()["ai"]
        self.assertEqual((r["tp"], r["fp"], r["fn"], r["tn"]), (8, 2, 1, 8))
        self.assertAlmostEqual(r["ppv"], 0.8)
        self.assertAlmostEqual(r["npv"], 8 / 9)
        self.assertEqual(r["targets"]["ppv"]["status"], "not_met")
        self.assertIn(r["targets"]["sensitivity"]["status"], ("point", "not_met", "met"))
        self.assertIn("ppv_range", r["adjusted"])

    def test_targets_need_lead(self):
        c = APIClient()
        r = c.put("/api/settings", {"targets": {"ppv": 0.85}, "approved_by": TECH}, format="json", **H(TECH))
        self.assertEqual(r.status_code, 403)
        r = c.put("/api/settings", {"targets": {"ppv": 0.85}, "prevalence": 0.07, "approved_by": LEAD}, format="json", **H(LEAD))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["targets"]["ppv"], 0.85)
        self.assertEqual(r.json()["prevalence"], 0.07)
        r = c.put("/api/settings", {"modality": "fm", "positive": 0.65, "approved_by": SENIOR}, format="json", **H(SENIOR))
        self.assertEqual(r.json()["thresholds"]["fm"]["positive"], 0.65)
        self.assertEqual(r.json()["thresholds"]["zn"]["positive"], 0.5)        # per microscopy type


class UserAgentTests(TestCase):
    def test_phones(self):
        cases = [
            ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
             "iOS 17", "Safari"),
            ("Mozilla/5.0 (Linux; Android 13; SM-A135F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
             "Android 13", "Chrome"),
            ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
             "Android 10", "Chrome"),
            ("Mozilla/5.0 (Linux; Android 12; SAMSUNG SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",
             "Android 12", "Samsung Internet"),
            ("Mozilla/5.0 (Linux; Android 9; TECNO KC8) AppleWebKit/537.36 Chrome/80.0 Mobile Safari/537.36", "Android 9", "Chrome"),
            ("Mozilla/5.0 (Linux; Android 7.0; Moto G (4) Build/NPJS25.93-14-18) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0 Mobile Safari/537.36", "Android 7", "Chrome"),
            ("Mozilla/5.0 (Linux; Android 7.0; Moto G (4)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0 Mobile Safari/537.36", "Android 7", "Chrome"),
            ("Mozilla/5.0 (Linux; Android 8.0.0; SM-G965U Build/R16NW) AppleWebKit/537.36 Chrome/80.0 Mobile Safari/537.36", "Android 8", "Chrome"),
            ("", "", ""),
        ]
        for ua, plat, br in cases:
            p, b, _ = parse_user_agent(ua)
            self.assertEqual((p, b), (plat, br), ua)
        self.assertEqual(parse_user_agent(cases[1][0])[2], "SM-A135F")
        self.assertEqual(parse_user_agent(cases[2][0])[2], "Android phone")      # "K" is a privacy placeholder
        self.assertEqual(parse_user_agent(cases[4][0])[2], "TECNO KC8")
        self.assertEqual(parse_user_agent(cases[5][0])[2], "Moto G (4)")      # with a Build/ suffix
        self.assertEqual(parse_user_agent(cases[6][0])[2], "Moto G (4)")      # without
        self.assertEqual(parse_user_agent(cases[7][0])[2], "SM-G965U")


class PhoneFlowTests(TestCase):
    ANDROID = "Mozilla/5.0 (Linux; Android 13; SM-A135F) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36"
    IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1"

    def setUp(self):
        self.pc = APIClient()
        self.slide = self.pc.post("/api/slides", {"code": "UG-1", "stain": "Auramine O", "magnification": "200x"},
                                  format="json", **H(TECH)).json()

    def pair(self, ua=None, client=None):
        client = client or APIClient()
        code = self.pc.post("/api/devices/pairing", {}, format="json", **H(TECH)).json()["code"]
        r = client.post("/api/phone/pair", {"code": code}, format="json", HTTP_USER_AGENT=ua or self.ANDROID)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_slide_modality_from_stain(self):
        self.assertEqual((self.slide["modality"], self.slide["magnification"]), ("fm", "200x"))
        s2 = self.pc.post("/api/slides", {"code": "UG-2"}, format="json").json()
        self.assertEqual((s2["modality"], s2["magnification"]), ("zn", "1000x"))
        s3 = self.pc.post("/api/slides", {"code": "UG-3", "microscopy": "fm", "magnification": "1000x"}, format="json").json()
        self.assertEqual((s3["stain"], s3["magnification"]), ("Auramine O", "400x"))
        self.assertEqual(s3["standard_fields"], 40)

    def test_pairing_code_is_single_use_and_names_the_phone(self):
        d = self.pair()
        self.assertEqual(d["device"]["name"], "SM-A135F")
        self.assertEqual(d["device"]["platform"], "Android 13")
        self.assertEqual(M.CaptureDevice.objects.get().token_hash, __import__("hashlib").sha256(d["token"].encode()).hexdigest())
        used = M.PairingCode.objects.get().code
        r = APIClient().post("/api/phone/pair", {"code": used}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertIn("wrong or has expired", r.json()["detail"])

    def test_pairing_is_rate_limited(self):
        from core import views_v2
        views_v2._pair_fails.clear(); views_v2._pair_fails_all.clear()
        c = APIClient()
        for _ in range(5):
            self.assertEqual(c.post("/api/phone/pair", {"code": "000000"}, format="json").status_code, 403)
        r = c.post("/api/phone/pair", {"code": "000000"}, format="json")
        self.assertEqual(r.status_code, 429)
        views_v2._pair_fails.clear(); views_v2._pair_fails_all.clear()

    def test_expired_code(self):
        code = self.pc.post("/api/devices/pairing", {}, format="json").json()["code"]
        from django.utils import timezone
        from datetime import timedelta
        M.PairingCode.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(APIClient().post("/api/phone/pair", {"code": code}, format="json").status_code, 403)

    def test_full_flow_select_upload_and_refresh(self):
        dv = self.pair()
        phone = APIClient()
        h = self.auth(dv["token"])
        # not selected yet
        self.assertIsNone(phone.get("/api/phone/status", **h).json()["slide"])
        r = phone.post("/api/phone/upload", {"file": f(fm_jpeg())}, format="multipart", **h)
        self.assertEqual(r.status_code, 409)
        # computer selects the phone for the slide
        r = self.pc.put(f"/api/slides/{self.slide['id']}/capture-device", {"device_id": dv["device"]["id"]}, format="json", **H(TECH))
        self.assertEqual(r.json()["capture_device"]["name"], "SM-A135F")
        st = phone.get("/api/phone/status", **h).json()
        self.assertEqual((st["slide"]["code"], st["slide"]["modality"], st["slide"]["target_fields"]), ("UG-1", "fm", 300))
        self.assertNotIn("detections", str(st))
        r = phone.post("/api/phone/upload", {"file": f(fm_jpeg(3))}, format="multipart", **h)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["n_fields"], 1)
        again = phone.post("/api/phone/upload", {"file": f(fm_jpeg(3))}, format="multipart", **h)
        self.assertEqual(again.status_code, 409)
        self.assertIn("Already added", again.json()["detail"])
        phone.post("/api/phone/upload", {"file": f(fm_jpeg(4))}, format="multipart", **h)
        poll = self.pc.get(f"/api/slides/{self.slide['id']}/capture-status").json()
        self.assertEqual(poll["n_fields"], 2)
        self.assertTrue(poll["device"]["online"])
        im = M.Image.objects.first()
        self.assertEqual((im.modality, im.device.name, im.added_by), ("fm", "SM-A135F", "phone: SM-A135F"))
        dev = self.pc.get("/api/devices").json()["devices"][0]
        self.assertEqual(dev["upload_count"], 2)
        self.assertNotIn("token", str(dev))
        kinds = [e["kind"] for e in self.pc.get("/api/capture/events").json()["events"]]
        self.assertIn("upload_ok", kinds)
        self.assertIn("pair", kinds)

    def test_blurry_photo_asks_for_retake_unless_forced(self):
        dv = self.pair()
        h = self.auth(dv["token"])
        slide = self.pc.post("/api/slides", {"code": "UG-Z"}, format="json").json()
        self.pc.put(f"/api/slides/{slide['id']}/capture-device", {"device_id": dv["device"]["id"]}, format="json")
        flat = jpeg(np.full((480, 640, 3), 140, np.uint8))
        r = APIClient().post("/api/phone/upload", {"file": f(flat)}, format="multipart", **h).json()
        self.assertFalse(r["ok"])
        self.assertTrue(r["retake"])
        self.assertEqual(r["quality_flag"], "blurry")
        self.assertEqual(M.Image.objects.count(), 0)
        r = APIClient().post("/api/phone/upload", {"file": f(flat), "force": "1"}, format="multipart", **h).json()
        self.assertTrue(r["ok"])
        self.assertEqual(M.Image.objects.get().quality_flag, "blurry")

    def test_exif_gps_is_removed_on_the_server(self):
        from PIL import Image as PI
        src = PI.fromarray(cv2.cvtColor(zn_jpeg() and synth.make_field(8, n_rods=3)[0], cv2.COLOR_BGR2RGB))
        ex = src.getexif()
        ex[0x010F] = "SecretPhone"                 # Make
        ex[0x8825] = {1: "N", 2: (0, 19, 0)}       # GPS block
        buf = io.BytesIO(); src.save(buf, "JPEG", exif=ex.tobytes(), quality=92)
        self.assertIn(b"SecretPhone", buf.getvalue())
        from core.services import imaging
        info = imaging.save_image(buf.getvalue())
        self.assertNotIn(b"SecretPhone", open(info["path"], "rb").read())
        self.assertNotIn(b"Exif", open(info["path"], "rb").read())

    def test_revoked_phone_is_cut_off(self):
        dv = self.pair(self.IPHONE)
        self.assertEqual(dv["device"]["platform"], "iOS 17")
        h = self.auth(dv["token"])
        self.assertEqual(APIClient().get("/api/phone/status", **h).status_code, 200)
        self.pc.put(f"/api/slides/{self.slide['id']}/capture-device", {"device_id": dv["device"]["id"]}, format="json")
        r = self.pc.delete(f"/api/devices/{dv['device']['id']}", **H(TECH))
        self.assertTrue(r.json()["revoked"])
        self.assertEqual(APIClient().get("/api/phone/status", **h).status_code, 401)
        self.assertEqual(APIClient().post("/api/phone/upload", {"file": f(fm_jpeg())}, format="multipart", **h).status_code, 401)
        self.assertIsNone(M.Slide.objects.get(pk=self.slide["id"]).capture_device)
        r = self.pc.put(f"/api/slides/{self.slide['id']}/capture-device", {"device_id": dv["device"]["id"]}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_bad_or_missing_token(self):
        c = APIClient()
        self.assertEqual(c.get("/api/phone/status").status_code, 401)
        self.assertEqual(c.get("/api/phone/status", HTTP_AUTHORIZATION="Bearer nonsense").status_code, 401)

    def test_one_phone_serves_one_slide(self):
        dv = self.pair()
        s2 = self.pc.post("/api/slides", {"code": "UG-9"}, format="json").json()
        for sid in (self.slide["id"], s2["id"]):
            self.pc.put(f"/api/slides/{sid}/capture-device", {"device_id": dv["device"]["id"]}, format="json")
        self.assertIsNone(M.Slide.objects.get(pk=self.slide["id"]).capture_device)
        self.assertEqual(M.Slide.objects.get(pk=s2["id"]).capture_device_id, dv["device"]["id"])

    def test_phone_feedback_and_health(self):
        dv = self.pair()
        h = self.auth(dv["token"])
        r = APIClient().post("/api/phone/feedback", {"rating": 4, "comment": "easy"}, format="json", **h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(APIClient().post("/api/phone/feedback", {"rating": 9}, format="json", **h).status_code, 400)
        fb = self.pc.get("/api/feedback").json()
        self.assertEqual((fb["n"], fb["by_source"]["phone"]["mean"]), (1, 4))
        hl = self.pc.get("/api/health").json()
        self.assertTrue(hl["ok"])
        self.assertEqual(hl["phones"]["paired"], 1)
        self.assertEqual(self.pc.get("/healthz").json(), {"ok": True})

    def test_pin_gate_lets_phones_reach_only_the_phone_paths(self):
        os.environ["SMEARSIGHT_PIN"] = "4321"
        try:
            c = APIClient()
            self.assertEqual(c.get("/api/state").status_code, 401)
            self.assertEqual(c.get("/api/devices").status_code, 401)
            self.assertEqual(c.post("/api/devices/pairing", {}, format="json").status_code, 401)   # a phone cannot make codes
            self.assertEqual(c.get("/api/phone/status").status_code, 401)                           # reaches the view: token error
            self.assertEqual(c.get("/api/phone/status").json()["detail"].startswith("This phone is not paired"), True)
            self.assertEqual(c.get("/api/slides").status_code, 401)
            self.assertEqual(c.get("/healthz").status_code, 200)
        finally:
            os.environ.pop("SMEARSIGHT_PIN", None)

    def test_pairing_codes_capped_and_qr_returned(self):
        r = None
        for _ in range(5):
            r = self.pc.post("/api/devices/pairing", {}, format="json").json()
        self.assertIn("<svg", r["qr_svg"])
        self.assertIn("?code=" + r["code"], r["url"])
        self.assertEqual(self.pc.post("/api/devices/pairing", {}, format="json").status_code, 429)

    def test_phone_page_is_served(self):
        r = self.pc.get("/phone")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"phone.js", r.content)


class ModalityIsolationTests(TestCase):
    def test_datasets_and_models_are_per_modality(self):
        c = APIClient()
        self.assertEqual(c.post("/api/synthetic", {"count": 24, "seed": 2, "modality": "fm"}, format="json").json()["made"], 24)
        self.assertEqual(c.get("/api/dataset/stats?modality=zn").json()["total"], 0)
        self.assertEqual(c.get("/api/dataset/stats?modality=fm").json()["total"], 24)
        r = c.post("/api/datasets/freeze", {"modality": "zn"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/datasets/freeze", {"modality": "fm", "name": "fm1"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(M.DatasetVersion.objects.get().modality, "fm")
        a = M.MLModel.objects.create(name="zn-a", path="x", status="active", modality="zn")
        b = M.MLModel.objects.create(name="fm-a", path="y", status="active", modality="fm")
        st = c.get("/api/state").json()
        self.assertEqual((st["active_models"]["zn"]["name"], st["active_models"]["fm"]["name"]), ("zn-a", "fm-a"))
        cand = M.MLModel.objects.create(name="fm-b", path="z", status="candidate", modality="fm",
                                        metrics={"test_images": 10, "sensitivity": 0.95})
        r = c.post(f"/api/models/{cand.id}/promote", {"approved_by": SENIOR}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.status, b.status), ("active", "archived"))          # the bright-field model is untouched

    def test_cutoff_endpoint_and_apply(self):
        rows = cutoff_table([(True, 0.9), (True, 0.7), (True, 0.4), (False, 0.3), (False, 0.1), (False, 0.0), (False, 0.55)])
        m = M.MLModel.objects.create(name="v1", path="x", status="candidate", modality="zn",
                                     metrics={"test_images": 7, "cutoffs": rows, "test_positive_share": 3 / 7})
        c = APIClient()
        d = c.get(f"/api/models/{m.id}/cutoffs").json()
        self.assertEqual(len(d["rows"]), 14)
        self.assertIn("ppv_ci", d["rows"][0])
        self.assertEqual(d["current_cutoff"], 0.5)
        self.assertEqual(c.post(f"/api/models/{m.id}/cutoff", {"cutoff": 0.6, "approved_by": TECH}, format="json").status_code, 403)
        r = c.post(f"/api/models/{m.id}/cutoff", {"cutoff": 0.6, "approved_by": SENIOR}, format="json", **H(SENIOR))
        self.assertEqual(r.json()["positive"], 0.6)
        self.assertGreaterEqual(r.json()["review"], 0.6)
        self.assertEqual(settings_store.thresholds("zn")["positive"], 0.6)
        self.assertEqual(settings_store.thresholds("fm")["positive"], 0.5)


def fake(grade, status="confirmed", by="Lab technician", modality="zn", sid=1):
    return SimpleNamespace(id=sid, final_grade=grade, status=status, confirmed_by=by, modality=modality)


def con(method, result="", grade=None, by="X", rif=""):
    return SimpleNamespace(method=method, result=result, grade=grade, by=by, rif_result=rif)


class ConfirmationLogicTests(TestCase):
    def test_concordance_rules(self):
        c = confirm.concordance
        self.assertEqual(c("1+", "1+"), "concordant")
        self.assertEqual(c("scanty", "1+"), "minor")
        self.assertEqual(c("1+", "2+"), "minor")
        self.assertEqual(c("scanty", "2+"), "discordant")
        self.assertEqual(c("1+", "3+"), "discordant")
        self.assertEqual(c("scanty", "negative"), "discordant")
        self.assertEqual(c("3+", "negative"), "discordant")

    def test_error_types(self):
        self.assertTrue(confirm.error_type("1+", "negative").startswith("HFN"))
        self.assertTrue(confirm.error_type("scanty", "negative").startswith("LFN"))
        self.assertTrue(confirm.error_type("negative", "scanty").startswith("LFP"))
        self.assertTrue(confirm.error_type("scanty", "3+").startswith("QE"))
        self.assertIsNone(confirm.error_type("1+", "2+"))

    def test_negative_needs_nothing(self):
        self.assertEqual(confirm.status(fake("negative"), [])["state"], "not_applicable")
        self.assertEqual(confirm.status(fake("2+", status="open"), [])["state"], "not_applicable")

    def test_high_grade_two_readers_is_enough_but_xpert_recommended(self):
        s = fake("3+")
        self.assertEqual(confirm.status(s, [])["state"], "awaiting_reread")
        st = confirm.status(s, [con("blind_reread", grade="2+", by="B")])
        self.assertEqual((st["state"], st["level"]), ("confirmed", "readers"))
        self.assertTrue(any("Xpert" in r for r in st["recommendations"]))
        st = confirm.status(s, [con("blind_reread", grade="3+", by="B"), con("xpert", "detected", rif="not_detected", by="B")])
        self.assertEqual((st["state"], st["level"], st["rif_result"]), ("confirmed", "molecular", "not_detected"))

    def test_low_grade_needs_molecular(self):
        for g in ("scanty", "1+"):
            s = fake(g)
            st = confirm.status(s, [con("blind_reread", grade=g, by="B")])
            self.assertEqual(st["state"], "awaiting_molecular", g)
            st = confirm.status(s, [con("blind_reread", grade=g, by="B"), con("xpert", "trace")])
            self.assertEqual(st["state"], "awaiting_molecular")
            self.assertIn("repeat", st["label"].lower())
            st = confirm.status(s, [con("blind_reread", grade=g, by="B"), con("xpert", "detected")])
            self.assertEqual(st["state"], "confirmed")

    def test_fluorescence_2plus_also_needs_molecular(self):
        st = confirm.status(fake("2+", modality="fm"), [con("blind_reread", grade="2+", by="B")])
        self.assertEqual(st["state"], "awaiting_molecular")

    def test_discordance_needs_referee_and_can_overturn(self):
        s = fake("scanty")
        st = confirm.status(s, [con("blind_reread", grade="negative", by="B")])
        self.assertEqual(st["state"], "awaiting_referee")
        st = confirm.status(s, [con("blind_reread", grade="negative", by="B"), con("referee_reread", grade="negative", by="S")])
        self.assertEqual(st["state"], "overturned")
        self.assertTrue(st["error_type"].startswith("LFP") or st["error_type"].startswith("HFN") or st["error_type"].startswith("LFN"))
        st = confirm.status(s, [con("blind_reread", grade="negative", by="B"), con("referee_reread", grade="1+", by="S")])
        self.assertEqual((st["state"], st["reconciled_grade"]), ("awaiting_molecular", "1+"))

    def test_molecular_negative_investigates_and_culture_wins(self):
        s = fake("2+")
        base = [con("blind_reread", grade="2+", by="B")]
        self.assertEqual(confirm.status(s, base + [con("xpert", "not_detected")])["state"], "needs_investigation")
        self.assertEqual(confirm.status(s, base + [con("xpert", "not_detected"), con("culture", "positive")])["state"], "confirmed")
        self.assertEqual(confirm.status(s, base + [con("xpert", "detected"), con("culture", "negative")])["state"], "needs_investigation")
        self.assertEqual(confirm.status(s, base + [con("xpert", "detected"), con("culture", "contaminated")])["state"], "confirmed")

    def test_lead_acceptance_closes(self):
        s = fake("1+")
        st = confirm.status(s, [con("blind_reread", grade="1+", by="B"), con("other", "accepted", by="L")])
        self.assertEqual((st["state"], st["level"]), ("confirmed", "lead_accepted"))

    def test_reference_from(self):
        self.assertEqual(confirm.reference_from([con("xpert", "detected")]), ("pos", "Xpert MTB/RIF Ultra"))
        self.assertEqual(confirm.reference_from([con("xpert", "trace")]), (None, None))
        self.assertEqual(confirm.reference_from([con("xpert", "detected"), con("culture", "negative")]), ("neg", "Culture"))


class ConfirmationApiTests(TestCase):
    def setUp(self):
        self.c = APIClient()

    def make(self, grade="scanty", modality="zn", code="C1"):
        s = self.c.post("/api/slides", {"code": code, "microscopy": modality}, format="json", **H(TECH)).json()
        M.Slide.objects.filter(pk=s["id"]).update(status="confirmed", final_grade=grade, confirmed_by=TECH)
        return s["id"]

    def post(self, sid, who, **body):
        return self.c.post(f"/api/slides/{sid}/confirmation", body, format="json", **H(who))

    def test_open_slide_cannot_be_confirmed_yet(self):
        s = self.c.post("/api/slides", {"code": "OPEN"}, format="json").json()
        self.assertEqual(self.post(s["id"], SENIOR, method="blind_reread", grade="1+").status_code, 409)

    def test_blind_reread_rules(self):
        sid = self.make("1+")
        self.assertEqual(self.post(sid, TECH, method="blind_reread", grade="1+").status_code, 409)       # same reader
        self.assertEqual(self.post(sid, SENIOR, method="blind_reread").status_code, 400)                  # no grade
        r = self.post(sid, SENIOR, method="blind_reread", grade="1+")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["confirmation"]["state"], "awaiting_molecular")
        self.assertEqual(self.post(sid, LEAD, method="blind_reread", grade="1+").status_code, 409)       # only once
        blind = self.c.get(f"/api/slides/{sid}/blind").json()
        self.assertNotIn("final_grade", blind)
        self.assertNotIn("ai_grade", blind)

    def test_referee_must_be_senior_and_new(self):
        sid = self.make("scanty")
        self.post(sid, SENIOR, method="blind_reread", grade="negative")
        self.assertEqual(self.post(sid, SENIOR, method="referee_reread", grade="1+").status_code, 409)    # already read it
        self.assertEqual(self.post(sid, TECH, method="referee_reread", grade="1+").status_code, 403)      # not senior
        M.Reader.objects.get_or_create(name="Reader R", defaults={"role": "reader"})
        self.assertEqual(self.post(sid, "Reader R", method="referee_reread", grade="1+").status_code, 403)
        r = self.post(sid, LEAD, method="referee_reread", grade="1+")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["confirmation"]["reconciled_grade"], "1+")

    def test_xpert_sets_reference_for_ppv_npv(self):
        sid = self.make("2+")
        self.post(sid, SENIOR, method="blind_reread", grade="2+")
        r = self.post(sid, LEAD, method="xpert", result="detected", rif_result="not_detected")
        self.assertEqual(r.status_code, 200, r.content)
        s = M.Slide.objects.get(pk=sid)
        self.assertEqual((s.reference_result, s.reference_method), ("pos", "Xpert MTB/RIF Ultra"))
        self.assertEqual(r.json()["confirmation"]["state"], "confirmed")
        r = self.post(sid, LEAD, method="culture", result="negative")
        self.assertEqual(M.Slide.objects.get(pk=sid).reference_result, "neg")        # culture outranks Xpert
        self.assertEqual(self.post(sid, LEAD, method="xpert", result="maybe").status_code, 400)

    def test_xpert_on_a_negative_slide_gives_npv_reference(self):
        sid = self.make("negative", code="NEG")
        r = self.post(sid, LEAD, method="xpert", result="not_detected")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(M.Slide.objects.get(pk=sid).reference_result, "neg")
        self.assertEqual(self.post(sid, SENIOR, method="blind_reread", grade="negative").status_code, 409)

    def test_trace_does_not_set_reference(self):
        sid = self.make("1+")
        self.post(sid, LEAD, method="xpert", result="trace")
        self.assertIsNone(M.Slide.objects.get(pk=sid).reference_result)

    def test_lead_acceptance_needs_reason_and_role(self):
        sid = self.make("scanty")
        self.post(sid, SENIOR, method="blind_reread", grade="scanty")
        self.assertEqual(self.post(sid, TECH, method="other", result="accepted", notes="no cartridge").status_code, 403)
        self.assertEqual(self.post(sid, LEAD, method="other", result="accepted").status_code, 400)
        r = self.post(sid, LEAD, method="other", result="accepted", notes="No Xpert cartridge this week")
        self.assertEqual(r.json()["confirmation"]["level"], "lead_accepted")

    def test_dashboard_lists_waiting_positives(self):
        a, b = self.make("3+", code="A"), self.make("1+", code="B")
        self.post(a, SENIOR, method="blind_reread", grade="3+")
        sm = self.c.get("/api/summary").json()
        self.assertEqual(sm["awaiting_confirmation_n"], 1)
        self.assertEqual(sm["awaiting_confirmation"][0]["code"], "B")
        self.assertEqual(sm["awaiting_confirmation"][0]["state"], "awaiting_reread")
