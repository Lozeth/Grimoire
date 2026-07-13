# Hi

import random
import re
import sys
import ctypes

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QInputDialog,
    QMessageBox,
)

import database
import youtube
from player import Player


def extract_youtube_video_id(url):
    """Return the video ID from a recognised YouTube URL."""
    patterns = (
        r"(?:youtube\.com/watch\?.*v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    )

    for pattern in patterns:
        match = re.search(pattern, url)

        if match:
            return match.group(1)

    return None

def resource_path(filename):
    """Find bundled resources both in development and in the packaged EXE."""
    base_path = Path(
        getattr(
            sys,
            "_MEIPASS",
            Path(__file__).resolve().parent,
        )
    )

    return base_path / filename

ICON_PATH = Path(__file__).resolve().parent / "Grimoire.ico"

class Grimoire(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Grimoire")
        self.setWindowIcon(
            QIcon(str(resource_path("Grimoire.ico")))
        )
        self.setWindowIcon(QIcon("Grimoire.ico"))
        self.setMinimumSize(700, 450)

        self.play_queue = []
        self.queue_position = -1
        self.advancing_album = False

        self.audio_player = Player()

        self.audio_player.playback_ended.connect(
            self.handle_audio_finished
        )

        self.audio_player.playback_error.connect(
            self.handle_audio_error
        )

        database.create_database()

        main_layout = QVBoxLayout(self)

        self.album_list = QListWidget()
        self.album_list.itemDoubleClicked.connect(
            self.play_selected_album
        )
        main_layout.addWidget(self.album_list)

        library_buttons = QHBoxLayout()

        add_button = QPushButton("Add Album")
        add_button.clicked.connect(self.add_album)

        delete_button = QPushButton("Delete Album")
        delete_button.clicked.connect(self.delete_album)

        library_buttons.addWidget(add_button)
        library_buttons.addWidget(delete_button)

        main_layout.addLayout(library_buttons)

        playback_buttons = QHBoxLayout()

        play_button = QPushButton("Play")
        play_button.clicked.connect(self.play_selected_album)

        pause_button = QPushButton("Pause/Resume")
        pause_button.clicked.connect(self.pause_playback)

        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_album)

        shuffle_button = QPushButton("Shuffle")
        shuffle_button.clicked.connect(self.shuffle_from_selected)

        playback_buttons.addWidget(play_button)
        playback_buttons.addWidget(pause_button)
        playback_buttons.addWidget(next_button)
        playback_buttons.addWidget(shuffle_button)

        main_layout.addLayout(playback_buttons)

        self.now_playing = QLabel("Nothing Playing")
        self.now_playing.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.now_playing.setWordWrap(True)

        main_layout.addWidget(self.now_playing)

        self.load_albums()

    def load_albums(self):
        self.album_list.clear()

        for title, url in database.get_albums():
            item = QListWidgetItem(title)
            item.setData(
                Qt.ItemDataRole.UserRole,
                url,
            )

            self.album_list.addItem(item)

    def get_all_albums(self):
        albums = []

        for row in range(self.album_list.count()):
            item = self.album_list.item(row)

            albums.append({
                "title": item.text(),
                "url": item.data(
                    Qt.ItemDataRole.UserRole
                ),
            })

        return albums

    def add_album(self):
        url, ok = QInputDialog.getText(
            self,
            "Add Album",
            "YouTube URL:",
        )

        url = url.strip()

        if not ok or not url:
            return

        video_id = extract_youtube_video_id(url)

        if not video_id:
            QMessageBox.warning(
                self,
                "Invalid URL",
                "Grimoire could not recognise that YouTube video URL.",
            )
            return

        title = youtube.get_video_title(url)

        if not title:
            QMessageBox.warning(
                self,
                "Lookup Failed",
                "Grimoire could not retrieve the video's name.",
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Add Album",
            f"Found:\n\n{title}\n\nAdd this album to Grimoire?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
        )

        if confirmation == QMessageBox.StandardButton.Yes:
            database.add_album(title, url)
            self.load_albums()

    def delete_album(self):
        selected = self.album_list.currentItem()

        if not selected:
            QMessageBox.information(
                self,
                "No Album Selected",
                "Please select an album first.",
            )
            return

        title = selected.text()

        confirmation = QMessageBox.question(
            self,
            "Delete Album",
            f"Remove '{title}' from Grimoire?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
        )

        if confirmation == QMessageBox.StandardButton.Yes:
            database.delete_album(title)
            self.load_albums()

    def play_selected_album(self, _item=None):
        selected_row = self.album_list.currentRow()

        if selected_row < 0:
            QMessageBox.information(
                self,
                "No Album Selected",
                "Please select an album first.",
            )
            return

        albums = self.get_all_albums()

        # Play the selected album first, then continue down the
        # visible list and wrap back to the beginning.
        self.play_queue = (
            albums[selected_row:]
            + albums[:selected_row]
        )

        self.queue_position = 0
        self.play_current_queue_album()

    def shuffle_from_selected(self):
        selected_row = self.album_list.currentRow()

        if selected_row < 0:
            QMessageBox.information(
                self,
                "No Album Selected",
                "Please select an album first.",
            )
            return

        albums = self.get_all_albums()
        selected_album = albums[selected_row]

        remaining_albums = (
            albums[:selected_row]
            + albums[selected_row + 1:]
        )

        random.shuffle(remaining_albums)

        # The selected album always plays first.
        self.play_queue = [
            selected_album,
            *remaining_albums,
        ]

        self.queue_position = 0
        self.play_current_queue_album()

    def play_current_queue_album(self):
        if not self.play_queue:
            return

        if not 0 <= self.queue_position < len(self.play_queue):
            self.now_playing.setText("Queue finished")
            return

        album = self.play_queue[self.queue_position]

        self.play_album(
            album["title"],
            album["url"],
        )

    def play_album(self, title, url):
        self.now_playing.setText(
            f"Playing: {title}"
        )

        self.audio_player.play_youtube(url)

    def pause_playback(self):
        self.audio_player.pause()

    def next_album(self):
        if not self.play_queue:
            QMessageBox.information(
                self,
                "Nothing Playing",
                "Start an album or shuffle first.",
            )
            return

        self.audio_player.stop()

        # Give VLC a moment to release the current stream before
        # resolving and starting the next album.
        QTimer.singleShot(
            300,
            self.play_next_album,
        )

    def play_next_album(self):
        self.queue_position += 1
        self.advancing_album = False

        if self.queue_position >= len(self.play_queue):
            self.now_playing.setText("Queue finished")
            return

        self.play_current_queue_album()

    def handle_audio_finished(self):
        if self.advancing_album:
            return

        self.advancing_album = True

        QTimer.singleShot(
            100,
            self.play_next_album,
        )

    def handle_audio_error(self, message):
        self.now_playing.setText("Playback failed")

        QMessageBox.warning(
            self,
            "Playback Error",
            message,
        )


if __name__ == "__main__":
    # Give Windows a unique identity for the taskbar icon.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "Grimoire.AlbumPlayer"
    )

    app = QApplication(sys.argv)

    app_icon = QIcon(str(ICON_PATH))

    print("Icon path:", ICON_PATH)
    print("Icon exists:", ICON_PATH.exists())
    print("Icon loaded:", not app_icon.isNull())

    app.setWindowIcon(app_icon)

    window = Grimoire()
    window.setWindowIcon(app_icon)
    window.show()

    sys.exit(app.exec())