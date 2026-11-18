"""Main window for RPI LAUNCHER."""

from __future__ import annotations

import datetime
import os
import platform

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QWidget,
)

from minecraft_launcher_lib import utils

from core import desktop_shortcut, launcher_engine

APP_NAME = "RPI LAUNCHER"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Substrings that mark a mod-loader profile id (never a clean Mojang release).
_LOADER_PROFILE_MARKERS = ("fabric-loader-", "quilt-loader-", "-forge-", "-neoforge-")


def _is_vanilla_version_id(version_id: str) -> bool:
    return not any(marker in version_id for marker in _LOADER_PROFILE_MARKERS)

# (slug, label, default_checked, tooltip)
MOD_CHECKBOXES = [
    ("vulkanmod", "VulkanMod (Vulkan renderer)", True,
     "Vulkan renderer using the Pi 5's v3dv driver. Recommended."),
    ("lithium", "Lithium (game-logic optimization)", True,
     "Reduces server/game-logic CPU overhead."),
    ("ferritecore", "FerriteCore (memory footprint)", True,
     "Lowers RAM usage."),
    ("sodium", "Sodium (OpenGL fallback)", False,
     "OpenGL fallback renderer. Conflicts with VulkanMod — enable only if you want OpenGL instead of Vulkan."),
]


class VersionRefreshWorker(QObject):
    finished = pyqtSignal(list)

    def __init__(self, minecraft_dir):
        super().__init__()
        self.minecraft_dir = minecraft_dir

    def run(self):
        try:
            versions = utils.get_available_versions(self.minecraft_dir)
        except Exception:
            versions = []
        self.finished.emit(versions)


