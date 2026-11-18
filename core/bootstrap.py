"""Self-healing bootstrap for RPI LAUNCHER.

This module must be importable *without* PyQt6 or minecraft-launcher-lib,
because it is responsible for installing them before anything else imports
them. It therefore only uses the Python standard library.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys

# (import_name, pip_distribution_name)
REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6"),
    ("minecraft_launcher_lib", "minecraft-launcher-lib"),
    ("requests", "requests"),
]

# System packages needed for the Raspberry Pi 5 (aarch64).
APT_PACKAGES = [
    "openjdk-21-jre",
    "mesa-vulkan-drivers",
    "vulkan-tools",
    "python3-pyqt6",
]

APP_NAME = "RPI LAUNCHER"


def _is_venv() -> bool:
    return sys.prefix != sys.base_prefix or hasattr(sys, "real_prefix")


def _is_debian_like() -> bool:
    return os.path.isfile("/etc/debian_version")


def missing_packages() -> list[str]:
    """Return the import names of required Python packages that are missing."""
    return [name for name, _dist in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None]


def _pip_install(dist_names: list[str], extra_flags: list[str] | None = None) -> int:
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + (extra_flags or []) + dist_names
    print("[bootstrap] $ " + " ".join(cmd))
    return subprocess.run(cmd).returncode


def install_python_dependencies() -> bool:
    """Install missing Python packages and upgrade minecraft-launcher-lib.

    minecraft-launcher-lib is version-sensitive: the ARM64/Fabric support this
    launcher relies on is fixed in newer releases, so it is upgraded even when
    it is already present.
    """
    missing = missing_packages()
    if missing:
        dists = [dist for name, dist in REQUIRED_PACKAGES if name in missing]
        print("[bootstrap] Missing Python packages: " + ", ".join(dists))
        _pip_install(dists)
    else:
        print("[bootstrap] Python dependencies OK.")

    # Always upgrade minecraft-launcher-lib to pick up the latest Fabric/ARM64 fixes.
    _pip_install(["minecraft-launcher-lib"])

    if not missing_packages():
        return True

    # Debian / Raspberry Pi OS marks the system Python as externally managed,
    # so a plain `pip install` fails outside a venv. Retry with the escape hatch.
    if _is_debian_like() and not _is_venv():
        print("[bootstrap] Retrying with --break-system-packages ...")
        _pip_install(
            [dist for name, dist in REQUIRED_PACKAGES if name in missing_packages()],
            extra_flags=["--break-system-packages"],
        )

    return not missing_packages()


def missing_system_packages() -> list[str]:
    """Return the apt packages that appear to be missing on aarch64 Linux."""
    missing: list[str] = []
    if shutil.which("java") is None:
        missing.append("openjdk-21-jre")
    if shutil.which("vulkaninfo") is None:
        missing.append("vulkan-tools")

    # A Mesa Vulkan ICD (e.g. the Pi 5's v3dv driver) is what actually makes
    # Vulkan work; vulkaninfo alone is just a probe utility.
    icd_dir = "/usr/share/vulkan/icd.d"
    has_icd = os.path.isdir(icd_dir) and any(f.endswith(".json") for f in os.listdir(icd_dir))
    if not has_icd:
        missing.append("mesa-vulkan-drivers")

    return missing


def run_apt_install(packages: list[str]) -> None:
    subprocess.run(["sudo", "apt-get", "update"])
    subprocess.run(["sudo", "apt-get", "install", "-y"] + packages)


def _is_arm64_linux() -> bool:
    return platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64")


def ensure(interactive: bool | None = None) -> bool:
    """Run the full bootstrap. Returns True when the app can continue."""
    print(f"[bootstrap] {APP_NAME} — checking dependencies ...")

    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()

    if not install_python_dependencies():
        print("[bootstrap] Failed to install Python dependencies.", file=sys.stderr)
        return False

    if _is_arm64_linux():
        missing = missing_system_packages()
        if missing:
            print("[bootstrap] Missing system packages: " + ", ".join(missing))
            if interactive:
                try:
                    answer = input("[bootstrap] Install them now with sudo apt-get? [Y/n] ").strip().lower()
                except EOFError:
                    answer = "n"
                if answer in ("", "y", "yes"):
                    run_apt_install(missing)
                else:
                    print("[bootstrap] Skipping system packages. Run install_rpi.sh if needed.")
            else:
                print("[bootstrap] Not interactive — run install_rpi.sh or:")
                print("[bootstrap]   sudo apt-get update && sudo apt-get install -y " + " ".join(missing))

    return True
