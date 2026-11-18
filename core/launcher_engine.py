"""High-level install + launch orchestration."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid

from minecraft_launcher_lib import command, install, mod_loader, utils

from . import arm64_patcher, mod_manager

APP_NAME = "RPI LAUNCHER"
APP_VERSION = "1.0.0"
# ``-Dminecraft.launcher.brand`` must be a single shell token (no spaces), so the
# user-facing APP_NAME above cannot be reused for the JVM flag.
LAUNCHER_BRAND = "RPI_LAUNCHER"


class LauncherEngine:
    def __init__(self, minecraft_dir: str, log=print):
        self.minecraft_dir = minecraft_dir
        self.log = log

    @staticmethod
    def _callback(status_cb=None, progress_cb=None, max_cb=None) -> dict:
        cb: dict = {}
        if status_cb is not None:
            cb["setStatus"] = status_cb
        if progress_cb is not None:
            cb["setProgress"] = progress_cb
        if max_cb is not None:
            cb["setMax"] = max_cb
        return cb

    def install_and_launch(
        self,
        version_id: str,
        username: str,
        ram_mb: int,
        mods_selection: dict[str, bool],
        status_cb=None,
        progress_cb=None,
        max_cb=None,
        java_path: str | None = None,
        on_output=None,
    ) -> None:
        cb = self._callback(status_cb, progress_cb, max_cb)

        if java_path is None:
            java_path = utils.get_java_executable()
        # On ARM64 Linux, drive both install and launch with system Java — never
        # Mojang's x86_64 bundled runtime that install_minecraft_version may fetch.
        if arm64_patcher.is_aarch64_linux():
            java_path = self._system_java()

        # 1. Vanilla Minecraft
        self.log(f"Installing Minecraft {version_id} ...")
        install.install_minecraft_version(version_id, self.minecraft_dir, callback=cb)

        # 2. Fabric loader (latest *stable* loader, not a bleeding-edge build)
        self.log("Installing Fabric loader ...")
        fabric = mod_loader.get_mod_loader("fabric")
        loader_version = self._stable_loader_version(fabric, version_id)
        self.log(f"Using Fabric loader {loader_version} ...")
        fabric_installed_id = fabric.install(
            version_id,
            self.minecraft_dir,
            loader_version=loader_version,
            callback=cb,
            java=java_path,
        )

        # 3. Resolve the exact installed profile id to launch. The id is read back
        #    from get_installed_versions() so we never hand a guessed
        #    "fabric-loader-..." string to the command builder; if Fabric is
        #    absent/disabled we fall back to the vanilla version.
        launch_id = self._resolve_launch_id(fabric_installed_id, version_id)

        # 4. ARM64 LWJGL natives
        natives_dir = arm64_patcher.patch_natives(self.minecraft_dir, launch_id, log=self.log)

        # 5. Selected performance mods
        mods_dir = os.path.join(self.minecraft_dir, "mods")
        mod_manager.install_mods(mods_selection, version_id, mods_dir, log=self.log)

        # 6. Launch
        self.log(f"Launching {launch_id} as {username} ({ram_mb} MB RAM) ...")
        self._launch(launch_id, username, ram_mb, natives_dir, java_path, on_output)

    @staticmethod
    def _system_java() -> str:
        """A known-good ARM64 system Java on Linux aarch64 (used for install + launch)."""
        return shutil.which("java") or "/usr/bin/java"

    @staticmethod
    def _strip_x86_64_natives_jars(cmd: list[str]) -> list[str]:
        """Remove x86_64 ``-natives-linux.jar`` entries from the ``-cp`` argument.

        On aarch64 these jars hold the wrong ELF class (e.g.
        ``jtracy-*-natives-linux.jar``) and must not sit on the classpath; the
        correct ARM64 natives live in the patched ``natives`` directory. ARM64
        jars (``*-natives-linux-arm64.jar``) are left untouched.
        """
        out: list[str] = []
        i = 0
        while i < len(cmd):
            if cmd[i] == "-cp" and i + 1 < len(cmd):
                out.append(cmd[i])
                classpath = cmd[i + 1]
                kept = [
                    entry
                    for entry in classpath.split(os.pathsep)
                    if not entry.endswith("-natives-linux.jar")
                ]
                out.append(os.pathsep.join(kept))
                i += 2
            else:
                out.append(cmd[i])
                i += 1
        return out

    def _stable_loader_version(self, fabric, version_id: str) -> str:
        """Pick the newest *stable* Fabric loader for ``version_id``.

        ``mod_loader`` returns loader versions newest-first. Restricting to
        stable builds avoids bleeding-edge loaders (e.g. 0.20.x) that Fabric may
        not yet support for this Minecraft version.
        """
        stable = fabric.get_loader_versions(version_id, stable_only=True)
        if stable:
            return stable[0]
        fallback = fabric.get_loader_versions(version_id, stable_only=False)
        if fallback:
            self.log(f"[fabric] No stable loader for {version_id}; using {fallback[0]}.")
            return fallback[0]
        raise ValueError(f"No Fabric loader available for Minecraft {version_id}")

    def _resolve_launch_id(self, fabric_id: str, vanilla_id: str) -> str:
        """Return the installed profile id to launch, preferring the Fabric profile."""
        installed = {v["id"] for v in utils.get_installed_versions(self.minecraft_dir)}
        if fabric_id in installed:
            return fabric_id
        # A different Fabric profile may already exist for this MC version.
        suffix = "-" + vanilla_id
        for vid in installed:
            if vid.startswith("fabric-loader-") and vid.endswith(suffix):
                return vid
        return vanilla_id

    def _launch(self, version_id, username, ram_mb, natives_dir, java_path, on_output):
        jvm_args = [f"-Xmx{ram_mb}M", "-Xms512M"]
        if arm64_patcher.is_aarch64_linux() and natives_dir:
            jvm_args += arm64_patcher.get_jvm_arguments(natives_dir)

        # On ARM64 Linux, force system Java so the launch NEVER invokes Mojang's
        # x86_64 bundled runtime (which install_minecraft_version may download for
        # the version's declared javaVersion).
        executable = java_path
        if arm64_patcher.is_aarch64_linux():
            executable = self._system_java()

        options = {
            "username": username,
            "uuid": str(uuid.uuid4()),
            "token": "",
            "executablePath": executable,
            "jvmArguments": jvm_args,
            "launcherName": LAUNCHER_BRAND,
            "launcherVersion": APP_VERSION,
            "enableLoggingConfig": True,
        }
        if natives_dir:
            options["nativesDirectory"] = natives_dir

        cmd = command.get_minecraft_command(version_id, self.minecraft_dir, options)
        env = os.environ.copy()
        if arm64_patcher.is_aarch64_linux():
            cmd = self._strip_x86_64_natives_jars(cmd)
            # Force GLFW onto X11/XWayland: on Raspberry Pi OS Wayland sessions the
            # Wayland backend can fail to negotiate a Vulkan surface and crash.
            env["WAYLAND_DISPLAY"] = ""
        self.log("[cmd] " + " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            cwd=self.minecraft_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if on_output is not None:
                on_output(line.rstrip("\r\n"))
        returncode = proc.wait()
        self.log(f"Game exited with code {returncode}.")
