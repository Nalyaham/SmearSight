"""Optional access PIN. If SMEARSIGHT_PIN is set, every page and API call needs it."""
import hashlib

from django.http import JsonResponse
from django.shortcuts import redirect

from .services.config import pin


def token():
    return hashlib.sha256(("smearsight:" + pin()).encode()).hexdigest()[:32]


# Paired phones do not know the PIN. They may reach ONLY the phone page and the phone API, where every
# call except pairing needs the phone's private token (and pairing needs a one-time code).
PHONE_OPEN = ("/phone", "/healthz")


def phone_path(path):
    return path in PHONE_OPEN or path.startswith("/api/phone/")


class PinGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if pin() and request.path != "/login" and not request.path.startswith("/static/") \
                and not phone_path(request.path):
            if request.COOKIES.get("ss_auth") != token():
                if request.path.startswith("/api"):
                    return JsonResponse({"detail": "PIN required"}, status=401)
                return redirect("/login")
        return self.get_response(request)
