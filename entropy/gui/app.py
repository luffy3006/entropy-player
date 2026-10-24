"""PyQt6 desktop interface for Entropy Player."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QMainWindow, QMenu, QMessageBox, QVBoxLayout, QWidget

from entropy.core.controller import PlayerController
from entropy.gui.styles import APP_STYLE
from entropy.gui.widgets import LibraryNavigation, PlaybackBar, TrackTable, format_time


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
        self.setWindowTitle("Entropy Player")
        self.resize(1200, 760)
        self.setMinimumSize(850, 560)
        self.setStyleSheet(APP_STYLE)

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
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tracks, artists, albums")
        self.search.setFixedWidth(280)
        heading.addWidget(self.search)
        center_layout.addLayout(heading)
        self.table = TrackTable()
        center_layout.addWidget(self.table, 1)
        content.addWidget(center, 1)
        root_layout.addLayout(content, 1)
        self.playback = PlaybackBar()
        root_layout.addWidget(self.playback)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")

        self.navigation.tree.itemClicked.connect(self._navigate)
        self.navigation.add_folder_button.clicked.connect(self._choose_folder)
        self.navigation.add_playlist_button.clicked.connect(self._create_playlist)
        self.search.textChanged.connect(self._render_tracks)
        self.table.cellDoubleClicked.connect(self._play_row)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._track_menu)
        self.playback.play_pause.clicked.connect(self.controller.play_pause)
        self.playback.next.clicked.connect(self.controller.next_track)
        self.playback.previous.clicked.connect(self.controller.previous_track)
        self.playback.volume.valueChanged.connect(lambda value: setattr(self.controller.audio, "volume", value))
        self.playback.mode.currentIndexChanged.connect(self._set_shuffle_mode)
        self.playback.scrub.sliderPressed.connect(self._begin_scrub)
        self.playback.scrub.sliderReleased.connect(self._finish_scrub)
        self.navigation.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.navigation.tree.customContextMenuRequested.connect(self._folder_menu)

        self._library_timer = QTimer(self)
        self._library_timer.timeout.connect(self._render_tracks)
        self._library_timer.start(1800)
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._update_playback)
        self._state_timer.start(300)
        self._refresh_folders()
        self._render_tracks()
        self._update_playback()

    @staticmethod
    def _label(text: str, object_name: str):
        from PyQt6.QtWidgets import QLabel

        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def _refresh_folders(self) -> None:
        self.navigation.set_folders(self.controller.database.get_watched_folders())
        self.navigation.set_playlists(self.controller.database.get_playlists())

    def _navigate(self, item: Any, _column: int) -> None:
        target = item.data(0, Qt.ItemDataRole.UserRole)
        if target == "library":
            self._view, self._active_folder, self._active_playlist_id = "library", None, None
            self.page_title.setText("LIBRARY")
        elif target == "excluded":
            self._view, self._active_folder, self._active_playlist_id = "excluded", None, None
            self.page_title.setText("EXCLUDED TRACKS")
        elif isinstance(target, tuple) and target[0] == "folder":
            self._view, self._active_folder, self._active_playlist_id = "folder", target[1], None
            self.page_title.setText(item.text(0).upper())
        elif isinstance(target, tuple) and target[0] == "playlist":
            self._view, self._active_folder, self._active_playlist_id = "playlist", None, target[1]
            self.page_title.setText(target[2].upper())
        elif target in {"watched", "playlists"}:
            self.statusBar().showMessage("Choose a watched folder." if target == "watched" else "No playlists yet.", 2500)
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
        folder = QFileDialog.getExistingDirectory(self, "Add watched music folder")
        if folder:
            try:
                self.controller.add_watch_folder(folder)
                self._refresh_folders()
                self._render_tracks()
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.warning(self, "Could not watch folder", str(exc))

    def _create_playlist(self) -> None:
        name, accepted = QInputDialog.getText(self, "New playlist", "Playlist name")
        if accepted and name.strip():
            try:
                self.controller.create_playlist(name)
                self._refresh_folders()
            except Exception as exc:
                QMessageBox.warning(self, "Could not create playlist", str(exc))

    def _folder_menu(self, position: Any) -> None:
        item = self.navigation.tree.itemAt(position)
        target = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(target, tuple) or target[0] != "folder":
            return
        menu = QMenu(self)
        remove = menu.addAction("Stop watching folder")
        if menu.exec(self.navigation.tree.viewport().mapToGlobal(position)) == remove:
            self.controller.remove_watch_folder(target[1])
            self._refresh_folders()

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

    def _finish_scrub(self) -> None:
        self._scrubbing = False
        duration = self.controller.audio.duration
        if duration > 0:
            self.controller.audio.seek(duration * self.playback.scrub.value() / 1000)

    def _update_playback(self) -> None:
        state = self.controller.state()
        current = state["current"]
        self.playback.track_title.setText(current["title"] if current else "Nothing playing")
        self.playback.track_artist.setText(current["artist"] if current else "Choose a track to begin")
        self.playback.play_pause.setText("▶" if state["paused"] or current is None else "Ⅱ")
        self.playback.volume.blockSignals(True)
        self.playback.volume.setValue(state["volume"])
        self.playback.volume.blockSignals(False)
        position, duration = state["position"], state["duration"]
        self.playback.elapsed.setText(format_time(position))
        self.playback.remaining.setText(format_time(max(0, duration - position)))
        if not self._scrubbing:
            self.playback.scrub.setValue(int(position / duration * 1000) if duration > 0 else 0)
        self.playback.mode.setCurrentIndex(0 if state["shuffle_mode"] == "entropy" else 1)
        self._update_cover(current)

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
        self.controller.close()
        event.accept()


def run(controller: PlayerController) -> int:
    app = QApplication.instance() or QApplication([])
    window = EntropyWindow(controller)
    window.show()
    return app.exec()