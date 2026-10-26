"""DRF serializers: model output (legacy JSON shape) and validated input."""
from rest_framework import serializers

from . import models
from .services.grading import GRADES


# ------------------------------------------------------------------ output
from .api_common import LegacyModelSerializer


class ReaderSerializer(LegacyModelSerializer):
    class Meta:
        model = models.Reader
        fields = "__all__"


class SlideSerializer(LegacyModelSerializer):
    class Meta:
        model = models.Slide
        fields = "__all__"

    def extra(self, inst):
        n = getattr(inst, "n_fields", None)
        return {"n_fields": n} if n is not None else {}


class ImageSerializer(LegacyModelSerializer):
    class Meta:
        model = models.Image
        fields = "__all__"

    def extra(self, inst):
        n = getattr(inst, "n_boxes", None)
        return {"n_boxes": n} if n is not None else {}


class AnnotationSerializer(LegacyModelSerializer):
    class Meta:
        model = models.Annotation
        fields = "__all__"


class AnalysisSerializer(LegacyModelSerializer):
    class Meta:
        model = models.Analysis
        fields = "__all__"


class DetectionSerializer(LegacyModelSerializer):
    class Meta:
        model = models.Detection
        fields = "__all__"


class ReviewItemSerializer(LegacyModelSerializer):
    class Meta:
        model = models.ReviewItem
        fields = "__all__"


class DatasetVersionSerializer(LegacyModelSerializer):
    class Meta:
        model = models.DatasetVersion
        fields = "__all__"


class TrainingRunSerializer(LegacyModelSerializer):
    class Meta:
        model = models.TrainingRun
        fields = "__all__"


class MLModelSerializer(LegacyModelSerializer):
    class Meta:
        model = models.MLModel
        fields = "__all__"


class AuditSerializer(LegacyModelSerializer):
    class Meta:
        model = models.AuditLog
        fields = "__all__"


# ------------------------------------------------------------------ input
class ReaderIn(serializers.Serializer):
    name = serializers.CharField(max_length=120, error_messages={"blank": "Name is required.", "required": "Name is required."})
    role = serializers.ChoiceField(choices=["technician", "reader", "senior", "lead"], default="technician",
                                   error_messages={"invalid_choice": "Role must be technician, reader, senior or lead."})


class SlideIn(serializers.Serializer):
    _msg = "Slide ID is required (use an anonymous lab code, never a patient name)."
    code = serializers.CharField(max_length=120, error_messages={"blank": _msg, "required": _msg})
    site = serializers.CharField(max_length=200, allow_blank=True, default="")
    stain = serializers.CharField(max_length=40, default="Ziehl-Neelsen")
    magnification = serializers.CharField(max_length=20, default="1000x")
    microscopy = serializers.ChoiceField(choices=["zn", "fm", ""], default="", required=False,
                                         error_messages={"invalid_choice": "Microscopy must be zn or fm."})
    device_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class ConfirmIn(serializers.Serializer):
    final_grade = serializers.ChoiceField(
        choices=GRADES, error_messages={"invalid_choice": "Grade must be one of: " + ", ".join(GRADES) + "."})
    override_reason = serializers.CharField(allow_blank=True, default="")
    manual_seconds = serializers.FloatField(required=False, allow_null=True, default=None, min_value=0)
    add_to_dataset = serializers.BooleanField(default=False)
    consent_confirmed = serializers.BooleanField(default=False)


class ReferenceIn(serializers.Serializer):
    reference_result = serializers.ChoiceField(choices=["pos", "neg", ""], allow_null=True, required=False, default=None,
                                               error_messages={"invalid_choice": "Reference result must be pos or neg."})
    reference_method = serializers.CharField(allow_blank=True, default="")


class DetectionIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=["pending", "kept", "removed"], error_messages={"invalid_choice": "Bad status."})


class BoxIn(serializers.Serializer):
    cx = serializers.FloatField()
    cy = serializers.FloatField()
    w = serializers.FloatField()
    h = serializers.FloatField()


class AnnotationsIn(serializers.Serializer):
    boxes = BoxIn(many=True, required=False, default=list)
    negative = serializers.BooleanField(default=False)


class SyntheticIn(serializers.Serializer):
    count = serializers.IntegerField(default=80)
    seed = serializers.IntegerField(default=1)
    modality = serializers.ChoiceField(choices=["zn", "fm"], default="zn")


