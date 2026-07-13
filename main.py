import re
import sys
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtCore import Qt, QUrl
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
from PySide6.QtWebEngineWidgets import QWebEngineView

import database
import youtube


PLAYER_HOST = "127.0.0.1"
PLAYER_PORT = 8765
PLAYER_ORIGIN = f"http://{PLAYER_HOST}:{PLAYER_PORT}"


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
    """Serve Grimoire's small local YouTube player page."""

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
            "strict-origin-when-cross-origin"
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

                iframe {{
                    width: 100%;
                    height: 100%;
                    border: 0;
                }}
            </style>

            <title>{safe_title}</title>
        </head>

        <body>
            <iframe
                src="https://www.youtube.com/embed/{video_id}?autoplay=1&playsinline=1&origin={PLAYER_ORIGIN}"
                title="{safe_title}"
                referrerpolicy="strict-origin-when-cross-origin"
                allow="autoplay; encrypted-media; picture-in-picture"
                allowfullscreen>
            </iframe>
        </body>
        </html>
        """

    def log_message(self, format, *args):
        # Prevent the local server from filling the terminal with requests.
        pass


def start_player_server():
    try:
        server = ThreadingHTTPServer(
            (PLAYER_HOST, PLAYER_PORT),
            PlayerPageHandler
        )
    except OSError as error:
        raise RuntimeError(
            f"Grimoire could not start its local player on "
            f"{PLAYER_ORIGIN}.\n\n{error}"
        ) from error

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True
    )
    thread.start()

    return server


class Grimoire(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Grimoire")
        self.setMinimumSize(700, 720)

        database.create_database()

        main_layout = QVBoxLayout(self)

        title = QLabel("Grimoire")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

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

        shuffle_button = QPushButton("Shuffle Albums")

        playback_buttons.addWidget(play_button)
        playback_buttons.addWidget(shuffle_button)
        main_layout.addLayout(playback_buttons)

        self.now_playing = QLabel("Nothing playing")
        self.now_playing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.now_playing.setWordWrap(True)
        main_layout.addWidget(self.now_playing)

        self.web_player = QWebEngineView()

        self.web_player.settings().setAttribute(
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,
            False
        )

        self.web_player.setMinimumSize(480, 270)
        main_layout.addWidget(self.web_player)

        self.web_player.load(
            QUrl(f"{PLAYER_ORIGIN}/")
        )

        self.load_albums()

    def load_albums(self):
        self.album_list.clear()

        for title, url in database.get_albums():
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, url)
            self.album_list.addItem(item)

    def add_album(self):
        url, ok = QInputDialog.getText(
            self,
            "Add Album",
            "YouTube URL:"
        )

        url = url.strip()

        if not ok or not url:
            return

        video_id = extract_youtube_video_id(url)

        if not video_id:
            QMessageBox.warning(
                self,
                "Invalid URL",
                "Grimoire could not recognise that YouTube video URL."
            )
            return

        title = youtube.get_video_title(url)

        if not title:
            QMessageBox.warning(
                self,
                "Lookup Failed",
                "Grimoire could not retrieve the video's name."
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Add Album",
            f"Found:\n\n{title}\n\nAdd this album to Grimoire?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
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
                "Please select an album first."
            )
            return

        title = selected.text()

        confirmation = QMessageBox.question(
            self,
            "Delete Album",
            f"Remove '{title}' from Grimoire?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )

        if confirmation == QMessageBox.StandardButton.Yes:
            database.delete_album(title)
            self.load_albums()

    def play_selected_album(self, _item=None):
        selected = self.album_list.currentItem()

        if not selected:
            QMessageBox.information(
                self,
                "No Album Selected",
                "Please select an album first."
            )
            return

        title = selected.text()
        url = selected.data(Qt.ItemDataRole.UserRole)
        video_id = extract_youtube_video_id(url)

        if not video_id:
            QMessageBox.warning(
                self,
                "Invalid URL",
                "The saved URL is not a recognised YouTube video URL."
            )
            return

        self.now_playing.setText(f"Now playing: {title}")

        player_url = QUrl(f"{PLAYER_ORIGIN}/player")
        query = player_url.query()

        from PySide6.QtCore import QUrlQuery

        parameters = QUrlQuery()
        parameters.addQueryItem("video", video_id)
        parameters.addQueryItem("title", title)
        player_url.setQuery(parameters)

        self.web_player.load(player_url)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    try:
        player_server = start_player_server()
    except RuntimeError as error:
        QMessageBox.critical(
            None,
            "Grimoire Could Not Start",
            str(error)
        )
        sys.exit(1)

    window = Grimoire()
    window.show()

    exit_code = app.exec()

    player_server.shutdown()
    player_server.server_close()

    sys.exit(exit_code)