"""Optional access PIN. If SMEARSIGHT_PIN is set, every page and API call needs it."""
import hashlib

from django.http import JsonResponse
from django.shortcuts import redirect

from .services.config import pin


def token():
    return hashlib.sha256(("smearsight:" + pin()).encode()).hexdigest()[:32]


class PinGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if pin() and request.path != "/login" and not request.path.startswith("/static/"):
            if request.COOKIES.get("ss_auth") != token():
                if request.path.startswith("/api"):
                    return JsonResponse({"detail": "PIN required"}, status=401)
                return redirect("/login")
        return self.get_response(request)
