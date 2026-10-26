"""Database models. The shape mirrors what the web interface expects."""
from django.db import models
from django.utils import timezone


class Reader(models.Model):
    ROLES = [("technician", "technician"), ("reader", "reader"), ("senior", "senior"), ("lead", "lead")]
    name = models.CharField(max_length=120, unique=True)
    role = models.CharField(max_length=20, choices=ROLES, default="technician")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.role})"


class MLModel(models.Model):
    """A trained detector. Only one is 'active' at a time; others are candidate or archived."""
    name = models.CharField(max_length=60)
    path = models.CharField(max_length=500)
    base = models.CharField(max_length=60, default="YOLOv8n")
    created_at = models.DateTimeField(default=timezone.now)
    dataset_version = models.ForeignKey("DatasetVersion", null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="models")
    run_id = models.IntegerField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="candidate")   # candidate | active | archived
    demo = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=120, blank=True, null=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    modality = models.CharField(max_length=4, default="zn")           # zn = bright-field, fm = fluorescence

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.name} [{self.status}]"


class Slide(models.Model):
    code = models.CharField(max_length=120, unique=True)
    site = models.CharField(max_length=200, blank=True, default="")
    stain = models.CharField(max_length=40, default="Ziehl-Neelsen")
    magnification = models.CharField(max_length=20, default="1000x")
    status = models.CharField(max_length=20, default="open")        # open | confirmed | synthetic
    started_at = models.DateTimeField(default=timezone.now)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    session_seconds = models.FloatField(null=True, blank=True)
    started_by = models.CharField(max_length=120, blank=True, null=True)
    model = models.ForeignKey(MLModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="slides")
    demo = models.BooleanField(default=False)
    ai_grade = models.CharField(max_length=20, blank=True, null=True)
    ai_bacilli = models.IntegerField(null=True, blank=True)
    ai_fields = models.IntegerField(null=True, blank=True)
    final_grade = models.CharField(max_length=20, blank=True, null=True)
    confirmed_by = models.CharField(max_length=120, blank=True, null=True)
    override_reason = models.TextField(blank=True, null=True)
    manual_seconds = models.FloatField(null=True, blank=True)
    reference_result = models.CharField(max_length=10, blank=True, null=True)   # pos | neg
    reference_method = models.CharField(max_length=80, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    modality = models.CharField(max_length=4, default="zn")           # zn = bright-field, fm = fluorescence
    capture_device = models.ForeignKey("CaptureDevice", null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="slides")        # the phone selected for this slide

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return self.code


class Image(models.Model):
    slide = models.ForeignKey(Slide, null=True, blank=True, on_delete=models.CASCADE, related_name="images")
    filename = models.CharField(max_length=255, blank=True, null=True)
    path = models.CharField(max_length=500)
    width = models.IntegerField(null=True)
    height = models.IntegerField(null=True)
    sha256 = models.CharField(max_length=64, db_index=True)
    blur_score = models.FloatField(null=True, blank=True)
    quality_flag = models.CharField(max_length=40, blank=True, null=True)
    status = models.CharField(max_length=20, default="unlabelled")   # unlabelled | labelled | verified | excluded
    synthetic = models.BooleanField(default=False)
    source = models.CharField(max_length=20, default="upload")       # upload | analysis | import | synthetic
    added_at = models.DateTimeField(default=timezone.now)
    added_by = models.CharField(max_length=120, blank=True, null=True)
    last_labelled_by = models.CharField(max_length=120, blank=True, null=True)
    site = models.CharField(max_length=200, blank=True, null=True)
    field_no = models.IntegerField(null=True, blank=True)
    consent = models.BooleanField(default=False)
    device = models.ForeignKey("CaptureDevice", null=True, blank=True, on_delete=models.SET_NULL, related_name="images")
    modality = models.CharField(max_length=4, default="zn")           # zn = bright-field, fm = fluorescence

    class Meta:
        ordering = ["id"]


class Annotation(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="annotations")
    label = models.CharField(max_length=20, default="afb")
    cx = models.FloatField()
    cy = models.FloatField()
    w = models.FloatField()
    h = models.FloatField()
    reader = models.CharField(max_length=120, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)


class Analysis(models.Model):
    slide = models.ForeignKey(Slide, on_delete=models.CASCADE, related_name="analyses")
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="analyses")
    model = models.ForeignKey(MLModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="analyses")
    inference_ms = models.FloatField(null=True)
    total_ms = models.FloatField(null=True)
    created_at = models.DateTimeField(default=timezone.now)


class Detection(models.Model):
    analysis = models.ForeignKey(Analysis, on_delete=models.CASCADE, related_name="detections")
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="detections")
    cx = models.FloatField()
    cy = models.FloatField()
    w = models.FloatField()
    h = models.FloatField()
    conf = models.FloatField()
    status = models.CharField(max_length=20, default="pending")      # pending | kept | removed | added


