"""Reusable desktop controls for the library and playback bar."""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSizePolicy, QSlider, QStyle, QStyleOptionSlider, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


class ClickSlider(QSlider):
    clicked = pyqtSignal(int)

    def _value_at(self, x_position: float) -> int:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        span = max(0, groove.width() - handle.width())
        position = int(x_position - groove.x() - handle.width() / 2)
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position, span, option.upsideDown)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._value_at(event.position().x()))
            self.setSliderDown(True)
            self.clicked.emit(self.value())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if self.isSliderDown() and event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self._value_at(event.position().x()))
            self.clicked.emit(self.value())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setValue(self._value_at(event.position().x()))
            self.setSliderDown(False)
            self.clicked.emit(self.value())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class LibraryNavigation(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(230)
        layout = QVBoxLayout(self)
        brand = QLabel("ENTROPY")
        brand.setStyleSheet("font-size: 17px; font-weight: 800; color: #c8e36d; padding: 8px 4px;")
        layout.addWidget(brand)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.library_item = QTreeWidgetItem(["Library"])
        self.tree.addTopLevelItem(self.library_item)
        self.tree.addTopLevelItem(QTreeWidgetItem(["Excluded Tracks"]))
        self.playlists_item = QTreeWidgetItem(["Playlists"])
        self.tree.addTopLevelItem(self.playlists_item)
        self.library_item.setData(0, Qt.ItemDataRole.UserRole, "library")
        self.tree.topLevelItem(1).setData(0, Qt.ItemDataRole.UserRole, "excluded")
        self.playlists_item.setData(0, Qt.ItemDataRole.UserRole, "playlists")
        self.tree.expandAll()
        layout.addWidget(self.tree, 1)
        controls = QVBoxLayout()
        controls.setSpacing(6)
        self.add_folder_button = QPushButton("+  Add folder to playlist")
        self.add_folder_button.setObjectName("addWatchedFolder")
        self.add_folder_button.setMinimumHeight(36)
        self.add_folder_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.add_folder_button.setEnabled(False)
        self.add_folder_button.setVisible(False)
        controls.addWidget(self.add_folder_button)
        self.add_playlist_button = QPushButton("+  Add playlist")
        self.add_playlist_button.setObjectName("addPlaylist")
        self.add_playlist_button.setMinimumHeight(36)
        self.add_playlist_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        controls.addWidget(self.add_playlist_button)
        self.reset_shuffle_button = QPushButton("Reset shuffle history")
        self.reset_shuffle_button.setObjectName("resetShuffleHistory")
        self.reset_shuffle_button.setMinimumHeight(34)
        self.reset_shuffle_button.setToolTip("Clear completed-play and early-skip history used by Entropy shuffle")
        controls.addWidget(self.reset_shuffle_button)
        layout.addLayout(controls)

    def set_playlists(self, playlists: list[dict[str, Any]]) -> None:
        self.playlists_item.takeChildren()
        for playlist in playlists:
            item = QTreeWidgetItem([playlist["name"]])
            item.setToolTip(
                0,
                f"{playlist['track_count']} manually added tracks; {playlist.get('folder_count', 0)} watched folders",
            )
            item.setData(0, Qt.ItemDataRole.UserRole, ("playlist", int(playlist["id"]), playlist["name"]))
            self.playlists_item.addChild(item)
            for folder in playlist.get("folders", []):
                name = folder.rstrip("/").rsplit("/", 1)[-1] or folder
                folder_item = QTreeWidgetItem([f"Folder · {name}"])
                folder_item.setToolTip(0, f"Watched folder: {folder}")
                folder_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", folder, int(playlist["id"])))
                item.addChild(folder_item)
        self.playlists_item.setExpanded(True)

    def select_playlist(self, playlist_id: int | None) -> None:
        visible = playlist_id is not None
        self.add_folder_button.setVisible(visible)
        self.add_folder_button.setEnabled(visible)


class TrackTable(QTableWidget):
    headers = ["Title", "Artist", "Album", "Duration", "Plays", "Skips", "Weight"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(self.headers), parent)
        self.setHorizontalHeaderLabels(self.headers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._column_ratios = (0.40, 0.16, 0.16, 0.08, 0.06, 0.06, 0.08)
        self.setSortingEnabled(True)
        self._resize_columns()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._resize_columns()

    def _resize_columns(self) -> None:
        available_width = self.viewport().width()
        if available_width <= 0:
            return
        widths = [int(available_width * ratio) for ratio in self._column_ratios]
        widths[0] += available_width - sum(widths)
        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)

    def set_tracks(self, tracks: list[dict[str, Any]]) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            values = [
                str(track["title"]), str(track["artist"]), str(track["album"]),
                format_time(track["duration"]), str(track["play_count"]), str(track["skip_count"]),
                f"{track.get('weight_percent', 0.0):.1f}%",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column >= 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(track["id"]))
                self.setItem(row, column, item)
        self.setSortingEnabled(True)

    def set_current_track(self, track_id: int | None) -> None:
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            is_current = item is not None and item.data(Qt.ItemDataRole.UserRole) == track_id
            for column in range(self.columnCount()):
                cell = self.item(row, column)
                if cell is not None:
                    cell.setBackground(QColor("#254a36") if is_current else QColor())
                    cell.setForeground(QColor("#d7f3a1") if is_current else QColor())


class WaveformWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(66)
        self.setMaximumHeight(76)
        self._phase = 0.0
        self._playing = False
        self._position = 0.0
        self._duration = 0.0
        self._volume = 1.0
        self._envelope: list[tuple[float, float]] = []
        self._accent = QColor("#42b9f5")
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._animate)

    def set_playing(self, playing: bool) -> None:
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def set_audio_state(self, position: float, duration: float, volume: int) -> None:
        self._position = max(0.0, position)
        self._duration = max(0.0, duration)
        self._volume = max(0.0, min(1.0, volume / 100.0))
        self.update()

    def set_envelope(self, envelope: list[tuple[float, float]]) -> None:
        self._envelope = envelope
        self.update()

    def clear_envelope(self) -> None:
        self._envelope = []
        self.update()

    def set_accent(self, color: str) -> None:
        self._accent = QColor(color)
        self.update()

    def _animate(self) -> None:
        self._phase += 0.13
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#334353"), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.setPen(Qt.PenStyle.NoPen)
        count = max(1, self.width() // 4)
        center = self.height() / 2
        accent = self._accent
        played = QColor(accent).lighter(150)
        bass_color = QColor(accent).lighter(118)
        for index in range(count):
            x = index * self.width() / count
            if self._envelope:
                sample_index = min(len(self._envelope) - 1, index * len(self._envelope) // count)
                amplitude, bass = self._envelope[sample_index]
            else:
                amplitude = 0.12 + 0.1 * abs(math.sin(index * 0.071))
                bass = 0.0
            pulse = 1.0 + (0.045 * math.sin(self._phase * 2 + index * 0.07) if self._playing else 0.0)
            height = max(2.0, (2.0 + amplitude * self._volume * (self.height() * 0.78)) * pulse)
            x_position = int(x)
            bar_width = max(2, int(self.width() / count) - 1)
            played_until = self._position / self._duration if self._duration > 0 else 0.0
            color = played if index / count <= played_until else accent
            painter.setBrush(bass_color if bass > amplitude * 0.52 else color)
            painter.drawRoundedRect(x_position, int(center - height / 2), bar_width, int(height), 1, 1)
        if self._duration > 0:
            playhead_x = int(self.width() * min(1.0, self._position / self._duration))
            painter.setPen(QPen(played, 1))
            painter.drawLine(playhead_x, 3, playhead_x, self.height() - 3)
        painter.end()


class PlaybackBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playbackBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        seek_row = QHBoxLayout()
        self.elapsed = QLabel("0:00")
        self.scrub = ClickSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, 1000)
        self.remaining = QLabel("0:00")
        seek_row.addWidget(self.elapsed)
        seek_row.addWidget(self.scrub, 1)
        seek_row.addWidget(self.remaining)
        layout.addLayout(seek_row)
        control_row = QHBoxLayout()
        self.cover = QLabel("EP")
        self.cover.setFixedSize(44, 44)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet("background: #1e3850; color: #42b9f5; font-weight: 800; border-radius: 3px;")
        info = QVBoxLayout()
        self.track_title = QLabel("Nothing playing")
        self.track_artist = QLabel("Choose a track to begin")
        self.track_artist.setStyleSheet("color: #92a6ba; font-size: 11px;")
        info.addWidget(self.track_title)
        info.addWidget(self.track_artist)
        control_row.addWidget(self.cover)
        control_row.addLayout(info)
        control_row.addStretch(1)
        self.previous = QPushButton("|◀")
        self.play_pause = QPushButton("▶")
        self.play_pause.setObjectName("primary")
        self.next = QPushButton("▶|")
        for control in (self.previous, self.play_pause, self.next):
            control.setFlat(True)
            control.setMinimumSize(42, 38)
            control.setMaximumWidth(48)
            control.setToolTip({self.previous: "Previous track", self.play_pause: "Play or pause", self.next: "Next track"}[control])
            control_row.addWidget(control)
        control_row.addSpacing(18)
        self.mode = QComboBox()
        self.mode.addItem("Entropy", "entropy")
        self.mode.addItem("Standard shuffle", "standard")
        control_row.addWidget(self.mode)
        volume_control = QVBoxLayout()
        volume_control.setSpacing(1)
        volume_heading = QHBoxLayout()
        volume_label = QLabel("Volume")
        volume_label.setStyleSheet("font-size: 10px; font-weight: 700;")
        volume_heading.addWidget(volume_label)
        self.volume_percent = QLabel("50%")
        self.volume_percent.setMinimumWidth(36)
        self.volume_percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        volume_heading.addWidget(self.volume_percent)
        volume_control.addLayout(volume_heading)
        self.volume = ClickSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("volumeSlider")
        self.volume.setRange(0, 100)
        self.volume.setMinimumWidth(145)
        self.volume.setMaximumWidth(190)
        self.volume.setMinimumHeight(24)
        volume_control.addWidget(self.volume)
        control_row.addLayout(volume_control)
        layout.addLayout(control_row)