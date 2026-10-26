"""Putting a photographed field onto a slide and running the model on it.
Used by both the computer's upload buttons and by paired phones."""
from django.db import transaction
from django.db.models import Max

from ..models import Analysis, Detection, Image, ReviewItem
from . import imaging, inference
from . import settings_store


def create_analysis(slide, image, path, model):
    review = settings_store.thresholds(slide.modality)["review"]
    res = inference.detect(path, model)
    if res is None:
        return None
    dets, inf_ms, tot_ms = res
    with transaction.atomic():
        an = Analysis.objects.create(slide=slide, image=image, model=model, inference_ms=inf_ms, total_ms=tot_ms)
        for d in dets:
            det = Detection.objects.create(analysis=an, image=image, status="pending", **d)
            if d["conf"] < review:
                ReviewItem.objects.create(detection=det, image=image, cx=d["cx"], cy=d["cy"], w=d["w"], h=d["h"],
                                          conf=d["conf"], status="open")
    return an.id


def add_field_images(slide, items, reader, device=None):
    """items: list of (filename, bytes). Returns (results, model_missing).
    Each result: {file, image_id?, field_no?, quality_flag?, n_detected?, error?}."""
    model = inference.active_model(slide.modality)
    positive = settings_store.thresholds(slide.modality)["positive"]
    results = []
    for name, data in items:
        try:
            info = imaging.save_image(data, slide.modality)
        except imaging.BadImage as e:
            results.append({"file": name, "error": str(e)})
            continue
        if Image.objects.filter(slide=slide, sha256=info["sha256"]).exists():
            results.append({"file": name, "error": "Already added to this slide."})
            continue
        fno = (Image.objects.filter(slide=slide).aggregate(m=Max("field_no"))["m"] or 0) + 1
        im = Image.objects.create(
            slide=slide, filename=name, path=info["path"], width=info["width"], height=info["height"],
            sha256=info["sha256"], blur_score=info["blur_score"], quality_flag=info["quality_flag"],
            status="unlabelled", source="analysis", added_by=reader, site=slide.site, field_no=fno, device=device,
            modality=slide.modality)
        r = {"file": name, "image_id": im.id, "field_no": fno, "quality_flag": info["quality_flag"]}
        if model:
            try:
                create_analysis(slide, im, info["path"], model)
                r["n_detected"] = Detection.objects.filter(image=im, conf__gte=positive).count()
            except Exception as e:
                r["error"] = f"Model failed on this image: {e}"
        results.append(r)
    if model and not slide.model_id:
        slide.model, slide.demo = model, model.demo
        slide.save(update_fields=["model", "demo"])
    return results, model is None
