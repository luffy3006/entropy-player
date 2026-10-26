"""Keyboard-driven Textual interface for Entropy Player."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Footer, Header, Input, ProgressBar, Static
from rich.text import Text

from entropy.core.controller import PlayerController

def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


class EntropyTUI(App[None]):
    TITLE = "Entropy Player"
    CSS = """
    Screen { background: $surface; }
    #masthead { height: 3; padding: 1 2; background: #202522; color: #c8e36d; text-style: bold; }
    #search { margin: 1 2 0 2; }
    #tracks { height: 1fr; margin: 1 2; }
    #now-playing { height: 3; padding: 1 2; background: #202522; color: #e4e8e2; }
    #progress { margin: 0 2 1 2; }
    #status { height: 1; color: #98a69a; padding: 0 2; }
    DataTable > .datatable--header { background: #2b342d; color: #d1e985; }
    """
    BINDINGS = [
        Binding("down", "move_down", "Down", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("left", "seek_back", "Seek -5s"),
        Binding("right", "seek_forward", "Seek +5s"),
        Binding("h", "seek_back", "Seek -5s"),
        Binding("l", "seek_forward", "Seek +5s"),
        Binding("-", "volume_down", "Volume -"),
        Binding("+", "volume_up", "Volume +"),
        Binding("space", "play_pause", "Play/Pause"),
        Binding("n", "next_track", "Next"),
        Binding("p", "previous_track", "Previous", show=False),
        Binding("m", "mute", "Mute"),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "focus_library", "Library", show=False),
        Binding("s", "toggle_shuffle", "Shuffle"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, controller: PlayerController) -> None:
        super().__init__()
        self.controller = controller
        self._query = ""
        self._last_track_ids: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Static("ENTROPY  /  LOCAL LIBRARY", id="masthead")
            yield Input(placeholder="Filter tracks, artists, albums  (press / to focus)", id="search")
            yield DataTable(id="tracks", cursor_type="row", zebra_stripes=True)
            yield Static("Nothing playing", id="now-playing")
            yield ProgressBar(total=100, show_eta=False, id="progress")
            yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Title", "Artist", "Album", "Time", "Plays", "Skips", "Weight")
        self.refresh_view()
        table.focus()
        self.set_interval(0.8, self.refresh_view)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self._query = event.value.casefold().strip()
            self.refresh_view()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            self.query_one(DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            self.controller.play_track(int(event.row_key.value))
        except (TypeError, ValueError):
            return

    def refresh_view(self) -> None:
        tracks = self.controller.tracks()
        if self._query:
            tracks = [track for track in tracks if self._query in " ".join((track["title"], track["artist"], track["album"])).casefold()]
        table = self.query_one(DataTable)
        selected_row = table.cursor_row
        selected_track_id = self._last_track_ids[selected_row] if 0 <= selected_row < len(self._last_track_ids) else None
        scroll_y = table.scroll_y
        state = self.controller.state()
        current = state["current"]
        current_id = int(current["id"]) if current else None
        track_ids = [int(track["id"]) for track in tracks]
        same_tracks = track_ids == self._last_track_ids
        if same_tracks:
            for row, track in enumerate(tracks):
                self._update_track_row(table, row, track, current_id)
        else:
            table.clear()
            self._last_track_ids = []
            for track in tracks:
                track_id = int(track["id"])
                self._last_track_ids.append(track_id)
                values = self._track_values(track)
                style = "bold #c8e36d on #26352b" if track_id == current_id else ""
                table.add_row(*(Text(value, style=style) for value in values), key=str(track_id))
            if selected_track_id in self._last_track_ids:
                selected_row = self._last_track_ids.index(selected_track_id)
            self._last_track_ids = track_ids
        if self._last_track_ids:
            table.move_cursor(row=min(max(selected_row, 0), len(self._last_track_ids) - 1))
            if not same_tracks:
                table.scroll_to(y=scroll_y, animate=False, immediate=True)
        label = f"NOW PLAYING   {current['artist']}  /  {current['title']}" if current else "NOTHING PLAYING"
        playback = "PAUSED" if state["paused"] else "PLAYING"
        label += f"    [{state['shuffle_mode'].upper()}]  {playback}  VOL {state['volume']}%"
        self.query_one("#now-playing", Static).update(label)
        progress = self.query_one("#progress", ProgressBar)
        duration = state["duration"]
        progress.update(total=max(1, int(duration)), progress=min(int(state["position"]), int(duration)) if duration else 0)
        status = f"{len(tracks)} tracks  |  {format_time(state['position'])} / {format_time(duration)}  |  Space play/pause  Left/Right seek  -/+ volume  n next  / search"
        self.query_one("#status", Static).update(status)

    @staticmethod
    def _track_values(track: dict[str, object]) -> list[str]:
        return [
            str(track["title"]), str(track["artist"]), str(track["album"]), format_time(float(track["duration"])),
            str(track["play_count"]), str(track["skip_count"]), f"{float(track['weight_percent']):.1f}%",
        ]

    def _update_track_row(self, table: DataTable, row: int, track: dict[str, object], current_id: int | None) -> None:
        style = "bold #c8e36d on #26352b" if int(track["id"]) == current_id else ""
        for column, value in enumerate(self._track_values(track)):
            table.update_cell_at(Coordinate(row, column), Text(value, style=style))

    def action_move_down(self) -> None:
        table = self.query_one(DataTable)
        if self._last_track_ids:
            table.move_cursor(row=min(table.cursor_row + 1, len(self._last_track_ids) - 1))

    def action_move_up(self) -> None:
        table = self.query_one(DataTable)
        if self._last_track_ids:
            table.move_cursor(row=max(0, table.cursor_row - 1))

    def action_seek_back(self) -> None:
        self.controller.audio.seek(self.controller.audio.time_pos - 5)

    def action_seek_forward(self) -> None:
        self.controller.audio.seek(self.controller.audio.time_pos + 5)

    def action_volume_down(self) -> None:
        self._set_volume(self.controller.audio.volume - 5)

    def action_volume_up(self) -> None:
        self._set_volume(self.controller.audio.volume + 5)

    def _set_volume(self, value: int) -> None:
        set_volume = getattr(self.controller, "set_volume", None)
        if set_volume is None:
            self.controller.audio.volume = max(0, min(100, value))
        else:
            set_volume(value)

    def action_play_pause(self) -> None:
        self.controller.play_pause()

    def action_next_track(self) -> None:
        self.controller.next_track()

    def action_previous_track(self) -> None:
        self.controller.previous_track()

    def action_mute(self) -> None:
        self.controller.audio.muted = not self.controller.audio.muted
        self.notify("Muted" if self.controller.audio.muted else "Unmuted", timeout=1)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_library(self) -> None:
        self.query_one(DataTable).focus()

    def action_toggle_shuffle(self) -> None:
        mode = "standard" if self.controller.shuffle_mode == "entropy" else "entropy"
        self.controller.set_shuffle_mode(mode)
        self.notify(f"{mode.title()} shuffle")

    def on_unmount(self) -> None:
        self.controller.close()


def run(controller: PlayerController) -> None:
    EntropyTUI(controller).run()