class LaunchWorker(QObject):
    log = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int)
    set_max = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, minecraft_dir, version_id, username, ram_mb, mods_selection, java_path):
        super().__init__()
        self.minecraft_dir = minecraft_dir
        self.version_id = version_id
        self.username = username
        self.ram_mb = ram_mb
        self.mods_selection = mods_selection
        self.java_path = java_path

    def run(self):
        engine = launcher_engine.LauncherEngine(self.minecraft_dir, log=self.log.emit)
        try:
            engine.install_and_launch(
                self.version_id,
                self.username,
                self.ram_mb,
                self.mods_selection,
                status_cb=self.status.emit,
                progress_cb=self.progress.emit,
                max_cb=self.set_max.emit,
                java_path=self.java_path,
                on_output=self.log.emit,
            )
            self.finished.emit(True, "Done.")
        except Exception as exc:
            self.log.emit(f"[error] {exc}")
            self.finished.emit(False, str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(560, 760)

        self.minecraft_dir = utils.get_minecraft_directory()
        self.java_path = utils.get_java_executable()
        self._versions = []
        self._thread = None
        self._worker = None
        self._refresh_thread = None
        self._refresh_worker = None

        self._build_ui()
        self._start_version_refresh()

    # --- UI construction ---

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        grid = QGridLayout(central)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # Row 0 — version selector + refresh
        grid.addWidget(QLabel("Minecraft Version:"), 0, 0)
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(220)
        grid.addWidget(self.version_combo, 0, 1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._start_version_refresh)
        grid.addWidget(self.refresh_btn, 0, 2)

        # Row 1 — offline username
        grid.addWidget(QLabel("Offline Username:"), 1, 0)
        self.username_edit = QLineEdit("Player")
        grid.addWidget(self.username_edit, 1, 1, 1, 2)

        # Row 2 — RAM slider + readout
        grid.addWidget(QLabel("RAM (MB):"), 2, 0)
        self.ram_slider = QSlider(Qt.Orientation.Horizontal)
        self.ram_slider.setRange(1024, 6144)
        self.ram_slider.setValue(3072)
        self.ram_slider.setSingleStep(256)
        self.ram_slider.setPageStep(1024)
        self.ram_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ram_slider.setTickInterval(1024)
        self.ram_slider.valueChanged.connect(self._on_ram_changed)
        grid.addWidget(self.ram_slider, 2, 1)
        self.ram_label = QLabel("3072 MB")
        self.ram_label.setMinimumWidth(72)
        grid.addWidget(self.ram_label, 2, 2)

        # Row 3 — mod checkboxes
        grid.addWidget(QLabel("Optimization mods:"), 3, 0, Qt.AlignmentFlag.AlignTop)
        mod_widget = QWidget()
        mod_layout = QGridLayout(mod_widget)
        mod_layout.setContentsMargins(0, 0, 0, 0)
        self.mod_checks = {}
        for i, (slug, label, default, tooltip) in enumerate(MOD_CHECKBOXES):
            cb = QCheckBox(label)
            cb.setChecked(default)
            cb.setToolTip(tooltip)
            self.mod_checks[slug] = cb
            mod_layout.addWidget(cb, i // 2, i % 2)
        grid.addWidget(mod_widget, 3, 1, 1, 2)

        sodium_cb = self.mod_checks.get("sodium")
        if sodium_cb is not None:
            sodium_cb.toggled.connect(self._on_sodium_toggled)

        # Row 4 — progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        grid.addWidget(self.progress, 4, 0, 1, 3)

        # Row 5 — launch button
        self.launch_btn = QPushButton("Install & Launch")
        self.launch_btn.setMinimumHeight(48)
        self.launch_btn.clicked.connect(self._on_launch)
        grid.addWidget(self.launch_btn, 5, 0, 1, 3)

        # Row 6 — console log
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setPlaceholderText("Launch output will appear here ...")
        grid.addWidget(self.console, 6, 0, 1, 3)
        grid.setRowStretch(6, 1)

        # Row 7 — desktop shortcut (Linux only)
        if platform.system() == "Linux":
            self.shortcut_btn = QPushButton("Create Desktop Shortcut (.desktop)")
            self.shortcut_btn.clicked.connect(self._on_create_shortcut)
            grid.addWidget(self.shortcut_btn, 7, 0, 1, 3)

    # --- helpers ---

    def _append_log(self, text: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console.appendPlainText(f"[{ts}] {text}")

    # --- version list ---

    def _start_version_refresh(self):
        if self._refresh_thread is not None and self._refresh_thread.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self._append_log("Refreshing Minecraft version list ...")
        self._refresh_thread = QThread(self)
        self._refresh_worker = VersionRefreshWorker(self.minecraft_dir)
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self._on_versions_ready)
        self._refresh_worker.finished.connect(self._refresh_thread.quit)
        self._refresh_worker.finished.connect(self._refresh_worker.deleteLater)
        self._refresh_thread.finished.connect(self._refresh_thread.deleteLater)
        self._refresh_thread.finished.connect(self._on_refresh_done)
        self._refresh_thread.start()

    def _on_versions_ready(self, versions):
        # Only show clean vanilla releases; never expose raw "fabric-loader-…"
        # profile ids, which would leak into the dropdown and confuse launches.
        self._versions = [
            v for v in versions
            if v.get("type") == "release" and _is_vanilla_version_id(v["id"])
        ]
        self._versions.sort(key=lambda v: v.get("releaseTime"), reverse=True)
        installed = {v["id"] for v in utils.get_installed_versions(self.minecraft_dir)}
        current = self.version_combo.currentData()

        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        for v in self._versions:
            label = v["id"] + ("  (installed)" if v["id"] in installed else "")
            self.version_combo.addItem(label, v["id"])

        if current is not None:
            idx = self.version_combo.findData(current)
            if idx >= 0:
                self.version_combo.setCurrentIndex(idx)
        if self.version_combo.count() > 0 and self.version_combo.currentIndex() < 0:
            for idx in range(self.version_combo.count()):
                if self.version_combo.itemText(idx).endswith("(installed)"):
                    self.version_combo.setCurrentIndex(idx)
                    break
            else:
                self.version_combo.setCurrentIndex(0)
        self.version_combo.blockSignals(False)

        self._append_log(f"{self.version_combo.count()} release version(s) available.")

    def _on_refresh_done(self):
        self.refresh_btn.setEnabled(True)

    # --- RAM ---

    def _on_ram_changed(self, value: int):
        self.ram_label.setText(f"{value} MB")

    # --- sodium warning ---

    def _on_sodium_toggled(self, checked: bool):
        if checked:
            self._append_log("Warning: Sodium (OpenGL) conflicts with VulkanMod. "
                             "Disable VulkanMod when using Sodium.")

    # --- launch ---

    def _on_launch(self):
        if self._thread is not None and self._thread.isRunning():
            self._append_log("Already launching — please wait.")
            return

        version_id = self.version_combo.currentData()
        if not version_id:
            QMessageBox.warning(self, APP_NAME, "Select a Minecraft version first.")
            return

        username = self.username_edit.text().strip()
        if not username:
            username = "Player"
            self.username_edit.setText(username)

        ram_mb = self.ram_slider.value()
        mods_selection = {slug: cb.isChecked() for slug, cb in self.mod_checks.items()}

        self.launch_btn.setEnabled(False)
        self.progress.setValue(0)

        self._thread = QThread(self)
        self._worker = LaunchWorker(
            self.minecraft_dir, version_id, username, ram_mb, mods_selection, self.java_path
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.status.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.set_max.connect(self._on_max)
        self._worker.finished.connect(self._on_launch_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_status(self, text: str):
        self._append_log(f"[install] {text}")

    def _on_progress(self, value: int):
        self.progress.setValue(value)

    def _on_max(self, value: int):
        self.progress.setMaximum(max(1, value))
        self.progress.setValue(0)

    def _on_launch_finished(self, ok: bool, message: str):
        self.launch_btn.setEnabled(True)
        self.progress.setValue(self.progress.maximum())
        if ok:
            self._append_log("Launch finished.")
        else:
            QMessageBox.warning(self, APP_NAME, f"Launch failed: {message}")

    # --- desktop shortcut ---

    def _on_create_shortcut(self):
        if platform.system() != "Linux":
            return
        self._append_log("Creating desktop shortcut ...")
        ok = desktop_shortcut.create_desktop_shortcuts(PROJECT_DIR, log=self._append_log)
        if ok:
            QMessageBox.information(self, APP_NAME, "Desktop shortcut created.")
