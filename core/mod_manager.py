"""Modrinth v2 API integration for Fabric performance mods.

Always resolves the newest game-version-compatible Fabric build of each mod;
no mod version is hardcoded.
"""

from __future__ import annotations

import json
import os

import requests

MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "rpi-launcher/1.0"

# display slug -> Modrinth slugs to try, in order
MODS = {
    "vulkanmod": ["vulkanmod"],
    "lithium": ["lithium"],
    "ferritecore": ["ferrite-core", "ferritecore"],
    "sodium": ["sodium"],
}


def _project_versions(slug: str, game_version: str) -> list[dict]:
    params = {
        "loaders": json.dumps(["fabric"]),
        "game_versions": json.dumps([game_version]),
    }
    resp = requests.get(
        f"{MODRINTH_API}/project/{slug}/version",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _pick_build(versions: list[dict]) -> dict | None:
    """Pick the newest release build, falling back to any build."""
    if not versions:
        return None
    # Modrinth returns versions newest-first by default.
    for version in versions:
        if version.get("version_type") == "release":
            return version
    return versions[0]


def _primary_file(version: dict) -> dict | None:
    for f in version.get("files", []):
        if f.get("primary"):
            return f
    files = version.get("files", [])
    return files[0] if files else None


def get_latest_fabric_build(slug: str, game_version: str) -> dict | None:
    """Resolve the newest game-version-compatible Fabric build for a mod slug."""
    for candidate in MODS.get(slug, [slug]):
        try:
            versions = _project_versions(candidate, game_version)
        except requests.RequestException:
            continue
        build = _pick_build(versions)
        if build is None:
            continue
        file_info = _primary_file(build)
        if file_info is None:
            continue
        return {
            "slug": candidate,
            "project_id": build.get("project_id"),
            "version_id": build.get("id"),
            "version_number": build.get("version_number"),
            "filename": file_info.get("filename"),
            "url": file_info.get("url"),
        }
    return None


def install_mod(slug: str, game_version: str, mods_dir: str, log=print) -> str | None:
    """Download and install one mod. Returns the filename, or None on failure."""
    os.makedirs(mods_dir, exist_ok=True)
    build = get_latest_fabric_build(slug, game_version)
    if build is None or not build.get("url") or not build.get("filename"):
        log(f"[mod] {slug}: no Fabric build for Minecraft {game_version}")
        return None

    dest = os.path.join(mods_dir, build["filename"])
    if os.path.isfile(dest):
        log(f"[mod] {slug}: already installed ({build['filename']})")
        return build["filename"]

    log(f"[mod] {slug}: downloading {build['filename']} ...")
    resp = requests.get(build["url"], headers={"User-Agent": USER_AGENT}, timeout=120, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    log(f"[mod] {slug}: installed {build['filename']}")
    return build["filename"]


def install_mods(selection: dict[str, bool], game_version: str, mods_dir: str, log=print) -> None:
    """Install every enabled mod, logging failures instead of raising."""
    for slug, enabled in selection.items():
        if not enabled:
            continue
        try:
            install_mod(slug, game_version, mods_dir, log=log)
        except Exception as exc:  # network/API failures must not abort the launch
            log(f"[mod] {slug}: failed — {exc}")
