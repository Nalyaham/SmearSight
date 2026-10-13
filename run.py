"""Start SmearSight.
    python run.py                 this computer only
    python run.py --lan --pin 1234   also reachable from phones on the same Wi-Fi (set a PIN)
"""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--lan", action="store_true", help="listen on all network interfaces (phones can connect)")
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--pin", default="", help="access PIN (or set SMEARSIGHT_PIN)")
ap.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
a = ap.parse_args()
if a.pin:
    os.environ["SMEARSIGHT_PIN"] = a.pin
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smearsight_site.settings")

try:
    import django
    from django.core.management import call_command
    from waitress import serve
except ImportError as e:
    sys.exit(f"\nA required package is missing ({e.name}). Run the installer first (install_windows.bat, or ./install.sh).\n")

django.setup()
call_command("migrate", interactive=False, verbosity=0)          # creates / updates the database
from smearsight_site.wsgi import application  # noqa: E402

host = "0.0.0.0" if a.lan else "127.0.0.1"
url = f"http://localhost:{a.port}"
print("\n  SmearSight is running.  Leave this window open while you use it (Ctrl+C stops it).")
print(f"  On this computer:  {url}")
if a.lan:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]; s.close()
        print(f"  On phones (same Wi-Fi):  http://{ip}:{a.port}")
    except Exception:
        print(f"  Find this computer's Wi-Fi address and open http://<address>:{a.port} on the phone.")
    if not os.environ.get("SMEARSIGHT_PIN"):
        print("\n  WARNING: no access PIN is set. Anyone on this network can open the app.")
        print("  Restart with:  python run.py --lan --pin 1234\n")
print()
if not a.no_browser:
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()
try:
    serve(application, host=host, port=a.port, threads=8, channel_timeout=600)
except OSError as e:
    sys.exit(f"\nCould not start on port {a.port} ({e}). Another program may be using it. Try:  python run.py --port {a.port + 10}\n")