class VoteIn(serializers.Serializer):
    vote = serializers.ChoiceField(choices=["afb", "not_afb", "unsure"],
                                   error_messages={"invalid_choice": "Vote must be afb, not_afb or unsure."})


class FreezeIn(serializers.Serializer):
    name = serializers.CharField(allow_blank=True, default="")
    seed = serializers.IntegerField(default=42)
    include_single_read = serializers.BooleanField(default=False)
    include_synthetic = serializers.BooleanField(default=True)
    modality = serializers.ChoiceField(choices=["zn", "fm"], default="zn")


class TrainIn(serializers.Serializer):
    dataset_version_id = serializers.IntegerField()
    epochs = serializers.IntegerField(default=30)
    imgsz = serializers.IntegerField(default=512)
    batch = serializers.IntegerField(default=8)
    base = serializers.ChoiceField(choices=["auto", "scratch"], default="auto")


class ConfirmationSerializer(LegacyModelSerializer):
    class Meta:
        model = models.SlideConfirmation
        fields = "__all__"


class PromoteIn(serializers.Serializer):
    approved_by = serializers.CharField()


# ------------------------------------------------------------------ v2: phones, feedback, confirmation, settings
def device_brief(d, online_seconds=90):
    """What the computer shows about a phone. The private token hash is never sent anywhere."""
    from django.utils import timezone as tz
    if d is None:
        return None
    seen = d.last_seen.timestamp() if d.last_seen else None
    return {"id": d.id, "name": d.name, "model_label": d.model_label, "platform": d.platform, "browser": d.browser,
            "paired_by": d.paired_by, "paired_at": d.paired_at.timestamp(), "last_seen": seen,
            "online": bool(d.last_seen and (tz.now() - d.last_seen).total_seconds() < online_seconds),
            "revoked": d.revoked, "upload_count": d.upload_count, "fail_count": d.fail_count,
            "last_error": d.last_error}


class RenameIn(serializers.Serializer):
    name = serializers.CharField(max_length=80, error_messages={"blank": "Give the phone a name.", "required": "Give the phone a name."})


class SelectDeviceIn(serializers.Serializer):
    device_id = serializers.IntegerField(allow_null=True)


class PairIn(serializers.Serializer):
    code = serializers.CharField(max_length=12, error_messages={"blank": "Enter the 6-digit code shown on the computer.",
                                                                 "required": "Enter the 6-digit code shown on the computer."})
    name = serializers.CharField(max_length=80, allow_blank=True, default="")


class FeedbackIn(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5,
                                      error_messages={"min_value": "Rating is 1 to 5.", "max_value": "Rating is 1 to 5.",
                                                      "required": "Choose a rating from 1 to 5.", "invalid": "Rating is 1 to 5."})
    comment = serializers.CharField(max_length=1000, allow_blank=True, default="")
    context = serializers.CharField(max_length=120, allow_blank=True, default="")


class ConfirmationIn(serializers.Serializer):
    method = serializers.ChoiceField(choices=["blind_reread", "referee_reread", "zn_restain", "xpert", "culture", "other"],
                                     error_messages={"invalid_choice": "Unknown confirmation step."})
    result = serializers.CharField(max_length=40, allow_blank=True, default="")
    grade = serializers.ChoiceField(choices=GRADES, required=False, allow_null=True, default=None,
                                    error_messages={"invalid_choice": "Grade must be one of: " + ", ".join(GRADES) + "."})
    rif_result = serializers.ChoiceField(choices=["detected", "not_detected", "indeterminate", ""], default="", required=False)
    notes = serializers.CharField(max_length=1000, allow_blank=True, default="")


class SettingsIn(serializers.Serializer):
    modality = serializers.ChoiceField(choices=["zn", "fm"], default="zn")
    positive = serializers.FloatField(required=False, min_value=0.05, max_value=0.95)
    review = serializers.FloatField(required=False, min_value=0.05, max_value=1.0)
    targets = serializers.DictField(child=serializers.FloatField(allow_null=True), required=False)
    prevalence = serializers.FloatField(required=False)
    approved_by = serializers.CharField(error_messages={"required": "Say who is making this change.", "blank": "Say who is making this change."})


class CutoffIn(serializers.Serializer):
    cutoff = serializers.FloatField(min_value=0.05, max_value=0.95)
    approved_by = serializers.CharField(error_messages={"required": "Say who is making this change.", "blank": "Say who is making this change."})
