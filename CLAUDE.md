# RPI LAUNCHER — Project Rules

RPI LAUNCHER is a **lightweight, utilitarian Minecraft launcher** built specifically for the **Raspberry Pi 5** (Linux `aarch64` / ARM64, Raspberry Pi OS Bookworm/Trixie). Every design and implementation decision in this repository must serve that single goal: a small, fast, functional launcher that actually runs Minecraft on a Pi 5 with the lowest possible overhead.

These rules are **strict**. Do not deviate from them without an explicit instruction from the user.

---

## 0. Hard constraints

- **Target platform:** Linux `aarch64` / ARM64, Raspberry Pi OS Bookworm/Trixie. This is not an x86_64 desktop launcher.
- **Runtime:** Python 3 + **PyQt6**.
- **Dependencies (Python):** `PyQt6`, `minecraft-launcher-lib`, `requests`. Do not add new third-party dependencies without approval.
- **Do not bloat the app.** It is a launcher, not a platform. No splash screens, no telemetry, no auto-updaters, no plugins, no skin/replay/snapshot viewers.

## 1. UI Philosophy (strictly functional)

The UI must be **functional, fast, and visually plain**, using **native system widgets** via PyQt6.

- **No frameless windows.** Use a standard title bar and window chrome provided by the OS.
- **No heavy animations**, transitions, splash screens, or custom-drawn decorative elements.
- **No theming engine, custom stylesheets, or icon packs** beyond what is strictly needed for clarity.
- Layout is a **clean grid** (`QGridLayout`) containing exactly these elements:
  1. **Version selector** (dropdown/combo box of installed Minecraft versions).
  2. **Offline Username** input (plain text field).
  3. **RAM allocation slider** in **MB** (`QSlider` + numeric readout).
  4. **Checkboxes** for auto-installing optimization/Vulkan mods.
  5. A **large "Launch Game" button** (primary action, prominent but native).
  6. A **live console log output box** (`QPlainTextEdit`, read-only) streaming launch output.
- The window should be resizable, small by default, and must not force full-screen or stay-on-top behavior.
- Prefer `QWidget`/`QMainWindow` defaults; do not subclass widgets for visual flourish.

## 2. ARM64 & LWJGL Handling

`minecraft-launcher-lib` handles vanilla version + Fabric Loader installation. On top of that, the launcher **must** work on ARM64, which stock x86_64 Minecraft natives do not.

- Implement `core/arm64_patcher.py` that:
  - **Detects** `aarch64` Linux (check `platform.machine()` / `uname`).
  - **Replaces** the x86_64 LWJGL native `.so` libraries in the version's `natives` directory with the **official `linux-arm64` LWJGL natives**.
  - **Sets ARM64 JVM flags**, including G1GC and `-Dorg.lwjgl.librarypath=<native dir>`.
- Never ship or assume x86_64 natives work on the Pi 5.
- Keep the patch idempotent and re-runnable; detect already-patched state to avoid redundant work.

## 3. Vulkan & Optimization Mods (Modrinth API)

`core/mod_manager.py` fetches and installs **Fabric** versions of performance mods from the **Modrinth API** (via `requests`).

- Always resolve the **game-version-compatible Fabric** build of each mod; do not hardcode a single mod version.
- Required mods to fetch/install:
  - **`vulkanmod`** — Vulkan renderer for the Pi 5's V3DV driver.
  - **`lithium`** — general server/game-logic optimization.
  - **`ferritecore`** — memory footprint reduction.
  - **`sodium`** — OpenGL fallback renderer (optional, controlled by its checkbox).
- Install mods into the correct Fabric `mods/` directory for the selected version.
- Respect the user's checkbox selections; never silently install unselected mods.
- Handle network/API failures gracefully with a clear console log message.

## 4. Portable USB Setup & `.desktop` Integration

The folder must be copyable onto a USB flash drive and installed on a Raspberry Pi 5 with a single command.

- Provide `install_rpi.sh` — **self-contained**, idempotent, and **LF line endings** (never CRLF).
  - Install system dependencies: `openjdk-21-jre`, `mesa-vulkan-drivers`, `python3-pyqt6`.
  - Create a Python **`venv`** and install the launcher's Python dependencies into it.
  - Generate a **`.desktop`** shortcut on both the **Desktop** and the **Applications menu**.
- The user must be able to run: `bash install_rpi.sh`.
- Do not assume the Pi has any of these packages pre-installed; the script checks and installs as needed (using `apt` where appropriate).

---

## Conventions

- Python code targets Linux ARM64 at runtime but must remain runnable/testable on the dev machine where practical.
- Use clear, minimal modules under `core/` (e.g. `core/arm64_patcher.py`, `core/mod_manager.py`). Keep the entry point thin.
- Log every significant launcher action to the console box; do not use silent `print` debugging in release paths.
- Do not add decorative assets, images, or animations.
- Keep startup time and memory footprint as low as possible.
