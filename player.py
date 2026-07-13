import os

from PySide6.QtCore import QObject, QThread, Signal, Slot

VLC_DIRECTORY = r"C:\Program Files\VideoLAN\VLC"

os.add_dll_directory(VLC_DIRECTORY)
os.environ["VLC_PLUGIN_PATH"] = os.path.join(
    VLC_DIRECTORY,
    "plugins",
)

import vlc
import yt_dlp


class StreamResolver(QObject):
    resolved = Signal(str, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, youtube_url):
        super().__init__()
        self.youtube_url = youtube_url

    @Slot()
    def run(self):
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "bestaudio/best",
            "socket_timeout": 15,
            "retries": 2,
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    self.youtube_url,
                    download=False,
                )

            if not info:
                raise RuntimeError(
                    "YouTube returned no media information."
                )

            stream_url = info.get("url")

            if not stream_url:
                raise RuntimeError(
                    "No playable audio stream was found."
                )

            headers = info.get("http_headers", {})

            self.resolved.emit(stream_url, headers)

        except Exception as error:
            self.failed.emit(str(error))

        finally:
            self.finished.emit()


class Player(QObject):
    playback_started = Signal()
    playback_ended = Signal()
    playback_error = Signal(str)
    resolving = Signal()

    def __init__(self):
        super().__init__()

        self.instance = vlc.Instance(
            "--no-video",
            "--quiet",
        )

        self.media_player = self.instance.media_player_new()

        event_manager = self.media_player.event_manager()

        event_manager.event_attach(
            vlc.EventType.MediaPlayerPlaying,
            self._on_playing,
        )

        event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self._on_end_reached,
        )

        event_manager.event_attach(
            vlc.EventType.MediaPlayerEncounteredError,
            self._on_error,
        )

        self.resolver_thread = None
        self.resolver_worker = None

    def play_youtube(self, youtube_url):
        if (
            self.resolver_thread is not None
            and self.resolver_thread.isRunning()
        ):
            return

        self.stop()
        self.resolving.emit()

        self.resolver_thread = QThread()
        self.resolver_worker = StreamResolver(youtube_url)

        self.resolver_worker.moveToThread(
            self.resolver_thread
        )

        self.resolver_thread.started.connect(
            self.resolver_worker.run
        )

        self.resolver_worker.resolved.connect(
            self._play_resolved_stream
        )

        self.resolver_worker.failed.connect(
            self.playback_error.emit
        )

        self.resolver_worker.finished.connect(
            self.resolver_thread.quit
        )

        self.resolver_worker.finished.connect(
            self.resolver_worker.deleteLater
        )

        self.resolver_thread.finished.connect(
            self._resolver_finished
        )

        self.resolver_thread.finished.connect(
            self.resolver_thread.deleteLater
        )

        self.resolver_thread.start()

    @Slot(str, object)
    def _play_resolved_stream(self, stream_url, headers):
        media = self.instance.media_new(stream_url)

        user_agent = headers.get("User-Agent")
        referrer = headers.get("Referer")

        if user_agent:
            media.add_option(
                f":http-user-agent={user_agent}"
            )

        if referrer:
            media.add_option(
                f":http-referrer={referrer}"
            )

        self.media_player.set_media(media)

        result = self.media_player.play()

        if result == -1:
            self.playback_error.emit(
                "VLC could not begin playback."
            )

    @Slot()
    def _resolver_finished(self):
        self.resolver_worker = None
        self.resolver_thread = None

    def pause(self):
        self.media_player.pause()

    def stop(self):
        self.media_player.stop()

    def _on_playing(self, _event):
        self.playback_started.emit()

    def _on_end_reached(self, _event):
        self.playback_ended.emit()

    def _on_error(self, _event):
        self.playback_error.emit(
            "VLC encountered a playback error."
        )