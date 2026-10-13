#!/usr/bin/env bash
# One-time install for Mac / Linux, then starts the app.   Usage: ./install.sh
set -e
cd "$(dirname "$0")"
PY=""
for c in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer was not found. Install Python 3.12 from https://www.python.org/downloads/ and run ./install.sh again."
  exit 1
fi
echo "Using $($PY --version)"
[ -d .venv ] || "$PY" -m venv .venv || { echo "Could not create the environment. On Ubuntu/Debian: sudo apt install python3-venv"; exit 1; }
.venv/bin/python -m pip install --upgrade pip --quiet --disable-pip-version-check
echo "Installing packages (big download, 5 to 20 minutes)..."
for i in 1 2 3; do
  .venv/bin/python -m pip install --prefer-binary --default-timeout=120 --log install_log.txt -r requirements.txt && break
  [ "$i" = 3 ] && { echo "Install failed. See install_log.txt. Check internet / disk space (3 GB) or try Python 3.12."; exit 1; }
  echo "Retrying..."
done
echo "Installed. Next time run ./start.sh"
exec .venv/bin/python run.py "$@"
