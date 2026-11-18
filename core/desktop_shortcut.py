"""Desktop shortcut (.desktop) generation for RPI LAUNCHER."""

from __future__ import annotations

import os
import platform
import stat
import sys

APP_NAME = "RPI LAUNCHER"


def is_linux() -> bool:
    return platform.system() == "Linux"


def _desktop_content(python_path: str, main_py: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=RPI LAUNCHER\n"
        "Comment=Lightweight Minecraft launcher for Raspberry Pi 5\n"
        f"Exec={python_path} {main_py}\n"
        "Icon=utilities-terminal\n"
        "Terminal=false\n"
        "Categories=Game;\n"
    )


def create_desktop_shortcuts(project_dir: str, log=print) -> bool:
    """Create/refresh Desktop + Applications-menu .desktop shortcuts (Linux)."""
    if not is_linux():
        log("[shortcut] Desktop shortcuts are only supported on Linux.")
        return False

    main_py = os.path.join(project_dir, "main.py")
    if not os.path.isfile(main_py):
        log(f"[shortcut] main.py not found at {main_py}")
        return False

    venv_python = os.path.join(project_dir, "venv", "bin", "python")
    if not os.path.isfile(venv_python):
        venv_python = sys.executable

    desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    apps_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
    os.makedirs(desktop_dir, exist_ok=True)
    os.makedirs(apps_dir, exist_ok=True)

    targets = [
        os.path.join(desktop_dir, "RPI-LAUNCHER.desktop"),
        os.path.join(apps_dir, "rpi-launcher.desktop"),
    ]
    content = _desktop_content(venv_python, main_py)
    for target in targets:
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        log(f"[shortcut] Wrote {target}")

    return True