class ReviewItem(models.Model):
    detection = models.ForeignKey(Detection, null=True, blank=True, on_delete=models.SET_NULL, related_name="review_items")
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="review_items")
    cx = models.FloatField()
    cy = models.FloatField()
    w = models.FloatField()
    h = models.FloatField()
    conf = models.FloatField()
    status = models.CharField(max_length=20, default="open")          # open | disputed | resolved
    resolution = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    disputed_after = models.IntegerField(null=True, blank=True)       # id of the vote that caused the dispute


class ReviewVote(models.Model):
    item = models.ForeignKey(ReviewItem, on_delete=models.CASCADE, related_name="votes")
    reader = models.CharField(max_length=120)
    vote = models.CharField(max_length=20)                            # afb | not_afb | unsure
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "reader"], name="one_vote_per_reader")]


class DatasetVersion(models.Model):
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now)
    seed = models.IntegerField(default=42)
    path = models.CharField(max_length=500, blank=True, default="")
    n_train = models.IntegerField(default=0)
    n_val = models.IntegerField(default=0)
    n_test = models.IntegerField(default=0)
    includes_synthetic = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    created_by = models.CharField(max_length=120, blank=True, null=True)
    modality = models.CharField(max_length=4, default="zn")

    class Meta:
        ordering = ["-id"]


class DatasetImage(models.Model):
    version = models.ForeignKey(DatasetVersion, on_delete=models.CASCADE, related_name="members")
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="dataset_members")
    split = models.CharField(max_length=10)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "image"], name="image_once_per_version")]


class TrainingRun(models.Model):
    dataset_version = models.ForeignKey(DatasetVersion, on_delete=models.CASCADE, related_name="runs")
    params = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="queued")        # queued | running | completed | failed | cancelled
    epoch = models.IntegerField(default=0)
    epochs = models.IntegerField(default=0)
    message = models.TextField(blank=True, null=True)
    pid = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    model_id = models.IntegerField(null=True, blank=True)
    history = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True, null=True)
    started_by = models.CharField(max_length=120, blank=True, null=True)

    class Meta:
        ordering = ["-id"]


class AuditLog(models.Model):
    ts = models.DateTimeField(default=timezone.now)
    reader = models.CharField(max_length=120, default="unknown")
    action = models.CharField(max_length=60)
    detail = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-id"]


# ------------------------------------------------------------------ phones used as cameras
class CaptureDevice(models.Model):
    """A phone or tablet paired with the app. It authenticates with a private token, never the PIN."""
    name = models.CharField(max_length=80)
    model_label = models.CharField(max_length=120, blank=True, default="")      # e.g. "Samsung SM-A135F"
    platform = models.CharField(max_length=60, blank=True, default="")          # e.g. "Android 13"
    browser = models.CharField(max_length=60, blank=True, default="")
    token_hash = models.CharField(max_length=64, unique=True)
    paired_by = models.CharField(max_length=120, blank=True, default="")
    paired_at = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_ip = models.CharField(max_length=60, blank=True, default="")
    revoked = models.BooleanField(default=False)
    upload_count = models.IntegerField(default=0)
    fail_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.model_label})"


class PairingCode(models.Model):
    """Six-digit, single-use, short-lived code shown on the computer to pair a phone."""
    code = models.CharField(max_length=6, db_index=True)
    created_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    device = models.ForeignKey(CaptureDevice, null=True, blank=True, on_delete=models.SET_NULL)


class CaptureEvent(models.Model):
    """Audit trail of phone activity, used for monitoring after deployment."""
    device = models.ForeignKey(CaptureDevice, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    kind = models.CharField(max_length=30)      # pair | pair_fail | upload_ok | upload_fail | select | revoke
    detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-id"]


class Feedback(models.Model):
    """Usability feedback from the phone page or the computer (used for user testing)."""
    device = models.ForeignKey(CaptureDevice, null=True, blank=True, on_delete=models.SET_NULL)
    reader = models.CharField(max_length=120, blank=True, default="")
    source = models.CharField(max_length=10, default="desktop")                 # phone | desktop
    rating = models.IntegerField()                                              # 1 to 5
    comment = models.TextField(blank=True, default="")
    context = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-id"]


class AppSetting(models.Model):
    """Editable cut-offs and targets (key -> JSON value)."""
    key = models.CharField(max_length=60, unique=True)
    value = models.JSONField(default=dict)


class SlideConfirmation(models.Model):
    """One step in confirming a positive slide (second reading, re-stain, molecular test, culture)."""
    METHODS = ["blind_reread", "referee_reread", "zn_restain", "xpert", "culture", "other"]
    slide = models.ForeignKey(Slide, on_delete=models.CASCADE, related_name="confirmations")
    method = models.CharField(max_length=20)
    result = models.CharField(max_length=40, blank=True, default="")            # detected | trace | not_detected | positive | ...
    rif_result = models.CharField(max_length=20, blank=True, default="")        # xpert only: detected | not_detected | indeterminate
    grade = models.CharField(max_length=20, blank=True, null=True)
    by = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    concordance = models.CharField(max_length=20, blank=True, null=True)        # concordant | minor | discordant
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
