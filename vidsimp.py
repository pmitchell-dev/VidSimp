import os
import subprocess
import sys
import tempfile
import base64

import vlc
from PyQt6.QtCore import QSettings, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
                             QListView, QListWidget, QListWidgetItem,
                             QMainWindow, QPushButton, QSlider, QVBoxLayout,
                             QWidget, QStyle)


class JumpSlider(QSlider):
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * ev.position().x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
            ev.accept()
        super().mousePressEvent(ev)


class CarouselWidget(QListWidget):
    def wheelEvent(self, event):
        if event.angleDelta().y() != 0:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - event.angleDelta().y()
            )
        else:
            super().wheelEvent(event)


class ThumbnailLoader(QThread):
    thumbnail_loaded = pyqtSignal(str, str)  # file_path, temp_image_path

    def __init__(self, directory, files, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.files = files

    def run(self):
        for f in self.files:
            if self.isInterruptionRequested():
                break
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
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
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
        self.setWindowIcon(QIcon("logo.png"))
        self.resize(1024, 768)

        # Settings for persistence
        self.settings = QSettings("VidSimp", "Player")

        # VLC Initialization
        # We include some common flags, like --no-xlib which is sometimes needed for multithreading
        # We disable d3d11 hardware decoding bugs by forcing direct3d9 vout which handles Qt embedding perfectly
        # We disable mouse events so VLC doesn't swallow double-clicks and try to handle fullscreen natively
        vlc_args = ["--no-xlib", "--no-mouse-events"]
        if sys.platform == "win32":
            vlc_args.append("--vout=direct3d9")

        self.vlc_instance = vlc.Instance(*vlc_args)
        self.media_player = self.vlc_instance.media_player_new()

        self.is_fullscreen = False
        self.pending_seek = -1.0
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
        self.video_frame.mouseDoubleClickEvent = lambda event: self.toggle_fullscreen()
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
        self.time_slider = JumpSlider(Qt.Orientation.Horizontal)
        self.time_slider.setMaximum(1000)
        self.time_slider.setToolTip("Seek")
        self.time_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.time_slider.sliderMoved.connect(self.set_position)
        self.control_layout.addWidget(self.time_slider)

        # 2. Carousel
        self.carousel = CarouselWidget()
        self.carousel.setViewMode(QListView.ViewMode.IconMode)
        self.carousel.setFlow(QListView.Flow.LeftToRight)
        self.carousel.setWrapping(False)
        self.carousel.setWordWrap(True)
        self.carousel.setIconSize(QSize(160, 90))
        self.carousel.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.carousel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.carousel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.carousel.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.carousel.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        from PyQt6.QtWidgets import QScroller
        QScroller.grabGesture(self.carousel.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        
        self.carousel.itemActivated.connect(
            self.play_selected_video
        )  # Handles double click or Enter/A
        self.control_layout.addWidget(self.carousel)

        # 3. Controller Row
        self.controller_row = QWidget()
        self.controller_row_layout = QHBoxLayout(self.controller_row)
        self.controller_row_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_open = QPushButton()
        self.btn_open.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.btn_open.setToolTip("Open Folder")
        self.btn_open.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_open.clicked.connect(self.open_folder)

        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play.setToolTip("Play")
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_play.clicked.connect(self.play_video)

        self.btn_pause = QPushButton()
        self.btn_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.btn_pause.setToolTip("Pause")
        self.btn_pause.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_pause.clicked.connect(self.pause_video)

        self.btn_stop = QPushButton()
        self.btn_stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.btn_stop.setToolTip("Stop")
        self.btn_stop.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_stop.clicked.connect(self.stop_video)

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setIcon(QIcon("fullscreen.svg"))
        self.btn_fullscreen.setToolTip("Fullscreen")
        self.btn_fullscreen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setToolTip("Volume")
        self.volume_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.volume_slider.setMaximumWidth(200)
        self.volume_slider.valueChanged.connect(self.set_volume)

        self.btn_quit = QPushButton()
        self.btn_quit.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton))
        self.btn_quit.setToolTip("Exit App")
        self.btn_quit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_quit.clicked.connect(self.close)

        self.controller_row_layout.addWidget(self.btn_open)
        self.controller_row_layout.addWidget(self.btn_play)
        self.controller_row_layout.addWidget(self.btn_pause)
        self.controller_row_layout.addWidget(self.btn_stop)
        self.controller_row_layout.addWidget(self.btn_fullscreen)
        self.controller_row_layout.addStretch()
        self.controller_row_layout.addWidget(self.volume_slider)
        self.controller_row_layout.addWidget(self.btn_quit)

        self.control_layout.addWidget(self.controller_row)
        self.main_layout.addWidget(self.control_panel)

    def setup_timers(self):
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(1000)
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start()

        # OSD Auto-Hide Timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3000)
        self.hide_timer.timeout.connect(self.hide_controls)

        # Cursor polling for OSD activation
        from PyQt6.QtGui import QCursor
        self.last_cursor_pos = QCursor.pos()
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(100)
        self.cursor_timer.timeout.connect(self.check_cursor_movement)

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
        if self.media_player.get_state() in [vlc.State.Playing, vlc.State.Paused]:
            self.save_current_position()

        if item is None:
            item = self.carousel.currentItem()
        if item is None:
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        
        # Explicitly release the old media object to prevent memory/VRAM leaks over long sessions
        old_media = self.media_player.get_media()
        
        media = self.vlc_instance.media_new(file_path)
        self.media_player.set_media(media)
        
        if old_media:
            old_media.release()

        if auto_play:
            self.media_player.play()
            self.set_volume(self.volume_slider.value())
            
            # Retrieve saved position
            key = "pos_" + base64.urlsafe_b64encode(file_path.encode('utf-8')).decode('utf-8').rstrip('=')
            saved_pos = self.settings.value(key, -1.0, type=float)
            if saved_pos > 0:
                self.pending_seek = saved_pos

    def play_video(self):
        if self.media_player.get_media() is None and self.carousel.currentItem():
            self.play_selected_video()
        else:
            self.media_player.play()
            self.set_volume(self.volume_slider.value())

    def pause_video(self):
        if self.media_player.is_playing():
            self.media_player.pause()

    def stop_video(self):
        self.media_player.stop()
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(0)
        self.time_slider.blockSignals(False)



    def set_volume(self, volume):
        self.media_player.audio_set_volume(volume)

    def set_position(self, value):
        # Value from QSlider is 0-1000
        self.media_player.set_position(value / 1000.0)

    def update_ui(self):
        # Update Time Slider
        if self.media_player.is_playing():
            current_volume = self.media_player.audio_get_volume()
            if current_volume != self.volume_slider.value():
                self.volume_slider.blockSignals(True)
                self.volume_slider.setValue(current_volume)
                self.volume_slider.blockSignals(False)

            # Handle pending seek
            if self.pending_seek >= 0:
                self.media_player.set_position(self.pending_seek)
                self.pending_seek = -1.0

            # Update slider position (0.0 to 1.0)
            pos = self.media_player.get_position()
            if pos >= 0:
                # Disconnect briefly to prevent sliderMoved from triggering set_position recursively
                self.time_slider.blockSignals(True)
                self.time_slider.setValue(int(pos * 1000))
                self.time_slider.blockSignals(False)

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
            self.cursor_timer.start()
        else:
            self.control_panel.setVisible(True)
            self.showNormal()
            self.cursor_timer.stop()
            self.hide_timer.stop()

    def check_cursor_movement(self):
        from PyQt6.QtGui import QCursor
        current_pos = QCursor.pos()
        if current_pos != self.last_cursor_pos:
            self.last_cursor_pos = current_pos
            if self.is_fullscreen:
                self.show_controls()

    def show_controls(self):
        if self.is_fullscreen:
            self.control_panel.setVisible(True)
            self.hide_timer.start()

    def hide_controls(self):
        if self.is_fullscreen:
            self.control_panel.setVisible(False)

    def save_current_position(self):
        if self.media_player.get_state() in [vlc.State.Playing, vlc.State.Paused]:
            item = self.carousel.currentItem()
            if item:
                file_path = item.data(Qt.ItemDataRole.UserRole)
                pos = self.media_player.get_position()
                key = "pos_" + base64.urlsafe_b64encode(file_path.encode('utf-8')).decode('utf-8').rstrip('=')
                if 0 < pos < 0.95:
                    self.settings.setValue(key, pos)
                else:
                    self.settings.remove(key)

    def closeEvent(self, event):
        self.save_current_position()
        if hasattr(self, "thumbnail_loader") and self.thumbnail_loader.isRunning():
            self.thumbnail_loader.requestInterruption()
            self.thumbnail_loader.wait()
        super().closeEvent(event)


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes
        myappid = 'pmitchell.vidsimp.player.1'
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    app = QApplication(sys.argv)

    player = VidSimp()
    player.show()

    sys.exit(app.exec())
