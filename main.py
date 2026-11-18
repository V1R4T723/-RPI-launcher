#!/usr/bin/env python3
"""RPI LAUNCHER — lightweight Minecraft launcher for the Raspberry Pi 5.

This entry point is deliberately thin. It runs the dependency bootstrap
*before* any third-party import so a fresh install can self-heal.
"""

import sys

# --- Bootstrap (runs before PyQt6 / minecraft-launcher-lib are imported) ---
from core import bootstrap  # noqa: E402

if not bootstrap.ensure():
    print("[bootstrap] Dependency setup failed. RPI LAUNCHER cannot start.", file=sys.stderr)
    sys.exit(1)

# --- Now it is safe to import the heavy dependencies ---
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402

APP_NAME = "RPI LAUNCHER"
APP_VERSION = "1.0.0"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
