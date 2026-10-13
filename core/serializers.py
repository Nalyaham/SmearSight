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


class VoteIn(serializers.Serializer):
    vote = serializers.ChoiceField(choices=["afb", "not_afb", "unsure"],
                                   error_messages={"invalid_choice": "Vote must be afb, not_afb or unsure."})


class FreezeIn(serializers.Serializer):
    name = serializers.CharField(allow_blank=True, default="")
    seed = serializers.IntegerField(default=42)
    include_single_read = serializers.BooleanField(default=False)
    include_synthetic = serializers.BooleanField(default=True)


class TrainIn(serializers.Serializer):
    dataset_version_id = serializers.IntegerField()
    epochs = serializers.IntegerField(default=30)
    imgsz = serializers.IntegerField(default=512)
    batch = serializers.IntegerField(default=8)
    base = serializers.ChoiceField(choices=["auto", "scratch"], default="auto")


class PromoteIn(serializers.Serializer):
    approved_by = serializers.CharField()
