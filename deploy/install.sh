#!/usr/bin/env bash
# PP-TH- server install / upgrade (Ubuntu/Debian/CentOS-like)
# - Public Web on 0.0.0.0:8080
# - Users fill their own proxy in the Web UI (no server-side residential pool)
# - Does NOT store secrets in git
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pp-th}"
APP_USER="${APP_USER:-root}"
REPO_URL="${REPO_URL:-https://github.com/suixin00001111/PP-TH-.git}"
BRANCH="${BRANCH:-main}"
HOST_BIND="${HOST_BIND:-0.0.0.0}"
PORT="${PORT:-8080}"
SERVICE_NAME="${SERVICE_NAME:-pp-th}"

echo "[1/7] Detect package manager / Python"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git curl ca-certificates
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip git curl ca-certificates
elif command -v yum >/dev/null 2>&1; then
  yum install -y python3 python3-pip git curl ca-certificates
else
  echo "Unsupported package manager; install python3/git/curl manually." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found" >&2
  exit 1
fi

echo "[2/7] Fetch repo into ${APP_DIR}"
mkdir -p "$(dirname "${APP_DIR}")"
if [[ -d "${APP_DIR}/.git" ]]; then
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}" || git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
else
  rm -rf "${APP_DIR}"
  git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${APP_DIR}"
fi
cd "${APP_DIR}"

echo "[3/7] Python venv + deps"
python3 -m venv "${APP_DIR}/.venv"
# shellcheck disable=SC1091
source "${APP_DIR}/.venv/bin/activate"
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt

echo "[4/7] .env (no secrets; users fill proxy in UI)"
if [[ ! -f "${APP_DIR}/.env" ]]; then
  if [[ -f "${APP_DIR}/.env.example" ]]; then
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  else
    touch "${APP_DIR}/.env"
  fi
fi
# Force server-safe pure-protocol defaults (do not embed any proxy credentials).
APP_DIR="${APP_DIR}" python - <<'PY'
import os
from pathlib import Path
p = Path(os.environ["APP_DIR"]) / ".env"
text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
keys = {
    "PAYPAL_RUNTIME_MODE": "protocol",
    "PAYPAL_FINGERPRINT_SOURCE": "random",
    "PAYPAL_DATADOME_MODE": "protocol",
    "PAYPAL_MTR_RUNTIME": "python_generated",
    "PAYPAL_PROXY_ENABLED": "0",
    "PAYPAL_USE_SYSTEM_PROXY": "0",
    "PAYPAL_CONTINUE_MERCHANT": "0",
    "PAYPAL_WEB_PRODUCTION": "1",
    "PAYPAL_WEB_ALLOW_DEBUG_LOGS": "0",
}
lines, seen = [], set()
for raw in text.splitlines():
    if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
        lines.append(raw)
        continue
    k = raw.split("=", 1)[0].strip()
    if k in keys:
        lines.append(f"{k}={keys[k]}")
        seen.add(k)
    else:
        lines.append(raw)
for k, v in keys.items():
    if k not in seen:
        lines.append(f"{k}={v}")
out = []
for raw in lines:
    s = raw.strip()
    if s.startswith("PAYPAL_PROXY_URL=") or s.startswith("PAYPAL_PROXY_POOL="):
        out.append("# " + raw + "  # cleared: users fill proxy in Web UI")
    else:
        out.append(raw)
p.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print(f"wrote {p}")
PY

echo "[5/7] Stop old process on :${PORT} (if any)"
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
fi
# also kill any leftover web.py
pkill -f "python.*web.py" 2>/dev/null || true
sleep 1

echo "[6/7] systemd unit ${SERVICE_NAME}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=PP-TH- PayPal multi-country BA Web UI
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=HOST=${HOST_BIND}
Environment=PORT=${PORT}
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/web.py --host ${HOST_BIND} --port ${PORT}
Restart=always
RestartSec=3
# Users supply proxy per job in Web UI — no shared proxy env required.

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
sleep 2
systemctl --no-pager --full status "${SERVICE_NAME}" || true

echo "[7/7] Firewall (best-effort open ${PORT})"
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${PORT}/tcp" || true
elif command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port="${PORT}/tcp" || true
  firewall-cmd --reload || true
fi

echo
echo "=== Health check ==="
curl -fsS "http://127.0.0.1:${PORT}/api/health" || curl -fsS "http://127.0.0.1:${PORT}/api/health" || true
echo
IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo YOUR_IP)"
echo
echo "Deploy OK."
echo "  Open:  http://${IP}:${PORT}/"
echo "  Users fill BA / phone / country / their own proxy in the Web form."
echo "  Upgrade later: bash ${APP_DIR}/deploy/install.sh"
echo
