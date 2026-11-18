# RPI LAUNCHER

A lightweight, utilitarian **Minecraft launcher built for the Raspberry Pi 5**
(Linux `aarch64` / ARM64, Raspberry Pi OS Bookworm/Trixie). It launches real
Minecraft — vanilla plus a Fabric performance stack — with the lowest possible
overhead, tuned for **50–60 FPS** on the Pi 5's Vulkan driver.

## Features

- **ARM64-native LWJGL patching** — downloads the official `linux-arm64` LWJGL
  natives and swaps them in place of the stock x86_64 libraries, so Minecraft
  actually runs on the Pi 5's ARM64 CPU.
- **Automatic performance mods** — resolves the correct game-version-compatible
  Fabric builds from the Modrinth API and installs **VulkanMod**, **Lithium**,
  and **FerriteCore** automatically (Sodium is available as an optional OpenGL
  fallback).
- **Tuned for the Pi 5** — G1GC JVM flags sized for a low-memory SBC, plus the
  Vulkan renderer running on the Pi 5's `v3dv` driver.
- **Clean, functional UI** — plain native PyQt6 widgets: version selector,
  offline username, RAM slider, mod checkboxes, and a live console log.
- **Portable USB install** — a single idempotent script sets up system packages,
  a Python `venv`, and desktop shortcuts.

## Installation

Run these two commands on your Raspberry Pi 5:

```bash
git clone https://github.com/V1R4T723/-RPI-launcher.git
cd ./-RPI-launcher && bash install_rpi.sh
```

> **Note:** the repository directory is named `-RPI-launcher` (it begins with a
> dash), so `cd` needs a path that doesn't look like a flag — the `./` prefix
> makes it unambiguous. A bare `cd -RPI-launcher` is parsed as a flag and fails.

The installer installs `openjdk-21-jre`, `mesa-vulkan-drivers`, `vulkan-tools`,
and `python3-pyqt6`, creates a Python `venv`, and adds a launcher shortcut to
both your Desktop and the Applications menu.

## Credits

RPI LAUNCHER was co-developed with **DeepSeek**.
