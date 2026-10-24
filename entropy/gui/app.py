"""PyQt6 desktop interface for Entropy Player."""

from __future__ import annotations

from pathlib import Path
from time import time
from typing import Any

from PyQt6.QtCore import QSettings, QThread, QTimer, Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import QApplication, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget

from entropy.core.controller import PlayerController
from entropy import __version__
from entropy.gui.styles import THEMES, style_for_theme
from entropy.gui.widgets import LibraryNavigation, PlaybackBar, TrackTable, WaveformWidget, format_time
from entropy.gui.audio_analysis import WaveformAnalysisThread
from entropy.gui.mpris import MprisBridge
from entropy.updates import UpdateResult, check_for_update


class UpdateWorker(QThread):
    completed = pyqtSignal(object, bool)

    def __init__(self, manual: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manual = manual

    def run(self) -> None:
        self.completed.emit(check_for_update(), self.manual)


class EntropyWindow(QMainWindow):
    def __init__(self, controller: PlayerController) -> None:
        super().__init__()
        self.controller = controller
        self._view = "library"
        self._active_folder: str | None = None
        self._active_playlist_id: int | None = None
        self._rows: list[dict[str, Any]] = []
        self._scrubbing = False
        self._cover_track_id: int | None = None
        self._waveform_track_id: int | None = None
        self._analysis_workers: list[WaveformAnalysisThread] = []
        self.settings = QSettings("EntropyPlayer", "EntropyPlayer")
        self._update_worker: UpdateWorker | None = None
        self._theme_name = str(self.settings.value("theme", "Strawberry Blue"))
        if self._theme_name not in THEMES:
            self._theme_name = "Strawberry Blue"
        self.setWindowTitle("Entropy Player")
        self.resize(1200, 760)
        self.setMinimumSize(850, 560)
        self.setStyleSheet(style_for_theme(self._theme_name))
        self._set_application_icon()

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        content = QHBoxLayout()
        content.setSpacing(0)
        self.navigation = LibraryNavigation()
        content.addWidget(self.navigation)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(24, 22, 24, 10)
        heading = QHBoxLayout()
        self.page_title = self._label("LIBRARY", "eyebrow")
        heading.addWidget(self.page_title)
        heading.addStretch(1)
        heading.addWidget(QLabel("THEME"))
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(THEMES.keys())
        self.theme_selector.setCurrentText(self._theme_name)
        self.theme_selector.setMinimumWidth(145)
        heading.addWidget(self.theme_selector)
        self.update_button = QPushButton("Check updates")
        self.update_button.setToolTip("Check GitHub for a newer Entropy Player release")
        heading.addWidget(self.update_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tracks, artists, albums")
        self.search.setFixedWidth(205)
        heading.addWidget(self.search)
        center_layout.addLayout(heading)
        self.waveform = WaveformWidget()
        self.waveform.set_accent(THEMES[self._theme_name]["accent"])
        center_layout.addWidget(self.waveform)
        self.table = TrackTable()
        center_layout.addWidget(self.table, 1)
        content.addWidget(center, 1)
        root_layout.addLayout(content, 1)
        self.playback = PlaybackBar()
        root_layout.addWidget(self.playback)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")
        self._mpris = MprisBridge(self.controller, self) if getattr(self.controller, "mpris_enabled", True) else None
        if self._mpris is not None and not self._mpris.registered:
            self.statusBar().showMessage("Desktop media keys unavailable: session media service could not be registered.", 5000)

        self.navigation.tree.itemClicked.connect(self._navigate)
        self.navigation.add_folder_button.clicked.connect(self._choose_folder)
        self.navigation.add_playlist_button.clicked.connect(self._create_playlist)
        self.navigation.reset_shuffle_button.clicked.connect(self._reset_shuffle_history)
        self.search.textChanged.connect(self._render_tracks)
        self.theme_selector.currentTextChanged.connect(self._change_theme)
        self.update_button.clicked.connect(lambda: self._start_update_check(manual=True))
        self.table.cellDoubleClicked.connect(self._play_row)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._track_menu)
        self.playback.play_pause.clicked.connect(self.controller.play_pause)
        self.playback.next.clicked.connect(self.controller.next_track)
        self.playback.previous.clicked.connect(self.controller.previous_track)
        self.playback.volume.valueChanged.connect(lambda value: setattr(self.controller.audio, "volume", value))
        self.playback.mode.currentIndexChanged.connect(self._set_shuffle_mode)
        self.playback.scrub.sliderPressed.connect(self._begin_scrub)
        self.playback.scrub.clicked.connect(self._seek_to_slider_value)
        self.playback.scrub.sliderMoved.connect(self._seek_to_slider_value)
        self.playback.scrub.sliderReleased.connect(self._finish_scrub)
        self.navigation.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.navigation.tree.customContextMenuRequested.connect(self._folder_menu)
        self._install_shortcuts()

        self._library_timer = QTimer(self)
        self._library_timer.timeout.connect(self._render_tracks)
        self._library_timer.start(1800)
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._update_playback)
        self._state_timer.start(300)
        self._refresh_folders()
        self._render_tracks()
        self._update_playback()
        QTimer.singleShot(1800, self._maybe_auto_check_updates)

    def _install_shortcuts(self) -> None:
        shortcuts = {
            "Space": self._shortcut_play_pause,
            "Left": lambda: self._seek_by(-5),
            "Right": lambda: self._seek_by(5),
            "Up": lambda: self._adjust_volume(5),
            "Down": lambda: self._adjust_volume(-5),
            "Ctrl+Up": lambda: self._adjust_volume(5),
            "Ctrl+Down": lambda: self._adjust_volume(-5),
        }
        self._shortcuts: list[QShortcut] = []
        for sequence, callback in shortcuts.items():
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _editing_text(self) -> bool:
        focus = QApplication.focusWidget()
        return isinstance(focus, QLineEdit)

    def _shortcut_play_pause(self) -> None:
        if not self._editing_text():
            self.controller.play_pause()

    def _seek_by(self, seconds: float) -> None:
        if self._editing_text():
            return
        position = self.controller.audio.time_pos
        duration = self.controller.audio.duration
        target = max(0.0, position + seconds)
        if duration > 0:
            target = min(target, duration)
        self.controller.audio.seek(target)

    def _adjust_volume(self, delta: int) -> None:
        focus = QApplication.focusWidget()
        if self._editing_text():
            return
        if focus is self.table and not QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            row_delta = -1 if delta > 0 else 1
            row = self.table.currentRow()
            if row >= 0:
                self.table.selectRow(max(0, min(self.table.rowCount() - 1, row + row_delta)))
            return
        self.controller.audio.volume = max(0, min(100, self.controller.audio.volume + delta))
        self._update_playback()

    def _set_application_icon(self) -> None:
        icon_paths = [
            Path(__file__).parents[2] / "packaging" / "icons" / "entropy-player.svg",
            Path("/usr/share/icons/hicolor/scalable/apps/entropy-player.svg"),
        ]
        for path in icon_paths:
            if path.is_file():
                self.setWindowIcon(QIcon(str(path)))
                return
        self.setWindowIcon(QIcon.fromTheme("audio-headphones"))

    def _change_theme(self, theme: str) -> None:
        if theme not in THEMES:
            return
        self._theme_name = theme
        self.settings.setValue("theme", theme)
        self.setStyleSheet(style_for_theme(theme))
        self.waveform.set_accent(THEMES[theme]["accent"])
        self.waveform.update()

    def _maybe_auto_check_updates(self) -> None:
        last_check = self.settings.value("last_update_check", 0.0, type=float)
        current_time = time()
        if current_time - last_check >= 86400:
            self.settings.setValue("last_update_check", current_time)
            self._start_update_check(manual=False)

    def _start_update_check(self, manual: bool) -> None:
        if self._update_worker is not None and self._update_worker.isRunning():
            if manual:
                self.statusBar().showMessage("Update check is already running.", 2500)
            return
        self.update_button.setEnabled(False)
        self.statusBar().showMessage("Checking for updates in the background...")
        worker = UpdateWorker(manual, self)
        self._update_worker = worker
        worker.completed.connect(self._update_check_finished)
        worker.finished.connect(lambda: self.update_button.setEnabled(True))
        worker.start()

    def _update_check_finished(self, result: UpdateResult, manual: bool) -> None:
        if result.update_available:
            message = f"Entropy Player {result.latest_version} is available. You are using {__version__}."
            self.statusBar().showMessage(f"Update available: {result.latest_version}", 10000)
            if manual:
                answer = QMessageBox.question(
                    self, "Update available", f"{message}\n\nOpen the release page to download it?",
                    QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Open,
                )
                if answer == QMessageBox.StandardButton.Open:
                    QDesktopServices.openUrl(QUrl(result.release_url))
            else:
                self.statusBar().showMessage(f"Update available: {result.latest_version}. Open Check updates for details.", 15000)
        elif result.error:
            self.statusBar().showMessage(result.error, 6000 if manual else 2500)
            if manual:
                QMessageBox.information(self, "Update check", result.error)
        else:
            self.statusBar().showMessage(f"Entropy Player {__version__} is up to date.", 5000)
            if manual:
                QMessageBox.information(self, "No updates", f"Entropy Player {__version__} is up to date.")
        self.settings.setValue("last_update_check", time())

    @staticmethod
    def _label(text: str, object_name: str):
        from PyQt6.QtWidgets import QLabel

        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def _refresh_folders(self) -> None:
        playlists = self.controller.database.get_playlists()
        for playlist in playlists:
            playlist["folders"] = self.controller.database.get_playlist_folders(int(playlist["id"]))
        self.navigation.set_playlists(playlists)

    def _navigate(self, item: Any, _column: int) -> None:
        target = item.data(0, Qt.ItemDataRole.UserRole)
        if target == "library":
            self._view, self._active_folder, self._active_playlist_id = "library", None, None
            self.navigation.select_playlist(None)
            self.controller.set_shuffle_playlist(None)
            self.page_title.setText("LIBRARY")
        elif target == "excluded":
            self._view, self._active_folder, self._active_playlist_id = "excluded", None, None
            self.navigation.select_playlist(None)
            self.controller.set_shuffle_playlist(None)
            self.page_title.setText("EXCLUDED TRACKS")
        elif isinstance(target, tuple) and target[0] == "folder":
            self._view, self._active_folder, self._active_playlist_id = "folder", target[1], target[2]
            self.navigation.select_playlist(target[2])
            self.controller.set_shuffle_playlist(int(target[2]))
            self.page_title.setText(item.text(0).upper())
        elif isinstance(target, tuple) and target[0] == "playlist":
            self._view, self._active_folder, self._active_playlist_id = "playlist", None, target[1]
            self.navigation.select_playlist(target[1])
            self.controller.set_shuffle_playlist(int(target[1]))
            self.page_title.setText(target[2].upper())
        elif target in {"watched", "playlists"}:
            self.navigation.select_playlist(None)
            self.controller.set_shuffle_playlist(None)
            self.statusBar().showMessage("Choose a watched folder." if target == "watched" else "No playlists yet.", 2500)
        else:
            self.navigation.select_playlist(None)
        self._render_tracks()

    def _render_tracks(self) -> None:
        include_excluded = self._view == "excluded"
        tracks = self.controller.tracks(include_excluded=include_excluded)
        if self._view == "excluded":
            tracks = [track for track in tracks if track["is_excluded"]]
        elif self._view == "playlist" and self._active_playlist_id is not None:
            tracks = self.controller.playlist_tracks(self._active_playlist_id)
        elif self._view == "folder" and self._active_folder:
            prefix = str(Path(self._active_folder).resolve()) + "/"
            tracks = [track for track in tracks if track["filepath"] == self._active_folder or track["filepath"].startswith(prefix)]
        query = self.search.text().strip().casefold()
        if query:
            tracks = [track for track in tracks if query in " ".join((track["title"], track["artist"], track["album"])).casefold()]
        self._rows = tracks
        self.table.set_tracks(tracks)
        self.statusBar().showMessage(f"{len(tracks)} tracks")

    def _choose_folder(self) -> None:
        if self._active_playlist_id is None:
            QMessageBox.information(self, "Select a playlist", "Select a playlist before adding a watched folder.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Add watched music folder")
        if folder:
            try:
                self.controller.add_watch_folder(folder, self._active_playlist_id)
                self._refresh_folders()
                self._render_tracks()
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.warning(self, "Could not watch folder", str(exc))

    def _create_playlist(self) -> None:
        name, accepted = QInputDialog.getText(self, "New playlist", "Playlist name")
        if accepted and name.strip():
            try:
                playlist_id = self.controller.create_playlist(name)
                self._refresh_folders()
                for index in range(self.navigation.playlists_item.childCount()):
                    item = self.navigation.playlists_item.child(index)
                    target = item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(target, tuple) and target[:2] == ("playlist", playlist_id):
                        self.navigation.tree.setCurrentItem(item)
                        self._navigate(item, 0)
                        break
            except Exception as exc:
                QMessageBox.warning(self, "Could not create playlist", str(exc))

    def _reset_shuffle_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset shuffle history",
            "Clear all completed-play and early-skip history? This resets play counts and shuffle weights but keeps your library and playlists.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.reset_shuffle_history()
            self._render_tracks()
            self.statusBar().showMessage("Shuffle history reset", 4000)

    def _folder_menu(self, position: Any) -> None:
        item = self.navigation.tree.itemAt(position)
        target = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if target is None:
            selected = self.navigation.tree.currentItem()
            selected_target = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
            if isinstance(selected_target, tuple) and selected_target[0] == "playlist":
                target = selected_target
        menu = QMenu(self)
        if target == "playlists":
            create = menu.addAction("Create new playlist")
            if menu.exec(self.navigation.tree.viewport().mapToGlobal(position)) == create:
                self._create_playlist()
            return
        if isinstance(target, tuple) and target[0] == "folder":
            add_folder = menu.addAction("Add folder to playlist")
            menu.addSeparator()
            remove = menu.addAction("Stop watching folder")
            selected = menu.exec(self.navigation.tree.viewport().mapToGlobal(position))
            if selected == add_folder:
                self._active_playlist_id = int(target[2])
                self.navigation.select_playlist(self._active_playlist_id)
                self._choose_folder()
            elif selected == remove:
                self.controller.remove_watch_folder(target[1])
                self._refresh_folders()
        elif isinstance(target, tuple) and target[0] == "playlist":
            create = menu.addAction("Create new playlist")
            add_folder = menu.addAction("Add folder to this playlist")
            menu.addSeparator()
            delete = menu.addAction("Delete playlist")
            selected = menu.exec(self.navigation.tree.viewport().mapToGlobal(position))
            if selected == create:
                self._create_playlist()
            elif selected == add_folder:
                self._active_playlist_id = int(target[1])
                self.navigation.select_playlist(self._active_playlist_id)
                self.controller.set_shuffle_playlist(self._active_playlist_id)
                self._choose_folder()
            elif selected == delete:
                answer = QMessageBox.question(
                    self,
                    "Delete playlist",
                    f"Delete playlist '{target[2]}' and stop watching its folders? Music files will remain on disk.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.controller.delete_playlist(int(target[1]))
                    if self._active_playlist_id == int(target[1]):
                        self._view, self._active_playlist_id, self._active_folder = "library", None, None
                        self.page_title.setText("LIBRARY")
                        self.navigation.select_playlist(None)
                        self.controller.set_shuffle_playlist(None)
                    self._refresh_folders()
                    self._render_tracks()
        elif target is None:
            create = menu.addAction("Create new playlist")
            selected = menu.exec(self.navigation.tree.viewport().mapToGlobal(position))
            if selected == create:
                self._create_playlist()

    def _selected_track_id(self) -> int | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _play_row(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item:
            self.controller.play_track(int(item.data(Qt.ItemDataRole.UserRole)))

    def _track_menu(self, position: Any) -> None:
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        self.table.selectRow(row)
        track_id = self._selected_track_id()
        if track_id is None:
            return
        track = self.controller.database.get_track(track_id)
        if track is None:
            return
        menu = QMenu(self)
        play = menu.addAction("Play now")
        force = menu.addAction("Force play next")
        playlist_menu = menu.addMenu("Add to Playlist")
        playlist_actions = {
            playlist_menu.addAction(playlist["name"]): int(playlist["id"])
            for playlist in self.controller.database.get_playlists()
        }
        menu.addSeparator()
        exclusion = menu.addAction("Restore to Library" if track["is_excluded"] else "Remove from Playlist (Soft Exclude)")
        reset = menu.addAction("Reset Track Statistics")
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        if selected == play:
            self.controller.play_track(track_id)
        elif selected == force:
            self.controller.force_play_next(track_id)
        elif selected in playlist_actions:
            self.controller.add_track_to_playlist(playlist_actions[selected], track_id)
            self._refresh_folders()
        elif selected == exclusion:
            self.controller.set_excluded(track_id, not bool(track["is_excluded"]))
            self._render_tracks()
        elif selected == reset:
            self.controller.reset_statistics(track_id)
            self._render_tracks()

    def _set_shuffle_mode(self, _index: int) -> None:
        self.controller.set_shuffle_mode(self.playback.mode.currentData())

    def _begin_scrub(self) -> None:
        self._scrubbing = True

    def _seek_to_slider_value(self, value: int) -> None:
        duration = self.controller.audio.duration
        if duration > 0:
            self.controller.audio.seek(duration * value / 1000)

    def _finish_scrub(self) -> None:
        self._scrubbing = False
        duration = self.controller.audio.duration
        if duration > 0:
            self._seek_to_slider_value(self.playback.scrub.value())

    def _update_playback(self) -> None:
        state = self.controller.state()
        current = state["current"]
        self._update_waveform_track(current)
        self.playback.track_title.setText(current["title"] if current else "Nothing playing")
        self.playback.track_artist.setText(current["artist"] if current else "Choose a track to begin")
        self.playback.play_pause.setText("▶" if state["paused"] or current is None else "Ⅱ")
        self.playback.volume.blockSignals(True)
        self.playback.volume.setValue(state["volume"])
        self.playback.volume.blockSignals(False)
        position, duration = state["position"], state["duration"]
        self.playback.volume_percent.setText(f"{state['volume']}%")
        self.playback.elapsed.setText(format_time(position))
        self.playback.remaining.setText(format_time(max(0, duration - position)))
        if not self._scrubbing:
            self.playback.scrub.setValue(int(position / duration * 1000) if duration > 0 else 0)
        self.playback.mode.setCurrentIndex(0 if state["shuffle_mode"] == "entropy" else 1)
        self.waveform.set_playing(bool(current and not state["paused"]))
        self.waveform.set_audio_state(position, duration, 0 if state["muted"] else state["volume"])
        self._update_cover(current)

    def _update_waveform_track(self, current: dict[str, Any] | None) -> None:
        track_id = int(current["id"]) if current else None
        if track_id == self._waveform_track_id:
            return
        self._waveform_track_id = track_id
        self.waveform.clear_envelope()
        if current is None:
            return
        worker = WaveformAnalysisThread(track_id, current["filepath"], self)
        worker.analyzed.connect(self._waveform_analyzed)
        worker.finished.connect(lambda worker=worker: self._discard_analysis_worker(worker))
        self._analysis_workers.append(worker)
        worker.start()

    def _waveform_analyzed(self, track_id: int, envelope: object) -> None:
        if track_id == self._waveform_track_id and isinstance(envelope, list):
            self.waveform.set_envelope(envelope)

    def _discard_analysis_worker(self, worker: WaveformAnalysisThread) -> None:
        if worker in self._analysis_workers:
            self._analysis_workers.remove(worker)

    def _update_cover(self, current: dict[str, Any] | None) -> None:
        track_id = int(current["id"]) if current else None
        if track_id == self._cover_track_id:
            return
        self._cover_track_id = track_id
        if not current:
            self.playback.cover.setPixmap(QPixmap())
            self.playback.cover.setText("EP")
            return
        directory = Path(current["filepath"]).parent
        for name in ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg"):
            image = directory / name
            if image.is_file():
                pixmap = QPixmap(str(image))
                if not pixmap.isNull():
                    self.playback.cover.setText("")
                    self.playback.cover.setPixmap(pixmap.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
                    return
        self.playback.cover.setPixmap(QPixmap())
        self.playback.cover.setText("EP")

    def closeEvent(self, event: Any) -> None:
        self._library_timer.stop()
        self._state_timer.stop()
        if self._update_worker is not None and self._update_worker.isRunning():
            self._update_worker.wait(6000)
        for worker in tuple(self._analysis_workers):
            worker.cancel()
            worker.wait(1500)
        if self._mpris is not None:
            self._mpris.close()
        self.controller.close()
        event.accept()


def run(controller: PlayerController) -> int:
    app = QApplication.instance() or QApplication([])
    window = EntropyWindow(controller)
    window.show()
    return app.exec()