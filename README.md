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

The SQLite database is stored at `~/.config/entropy/entropy.db`; the selected volume is saved in `~/.config/entropy/settings.json` and shared between the GUI and TUI. Play history records completed tracks. Skips are recorded only when the next-track action occurs before 30 seconds have elapsed.

## Shuffle

Entropy shuffle combines rolling play pressure, a time-decaying early-skip rate, a 1.25 temperature, and a four-track recent-play cooldown. Let $N_i$ be completed plays, $R_i$ be the sum of each early skip discounted by $1/(1+age/7 days)$, and $q_i=(R_i+1)/(N_i+5)$ be the smoothed skip rate with a 20% prior. The raw weight is:

$$W_i = \left[\frac{1}{(1 + 5P_{day} + 2P_{week} + 0.5P_{month})(1 + 4\max(0, q_i - 0.20))}\right]^{1/1.25}$$

The last four played tracks are excluded when alternatives exist; the cooldown relaxes automatically for small libraries. When a playlist is selected, shuffle candidates stay within that playlist. The displayed percentage is each candidate's current weight normalized across the active collection. The GUI offers both entropy-weighted and standard shuffle; press `s` in the TUI to switch modes. The GUI's **Reset shuffle history** action clears completed-play and early-skip history and the in-memory cooldown, while preserving tracks, playlists, and watched folders.

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

In the TUI, use `Up`/`Down` or `j`/`k` to move through the scrollable track list, `Enter` to play the selected row, `Space` to play or pause, `Left`/`Right` (or `h`/`l`) to seek, `-`/`+` to change volume, `n`/`p` for next and previous, `m` to mute, `/` to search, and `s` to switch shuffle mode. The playing track is highlighted in both interfaces. Press `Enter` in search to return keyboard focus to the track list.

In the GUI, click or drag anywhere on the seek bar to set playback position and click or drag the volume bar to change volume, as in VLC. `Space` toggles play/pause, `Left`/`Right` seek backward/forward by five seconds, and `Up`/`Down` navigate the track table. Use `Ctrl`+`Up`/`Down` to raise or lower volume by five percent; those volume shortcuts also work when the track table is focused. These shortcuts do not intercept arrow keys or Space while editing search text. The GUI also supports track search, double-click playback, right-click track actions, and playlist deletion. On Linux, earphone and desktop media buttons use the MPRIS service. mpv queues the next selection for a gapless handoff when a track finishes.

## Development

The v0.1.2 maintenance release hardens mpv end-file reason handling, prevents manual transitions from being counted as natural completions, limits consecutive playback-error recovery, and debounces volume preference writes. The Arch recipe now targets a versioned release archive.

Install the test/lint dependencies and run the same checks as CI:

```sh
python -m pip install -e ".[test]"
QT_QPA_PLATFORM=offscreen dbus-run-session -- python -m unittest discover -s tests -v
python scripts/check_version.py
ruff check entropy tests scripts
```
