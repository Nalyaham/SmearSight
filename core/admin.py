from django.contrib import admin

from . import models

for m in (models.Reader, models.MLModel, models.Slide, models.Image, models.Annotation, models.Analysis,
          models.Detection, models.ReviewItem, models.ReviewVote, models.DatasetVersion, models.TrainingRun,
          models.AuditLog):
    admin.site.register(m)
