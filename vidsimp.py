import os
import subprocess
import sys
import tempfile

import vlc
from PyQt6.QtCore import QSettings, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
                             QListView, QListWidget, QListWidgetItem,
                             QMainWindow, QPushButton, QSlider, QVBoxLayout,
                             QWidget)


class ThumbnailLoader(QThread):
    thumbnail_loaded = pyqtSignal(str, str)  # file_path, temp_image_path

    def __init__(self, directory, files, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.files = files

    def run(self):
        for f in self.files:
            file_path = os.path.join(self.directory, f)
            temp_image_path = self.generate_thumbnail(file_path)
            if temp_image_path:
                self.thumbnail_loaded.emit(file_path, temp_image_path)

    def generate_thumbnail(self, video_path):
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)

            command = [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-ss",
                "00:00:05",
                "-vframes",
                "1",
                "-q:v",
                "2",
                "-vf",
                "scale=160:-1",
                temp_path,
            ]

            subprocess.run(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
            )

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path
            else:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return None
        except Exception as e:
            print(f"Failed to generate thumbnail for {video_path}: {e}")
            return None


class VidSimp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VidSimp")
        self.resize(1024, 768)

        # Settings for persistence
        self.settings = QSettings("VidSimp", "Player")

        # VLC Initialization
        # We include some common flags, like --no-xlib which is sometimes needed for multithreading
        self.vlc_instance = vlc.Instance("--no-xlib")
        self.media_player = self.vlc_instance.media_player_new()

        self.is_fullscreen = False
        self.current_directory = ""
        self.supported_extensions = (
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".flv",
            ".wmv",
            ".webm",
            ".m4v",
        )

        self.init_ui()
        self.setup_timers()
        self.load_last_directory()

    def init_ui(self):
        # Global Stylesheet for Touchscreen / Steam Deck (45px minimums)
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #FFFFFF;
                font-family: sans-serif;
            }
            QPushButton {
                min-height: 45px;
                min-width: 45px;
                background-color: #2A2A2A;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:focus, QPushButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #0078D7;
            }
            QSlider::groove:horizontal {
                height: 12px;
                background: #333;
                border-radius: 6px;
            }
            QSlider::handle:horizontal {
                background: #0078D7;
                width: 24px;
                height: 24px;
                margin: -6px 0;
                border-radius: 12px;
            }
            QSlider::handle:horizontal:focus {
                background: #50A0FF;
            }
            QListWidget {
                min-height: 160px;
                max-height: 160px;
                background-color: #1E1E1E;
                border: none;
            }
            QListWidget::item {
                min-width: 170px;
                max-width: 170px;
                padding: 5px;
                margin: 5px;
                background-color: #2A2A2A;
                border-radius: 5px;
            }
            QListWidget::item:selected, QListWidget::item:focus {
                background-color: #0078D7;
            }
        """)

        # Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Top Section: Video Canvas
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setSizePolicy(
            self.video_frame.sizePolicy().Policy.Expanding,
            self.video_frame.sizePolicy().Policy.Expanding,
        )
        self.main_layout.addWidget(self.video_frame, stretch=1)

        # Set VLC Window
        if sys.platform.startswith("linux"):  # for Linux using the X Server
            self.media_player.set_xwindow(int(self.video_frame.winId()))
        elif sys.platform == "win32":  # for Windows
            self.media_player.set_hwnd(int(self.video_frame.winId()))
        elif sys.platform == "darwin":  # for MacOS
            self.media_player.set_nsobject(int(self.video_frame.winId()))

        # Bottom Section: Control Panel
        self.control_panel = QWidget()
        self.control_layout = QVBoxLayout(self.control_panel)
        self.control_layout.setContentsMargins(15, 15, 15, 15)
        self.control_layout.setSpacing(10)

        # 1. Time Slider
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setMaximum(1000)
        self.time_slider.setToolTip("Seek")
        self.time_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.time_slider.sliderMoved.connect(self.set_position)
        self.control_layout.addWidget(self.time_slider)

        # 2. Carousel
        self.carousel = QListWidget()
        self.carousel.setViewMode(QListView.ViewMode.IconMode)
        self.carousel.setFlow(QListView.Flow.LeftToRight)
        self.carousel.setWrapping(False)
        self.carousel.setWordWrap(True)
        self.carousel.setIconSize(QSize(160, 90))
        self.carousel.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.carousel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.carousel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.carousel.itemActivated.connect(
            self.play_selected_video
        )  # Handles double click or Enter/A
        self.control_layout.addWidget(self.carousel)

        # 3. Controller Row
        self.controller_row = QWidget()
        self.controller_row_layout = QHBoxLayout(self.controller_row)
        self.controller_row_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_open = QPushButton("Open Folder")
        self.btn_open.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_open.clicked.connect(self.open_folder)

        self.btn_play_pause = QPushButton("Play")
        self.btn_play_pause.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setToolTip("Volume")
        self.volume_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.volume_slider.setMaximumWidth(200)
        self.volume_slider.valueChanged.connect(self.set_volume)

        self.controller_row_layout.addWidget(self.btn_open)
        self.controller_row_layout.addWidget(self.btn_play_pause)
        self.controller_row_layout.addStretch()
        self.controller_row_layout.addWidget(self.volume_slider)

        self.control_layout.addWidget(self.controller_row)
        self.main_layout.addWidget(self.control_panel)

    def setup_timers(self):
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(1000)
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start()

    def load_last_directory(self):
        last_dir = self.settings.value("last_directory", "")
        if last_dir and os.path.exists(last_dir):
            self.current_directory = last_dir
            self.populate_carousel()
            if self.carousel.count() > 0:
                self.carousel.setCurrentRow(0)
                # Queue the first video without playing it
                self.play_selected_video(self.carousel.item(0), auto_play=False)

    def open_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Video Folder", self.current_directory
        )
        if folder_path:
            self.current_directory = folder_path
            self.settings.setValue("last_directory", folder_path)
            self.populate_carousel()

    def populate_carousel(self):
        self.carousel.clear()
        if not self.current_directory:
            return

        try:
            files = [
                f
                for f in os.listdir(self.current_directory)
                if f.lower().endswith(self.supported_extensions)
            ]
            # Sort chronologically or alphabetically. Alphabetical provides a consistent experience.
            files.sort()

            for f in files:
                item = QListWidgetItem(f)
                # Store full path in UserRole for easy playback access
                file_path = os.path.join(self.current_directory, f)
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.carousel.addItem(item)

            if self.carousel.count() > 0:
                self.carousel.setCurrentRow(0)

            # Start background thread to load thumbnails
            if hasattr(self, "thumbnail_loader") and self.thumbnail_loader.isRunning():
                self.thumbnail_loader.terminate()
                self.thumbnail_loader.wait()

            self.thumbnail_loader = ThumbnailLoader(self.current_directory, files, self)
            self.thumbnail_loader.thumbnail_loaded.connect(self.on_thumbnail_loaded)
            self.thumbnail_loader.start()

        except Exception as e:
            print(f"Error loading directory: {e}")

    def on_thumbnail_loaded(self, file_path, temp_image_path):
        for i in range(self.carousel.count()):
            item = self.carousel.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                icon = QIcon(temp_image_path)
                item.setIcon(icon)
                break
        try:
            os.remove(temp_image_path)
        except OSError:
            pass

    def play_selected_video(self, item=None, auto_play=True):
        if item is None:
            item = self.carousel.currentItem()
        if item is None:
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        media = self.vlc_instance.media_new(file_path)
        self.media_player.set_media(media)

        if auto_play:
            self.media_player.play()
            self.btn_play_pause.setText("Pause")
        else:
            self.btn_play_pause.setText("Play")

    def toggle_play_pause(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.btn_play_pause.setText("Play")
        else:
            # If no media is currently loaded but we have an item in carousel
            if self.media_player.get_media() is None and self.carousel.currentItem():
                self.play_selected_video()
            else:
                self.media_player.play()
                self.btn_play_pause.setText("Pause")

    def set_volume(self, volume):
        self.media_player.audio_set_volume(volume)

    def set_position(self, value):
        # Value from QSlider is 0-1000
        self.media_player.set_position(value / 1000.0)

    def update_ui(self):
        # Update Time Slider and Play/Pause text
        if self.media_player.is_playing():
            self.btn_play_pause.setText("Pause")

            # Update slider position (0.0 to 1.0)
            pos = self.media_player.get_position()
            if pos >= 0:
                # Disconnect briefly to prevent sliderMoved from triggering set_position recursively
                self.time_slider.blockSignals(True)
                self.time_slider.setValue(int(pos * 1000))
                self.time_slider.blockSignals(False)
        else:
            # Ensure text says play if paused
            if self.media_player.get_state() in [vlc.State.Paused, vlc.State.Stopped]:
                self.btn_play_pause.setText("Play")

        # Check for continuous playback (video ended naturally)
        state = self.media_player.get_state()
        if state == vlc.State.Ended:
            self.play_next()

    def play_next(self):
        current_row = self.carousel.currentRow()
        if current_row < self.carousel.count() - 1:
            self.carousel.setCurrentRow(current_row + 1)
            self.play_selected_video(self.carousel.currentItem())
        else:
            self.media_player.stop()
            self.btn_play_pause.setText("Play")

    def keyPressEvent(self, event):
        # Toggle Fullscreen on 'F' or 'F11'
        if event.key() == Qt.Key.Key_F or event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.control_panel.setVisible(False)
            self.showFullScreen()
        else:
            self.control_panel.setVisible(True)
            self.showNormal()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    player = VidSimp()
    player.show()

    sys.exit(app.exec())
