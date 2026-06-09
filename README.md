# VidSimp

VidSimp is a robust, production-ready video player application for Linux, specifically optimized for Arch Linux and the Steam Deck. It is built as a clean, single-file Python script (`vidsimp.py`) with its dependencies clearly defined.

## Key Features

- **Target Environment:** Built using `PyQt6` and `python-vlc` for cross-platform support with deep native VLC integration on Linux (`set_xwindow`).
- **UI Stacking Architecture:**
  - **Top:** A black Video Canvas that expands dynamically.
  - **Bottom:** The Control Panel which includes a Seek Slider, a horizontal Carousel (`QListWidget`), and the Controller Row (Open Folder, Play/Pause, Volume Slider).
- **Steam Deck & Touchscreen Optimizations:**
  - Buttons and list items have a generous `min-height` and `min-width` of 45px.
  - Elements have `Qt.FocusPolicy.StrongFocus` so they can be seamlessly navigated via a controller's D-Pad when added as a non-Steam game.
- **Dynamic Video Carousel:**
  - Automatically extracts and displays video thumbnails using `ffmpeg` asynchronously via a background thread (`QThread`).
  - Filenames wrap cleanly underneath the thumbnails.
- **Persistent Directory Memory:**
  - Integrated `QSettings` to remember the last opened video directory. Upon booting, it will automatically populate the carousel with valid video files.
- **Playback & Continuous Queue:**
  - Automatic directory scanning for common video formats (`.mp4`, `.mkv`, etc.).
  - A background `QTimer` detects when the video ends naturally (`vlc.State.Ended`) and auto-increments to the next item in the carousel to begin playback.
- **Fullscreen Toggling:**
  - 'F' and 'F11' keys are mapped to toggle fullscreen. When engaged, the entire Bottom Control Panel completely disappears, giving the Video Canvas 100% of the screen.

## How to Run

1. Install the Python dependencies:
```bash
pip install -r requirements.txt
```

*Note: `ffmpeg` is required to be installed on your system for thumbnail extraction.*

2. Run the application:
```bash
python vidsimp.py
```

> [!TIP]
> When adding this as a non-Steam game on SteamOS, consider using a simple bash script to launch it:
> `#!/bin/bash`
> `/path/to/your/venv/bin/python /path/to/VidSimp/vidsimp.py`
> And point the Steam shortcut to the bash script. This ensures the environment is loaded correctly in Game Mode!
