# Entropy Player

Entropy Player is a local music player with a shared playback core, PyQt6 desktop interface, Textual terminal interface, watched folders, soft exclusions, and history-aware shuffle.

## Requirements

- Python 3.10 or newer
- `libmpv` installed by the operating system (for example, `libmpv2` on Debian/Ubuntu or `mpv-libs` on Fedora)
- A working audio output device for playback

Install the Python package and launch it with:

```sh
python -m pip install .
entropy
```

`entropy` and `entropy --gui` open the desktop interface when a display is available. On a headless session, plain `entropy` defaults to the terminal interface. Use `entropy --cli` or `entropy --tui` to request it explicitly.

## Library

Add a folder from the GUI with **Add folder**. The initial scan indexes `.mp3`, `.flac`, `.ogg`, and `.wav`; later file additions, moves, and deletions are reflected through watchdog. Tags are read when available, with the filename used as a title fallback. Excluding a track only hides it from normal library and shuffle views; it does not remove the file and the exclusion remains set if the file is scanned again.

The SQLite database is stored at `~/.config/entropy/entropy.db`. Play history records completed tracks. Skips are recorded only when the next-track action occurs before 30 seconds have elapsed.

## Shuffle

Entropy shuffle calculates per-track weight from completed plays in the rolling day, week, and month windows and early skips:

$$W_i = \frac{1}{(1 + 5P_{day} + 2P_{week} + 0.5P_{month})(1 + 1.5S_i)}$$

The displayed percentage is the track's current weight normalized across the visible library. The GUI offers both entropy-weighted and standard shuffle; press `s` in the TUI to switch modes.

## Controls

In the TUI, use `j`/`k` to move, `Enter` to play the selected row, `Space` to play or pause, `n`/`p` for next and previous, `m` to mute, `/` to search, and `s` to switch shuffle mode. The GUI supports track search, double-click playback, right-click track actions, and right-click removal of watched folders.

## Development

Run the core tests with:

```sh
python -m unittest discover -s tests
```