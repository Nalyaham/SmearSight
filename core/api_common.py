"""Small helpers shared by the API views."""
from datetime import datetime

from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler

from .models import AuditLog, Reader
from .services.config import CONF_POSITIVE


class ApiError(APIException):
    """An error with a plain-language message and a chosen HTTP status."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status_code = status


def fail(message, status=400):
    raise ApiError(message, status)


def reader_name(request):
    return request.headers.get("X-Reader", "").strip() or "Lab technician"


def reader_role(name):
    r = Reader.objects.filter(name=name).first()
    return r.role if r else "technician"


def audit(reader, action, detail=""):
    AuditLog.objects.create(reader=reader or "unknown", action=action, detail=str(detail))


def counted(det):
    """Does this detection count as a bacillus in the grade?"""
    return det.status in ("kept", "added") or (det.status == "pending" and det.conf >= CONF_POSITIVE)


class LegacyModelSerializer(serializers.ModelSerializer):
    """Writes every column of the row, with datetimes as epoch seconds and foreign keys as
    `<name>_id`. This is the JSON shape the web interface was built against."""

    def to_representation(self, inst):
        out = {}
        for f in inst._meta.concrete_fields:
            v = getattr(inst, f.attname)
            out[f.attname] = v.timestamp() if isinstance(v, datetime) else v
        out.update(self.extra(inst))
        return out

    def extra(self, inst):
        return {}


_GENERIC = ("This field", "A valid", "Not a valid", "Ensure", "\"")


def _flatten(data, prefix=""):
    msgs = []
    if isinstance(data, dict):
        for k, v in data.items():
            msgs += _flatten(v, k if not prefix else f"{prefix}.{k}")
    elif isinstance(data, (list, tuple)):
        for v in data:
            msgs += _flatten(v, prefix)
    else:
        s = str(data)
        msgs.append(f"{prefix}: {s}" if prefix and s.startswith(_GENERIC) else s)
    return msgs


def api_exception_handler(exc, context):
    """Always answer with {"detail": "<one readable sentence>"} so the interface can show it."""
    resp = drf_exception_handler(exc, context)
    if resp is not None and isinstance(resp.data, (dict, list)) and not (isinstance(resp.data, dict) and set(resp.data) == {"detail"}):
        resp.data = {"detail": " ".join(_flatten(resp.data))}
    return resp
