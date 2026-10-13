from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from core import views, views_ml

router = SimpleRouter(trailing_slash=False)
router.register("slides", views.SlideViewSet, basename="slide")
router.register("detections", views.DetectionViewSet, basename="detection")
router.register("images", views.ImageViewSet, basename="image")
router.register("review", views.ReviewViewSet, basename="review")
router.register("datasets", views_ml.DatasetViewSet, basename="dataset")
router.register("training", views_ml.TrainingViewSet, basename="training")
router.register("models", views_ml.ModelViewSet, basename="model")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login", views.login_view),
    path("api/state", views.state),
    path("api/readers", views.add_reader),
    path("api/dataset/stats", views.dataset_stats),
    path("api/synthetic", views.make_synthetic),
    path("api/import/yolo", views.import_yolo),
    path("api/performance", views_ml.performance),
    path("api/summary", views_ml.summary),
    path("api/export/slides.csv", views_ml.export_slides),
    path("api/audit", views_ml.audit_log),
    path("api/backup.zip", views_ml.backup),
    path("api/", include(router.urls)),
    path("", views.index_view),
]
