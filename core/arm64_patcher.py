"""ARM64 LWJGL native patching for the Raspberry Pi 5.

Minecraft ships x86_64 LWJGL natives; on aarch64 Linux those ``.so`` files are
the wrong ELF class and the game fails to start. This module downloads the
official ``linux-arm64`` LWJGL natives and drops them into the version's
``natives`` directory, then supplies the matching JVM flags.
"""

from __future__ import annotations

import io
import json
import os
import platform
import zipfile

import requests

MAVEN_BASE = "https://repo1.maven.org/maven2/"
PATCH_MARKER = ".rpi-launcher-arm64-patched"
USER_AGENT = "rpi-launcher/1.0"

# VulkanMod links against these LWJGL modules, which vanilla Minecraft's version
# manifest does NOT list. They must always be fetched explicitly (at the same
# LWJGL version as the vanilla natives) or the game dies on launch with:
#   UnsatisfiedLinkError: Failed to locate library: liblwjgl_vma.so
VULKANMOD_LWJGL_NATIVES = ("lwjgl-vma", "lwjgl-shaderc")


def is_aarch64_linux() -> bool:
    return platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64")


def _load_version_json(minecraft_dir: str, version_id: str) -> dict:
    path = os.path.join(minecraft_dir, "versions", version_id, version_id + ".json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _iter_lwjgl_natives(data: dict):
    """Yield ``(group, artifact, version)`` for x86_64 LWJGL native libs."""
    for lib in data.get("libraries", []):
        name = lib.get("name", "")
        if not name.startswith("org.lwjgl:"):
            continue
        parts = name.split(":")
        # New format: the native classifier is embedded in the coordinate.
        if len(parts) >= 4 and parts[3].startswith("natives-"):
            if parts[3] == "natives-linux":
                yield parts[0], parts[1], parts[2]
        # Old format: a "natives" mapping keyed by OS.
        elif lib.get("natives", {}).get("linux"):
            yield parts[0], parts[1], parts[2]


def find_lwjgl_natives(minecraft_dir: str, version_id: str) -> list[tuple[str, str, str]]:
    """Walk the version inheritance chain and collect LWJGL native coordinates."""
    found: dict[str, tuple[str, str, str]] = {}
    current = version_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        path = os.path.join(minecraft_dir, "versions", current, current + ".json")
        if not os.path.isfile(path):
            break
        data = _load_version_json(minecraft_dir, current)
        for group, artifact, version in _iter_lwjgl_natives(data):
            key = f"{group}:{artifact}:{version}"
            if key not in found:
                found[key] = (group, artifact, version)
        current = data.get("inheritsFrom")
    return list(found.values())


def _lwjgl_version(artifacts: list[tuple[str, str, str]]) -> str | None:
    """Return the LWJGL version shared by the vanilla native modules."""
    for group, artifact, version in artifacts:
        if group == "org.lwjgl" and artifact == "lwjgl":
            return version
    return artifacts[0][2] if artifacts else None


def _with_vulkanmod_natives(
    artifacts: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Add the VulkanMod-required natives at the vanilla LWJGL version.

    Vanilla Minecraft never lists ``lwjgl-vma`` or ``lwjgl-shaderc`` in its
    manifest, so a vanilla-only patch leaves VulkanMod without the native
    libraries it links against. They are fetched at the same LWJGL version as
    the rest of the natives.
    """
    lwjgl_version = _lwjgl_version(artifacts)
    if lwjgl_version is None:
        return list(artifacts)
    combined = list(artifacts)
    seen = {f"{group}:{artifact}:{version}" for group, artifact, version in combined}
    for artifact in VULKANMOD_LWJGL_NATIVES:
        coord = ("org.lwjgl", artifact, lwjgl_version)
        key = ":".join(coord)
        if key not in seen:
            combined.append(coord)
            seen.add(key)
    return combined


def _maven_url(group: str, artifact: str, version: str) -> str:
    return (
        f"{MAVEN_BASE}{group.replace('.', '/')}/{artifact}/{version}/"
        f"{artifact}-{version}-natives-linux-arm64.jar"
    )


def _extract_so(jar_bytes: bytes, natives_dir: str) -> int:
    count = 0
    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as zf:
        for entry in zf.namelist():
            if entry.endswith(".so"):
                dest = os.path.join(natives_dir, os.path.basename(entry))
                with open(dest, "wb") as f:
                    f.write(zf.read(entry))
                count += 1
    return count


def patch_natives(minecraft_dir: str, version_id: str, log=print) -> str | None:
    """Download ARM64 LWJGL natives into ``versions/<id>/natives``. Idempotent.

    Returns the natives directory, or ``None`` when no patching was needed.
    """
    if not is_aarch64_linux():
        return None

    natives_dir = os.path.join(minecraft_dir, "versions", version_id, "natives")
    os.makedirs(natives_dir, exist_ok=True)
    marker = os.path.join(natives_dir, PATCH_MARKER)

    artifacts = _with_vulkanmod_natives(find_lwjgl_natives(minecraft_dir, version_id))
    if not artifacts:
        log("[arm64] No LWJGL native libraries found to patch.")
        return natives_dir

    # A ``.patched`` marker alone is not proof of a complete patch: VulkanMod
    # needs ``liblwjgl_vma.so``, which vanilla never ships. If it is missing
    # (e.g. a marker written by an older patch that predates VulkanMod support),
    # re-extract the natives instead of trusting the stale marker.
    vma_so = os.path.join(natives_dir, "liblwjgl_vma.so")
    if os.path.isfile(marker) and os.path.isfile(vma_so):
        log("[arm64] LWJGL natives already patched (marker + liblwjgl_vma.so present).")
        return natives_dir
    if os.path.isfile(marker):
        log("[arm64] Stale patch marker (liblwjgl_vma.so missing); re-patching ...")
        os.remove(marker)

    log(f"[arm64] Patching {len(artifacts)} LWJGL native library(ies) for linux-arm64 ...")
    failed: list[str] = []
    for group, artifact, version in artifacts:
        url = _maven_url(group, artifact, version)
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
            if resp.status_code != 200:
                failed.append(f"{artifact}-{version}")
                log(f"[arm64]   {artifact}-{version}: HTTP {resp.status_code} (no arm64 native)")
                continue
            extracted = _extract_so(resp.content, natives_dir)
            log(f"[arm64]   {artifact}-{version}: extracted {extracted} .so file(s)")
        except Exception as exc:  # network/parse errors are non-fatal per library
            failed.append(f"{artifact}-{version}")
            log(f"[arm64]   {artifact}-{version}: {exc}")

    if failed and len(failed) == len(artifacts):
        raise RuntimeError("Failed to download any ARM64 LWJGL natives.")

    if not failed:
        with open(marker, "w", encoding="utf-8") as f:
            f.write(f"patched {len(artifacts)} LWJGL native(s) for linux-arm64\n")

    return natives_dir


def get_jvm_arguments(natives_dir: str) -> list[str]:
    """ARM64 JVM flags: G1GC plus the LWJGL native library path."""
    return [
        "-XX:+UseG1GC",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:G1NewSizePercent=20",
        "-XX:G1ReservePercent=20",
        "-XX:MaxGCPauseMillis=50",
        f"-Dorg.lwjgl.librarypath={natives_dir}",
    ]
