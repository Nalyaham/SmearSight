"""Network helpers for pairing phones: this computer's Wi-Fi address and phone user-agent parsing."""
import os
import re
import socket


def lan_ip():
    """The address a phone on the same Wi-Fi would use to reach this computer."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))        # nothing is sent; this just picks the right network card
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return None


def lan_enabled():
    return os.environ.get("SMEARSIGHT_LAN", "") == "1"


def server_port(default=8000):
    try:
        return int(os.environ.get("SMEARSIGHT_PORT", default))
    except ValueError:
        return default


def parse_user_agent(ua: str):
    """Best-effort (platform, browser, suggested_name) from a phone's user-agent string.
    Browsers hide the exact model on purpose (iPhones never say; recent Android Chrome sends "K"),
    so the technician names the phone and this is only a starting suggestion."""
    ua = ua or ""
    platform, model = "", ""
    m = re.search(r"(iPhone|iPad|iPod).*?OS (\d+)[_.]", ua)
    if m:
        platform = f"iOS {m.group(2)}"
        model = m.group(1)
    else:
        m = re.search(r"Android (\d+)", ua)
        if m:
            platform = f"Android {m.group(1)}"
            # the platform group is everything up to ") AppleWebKit"; model names can contain brackets ("Moto G (4)")
            mm = re.search(r"Android [\d.]+; (.+?)\)\s+AppleWebKit", ua) or re.search(r"Android [\d.]+; ([^;)]+)\)", ua)
            if mm:
                cand = re.sub(r"\s*Build/\S+.*$", "", mm.group(1)).replace("; wv", "").strip()
                if cand and cand not in ("K", "wv", "Mobile") and ";" not in cand:
                    model = cand
    browser = ""
    for key, label in (("SamsungBrowser", "Samsung Internet"), ("EdgA", "Edge"), ("EdgiOS", "Edge"), ("OPR", "Opera"),
                       ("Firefox", "Firefox"), ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome", "Chrome"),
                       ("Safari", "Safari")):
        if key in ua:
            browser = label
            break
    suggested = model or (f"{platform.split()[0]} phone" if platform else "Phone")
    return platform, browser, suggested
