# Entropy Player

Entropy Player is a local music player with a shared playback core, PyQt6 desktop interface, Textual terminal interface, watched folders, soft exclusions, and history-aware shuffle.

## Requirements

- Python 3.10 or newer
- `libmpv` installed by the operating system (for example, `mpv` on Arch or `mpv`/`libmpv2` on Debian/Ubuntu)
- A working audio output device for playback

Install the Python package and launch it with:

```sh
python -m pip install .
entropy
```

`entropy` and `entropy --gui` open the desktop interface when a display is available. On a headless session, plain `entropy` defaults to the terminal interface. Use `entropy --cli` or `entropy --tui` to request it explicitly.

## Library

Create a playlist, select it, then choose **Add folder to playlist** (or right-click that playlist and add a folder). Watched folders appear beneath their owning playlist and their tracks appear in that playlist view. Deleting a playlist stops watching its folders and removes its playlist membership, but leaves media files and library entries intact. Existing watched folders are migrated into an **Imported folders** playlist. The initial scan indexes `.mp3`, `.flac`, `.ogg`, `.wav`, `.mp4`, and `.mkv`; MP4 and MKV files play with their video stream disabled, as audio-only items. Tags are read when available, with the filename used as a title fallback. Excluding a track only hides it from normal library and shuffle views; it does not remove the file and the exclusion remains set if the file is scanned again.

The SQLite database is stored at `~/.config/entropy/entropy.db`. Play history records completed tracks. Skips are recorded only when the next-track action occurs before 30 seconds have elapsed.

## Shuffle

Entropy shuffle calculates per-track weight from completed plays in the rolling day, week, and month windows and early skips:

$$W_i = \frac{1}{(1 + 5P_{day} + 2P_{week} + 0.5P_{month})(1 + 1.5S_i)}$$

The displayed percentage is the track's current weight normalized across the visible library. The GUI offers both entropy-weighted and standard shuffle; press `s` in the TUI to switch modes.

## Desktop Appearance And Updates

The GUI defaults to the blue-on-black **Strawberry Blue** theme. Use the theme selector to switch to Midnight Teal, Classic Green, or Light; the choice is stored in the desktop settings. The waveform is decoded from the track's audio in the background, shows amplitude and bass response, marks playback progress, and scales with volume.

The GUI checks GitHub releases in the background at most once per day and includes a **Check updates** button for an immediate check. Checks need an internet connection. When a release is available, the app offers its GitHub release page; updates are downloaded and installed through the package manager or the installation method you chose.

## Linux Packages

The repository includes a scalable application icon and desktop entry in `packaging/`, an Arch `PKGBUILD` in `packaging/arch/`, and Debian packaging metadata in `debian/`.

### Arch Linux

Install the build tools and native audio engine, then build the package from the checkout:

```sh
sudo pacman -S --needed base-devel mpv python-build python-installer python-setuptools python-wheel
cd packaging/arch
makepkg -si
```

The package recipe fetches the public `main` branch. For a reproducible release build, change its source to a tagged GitHub release and update `pkgver` before publishing the package.

### Debian And Ubuntu

Install the packaging tools and runtime dependencies, then build a local `.deb`:

```sh
sudo apt install build-essential debhelper dh-python python3-all python3-build python3-installer python3-setuptools python3-wheel mpv python3-mutagen python3-mpv python3-pyqt6 python3-textual python3-watchdog
dpkg-buildpackage -us -uc -b
```

The generated package is written to the parent directory. Install it with `sudo apt install ../entropy-player_*.deb`. Package names can vary by Debian/Ubuntu release; use the distribution's equivalent Python modules if a dependency is unavailable in its repositories.

Before publishing to an official distro repository, choose and add the project's license and replace maintainer metadata in `debian/control` and `debian/changelog`. No license was supplied with this project, so the Arch recipe deliberately marks it unknown.

## Controls

In the TUI, use `Up`/`Down` or `j`/`k` to move, `Enter` to play the selected row, `Space` to play or pause, `n`/`p` for next and previous, `m` to mute, `/` to search, and `s` to switch shuffle mode. Press `Enter` in search to return keyboard focus to the track list.

In the GUI, click or drag anywhere on the seek bar to set playback position and click or drag the volume bar to change volume, as in VLC. `Space` toggles play/pause, `Left`/`Right` seek backward/forward by five seconds, and `Up`/`Down` navigate the track table. Use `Ctrl`+`Up`/`Down` to raise or lower volume by five percent; those volume shortcuts also work when the track table is focused. These shortcuts do not intercept arrow keys or Space while editing search text. The GUI also supports track search, double-click playback, right-click track actions, and playlist deletion. On Linux, earphone and desktop media buttons use the MPRIS service. mpv queues the next selection for a gapless handoff when a track finishes.

## Development

Run the core tests with:

```sh
python -m unittest discover -s tests
```