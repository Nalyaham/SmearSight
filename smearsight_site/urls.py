from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from core import views, views_ml, views_v2

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
    path("phone", views_v2.phone_page),
    path("healthz", views_v2.healthz),
    path("api/phone/pair", views_v2.phone_pair),
    path("api/phone/status", views_v2.phone_status),
    path("api/phone/upload", views_v2.phone_upload),
    path("api/phone/feedback", views_v2.phone_feedback),
    path("api/phone/forget", views_v2.phone_forget),
    path("api/devices", views_v2.devices_list),
    path("api/devices/pairing", views_v2.devices_pairing),
    path("api/devices/<int:pk>", views_v2.device_detail),
    path("api/capture/events", views_v2.capture_events),
    path("api/slides/<int:pk>/capture-device", views_v2.slide_capture_device),
    path("api/slides/<int:pk>/capture-status", views_v2.slide_capture_status),
    path("api/slides/<int:pk>/confirmation", views_v2.slide_confirmation),
    path("api/slides/<int:pk>/blind", views_v2.slide_blind),
    path("api/feedback", views_v2.feedback),
    path("api/health", views_v2.health),
    path("api/grade-preview", views_v2.grade_preview),
    path("api/settings", views_v2.app_settings),
    path("api/", include(router.urls)),
    path("", views.index_view),
]
