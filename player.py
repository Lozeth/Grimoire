import vlc
import yt_dlp


class Player:
    def __init__(self):
        self.instance = vlc.Instance(
            "--no-video",
            "--quiet",
        )

        self.media_player = self.instance.media_player_new()

    def resolve_stream(self, youtube_url):
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "bestaudio/best",
            "socket_timeout": 15,
            "retries": 2,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                youtube_url,
                download=False,
            )

        if not info:
            raise RuntimeError("YouTube returned no media information.")

        stream_url = info.get("url")

        if not stream_url:
            raise RuntimeError("No playable stream URL was found.")

        headers = info.get("http_headers", {})

        return stream_url, headers

    def play_youtube(self, youtube_url):
        stream_url, headers = self.resolve_stream(youtube_url)

        media = self.instance.media_new(stream_url)

        user_agent = headers.get("User-Agent")
        referrer = headers.get("Referer")

        if user_agent:
            media.add_option(f":http-user-agent={user_agent}")

        if referrer:
            media.add_option(f":http-referrer={referrer}")

        self.media_player.set_media(media)
        self.media_player.play()

    def pause(self):
        self.media_player.pause()

    def stop(self):
        self.media_player.stop()

    def is_playing(self):
        return bool(self.media_player.is_playing())