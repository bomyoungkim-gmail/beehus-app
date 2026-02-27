#!/bin/bash
set -e

mkdir -p /app/artifacts

# Fail fast when worker image is stale and missing processing deps.
python - <<'PY'
import importlib.util
import sys

required = ("pandas", "openpyxl", "xlrd")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(
        "Missing runtime dependencies in worker image: "
        + ", ".join(missing)
        + ". Rebuild celery-worker image and redeploy.",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY

# Start Xvfb
echo "Starting Xvfb on :99..."
export DISPLAY=:99
export XAUTHORITY=/tmp/.Xauthority
# Create an X11 auth cookie so x11vnc can attach reliably.
touch "${XAUTHORITY}"
if command -v mcookie >/dev/null 2>&1; then
  xauth -f "${XAUTHORITY}" add "${DISPLAY}" . "$(mcookie)"
fi
Xvfb :99 -screen 0 1920x1080x24 -ac -auth "${XAUTHORITY}" > /app/artifacts/xvfb.log 2>&1 &

echo "Waiting for Xvfb..."
# Wait for the X socket so VNC binds to the correct display.
for i in {1..20}; do
  if [ -S /tmp/.X11-unix/X99 ]; then
    break
  fi
  sleep 0.5
done
if ! pgrep -x Xvfb >/dev/null; then
  echo "Xvfb failed to start; check /app/artifacts/xvfb.log"
  exit 1
fi

# Start Fluxbox
echo "Starting Fluxbox..."
fluxbox > /app/artifacts/fluxbox.log 2>&1 &

# Start x11vnc
echo "Starting x11vnc on port 5900..."
# Bind to the existing Xvfb display and log output for debugging.
x11vnc -display :99 -forever -shared -rfbport 5900 -nopw -noxdamage -auth "${XAUTHORITY}" -o /app/artifacts/x11vnc.log &

echo "Waiting for x11vnc to listen on 5900..."
for i in {1..40}; do
  if pgrep -x x11vnc >/dev/null 2>&1; then
    echo "PORT=5900"
    break
  fi
  sleep 0.5
done
if ! pgrep -x x11vnc >/dev/null 2>&1; then
  echo "x11vnc failed to start; check /app/artifacts/x11vnc.log"
  cat /app/artifacts/x11vnc.log || true
  exit 1
fi

# Start websockify (NoVNC)
echo "Starting NoVNC on port 6901..."
# Link default index.html to vnc.html for automatic redirect
ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html 2>/dev/null || true
websockify --web /usr/share/novnc 6901 localhost:5900 &

# Start Celery Worker
echo "Starting Celery Worker..."
celery -A core.celery_app worker --loglevel=info --concurrency=1
