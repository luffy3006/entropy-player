"""Reusable desktop controls for the library and playback bar."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


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
        self.watched_item = QTreeWidgetItem(["Watched Folders"])
        self.tree.addTopLevelItem(self.watched_item)
        self.playlists_item = QTreeWidgetItem(["Playlists"])
        self.tree.addTopLevelItem(self.playlists_item)
        self.library_item.setData(0, Qt.ItemDataRole.UserRole, "library")
        self.tree.topLevelItem(1).setData(0, Qt.ItemDataRole.UserRole, "excluded")
        self.watched_item.setData(0, Qt.ItemDataRole.UserRole, "watched")
        self.playlists_item.setData(0, Qt.ItemDataRole.UserRole, "playlists")
        self.tree.expandAll()
        layout.addWidget(self.tree, 1)
        controls = QHBoxLayout()
        self.add_folder_button = QPushButton("+ Add folder")
        self.add_folder_button.setStyleSheet("color: #c8e36d; padding: 7px 4px; text-align: left;")
        controls.addWidget(self.add_folder_button)
        self.add_playlist_button = QPushButton("+ Playlist")
        self.add_playlist_button.setStyleSheet("color: #c8e36d; padding: 7px 4px; text-align: left;")
        controls.addWidget(self.add_playlist_button)
        layout.addLayout(controls)

    def set_folders(self, folders: list[str]) -> None:
        self.watched_item.takeChildren()
        for folder in folders:
            item = QTreeWidgetItem([folder.rsplit("/", 1)[-1] or folder])
            item.setToolTip(0, folder)
            item.setData(0, Qt.ItemDataRole.UserRole, ("folder", folder))
            self.watched_item.addChild(item)
        self.watched_item.setExpanded(True)

    def set_playlists(self, playlists: list[dict[str, Any]]) -> None:
        self.playlists_item.takeChildren()
        for playlist in playlists:
            item = QTreeWidgetItem([f"{playlist['name']}  ({playlist['track_count']})"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("playlist", int(playlist["id"]), playlist["name"]))
            self.playlists_item.addChild(item)
        self.playlists_item.setExpanded(True)


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
        self.horizontalHeader().setStretchLastSection(True)
        self.setSortingEnabled(True)

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


class PlaybackBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("QFrame { border-top: 1px solid #343c36; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        seek_row = QHBoxLayout()
        self.elapsed = QLabel("0:00")
        self.scrub = QSlider(Qt.Orientation.Horizontal)
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
        self.cover.setStyleSheet("background: #344339; color: #c8e36d; font-weight: 800; border-radius: 3px;")
        info = QVBoxLayout()
        self.track_title = QLabel("Nothing playing")
        self.track_artist = QLabel("Choose a track to begin")
        self.track_artist.setStyleSheet("color: #91a095; font-size: 11px;")
        info.addWidget(self.track_title)
        info.addWidget(self.track_artist)
        control_row.addWidget(self.cover)
        control_row.addLayout(info)
        control_row.addStretch(1)
        self.previous = QPushButton("|<")
        self.play_pause = QPushButton("▶")
        self.next = QPushButton(">|")
        for control in (self.previous, self.play_pause, self.next):
            control.setFlat(True)
            control.setFixedSize(38, 34)
            control_row.addWidget(control)
        control_row.addSpacing(18)
        self.mode = QComboBox()
        self.mode.addItem("Entropy weighted", "entropy")
        self.mode.addItem("Standard shuffle", "standard")
        control_row.addWidget(self.mode)
        control_row.addWidget(QLabel("Vol"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(100)
        control_row.addWidget(self.volume)
        layout.addLayout(control_row)