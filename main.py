import json
import random
import re
import sys
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import Qt, QTimer, QUrl, QUrlQuery
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
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


PLAYER_HOST = "127.0.0.1"
PLAYER_PORT = 8765
PLAYER_ORIGIN = f"http://{PLAYER_HOST}:{PLAYER_PORT}"

ENDED_PAGE_TITLE = "GRIMOIRE_ALBUM_ENDED"


def extract_youtube_video_id(url):
    """Return the 11-character ID from common YouTube video URLs."""
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


class PlayerPageHandler(BaseHTTPRequestHandler):
    """Serve Grimoire's local YouTube player page."""

    def do_GET(self):
        request = urlparse(self.path)

        if request.path == "/":
            self.send_html(self.empty_page())
            return

        if request.path == "/player":
            parameters = parse_qs(request.query)

            video_id = parameters.get("video", [""])[0]
            title = parameters.get("title", ["YouTube album"])[0]

            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                self.send_error(400, "Invalid YouTube video ID")
                return

            self.send_html(self.player_page(video_id, title))
            return

        self.send_error(404)

    def send_html(self, content):
        encoded = content.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        self.end_headers()

        self.wfile.write(encoded)

    @staticmethod
    def empty_page():
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">

            <style>
                html, body {
                    height: 100%;
                    margin: 0;
                    background: #111;
                    color: #ddd;
                    font-family: sans-serif;
                }

                body {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
            </style>
        </head>

        <body>
            Select an album and press Play.
        </body>
        </html>
        """

    @staticmethod
    def player_page(video_id, title):
        safe_title = escape(title)
        javascript_title = json.dumps(title)

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">

            <meta
                name="referrer"
                content="strict-origin-when-cross-origin"
            >

            <style>
                html, body {{
                    width: 100%;
                    height: 100%;
                    margin: 0;
                    overflow: hidden;
                    background: #000;
                }}

                #player {{
                    width: 100%;
                    height: 100%;
                }}
            </style>

            <title>{safe_title}</title>
        </head>

        <body>
            <div id="player"></div>

            <script src="https://www.youtube.com/iframe_api"></script>

            <script>
                let player;

                function onYouTubeIframeAPIReady() {{
                    player = new YT.Player("player", {{
                        width: "100%",
                        height: "100%",
                        videoId: "{video_id}",

                        playerVars: {{
                            autoplay: 1,
                            playsinline: 1,
                            origin: "{PLAYER_ORIGIN}"
                        }},

                        events: {{
                            onReady: onPlayerReady,
                            onStateChange: onPlayerStateChange
                        }}
                    }});
                }}

                function onPlayerReady(event) {{
                    document.title = {javascript_title};
                    event.target.playVideo();
                }}

                function onPlayerStateChange(event) {{
                    if (event.data === YT.PlayerState.ENDED) {{
                        document.title = "{ENDED_PAGE_TITLE}";
                    }}
                }}
            </script>
        </body>
        </html>
        """

    def log_message(self, format, *args):
        # Keep routine local-server requests out of the terminal.
        pass


def start_player_server():
    try:
        server = ThreadingHTTPServer(
            (PLAYER_HOST, PLAYER_PORT),
            PlayerPageHandler,
        )

    except OSError as error:
        raise RuntimeError(
            f"Grimoire could not start its local player at "
            f"{PLAYER_ORIGIN}.\n\n{error}"
        ) from error

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    return server


class Grimoire(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Grimoire")
        self.setMinimumSize(700, 720)

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

        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_album)

        shuffle_button = QPushButton("Shuffle Albums")
        shuffle_button.clicked.connect(self.shuffle_from_selected)

        playback_buttons.addWidget(play_button)
        playback_buttons.addWidget(next_button)
        playback_buttons.addWidget(shuffle_button)

        main_layout.addLayout(playback_buttons)

        self.now_playing = QLabel("Nothing playing")
        self.now_playing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.now_playing.setWordWrap(True)

        main_layout.addWidget(self.now_playing)

        self.load_albums()

    def load_albums(self):
        self.album_list.clear()

        for title, url in database.get_albums():
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, url)

            self.album_list.addItem(item)

    def get_all_albums(self):
        albums = []

        for row in range(self.album_list.count()):
            item = self.album_list.item(row)

            albums.append(
                {
                    "title": item.text(),
                    "url": item.data(Qt.ItemDataRole.UserRole),
                }
            )

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

        # Selected album first, then continue down the visible list,
        # wrapping back to the beginning.
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

        # Your chosen album always plays first.
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

    def handle_audio_finished(self):
        QTimer.singleShot(
            100,
            self.play_next_album,
        )

    def handle_audio_error(self, message):
        self.now_playing.setText(
            "Playback failed"
        )

        QMessageBox.warning(
            self,
            "Playback Error",
            message,
        )    
      
    def play_album(self, title, url):
        self.now_playing.setText(
            f"Loading: {title}"
        )

        self.audio_player.play_youtube(url)

    def handle_player_title_change(self, page_title):
        if page_title != ENDED_PAGE_TITLE:
            return

        if self.advancing_album:
            return

        self.advancing_album = True

        # Let the current browser event finish before loading the next page.
        QTimer.singleShot(
            100,
            self.play_next_album,
        )

    def next_album(self):
        if not self.play_queue:
            QMessageBox.information(
                self,
                "Nothing Playing",
                "Start an album or shuffle first.",
            )
            return

        self.audio_player.stop()
        self.play_next_album()    
    
    
    def play_next_album(self):
        self.queue_position += 1
        self.advancing_album = False

        if self.queue_position >= len(self.play_queue):
            self.now_playing.setText("Queue finished")
            return

        self.play_current_queue_album()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    try:
        player_server = start_player_server()

    except RuntimeError as error:
        QMessageBox.critical(
            None,
            "Grimoire Could Not Start",
            str(error),
        )

        sys.exit(1)

    window = Grimoire()
    window.show()

    exit_code = app.exec()

    player_server.shutdown()
    player_server.server_close()

    sys.exit(exit_code)