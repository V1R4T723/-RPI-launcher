#!/usr/bin/env bash
# RPI LAUNCHER — self-contained, idempotent installer for the Raspberry Pi 5.
#
# Run from the project folder (or a USB flash drive):
#     bash install_rpi.sh
set -euo pipefail

APP_NAME="RPI LAUNCHER"
INSTALL_DIR="$HOME/rpi-launcher"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> ${APP_NAME} installer"

# 1. Copy the project into ~/rpi-launcher (idempotent, excludes venv/.git).
echo "==> Copying project into ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
if [ "${SOURCE_DIR}" != "${INSTALL_DIR}" ]; then
    tar --exclude='./venv' --exclude='./.git' --exclude='__pycache__' \
        -cf - -C "${SOURCE_DIR}" . | tar -xf - -C "${INSTALL_DIR}"
fi

# 2. System dependencies (Mesa Vulkan, Java 21, PyQt6, venv support).
echo "==> Installing system packages (sudo will prompt for your password)"
sudo apt-get update
sudo apt-get install -y python3-pyqt6 python3-venv openjdk-21-jre mesa-vulkan-drivers vulkan-tools

# 3. Python virtual environment (reuses system PyQt6 via --system-site-packages).
echo "==> Creating Python venv"
cd "${INSTALL_DIR}"
if [ ! -d "venv" ]; then
    python3 -m venv --system-site-packages venv
fi

# 4. Python dependencies.
echo "==> Installing Python dependencies"
"${INSTALL_DIR}/venv/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/venv/bin/python" -m pip install --upgrade minecraft-launcher-lib requests

# 5. Desktop shortcuts (same code path as the in-app button).
echo "==> Generating desktop shortcuts"
"${INSTALL_DIR}/venv/bin/python" - <<'PY'
import os
import sys

sys.path.insert(0, os.path.expanduser("~/rpi-launcher"))
from core.desktop_shortcut import create_desktop_shortcuts

create_desktop_shortcuts(os.path.expanduser("~/rpi-launcher"))
PY

echo "==> Done. ${APP_NAME} is installed in ${INSTALL_DIR}"
echo "    Launch it from your desktop menu or run:"
echo "    ${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py"
